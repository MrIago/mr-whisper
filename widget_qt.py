#!/usr/bin/env python3
"""Widget flutuante do mr-whisper em Qt (PySide6) — cross-platform (Linux/Mac/Win).

Processo próprio. Lê comandos do stdin (uma linha por comando):
  listening      → mostra a pill "ouvindo", anima a waveform
  level <0..1>   → atualiza a amplitude da waveform
  transcribing   → estado "transcrevendo" (spinner)
  hide           → some
  quit           → fecha

Pill escura, sem borda, always-on-top, sem foco, fundo transparente. Posiciona
no centro-baixo da tela que contém o cursor.
"""
from __future__ import annotations

import math
import sys
import threading

from PySide6 import QtCore, QtGui, QtWidgets

BARS = 13
PILL_W = 150
PILL_H = 52


class Pill(QtWidgets.QWidget):
    # sinal pra aplicar comandos vindos da thread do stdin na thread da UI
    command = QtCore.Signal(str, str)

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

        self.mode = "listening"      # listening | transcribing
        self.level = 0.0
        self.bars = [0.08] * BARS
        self.phase = 0.0

        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.setInterval(33)  # ~30 fps

        self.command.connect(self._handle)

    # ── posicionamento ────────────────────────────────────────────────────────
    def position(self) -> None:
        screen = QtWidgets.QApplication.screenAt(QtGui.QCursor.pos())
        if screen is None:
            screen = QtWidgets.QApplication.primaryScreen()
        geo = screen.geometry()
        x = geo.x() + (geo.width() - PILL_W) // 2
        y = geo.y() + int(geo.height() * 0.82)
        self.move(x, y)

    # ── animação ──────────────────────────────────────────────────────────────
    def _tick(self) -> None:
        self.phase += 0.35
        for i in range(BARS):
            wobble = 0.5 + 0.5 * math.sin(self.phase + i * 0.6)
            target = 0.08 + self.level * (0.25 + 0.75 * wobble)
            self.bars[i] += (target - self.bars[i]) * 0.4
        self.update()

    # ── desenho ───────────────────────────────────────────────────────────────
    def paintEvent(self, _event) -> None:
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        w, h = self.width(), self.height()

        # pill escura
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(QtGui.QColor(26, 26, 31, 235))
        p.drawRoundedRect(0, 0, w, h, h / 2, h / 2)

        if self.mode == "transcribing":
            self._draw_spinner(p, w, h)
        else:
            self._draw_waveform(p, w, h)
        p.end()

    def _draw_waveform(self, p: QtGui.QPainter, w: int, h: int) -> None:
        pad = 18
        usable = w - pad * 2
        gap = usable / BARS
        bw = gap * 0.45
        p.setBrush(QtGui.QColor(242, 242, 247))
        for i, lvl in enumerate(self.bars):
            bh = max(3, lvl * (h * 0.62))
            x = pad + i * gap + (gap - bw) / 2
            y = (h - bh) / 2
            p.drawRoundedRect(QtCore.QRectF(x, y, bw, bh), bw / 2, bw / 2)

    def _draw_spinner(self, p: QtGui.QPainter, w: int, h: int) -> None:
        cx, cy = w / 2, h / 2
        rad = h * 0.22
        pen = QtGui.QPen()
        pen.setWidth(3)
        for i in range(12):
            a = self.phase + i * (math.pi / 6)
            alpha = int((i / 12.0) * 255)
            pen.setColor(QtGui.QColor(242, 242, 247, alpha))
            p.setPen(pen)
            p.drawLine(
                QtCore.QPointF(cx + math.cos(a) * rad * 0.55, cy + math.sin(a) * rad * 0.55),
                QtCore.QPointF(cx + math.cos(a) * rad, cy + math.sin(a) * rad),
            )

    # ── comandos ──────────────────────────────────────────────────────────────
    @QtCore.Slot(str, str)
    def _handle(self, cmd: str, arg: str) -> None:
        if cmd == "listening":
            self.mode = "listening"
            self.level = 0.0
            self.position()
            self.show()
            self._timer.start()
        elif cmd == "level":
            try:
                self.level = max(0.0, min(1.0, float(arg)))
            except ValueError:
                pass
        elif cmd == "transcribing":
            self.mode = "transcribing"
        elif cmd == "hide":
            self._timer.stop()
            self.hide()
        elif cmd == "quit":
            QtWidgets.QApplication.quit()


def _stdin_loop(pill: Pill) -> None:
    """Lê o stdin numa thread e repassa comandos pra UI via signal (thread-safe)."""
    for line in sys.stdin:
        cmd, _, arg = line.strip().partition(" ")
        if not cmd:
            continue
        pill.command.emit(cmd, arg)
    pill.command.emit("quit", "")


def main() -> int:
    app = QtWidgets.QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # esconder a pill não encerra o app
    pill = Pill()
    threading.Thread(target=_stdin_loop, args=(pill,), daemon=True).start()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
