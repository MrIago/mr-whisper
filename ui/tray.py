#!/usr/bin/env python3
"""Ícone de bandeja do mr-whisper.

Reflete o estado com ícones ESTÁTICOS (um por estado) — sem animar via setIcon.
Motivo: o AppIndicator do GNOME (StatusNotifierItem) faz throttle/cache de ícone
e engasga com updates rápidos, ficando preso num frame. A animação viva fica na
pill (janela Qt própria); o tray só troca entre ícones fixos, que o indicador
processa bem.

Estados:
- idle         → mic neutro/apagado
- recording    → mic verde + ponto vermelho (REC)
- transcribing → mic verde + ponto teal (processando)
- paused       → mic neutro + risco vermelho
"""
from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

GREEN = "#9acd32"
MUTED = "#8a8a8a"
RED = "#ff4444"
TEAL = "#28e0c8"


class TrayIcon(QtWidgets.QSystemTrayIcon):
    def __init__(self) -> None:
        super().__init__()
        self._state = None
        # pré-renderiza um ícone por estado (nada de animação em runtime).
        self._icons = {s: self._make(s) for s in
                       ("idle", "recording", "transcribing", "paused")}
        self.set_state("idle")

    @QtCore.Slot(str)
    def set_state(self, state: str) -> None:
        if state not in self._icons:
            state = "idle"
        if state == self._state:
            return
        # NB: só trocamos entre ícones fixos — nunca animar via setIcon (o
        # AppIndicator do GNOME engasga e trava num frame). Anima na pill.
        self._state = state
        self.setIcon(self._icons[state])

    # ── desenho de cada ícone (uma vez, no init) ──────────────────────────────
    def _make(self, state: str) -> QtGui.QIcon:
        pix = QtGui.QPixmap(64, 64)
        pix.fill(QtCore.Qt.transparent)
        p = QtGui.QPainter(pix)
        p.setRenderHint(QtGui.QPainter.Antialiasing)

        active = state in ("recording", "transcribing")
        color = QtGui.QColor(GREEN if active else MUTED)

        # mic
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(color)
        p.drawRoundedRect(24, 8, 16, 26, 8, 8)
        pen = QtGui.QPen(color, 4)
        p.setPen(pen)
        p.setBrush(QtCore.Qt.NoBrush)
        p.drawArc(18, 18, 28, 28, 180 * 16, 180 * 16)
        p.drawLine(32, 46, 32, 54)

        # badge por estado (ponto fixo, sem animação)
        p.setPen(QtCore.Qt.NoPen)
        if state == "recording":
            p.setBrush(QtGui.QColor(RED))
            p.drawEllipse(42, 4, 18, 18)
        elif state == "transcribing":
            p.setBrush(QtGui.QColor(TEAL))
            p.drawEllipse(42, 4, 18, 18)
        elif state == "paused":
            pen2 = QtGui.QPen(QtGui.QColor(RED), 5)
            pen2.setCapStyle(QtCore.Qt.RoundCap)
            p.setPen(pen2)
            p.drawLine(14, 50, 50, 14)

        p.end()
        return QtGui.QIcon(pix)
