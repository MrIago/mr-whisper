#!/usr/bin/env python3
"""Peças cross-platform (macOS + Windows) do mr-whisper.

Áudio e teclado são idênticos nos dois via libs portáveis; só o PASTE difere
(Cmd+V no Mac, Ctrl+V no Windows), então cada plataforma define só a delivery.

Dependências (instaladas pelo setup): sounddevice, pynput, pyperclip.
"""
from __future__ import annotations

import tempfile
import threading
import time
import wave
from typing import Callable

from .base import rms16

SAMPLE_RATE = 16000
CHANNELS = 1


def _log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


# ── áudio (sounddevice → buffer → wav) ────────────────────────────────────────
class SounddeviceRecorder:
    """Grava do mic em memória via sounddevice (PortAudio) e escreve o wav no
    stop(). O nível (RMS) sai direto de cada bloco, sem ler arquivo parcial."""

    def __init__(self, on_level: Callable[[float], None]) -> None:
        self.on_level = on_level
        self.started_at = 0.0
        self._stream = None
        self._frames: list[bytes] = []
        self._lock = threading.Lock()

    def _callback(self, indata, frames, time_info, status):  # sounddevice thread
        buf = bytes(indata)
        with self._lock:
            self._frames.append(buf)
        if len(buf) >= 2:
            rms = rms16(buf)
            self.on_level(min(1.0, rms / 8000.0))

    def start(self) -> None:
        import sounddevice as sd
        with self._lock:
            self._frames = []
        self.started_at = time.time()
        self._stream = sd.RawInputStream(
            samplerate=SAMPLE_RATE, channels=CHANNELS, dtype="int16",
            blocksize=int(SAMPLE_RATE * 0.05), callback=self._callback,
        )
        self._stream.start()
        _log("gravando (sounddevice)")

    def stop(self) -> str | None:
        if not self._stream:
            return None
        self._stream.stop()
        self._stream.close()
        self._stream = None
        with self._lock:
            data = b"".join(self._frames)
            self._frames = []
        if len(data) < 2:
            return None
        fd, path = tempfile.mkstemp(prefix="mr-whisper-", suffix=".wav")
        import os
        os.close(fd)
        with wave.open(path, "wb") as w:
            w.setnchannels(CHANNELS)
            w.setsampwidth(2)  # int16
            w.setframerate(SAMPLE_RATE)
            w.writeframes(data)
        return path


# ── teclado (pynput) ──────────────────────────────────────────────────────────
class PynputHotkey:
    """Hold-to-talk via pynput com atalho CONFIGURÁVEL (core.config.hotkey_combo).
    Segura os modificadores + tecla → press; solta → release; Esc cancela."""

    def __init__(self, on_press, on_release, on_cancel) -> None:
        self.on_press = on_press
        self.on_release = on_release
        self.on_cancel = on_cancel
        from core import config
        self.mods, self.key = config.hotkey_combo()  # ex: ({"alt"}, "space")
        self.held = {m: False for m in self.mods}
        self.held["_key"] = False
        self.active = False

    def _update(self):
        combo = self.held["_key"] and all(self.held[m] for m in self.mods)
        if combo and not self.active:
            self.active = True
            self.on_press()
        elif not combo and self.active:
            self.active = False
            self.on_release()

    def run(self) -> None:
        from pynput import keyboard as kb

        # mapeia nome do modificador → conjunto de Keys do pynput (esq/dir)
        mod_keys = {
            "ctrl": {kb.Key.ctrl, kb.Key.ctrl_l, kb.Key.ctrl_r},
            "alt": {kb.Key.alt, kb.Key.alt_l, kb.Key.alt_r, kb.Key.alt_gr},
            "shift": {kb.Key.shift, kb.Key.shift_l, kb.Key.shift_r},
            "cmd": {kb.Key.cmd, getattr(kb.Key, "cmd_l", kb.Key.cmd),
                    getattr(kb.Key, "cmd_r", kb.Key.cmd)},
            "super": {kb.Key.cmd},
        }
        key_map = {"space": kb.Key.space, "enter": kb.Key.enter, "tab": kb.Key.tab}
        trigger = key_map.get(self.key)  # None se for uma letra comum

        def which_mod(k):
            for name in self.mods:
                if k in mod_keys.get(name, set()):
                    return name
            return None

        def is_trigger(k):
            if trigger is not None:
                return k == trigger
            # tecla comum (letra): pynput entrega KeyCode com .char
            return getattr(k, "char", None) == self.key

        def on_press(k):
            if k == kb.Key.esc:
                self.on_cancel()
                return
            m = which_mod(k)
            if m:
                self.held[m] = True
            elif is_trigger(k):
                self.held["_key"] = True
            else:
                return
            self._update()

        def on_release(k):
            m = which_mod(k)
            if m:
                self.held[m] = False
            elif is_trigger(k):
                self.held["_key"] = False
            else:
                return
            self._update()

        _log(f"escutando teclado (pynput), {'+'.join(sorted(self.mods))}+{self.key}")
        with kb.Listener(on_press=on_press, on_release=on_release) as listener:
            listener.join()


# ── paste (pyperclip + pynput controller) ─────────────────────────────────────
class ClipboardDelivery:
    """Copia pro clipboard (pyperclip) e cola com o atalho do SO via pynput.
    `paste_key` = 'cmd' (macOS) ou 'ctrl' (Windows)."""

    def __init__(self, paste_modifier: str) -> None:
        self.paste_modifier = paste_modifier  # "cmd" | "ctrl"

    def deliver(self, text: str, paste: bool = True, shortcut: str = "") -> bool:
        """Copia `text`. Se `paste`, cola com o atalho do SO. `shortcut` (ex:
        "ctrl+shift+v") permite forçar Shift; senão usa o modificador padrão do
        SO (Cmd no macOS, Ctrl no Windows). `paste=False` → só copia.
        Retorna True se colou, False se só copiou."""
        import pyperclip
        from pynput import keyboard as kb

        pyperclip.copy(text)
        if not paste:
            return False
        time.sleep(0.12)
        ctrl = kb.Controller()
        mod = kb.Key.cmd if self.paste_modifier == "cmd" else kb.Key.ctrl
        use_shift = "shift" in (shortcut or "").lower()
        mods = [mod] + ([kb.Key.shift] if use_shift else [])
        # try/finally: se algo falhar no meio, os modificadores NUNCA ficam
        # grudados no SO (Cmd/Ctrl preso trava o teclado do usuário).
        try:
            for m in mods:
                ctrl.press(m)
            ctrl.press("v")
            ctrl.release("v")
        finally:
            for m in reversed(mods):
                try:
                    ctrl.release(m)
                except Exception:
                    pass
        return True
