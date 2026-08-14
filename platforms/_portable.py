#!/usr/bin/env python3
"""Peças cross-platform (macOS + Windows) do mr-whisper.

Áudio e teclado são idênticos nos dois via libs portáveis; só o PASTE difere
(Cmd+V no Mac, Ctrl+V no Windows), então cada plataforma define só a delivery.

Dependências (instaladas pelo setup): sounddevice, pynput, pyperclip.
"""
from __future__ import annotations

import audioop
import tempfile
import threading
import time
import wave
from typing import Callable

SAMPLE_RATE = 16000
CHANNELS = 1


def _log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


# ── áudio (sounddevice → buffer → wav) ────────────────────────────────────────
class SounddeviceRecorder:
    """Grava do mic em memória via sounddevice (PortAudio) e escreve o wav no
    stop(). O nível (RMS) sai direto de cada bloco — sem ler arquivo parcial."""

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
            rms = audioop.rms(buf[: len(buf) - (len(buf) % 2)], 2)
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
    """Hold-to-talk via pynput: Ctrl+Alt+Espaço segura/solta; Esc cancela.
    run() bloqueia no listener."""

    def __init__(self, on_press, on_release, on_cancel) -> None:
        self.on_press = on_press
        self.on_release = on_release
        self.on_cancel = on_cancel
        self.held = {"ctrl": False, "alt": False, "space": False}
        self.active = False

    def _update(self):
        combo = self.held["ctrl"] and self.held["alt"] and self.held["space"]
        if combo and not self.active:
            self.active = True
            self.on_press()
        elif not combo and self.active:
            self.active = False
            self.on_release()

    def run(self) -> None:
        from pynput import keyboard as kb

        def is_ctrl(k):
            return k in (kb.Key.ctrl, kb.Key.ctrl_l, kb.Key.ctrl_r)

        def is_alt(k):
            return k in (kb.Key.alt, kb.Key.alt_l, kb.Key.alt_r, kb.Key.alt_gr)

        def on_press(k):
            if is_ctrl(k):
                self.held["ctrl"] = True
            elif is_alt(k):
                self.held["alt"] = True
            elif k == kb.Key.space:
                self.held["space"] = True
            elif k == kb.Key.esc:
                self.on_cancel()
                return
            else:
                return
            self._update()

        def on_release(k):
            if is_ctrl(k):
                self.held["ctrl"] = False
            elif is_alt(k):
                self.held["alt"] = False
            elif k == kb.Key.space:
                self.held["space"] = False
            else:
                return
            self._update()

        _log("escutando teclado (pynput) — Ctrl+Alt+Espaço")
        with kb.Listener(on_press=on_press, on_release=on_release) as listener:
            listener.join()


# ── paste (pyperclip + pynput controller) ─────────────────────────────────────
class ClipboardDelivery:
    """Copia pro clipboard (pyperclip) e cola com o atalho do SO via pynput.
    `paste_key` = 'cmd' (macOS) ou 'ctrl' (Windows)."""

    def __init__(self, paste_modifier: str) -> None:
        self.paste_modifier = paste_modifier  # "cmd" | "ctrl"

    def deliver(self, text: str) -> None:
        import pyperclip
        from pynput import keyboard as kb

        pyperclip.copy(text)
        time.sleep(0.12)
        ctrl = kb.Controller()
        mod = kb.Key.cmd if self.paste_modifier == "cmd" else kb.Key.ctrl
        with ctrl.pressed(mod):
            ctrl.press("v")
            ctrl.release("v")
