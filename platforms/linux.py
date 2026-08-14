#!/usr/bin/env python3
"""Implementação Linux/X11 do mr-whisper (o caminho original, testado).

- Áudio  → arecord (ALSA)
- Teclado → evdev (/dev/input, precisa do grupo 'input')
- Paste  → xclip (clipboard) + xdotool (paste sintético), com detecção de
           terminal via xprop pra decidir o atalho.

É a plataforma de referência; a lógica aqui é a que rodava no daemon monolítico.
"""
from __future__ import annotations

import audioop
import os
import selectors
import signal
import subprocess
import tempfile
import threading
import time
from typing import Callable

import evdev
from evdev import ecodes

ARECORD_DEVICE = os.environ.get("VOICEFLOW_MIC", "default")
CTRL_KEYS = {ecodes.KEY_LEFTCTRL, ecodes.KEY_RIGHTCTRL}
ALT_KEYS = {ecodes.KEY_LEFTALT, ecodes.KEY_RIGHTALT}
TRIGGER_KEY = ecodes.KEY_SPACE
CANCEL_KEY = ecodes.KEY_ESC


def _log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


# ── áudio (arecord) ───────────────────────────────────────────────────────────
class ArecordRecorder:
    def __init__(self, on_level: Callable[[float], None]) -> None:
        self.on_level = on_level
        self.proc: subprocess.Popen | None = None
        self.wav_path: str | None = None
        self.started_at = 0.0
        self._stop_meter = threading.Event()

    def start(self) -> None:
        fd, path = tempfile.mkstemp(prefix="mr-whisper-", suffix=".wav")
        os.close(fd)
        self.wav_path = path
        self.started_at = time.time()
        self.proc = subprocess.Popen(
            ["arecord", "-D", ARECORD_DEVICE, "-f", "S16_LE", "-r", "16000",
             "-c", "1", "-t", "wav", path],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        self._stop_meter.clear()
        threading.Thread(target=self._meter, args=(path,), daemon=True).start()
        _log(f"gravando → {path}")

    def _meter(self, path: str) -> None:
        last = 0
        time.sleep(0.12)
        while not self._stop_meter.is_set():
            try:
                with open(path, "rb") as f:
                    f.seek(last)
                    chunk = f.read()
                    last += len(chunk)
                if len(chunk) >= 2:
                    rms = audioop.rms(chunk[: len(chunk) - (len(chunk) % 2)], 2)
                    self.on_level(min(1.0, rms / 8000.0))
            except OSError:
                pass
            time.sleep(0.05)

    def stop(self) -> str | None:
        self._stop_meter.set()
        if not self.proc:
            return None
        self.proc.send_signal(signal.SIGINT)
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        path = self.wav_path
        self.proc = None
        self.wav_path = None
        return path


# ── teclado (evdev) ───────────────────────────────────────────────────────────
def _find_keyboards() -> list[evdev.InputDevice]:
    kbs = []
    for path in evdev.list_devices():
        try:
            d = evdev.InputDevice(path)
            keys = d.capabilities().get(ecodes.EV_KEY, [])
            if ecodes.KEY_SPACE in keys and ecodes.KEY_A in keys:
                kbs.append(d)
        except Exception:
            pass
    return kbs


class EvdevHotkey:
    def __init__(self, on_press, on_release, on_cancel) -> None:
        self.on_press = on_press
        self.on_release = on_release
        self.on_cancel = on_cancel

    def run(self) -> None:
        keyboards = _find_keyboards()
        if not keyboards:
            _log("ERRO: nenhum teclado evdev acessível (grupo 'input'? relogar?).")
        else:
            _log(f"escutando {len(keyboards)} teclado(s): {[k.name for k in keyboards]}")

        held = {"ctrl": False, "alt": False, "space": False}
        active = False

        def update():
            nonlocal active
            combo = held["ctrl"] and held["alt"] and held["space"]
            if combo and not active:
                active = True
                self.on_press()
            elif not combo and active:
                active = False
                self.on_release()

        sel = selectors.DefaultSelector()
        for kb in keyboards:
            sel.register(kb, selectors.EVENT_READ)

        while True:
            for key, _ in sel.select(timeout=1):
                try:
                    for event in key.fileobj.read():
                        if event.type != ecodes.EV_KEY:
                            continue
                        pressed = event.value in (1, 2)
                        code = event.code
                        if code in CTRL_KEYS:
                            held["ctrl"] = pressed
                        elif code in ALT_KEYS:
                            held["alt"] = pressed
                        elif code == TRIGGER_KEY:
                            held["space"] = pressed
                        elif code == CANCEL_KEY and event.value == 1:
                            self.on_cancel()
                            continue
                        else:
                            continue
                        update()
                except OSError:
                    pass


# ── paste (xclip + xdotool) ───────────────────────────────────────────────────
TERMINAL_CLASSES = (
    "terminal", "gnome-terminal", "konsole", "xterm", "rxvt", "urxvt",
    "alacritty", "kitty", "wezterm", "st-256color", "tilix", "terminator",
    "foot", "xfce4-terminal", "guake", "yakuake", "ptyxis",
)


def _window_is_terminal(wid: str) -> bool:
    if not wid:
        return False
    try:
        out = subprocess.run(
            ["xprop", "-id", wid, "WM_CLASS"], capture_output=True, text=True, timeout=1
        ).stdout.lower()
    except (subprocess.SubprocessError, OSError):
        return False
    cls = out.split("=", 1)[1] if "=" in out else ""
    return any(t in cls for t in TERMINAL_CLASSES)


class X11Delivery:
    def deliver(self, text: str) -> None:
        # janela alvo (só pra decidir o atalho; não reativa a janela).
        try:
            wid = subprocess.run(
                ["xdotool", "getactivewindow"], capture_output=True, text=True, timeout=1
            ).stdout.strip()
        except (subprocess.SubprocessError, OSError):
            wid = ""
        _ = _window_is_terminal(wid)  # (mantido: Ctrl+Shift+V já é universal)

        self._set_clipboard(text)
        time.sleep(0.18)  # deixa a extensão de clipboard selecionar nosso texto

        # solta modificadores presos (Ctrl+Alt+Espaço dessincroniza o X)
        subprocess.run(["xdotool", "keyup", "ctrl", "alt", "shift", "super"], check=False)
        time.sleep(0.05)
        combo = os.environ.get("VOICEFLOW_PASTE", "ctrl+shift+v")
        subprocess.run(["xdotool", "key", "--clearmodifiers", combo], check=False)

    @staticmethod
    def _set_clipboard(text: str) -> None:
        subprocess.run(
            ["xclip", "-selection", "clipboard"],
            input=text.encode("utf-8"), check=False,
        )


# ── fábrica ───────────────────────────────────────────────────────────────────
class LinuxPlatform:
    name = "linux"

    def make_recorder(self, on_level):
        return ArecordRecorder(on_level)

    def make_hotkey(self, on_press, on_release, on_cancel):
        return EvdevHotkey(on_press, on_release, on_cancel)

    def make_delivery(self):
        return X11Delivery()
