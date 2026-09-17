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

from .base import level_from_rms, rms16

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
            self.on_level(level_from_rms(rms16(buf)))

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
# Códigos físicos (virtual keycodes) por SO, pra reconhecer a tecla-gatilho mesmo
# com modificador segurado. macOS: kVK_ANSI_* (layout ANSI). Windows: VK_*.
_MAC_VK = {
    "a": 0, "s": 1, "d": 2, "f": 3, "h": 4, "g": 5, "z": 6, "x": 7, "c": 8,
    "v": 9, "b": 11, "q": 12, "w": 13, "e": 14, "r": 15, "y": 16, "t": 17,
    "1": 18, "2": 19, "3": 20, "4": 21, "6": 22, "5": 23, "=": 24, "9": 25,
    "7": 26, "-": 27, "8": 28, "0": 29, "]": 30, "o": 31, "u": 32, "[": 33,
    "i": 34, "p": 35, "l": 37, "j": 38, "'": 39, "k": 40, ";": 41, "\\": 42,
    ",": 43, "/": 44, "n": 45, "m": 46, ".": 47, "`": 50,
}
_WIN_VK = {",": 0xBC, ".": 0xBE, "/": 0xBF, ";": 0xBA, "'": 0xDE, "[": 0xDB,
           "]": 0xDD, "\\": 0xDC, "-": 0xBD, "=": 0xBB, "`": 0xC0}


def _vk_for(key: str) -> int | None:
    """Código físico da tecla `key` neste SO, ou None se não mapeada."""
    import sys
    if sys.platform == "darwin":
        return _MAC_VK.get(key)
    if sys.platform == "win32":
        if len(key) == 1 and key.isalnum():
            return ord(key.upper())  # VK de letra/dígito = ASCII maiúsculo
        return _WIN_VK.get(key)
    return None


class PynputHotkey:
    """Hold-to-talk via pynput com atalho CONFIGURÁVEL (core.config.hotkey_combo).
    Segura os modificadores + tecla → press; solta → release; Esc cancela."""

    def __init__(self, on_press, on_release, on_cancel) -> None:
        self.on_press = on_press
        self.on_release = on_release
        self.on_cancel = on_cancel
        from core import config
        # ex: ({"alt"}, "space"), ou ({"ctrl","alt"}, "") quando é só modificador
        self.mods, self.key = config.hotkey_combo()
        self.held = {m: False for m in self.mods}
        # atalho só de modificadores: não há tecla-gatilho, ela conta como "sempre
        # segurada" e o combo depende apenas dos modificadores.
        self.held["_key"] = not self.key
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
        key_map = {"space": kb.Key.space, "enter": kb.Key.enter, "tab": kb.Key.tab,
                   "backspace": kb.Key.backspace}
        key_map.update({f"f{i}": getattr(kb.Key, f"f{i}") for i in range(1, 13)})
        trigger = key_map.get(self.key)  # None se for letra/número/símbolo
        trigger_vk = _vk_for(self.key)   # código físico da tecla neste SO

        def which_mod(k):
            for name in self.mods:
                if k in mod_keys.get(name, set()):
                    return name
            return None

        def is_trigger(k):
            if not self.key:  # atalho só de modificadores: não existe gatilho
                return False
            if trigger is not None:
                return k == trigger
            # letra/número/símbolo. O .char muda com o modificador segurado
            # (Option+r vira "®" no Mac, Ctrl+r vira caractere de controle no
            # Windows), então comparamos também o código FÍSICO da tecla (vk).
            if trigger_vk is not None and getattr(k, "vk", None) == trigger_vk:
                return True
            ch = getattr(k, "char", None)
            return bool(ch) and ch.lower() == self.key

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

        label = "+".join(sorted(self.mods)) + (f"+{self.key}" if self.key else "")
        _log(f"escutando teclado (pynput), {label}")
        extra = {}
        swallow = _mac_swallow_trigger(self) if self.key else None
        if swallow is not None:
            # macOS: o listener só ESCUTA, então a tecla do atalho também chegava
            # no app em foco e, segurada, repetia (Option+Espaço enchia o texto
            # de espaços). Com o intercept a tecla-gatilho é consumida enquanto
            # os modificadores do atalho estão segurados.
            extra["darwin_intercept"] = swallow
        with kb.Listener(on_press=on_press, on_release=on_release, **extra) as listener:
            listener.join()


# keycodes físicos do macOS pras teclas especiais (as demais vêm de _MAC_VK)
_MAC_SPECIAL_VK = {"space": 49, "enter": 36, "tab": 48, "backspace": 51,
                   "f1": 122, "f2": 120, "f3": 99, "f4": 118, "f5": 96, "f6": 97,
                   "f7": 98, "f8": 100, "f9": 101, "f10": 109, "f11": 103,
                   "f12": 111}


def _mac_swallow_trigger(hotkey: "PynputHotkey"):
    """Devolve o callback `darwin_intercept` do pynput que CONSOME a tecla-gatilho
    enquanto os modificadores do atalho estão segurados (o pynput ainda chama
    on_press/on_release antes; só o app em foco deixa de receber a tecla). None
    fora do macOS ou se o Quartz não estiver disponível."""
    import sys
    if sys.platform != "darwin":
        return None
    vk = _MAC_SPECIAL_VK.get(hotkey.key, _MAC_VK.get(hotkey.key))
    if vk is None:
        return None
    try:
        import Quartz
    except Exception:
        return None
    key_events = (Quartz.kCGEventKeyDown, Quartz.kCGEventKeyUp)

    def intercept(event_type, event):
        try:
            if event_type in key_events and all(hotkey.held[m] for m in hotkey.mods):
                code = Quartz.CGEventGetIntegerValueField(
                    event, Quartz.kCGKeyboardEventKeycode)
                if code == vk:
                    return None  # consome: o app em foco não recebe a tecla
        except Exception:
            pass
        return event

    return intercept


# ── paste (pyperclip + tecla de colar) ────────────────────────────────────────
def _mac_paste(use_shift: bool = False) -> bool:
    """Cmd+V (ou Cmd+Shift+V) no macOS via eventos Quartz por keycode. Retorna
    True se postou o atalho, False se não deu (o texto já está no clipboard)."""
    try:
        import Quartz
    except Exception as exc:
        _log(f"paste: Quartz indisponível ({exc}); texto ficou no clipboard")
        return False
    try:
        v_key = 9  # kVK_ANSI_V
        flags = Quartz.kCGEventFlagMaskCommand
        if use_shift:
            flags |= Quartz.kCGEventFlagMaskShift
        src = Quartz.CGEventSourceCreate(Quartz.kCGEventSourceStateHIDSystemState)
        for is_down in (True, False):
            ev = Quartz.CGEventCreateKeyboardEvent(src, v_key, is_down)
            # flags explícitas: ignora modificadores que o usuário ainda esteja
            # segurando do atalho (senão viraria Ctrl+Option+Cmd+V).
            Quartz.CGEventSetFlags(ev, flags)
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, ev)
        return True
    except Exception as exc:
        _log(f"paste falhou ({exc}); texto ficou no clipboard")
        return False


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
        import sys
        import pyperclip

        pyperclip.copy(text)
        if not paste:
            return False
        time.sleep(0.12)
        use_shift = "shift" in (shortcut or "").lower()
        if sys.platform == "darwin":
            # NÃO usar pynput.Controller no macOS: ao ser criado ele consulta o
            # layout do teclado (TSMGetInputSourceProperty), API que só pode rodar
            # na thread principal. Esta função roda na thread de processamento, e
            # no macOS 14/15 isso derruba o app com SIGTRAP logo após transcrever
            # (crash nativo, try/except não segura). Eventos Quartz por keycode
            # não tocam nessa API e podem ser postados de qualquer thread.
            return _mac_paste(use_shift)

        from pynput import keyboard as kb
        ctrl = kb.Controller()
        mod = kb.Key.cmd if self.paste_modifier == "cmd" else kb.Key.ctrl
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
