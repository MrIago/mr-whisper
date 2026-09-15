#!/usr/bin/env python3
"""A pill flutuante do mr-whisper, integrada ao app Qt.

Fluxo visual (chamado pelo app na thread da UI):
- show_listening(): pill larga com waveform reagindo à voz (set_level()).
- show_transcribing(): a pill ENCOLHE as laterais (largura anima até virar um
  círculo, mantendo-se centralizada) e mostra um spinner girando.
- show_done(): no círculo, aparece um ícone de "copiado" por um instante e some.
- hide_pill(): esconde na hora (cancelamento).

A largura é animada de dentro (a janela redimensiona), então a mesma pill vira
círculo sem trocar de widget.
"""
from __future__ import annotations

import math

from PySide6 import QtCore, QtGui, QtWidgets

BARS = 13
PILL_W = 150          # largura no modo "ouvindo"
PILL_H = 52           # altura fixa (a largura mínima = altura = círculo)
INK = QtGui.QColor(242, 242, 247)
BG = QtGui.QColor(26, 26, 31, 235)
GREEN = QtGui.QColor("#9acd32")


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
        # a janela é sempre do tamanho MÁXIMO (largura cheia); a pill é desenhada
        # centralizada dentro dela e encolhe por animação (sem mover a janela).
        self.resize(PILL_W, PILL_H)

        self.mode = "listening"     # listening | transcribing | done
        self.level = 0.0
        self.bars = [0.08] * BARS
        self.phase = 0.0
        self.shrink = 0.0           # 0 = largura cheia, 1 = círculo (ease-out)
        self._shrink_t = 0.0        # progresso linear 0→1 do encolhimento
        self._done_frames = 0
        self._pending_done = False
        self._done_kind = "copied"  # copied | note

    SHRINK_FRAMES = 12  # ~0.4s pra virar círculo (curva ease-out aplicada)

    @staticmethod
    def _ease_out(t: float) -> float:
        # bézier de saída (aceleração decrescente): rápido no começo, freia no fim
        return 1.0 - (1.0 - t) ** 3

        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.setInterval(33)  # ~30 fps

    # ── largura atual da pill (anima com `shrink`; no fim = altura → círculo) ──
    def _pill_w(self) -> float:
        h = self.height()
        return PILL_W - (PILL_W - h) * self.shrink

    # ── API (thread da UI) ─────────────────────────────────────────────────────
    def show_listening(self) -> None:
        self.mode = "listening"
        self.level = 0.0
        self.shrink = 0.0
        self.bars = [0.08] * BARS
        # posiciona antes e depois do show (WMs divergem) + reaplica em 50ms pra
        # geometria de tela que no boot ainda não estava pronta.
        self._position()
        self.show()
        self._position()
        self.raise_()
        QtCore.QTimer.singleShot(50, self._position)
        self._timer.start()

    def set_level(self, lvl: float) -> None:
        self.level = max(0.0, min(1.0, lvl))

    def show_transcribing(self) -> None:
        # inicia o encolhimento por TEMPO (curva ease-out), não por STT ter
        # terminado — garante que a animação de virar círculo sempre apareça.
        if self.mode != "transcribing":
            self._shrink_t = 0.0
        self.mode = "transcribing"

    def show_done(self, kind: str = "copied") -> None:
        """Ao terminar: mostra o ícone (copied|note) no círculo e some. Espera a
        pill JÁ estar círculo (se o STT foi rápido demais, deixa o encolhimento
        completar antes de trocar pro ícone)."""
        self._done_kind = kind
        self._pending_done = True  # o _tick vira "done" quando shrink ~ 1

    def hide_pill(self) -> None:
        self._timer.stop()
        self.hide()

    # ── posição (centro-baixo da tela do cursor) ──────────────────────────────
    def _position(self) -> None:
        screen = QtWidgets.QApplication.screenAt(QtGui.QCursor.pos()) \
            or QtWidgets.QApplication.primaryScreen()
        geo = screen.geometry()
        self.move(geo.x() + (geo.width() - PILL_W) // 2,
                  geo.y() + int(geo.height() * 0.82))

    # ── animação ───────────────────────────────────────────────────────────────
    def _tick(self) -> None:
        self.phase += 0.35
        # waveform (só no listening)
        for i in range(BARS):
            wobble = 0.5 + 0.5 * math.sin(self.phase + i * 0.6)
            target = 0.08 + self.level * (0.25 + 0.75 * wobble)
            self.bars[i] += (target - self.bars[i]) * 0.4

        # encolhimento: progresso por TEMPO + curva ease-out (bézier de saída).
        # avança quando transcrevendo/done; recua se voltar pro listening.
        if self.mode in ("transcribing", "done"):
            self._shrink_t = min(1.0, self._shrink_t + 1.0 / self.SHRINK_FRAMES)
        else:
            self._shrink_t = 0.0
        self.shrink = self._ease_out(self._shrink_t)

        # só troca pro ícone final quando a pill JÁ virou círculo (shrink ~ 1)
        if self._pending_done and self.shrink > 0.985:
            self._pending_done = False
            self.mode = "done"
            self._done_frames = 24  # ~0.8s de ícone visível

        if self.mode == "done":
            self._done_frames -= 1
            if self._done_frames <= 0:
                self.hide_pill()
                return
        self.update()

    # ── desenho ───────────────────────────────────────────────────────────────
    def paintEvent(self, _event) -> None:
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        W, H = self.width(), self.height()
        pw = self._pill_w()
        x0 = (W - pw) / 2  # centraliza a pill encolhida dentro da janela cheia

        # corpo da pill (retângulo arredondado; quando pw==H vira círculo)
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(BG)
        p.drawRoundedRect(QtCore.QRectF(x0, 0, pw, H), H / 2, H / 2)

        cx, cy = W / 2, H / 2
        if self.mode == "done":
            if self._done_kind == "note":
                self._draw_note(p, cx, cy, H)
            else:
                self._draw_copied(p, cx, cy, H)
        elif self.shrink < 0.35:
            # ainda largo: waveform (vai sumindo com fade conforme encolhe)
            self._draw_waveform(p, x0, W, H)
        else:
            # já quase círculo: spinner
            self._draw_spinner(p, cx, cy, H)
        p.end()

    def _draw_waveform(self, p, x0, W, H) -> None:
        # fade das barras conforme a pill começa a encolher
        alpha = int(255 * max(0.0, 1.0 - self.shrink * 2))
        color = QtGui.QColor(INK); color.setAlpha(alpha)
        pad = 18
        pw = self._pill_w()
        gap = (pw - pad * 2) / BARS
        bw = gap * 0.45
        p.setBrush(color)
        for i, lvl in enumerate(self.bars):
            bh = max(3, lvl * (H * 0.62))
            x = x0 + pad + i * gap + (gap - bw) / 2
            p.drawRoundedRect(QtCore.QRectF(x, (H - bh) / 2, bw, bh), bw / 2, bw / 2)

    def _draw_spinner(self, p, cx, cy, H) -> None:
        # arco de ~270° girando (mais limpo que raios soltos)
        rad = H * 0.24
        rect = QtCore.QRectF(cx - rad, cy - rad, rad * 2, rad * 2)
        pen = QtGui.QPen(INK, 3)
        pen.setCapStyle(QtCore.Qt.RoundCap)
        p.setPen(pen)
        p.setBrush(QtCore.Qt.NoBrush)
        start = int(-self.phase * 180 / math.pi * 2) % 360
        p.drawArc(rect, start * 16, 270 * 16)

    def _draw_copied(self, p, cx, cy, H) -> None:
        """Ícone de 'copiado' (dois retângulos sobrepostos, estilo clipboard) em
        verde, com um pop de escala rápido pra dar o toque de sucesso."""
        pop = 1.0 + 0.15 * max(0.0, math.sin(min(1.0, (24 - self._done_frames) / 6) * math.pi))
        s = H * 0.18 * pop
        pen = QtGui.QPen(GREEN, 2.4)
        pen.setJoinStyle(QtCore.Qt.RoundJoin)
        p.setPen(pen)
        p.setBrush(QtCore.Qt.NoBrush)
        # folha de trás (deslocada) + folha da frente = ícone de copiar
        p.drawRoundedRect(QtCore.QRectF(cx - s * 0.3, cy - s * 0.9, s * 1.2, s * 1.5), 3, 3)
        p.setBrush(BG)
        p.drawRoundedRect(QtCore.QRectF(cx - s * 0.9, cy - s * 0.4, s * 1.2, s * 1.5), 3, 3)

    def _draw_note(self, p, cx, cy, H) -> None:
        """Ícone de nota/anotação (folha com linhas de texto) em verde, para o
        comando 'new dump', que salva nas notas em vez de colar."""
        pop = 1.0 + 0.15 * max(0.0, math.sin(min(1.0, (24 - self._done_frames) / 6) * math.pi))
        w = H * 0.30 * pop
        h = H * 0.40 * pop
        x, y = cx - w / 2, cy - h / 2
        pen = QtGui.QPen(GREEN, 2.2)
        pen.setJoinStyle(QtCore.Qt.RoundJoin)
        pen.setCapStyle(QtCore.Qt.RoundCap)
        p.setPen(pen)
        p.setBrush(QtCore.Qt.NoBrush)
        p.drawRoundedRect(QtCore.QRectF(x, y, w, h), 3, 3)   # folha
        # linhas de texto
        for i in range(3):
            ly = y + h * (0.28 + i * 0.22)
            p.drawLine(QtCore.QPointF(x + w * 0.22, ly),
                       QtCore.QPointF(x + w * 0.78, ly))
