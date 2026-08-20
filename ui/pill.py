#!/usr/bin/env python3
"""A pill flutuante (waveform + spinner), como QWidget integrado ao app Qt.

Diferente do widget_qt.py (processo separado via stdin), esta versão é chamada
direto pelo app: show_listening() / set_level() / show_transcribing() / hide_pill().
Todos os métodos devem ser chamados na thread da UI (use signals se vier de outra).
"""
from __future__ import annotations

import math

from PySide6 import QtCore, QtGui, QtWidgets

BARS = 13
PILL_W = 150
PILL_H = 52


class Pill(QtWidgets.QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowFlags(
            QtCore.Qt.FramelessWindowHint
            | QtCore.Qt.WindowStaysOnTopHint
            | QtCore.Qt.Tool
            | QtCore.Qt.WindowDoesNotAcceptFocus
        )
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.setAttribute(QtCore.Qt.WA_ShowWithoutActivating)
        self.resize(PILL_W, PILL_H)

        self.mode = "listening"
        self.level = 0.0
        self.bars = [0.08] * BARS
        self.phase = 0.0

        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.setInterval(33)

    # ── API (chamada pelo app) ────────────────────────────────────────────────
    def show_listening(self) -> None:
        self.mode = "listening"
        self.level = 0.0
        self.show()
        self._position()   # depois do show(): mover antes do mapeamento é
        self.raise_()      # ignorado por vários WMs (janela ia parar em 0,0)
        self._timer.start()

    def set_level(self, lvl: float) -> None:
        self.level = max(0.0, min(1.0, lvl))

    def show_transcribing(self) -> None:
        self.mode = "transcribing"

    def hide_pill(self) -> None:
        self._timer.stop()
        self.hide()

    # ── interno ───────────────────────────────────────────────────────────────
    def _position(self) -> None:
        screen = QtWidgets.QApplication.screenAt(QtGui.QCursor.pos()) \
            or QtWidgets.QApplication.primaryScreen()
        geo = screen.geometry()
        self.move(geo.x() + (geo.width() - PILL_W) // 2,
                  geo.y() + int(geo.height() * 0.82))

    def _tick(self) -> None:
        self.phase += 0.35
        for i in range(BARS):
            wobble = 0.5 + 0.5 * math.sin(self.phase + i * 0.6)
            target = 0.08 + self.level * (0.25 + 0.75 * wobble)
            self.bars[i] += (target - self.bars[i]) * 0.4
        self.update()

    def paintEvent(self, _event) -> None:
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        w, h = self.width(), self.height()
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(QtGui.QColor(26, 26, 31, 235))
        p.drawRoundedRect(0, 0, w, h, h / 2, h / 2)
        if self.mode == "transcribing":
            self._draw_spinner(p, w, h)
        else:
            self._draw_waveform(p, w, h)
        p.end()

    def _draw_waveform(self, p, w, h) -> None:
        pad = 18
        gap = (w - pad * 2) / BARS
        bw = gap * 0.45
        p.setBrush(QtGui.QColor(242, 242, 247))
        for i, lvl in enumerate(self.bars):
            bh = max(3, lvl * (h * 0.62))
            x = pad + i * gap + (gap - bw) / 2
            p.drawRoundedRect(QtCore.QRectF(x, (h - bh) / 2, bw, bh), bw / 2, bw / 2)

    def _draw_spinner(self, p, w, h) -> None:
        cx, cy = w / 2, h / 2
        rad = h * 0.22
        pen = QtGui.QPen()
        pen.setWidth(3)
        for i in range(12):
            a = self.phase + i * (math.pi / 6)
            pen.setColor(QtGui.QColor(242, 242, 247, int((i / 12.0) * 255)))
            p.setPen(pen)
            p.drawLine(
                QtCore.QPointF(cx + math.cos(a) * rad * 0.55, cy + math.sin(a) * rad * 0.55),
                QtCore.QPointF(cx + math.cos(a) * rad, cy + math.sin(a) * rad),
            )
