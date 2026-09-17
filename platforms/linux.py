#!/usr/bin/env python3
"""Implementação Linux/X11 do mr-whisper (o caminho original, testado).

- Áudio  → arecord (ALSA)
- Teclado → evdev (/dev/input, precisa do grupo 'input')
- Paste  → xclip (clipboard) + xdotool (paste sintético), com detecção de
           terminal via xprop pra decidir o atalho.

É a plataforma de referência; a lógica aqui é a que rodava no daemon monolítico.
"""
from __future__ import annotations

import os
import selectors
import shutil
import signal
import subprocess
import tempfile
import threading
import time
from typing import Callable

from .base import level_from_rms, rms16

import evdev
from evdev import ecodes

ARECORD_DEVICE = os.environ.get("VOICEFLOW_MIC", "default")
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
                    self.on_level(level_from_rms(rms16(chunk)))
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
            # ignora o teclado virtual do ydotool: se escutássemos ele, o Ctrl+V
            # que NÓS injetamos pra colar voltaria como evento e podia disparar
            # gravação (loop).
            if "ydotool" in (d.name or "").lower():
                continue
            keys = d.capabilities().get(ecodes.EV_KEY, [])
            if ecodes.KEY_SPACE in keys and ecodes.KEY_A in keys:
                kbs.append(d)
        except Exception:
            pass
    return kbs


# nome de modificador → conjunto de keycodes evdev (esq/dir)
_MOD_CODES = {
    "ctrl": {ecodes.KEY_LEFTCTRL, ecodes.KEY_RIGHTCTRL},
    "alt": {ecodes.KEY_LEFTALT, ecodes.KEY_RIGHTALT},
    "shift": {ecodes.KEY_LEFTSHIFT, ecodes.KEY_RIGHTSHIFT},
    "super": {ecodes.KEY_LEFTMETA, ecodes.KEY_RIGHTMETA},
    "cmd": {ecodes.KEY_LEFTMETA, ecodes.KEY_RIGHTMETA},
}
# tecla-gatilho: tudo que o Settings oferece nas pills (letras, números, F1-F12,
# símbolos). evdev lê a tecla FÍSICA, então não depende de layout nem de Shift.
_KEY_CODES = {
    "space": ecodes.KEY_SPACE, "enter": ecodes.KEY_ENTER, "tab": ecodes.KEY_TAB,
    "backspace": ecodes.KEY_BACKSPACE,
    ",": ecodes.KEY_COMMA, ".": ecodes.KEY_DOT, "/": ecodes.KEY_SLASH,
    ";": ecodes.KEY_SEMICOLON, "'": ecodes.KEY_APOSTROPHE,
    "[": ecodes.KEY_LEFTBRACE, "]": ecodes.KEY_RIGHTBRACE,
    "\\": ecodes.KEY_BACKSLASH, "-": ecodes.KEY_MINUS, "=": ecodes.KEY_EQUAL,
    "`": ecodes.KEY_GRAVE,
}
_KEY_CODES.update({c: getattr(ecodes, f"KEY_{c.upper()}")
                   for c in "abcdefghijklmnopqrstuvwxyz"})
_KEY_CODES.update({d: getattr(ecodes, f"KEY_{d}") for d in "0123456789"})
_KEY_CODES.update({f"f{i}": getattr(ecodes, f"KEY_F{i}") for i in range(1, 13)})


class EvdevHotkey:
    def __init__(self, on_press, on_release, on_cancel) -> None:
        self.on_press = on_press
        self.on_release = on_release
        self.on_cancel = on_cancel
        from core import config
        mods, key = config.hotkey_combo()  # ex: ({"ctrl","alt"}, "space")
        # keycodes de cada modificador e da tecla-gatilho
        self._mod_codes = {m: _MOD_CODES.get(m, set()) for m in mods}
        self._trigger = _KEY_CODES.get(key, ecodes.KEY_SPACE)
        self._label = "+".join(sorted(mods)) + "+" + key

    def run(self) -> None:
        keyboards = _find_keyboards()
        if not keyboards:
            _log("ERRO: nenhum teclado evdev acessível (grupo 'input'? relogar?).")
        else:
            _log(f"escutando {len(keyboards)} teclado(s) [{self._label}]: "
                 f"{[k.name for k in keyboards]}")

        held = {m: False for m in self._mod_codes}
        held["_key"] = False
        active = False

        def update():
            nonlocal active
            combo = held["_key"] and all(held[m] for m in self._mod_codes)
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
                        matched = False
                        for m, codes in self._mod_codes.items():
                            if code in codes:
                                held[m] = pressed
                                matched = True
                                break
                        if not matched:
                            if code == self._trigger:
                                held["_key"] = pressed
                            elif code == CANCEL_KEY and event.value == 1:
                                self.on_cancel()
                                continue
                            else:
                                continue
                        update()
                except OSError:
                    pass


# ── paste, detecta Wayland vs X11 e usa as ferramentas certas ────────────────
def _is_wayland() -> bool:
    return bool(os.environ.get("WAYLAND_DISPLAY")) or \
        os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland"


def _have(cmd: str) -> bool:
    return shutil.which(cmd) is not None


class LinuxDelivery:
    """Entrega o texto respeitando o servidor gráfico.

    - Clipboard: wl-copy (Wayland) ou xclip (X11).
    - Paste sintético: ydotool/wtype (Wayland) ou xdotool (X11). No GNOME
      Wayland a injeção de teclas costuma ser bloqueada; se nenhuma ferramenta
      de paste funciona, o texto fica no clipboard e retornamos False de
      `deliver` pra o app avisar "copiado, cole com Ctrl+V".
    """

    def __init__(self) -> None:
        self.wayland = _is_wayland()

    def deliver(self, text: str, paste: bool = True, shortcut: str = "ctrl+v") -> bool:
        """Retorna True se colou de fato; False se só copiou (o app notifica)."""
        self._set_clipboard(text)
        if not paste:
            return False
        time.sleep(0.15)
        if self.wayland:
            return self._paste_wayland(shortcut)
        return self._paste_x11(shortcut)

    # ── clipboard ─────────────────────────────────────────────────────────────
    def _set_clipboard(self, text: str) -> None:
        if self.wayland and _have("wl-copy"):
            subprocess.run(["wl-copy"], input=text.encode("utf-8"), check=False)
        else:
            subprocess.run(["xclip", "-selection", "clipboard"],
                           input=text.encode("utf-8"), check=False)

    # ── paste X11 ─────────────────────────────────────────────────────────────
    def _paste_x11(self, shortcut: str) -> bool:
        if not _have("xdotool"):
            return False
        subprocess.run(["xdotool", "keyup", "ctrl", "alt", "shift", "super"], check=False)
        time.sleep(0.05)
        r = subprocess.run(["xdotool", "key", "--clearmodifiers", shortcut], check=False)
        return r.returncode == 0

    # ── paste Wayland ─────────────────────────────────────────────────────────
    def _paste_wayland(self, shortcut: str) -> bool:
        keys = shortcut.split("+")  # ex: ["ctrl","v"] ou ["ctrl","shift","v"]
        # ydotool: injeta via uinput. Precisa de acesso ao /dev/uinput (grupo
        # input + udev rule), ver run/setup-linux-wayland.sh.
        if _have("ydotool"):
            code = {"ctrl": 29, "shift": 42, "v": 47}
            press = [f"{code[k]}:1" for k in keys if k in code]
            release = [f"{code[k]}:0" for k in reversed(keys) if k in code]
            # aponta pro socket do ydotoold (serviço --user), se existir, sem o
            # daemon o ydotool é errático. --key-delay dá tempo do compositor
            # registrar o Ctrl+V.
            env = dict(os.environ)
            sock = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/run/user/%d" % os.getuid()),
                                ".ydotool_socket")
            if os.path.exists(sock):
                env["YDOTOOL_SOCKET"] = sock
            r = subprocess.run(["ydotool", "key", "--key-delay", "25",
                                *press, *release],
                               check=False, capture_output=True, env=env)
            if r.returncode == 0:
                return True
        # wtype: precisa do protocolo virtual-keyboard (não no GNOME).
        if _have("wtype"):
            mods = [f"-M{k}" for k in keys[:-1]]
            unmods = [f"-m{k}" for k in keys[:-1]]
            r = subprocess.run(["wtype", *mods, "-k", keys[-1], *unmods],
                               check=False, capture_output=True)
            if r.returncode == 0:
                return True
        return False  # sem forma de colar → clipboard-only


# ── fábrica ───────────────────────────────────────────────────────────────────
class LinuxPlatform:
    name = "linux"

    def make_recorder(self, on_level):
        return ArecordRecorder(on_level)

    def make_hotkey(self, on_press, on_release, on_cancel):
        return EvdevHotkey(on_press, on_release, on_cancel)

    def make_delivery(self):
        return LinuxDelivery()
