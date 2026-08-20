#!/usr/bin/env python3
"""Ícone de bandeja animado do mr-whisper.

Desenhado em runtime (sem asset externo), reflete o estado:
- idle         → mic neutro/apagado (não está gravando)
- recording    → mic verde + bolinha vermelha piscando (estilo REC de rádio)
- transcribing → mic verde + spinner girando (processando/traduzindo)

set_state() troca o estado; um QTimer redesenha ~12fps só quando há animação.
"""
from __future__ import annotations

import math

from PySide6 import QtCore, QtGui, QtWidgets

GREEN = "#9acd32"
MUTED = "#8a8a8a"
RED = "#ff4444"


class TrayIcon(QtWidgets.QSystemTrayIcon):
    def __init__(self) -> None:
        super().__init__()
        self._state = "idle"       # idle | recording | transcribing
        self._phase = 0.0
        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self._animate)
        self._timer.setInterval(80)  # ~12 fps
        self._render()

    # ── API ───────────────────────────────────────────────────────────────────
    @QtCore.Slot(str)
    def set_state(self, state: str) -> None:
        if state == self._state:
            return
        self._state = state
        self._phase = 0.0
        if state in ("recording", "transcribing"):
            self._timer.start()  # só esses animam
        else:
            self._timer.stop()   # idle e paused são estáticos
        self._render()

    # ── animação ────────────────────────────────────────────────────────────────
    def _animate(self) -> None:
        self._phase += 0.18
        self._render()

    # ── desenho ───────────────────────────────────────────────────────────────
    def _render(self) -> None:
        pix = QtGui.QPixmap(64, 64)
        pix.fill(QtCore.Qt.transparent)
        p = QtGui.QPainter(pix)
        p.setRenderHint(QtGui.QPainter.Antialiasing)

        active = self._state in ("recording", "transcribing")
        color = QtGui.QColor(GREEN if active else MUTED)

        # mic
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(color)
        p.drawRoundedRect(24, 8, 16, 26, 8, 8)             # corpo
        pen = QtGui.QPen(color, 4)
        p.setPen(pen)
        p.setBrush(QtCore.Qt.NoBrush)
        p.drawArc(18, 18, 28, 28, 180 * 16, 180 * 16)       # arco
        p.drawLine(32, 46, 32, 54)                           # haste

        # estado pausado: risco diagonal sobre o mic
        if self._state == "paused":
            pen2 = QtGui.QPen(QtGui.QColor(RED), 5)
            pen2.setCapStyle(QtCore.Qt.RoundCap)
            p.setPen(pen2)
            p.drawLine(14, 50, 50, 14)

        # badge de estado (canto superior direito)
        if self._state == "recording":
            # bolinha vermelha piscando (REC)
            blink = 0.5 + 0.5 * math.sin(self._phase * 2)
            c = QtGui.QColor(RED)
            c.setAlphaF(0.35 + 0.65 * blink)
            p.setPen(QtCore.Qt.NoPen)
            p.setBrush(c)
            p.drawEllipse(42, 4, 18, 18)
        elif self._state == "transcribing":
            # spinner (arco girando) verde-claro
            p.setBrush(QtCore.Qt.NoBrush)
            sp = QtGui.QPen(QtGui.QColor("#28e0c8"), 5)
            sp.setCapStyle(QtCore.Qt.RoundCap)
            p.setPen(sp)
            start = int((-self._phase * 180 / math.pi) % 360) * 16
            p.drawArc(42, 4, 18, 18, start, 270 * 16)

        p.end()
        self.setIcon(QtGui.QIcon(pix))
