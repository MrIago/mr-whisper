#!/usr/bin/env python3
"""Ícone de bandeja do mr-whisper.

Reflete o estado com ícones ESTÁTICOS (um por estado), sem animar via setIcon.
Motivo: o AppIndicator do GNOME (StatusNotifierItem) faz throttle/cache de ícone
e engasga com updates rápidos, ficando preso num frame. Toda a animação viva
mora na pill (janela Qt própria, a bolinha flutuante); o tray fica sóbrio.

Desenho: um microfone só, que muda de COR conforme o estado. Sem badge, sem
bolinha, sem spinner (o "frufru" é a pill):

- idle          → microfone muted (cinza)
- recording     → microfone branco (falando)
- transcribing  → microfone branco (segue branco enquanto processa)
- paused        → microfone muted com um risco vermelho por cima

No macOS a barra de menu recolore o ícone (template mask), então lá o mic
aparece no tom do tema em vez do branco/cinza; a diferença idle vs. ativo some
no Mac, mas a pill já sinaliza o estado com folga.
"""
from __future__ import annotations

import sys

from PySide6 import QtCore, QtGui, QtWidgets

WHITE = "#f2f2f5"
MUTED = "#8a8a8a"
RED = "#ff4444"


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
        # NB: só trocamos entre ícones fixos, nunca animar via setIcon (o
        # AppIndicator do GNOME engasga e trava num frame). Anima na pill.
        self._state = state
        self.setIcon(self._icons[state])

    # ── desenho de cada ícone (uma vez, no init) ──────────────────────────────
    def _make(self, state: str) -> QtGui.QIcon:
        pix = QtGui.QPixmap(64, 64)
        pix.fill(QtCore.Qt.transparent)
        p = QtGui.QPainter(pix)
        p.setRenderHint(QtGui.QPainter.Antialiasing)

        # ativo (gravando ou transcrevendo) = branco; senão muted.
        active = state in ("recording", "transcribing")
        color = QtGui.QColor(WHITE if active else MUTED)

        # microfone
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(color)
        p.drawRoundedRect(24, 8, 16, 26, 8, 8)
        pen = QtGui.QPen(color, 4)
        p.setPen(pen)
        p.setBrush(QtCore.Qt.NoBrush)
        p.drawArc(18, 18, 28, 28, 180 * 16, 180 * 16)
        p.drawLine(32, 46, 32, 54)

        # pausado: risco vermelho por cima (única exceção que usa outra cor)
        if state == "paused":
            pen2 = QtGui.QPen(QtGui.QColor(RED), 5)
            pen2.setCapStyle(QtCore.Qt.RoundCap)
            p.setPen(pen2)
            p.drawLine(14, 50, 50, 14)

        p.end()
        # No macOS a barra de menu espera um ícone "template" (mask), senão um
        # pixmap colorido pode não aparecer. Marcamos como mask; o macOS o
        # recolore pro tema (claro/escuro). Nos outros OS, ícone colorido normal.
        if sys.platform == "darwin":
            pix.setDevicePixelRatio(2.0)  # nítido na barra ~22px
            pix.setMask(pix.createMaskFromColor(QtCore.Qt.transparent,
                                                QtCore.Qt.MaskInColor))
        icon = QtGui.QIcon(pix)
        if sys.platform == "darwin":
            icon.setIsMask(True)
        return icon
