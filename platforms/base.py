#!/usr/bin/env python3
"""Interface de plataforma do mr-whisper.

Cada SO implementa estas 3 peças (platform/linux.py, macos.py, windows.py). O
daemon fala só com esta interface, não sabe se está no X11, no CoreAudio ou no
Windows. Preferimos DUPLICAR lógica entre os OSes a criar abstrações frágeis:
orquestrar áudio+teclado+paste é específico demais por plataforma.

Peças:
- Recorder     , grava o microfone num .wav 16k mono; reporta nível (0..1) por
                  callback pro widget desenhar o waveform.
- HotkeyListener, escuta o atalho hold-to-talk (Ctrl+Alt+Espaço) e o cancelar
                  (ESC); dispara callbacks press/release/cancel.
- TextDelivery , entrega o texto final na janela focada (clipboard + paste).

`get_platform()` devolve a implementação do SO atual.
"""
from __future__ import annotations

import sys
from typing import Callable, Protocol


class Recorder(Protocol):
    """Grava o microfone. start() começa; stop() finaliza e devolve o path do
    wav (ou None se nada gravado). `on_level` recebe 0..1 durante a gravação."""

    started_at: float

    def start(self) -> None: ...
    def stop(self) -> str | None: ...


class HotkeyListener(Protocol):
    """Escuta as teclas globais. run() bloqueia (loop de eventos). Dispara:
    - on_press()  quando o combo hold-to-talk é pressionado
    - on_release() quando é solto
    - on_cancel() quando o cancelar (ESC) é pressionado
    """

    def run(self) -> None: ...


class TextDelivery(Protocol):
    """Entrega o texto na janela ativa (clipboard + paste sintético)."""

    def deliver(self, text: str) -> None: ...


class Platform(Protocol):
    """Fábrica das 3 peças pro SO atual."""

    name: str

    def make_recorder(self, on_level: Callable[[float], None]) -> Recorder: ...
    def make_hotkey(
        self,
        on_press: Callable[[], None],
        on_release: Callable[[], None],
        on_cancel: Callable[[], None],
    ) -> HotkeyListener: ...
    def make_delivery(self) -> TextDelivery: ...


def get_platform() -> Platform:
    """Detecta o SO e devolve a implementação correspondente."""
    if sys.platform.startswith("linux"):
        from . import linux
        return linux.LinuxPlatform()
    if sys.platform == "darwin":
        from . import macos
        return macos.MacPlatform()
    if sys.platform == "win32":
        from . import windows
        return windows.WindowsPlatform()
    raise RuntimeError(f"plataforma não suportada: {sys.platform}")
