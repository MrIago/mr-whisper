#!/usr/bin/env python3
"""Plataforma Windows: sounddevice + pynput + pyperclip, paste com Ctrl+V.

Sem privilégio elevado necessário (hooks globais do pynput funcionam no user).
"""
from __future__ import annotations

from ._portable import SounddeviceRecorder, PynputHotkey, ClipboardDelivery


class WindowsPlatform:
    name = "windows"

    def make_recorder(self, on_level):
        return SounddeviceRecorder(on_level)

    def make_hotkey(self, on_press, on_release, on_cancel):
        return PynputHotkey(on_press, on_release, on_cancel)

    def make_delivery(self):
        return ClipboardDelivery(paste_modifier="ctrl")  # Ctrl+V no Windows
