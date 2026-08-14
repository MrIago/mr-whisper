#!/usr/bin/env python3
"""Plataforma macOS: sounddevice + pynput + pyperclip, paste com Cmd+V.

Permissões necessárias no macOS (System Settings → Privacy & Security):
- Accessibility  → pra pynput ler/enviar teclas globais
- Input Monitoring → idem
- Microphone     → pra sounddevice gravar
"""
from __future__ import annotations

from ._portable import SounddeviceRecorder, PynputHotkey, ClipboardDelivery


class MacPlatform:
    name = "macos"

    def make_recorder(self, on_level):
        return SounddeviceRecorder(on_level)

    def make_hotkey(self, on_press, on_release, on_cancel):
        return PynputHotkey(on_press, on_release, on_cancel)

    def make_delivery(self):
        return ClipboardDelivery(paste_modifier="cmd")  # Cmd+V no macOS
