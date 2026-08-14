#!/usr/bin/env python3
"""mr-whisper — app de bandeja cross-platform (Linux/macOS/Windows).

Um único processo Qt: tray icon (Settings / Pause / Quit), a pill flutuante, e a
janela de settings. O listener de teclado (hold-to-talk) roda numa thread e fala
com a UI por signals. Transcrição na nuvem (groq/openai/openrouter) + comandos
de voz (translate/context/adjust/dump).

Entrypoint do produto (substitui o antigo daemon.py de terminal).
"""
from __future__ import annotations

import os
import sys
import threading
import time
import wave
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

from core import config, cloud, dump, translate
from platforms import base
from ui.pill import Pill
from ui.settings import SettingsWindow

HERE = Path(__file__).parent
MIN_HOLD = 0.3


def wav_duration(path: str) -> float:
    try:
        with wave.open(path, "rb") as w:
            return w.getnframes() / float(w.getframerate() or 16000)
    except Exception:
        return 0.0


class Controller(QtCore.QObject):
    """Cola a UI (thread principal Qt) com o áudio/STT (threads). Todos os
    sinais chegam na thread da UI."""

    sig_listening = QtCore.Signal()
    sig_level = QtCore.Signal(float)
    sig_transcribing = QtCore.Signal()
    sig_hide = QtCore.Signal()

    def __init__(self, platform: base.Platform, pill: Pill) -> None:
        super().__init__()
        self.platform = platform
        self.pill = pill
        self.recorder = platform.make_recorder(lambda lvl: self.sig_level.emit(lvl))
        self.delivery = platform.make_delivery()
        self.recording = False
        self.transcribing = False
        self.paused = False
        self._cancel = False
        self.lock = threading.Lock()

        self.sig_listening.connect(pill.show_listening)
        self.sig_level.connect(pill.set_level)
        self.sig_transcribing.connect(pill.show_transcribing)
        self.sig_hide.connect(pill.hide_pill)

    # chamados pela thread do hotkey
    def press(self) -> None:
        with self.lock:
            if self.paused or self.recording or self.transcribing:
                return
            self.recording = True
            self.recorder.start()
            self.sig_listening.emit()

    def release(self) -> None:
        with self.lock:
            if not self.recording:
                return
            self.recording = False
            held = time.time() - self.recorder.started_at
            wav = self.recorder.stop()
            if held < MIN_HOLD or not wav:
                self.sig_hide.emit()
                self._rm(wav)
                return
            self.transcribing = True
            self._cancel = False
            self.sig_transcribing.emit()
            threading.Thread(target=self._process, args=(wav,), daemon=True).start()

    def cancel(self) -> None:
        with self.lock:
            if not self.transcribing:
                return
            self._cancel = True
            self.transcribing = False
            self.sig_hide.emit()

    def _process(self, wav: str) -> None:
        try:
            if wav_duration(wav) < 0.25:
                self.sig_hide.emit()
                return
            try:
                text = cloud.transcribe_cloud(wav)
            except Exception as exc:
                print(f"STT falhou: {exc}", flush=True)
                self.sig_hide.emit()
                return
            if self._cancel:
                return
            print(f"transcrito: {text!r}", flush=True)
            note = dump.parse(text) if text else None
            if note is not None:
                dump.save(note)
                self.sig_hide.emit()
                return
            if text and translate.parse(text):
                self.sig_transcribing.emit()
                text = translate.maybe_transform(text)
            self.sig_hide.emit()
            if text and not self._cancel:
                self.delivery.deliver(text)
        finally:
            with self.lock:
                self.transcribing = False
            self._rm(wav)

    @staticmethod
    def _rm(path) -> None:
        if path:
            try:
                os.unlink(path)
            except OSError:
                pass


def _tray_icon() -> QtGui.QIcon:
    """Ícone simples desenhado em runtime (mic verde) — sem asset externo."""
    pix = QtGui.QPixmap(64, 64)
    pix.fill(QtCore.Qt.transparent)
    p = QtGui.QPainter(pix)
    p.setRenderHint(QtGui.QPainter.Antialiasing)
    p.setBrush(QtGui.QColor("#9acd32"))
    p.setPen(QtCore.Qt.NoPen)
    p.drawRoundedRect(24, 10, 16, 28, 8, 8)          # corpo do mic
    p.setPen(QtGui.QPen(QtGui.QColor("#9acd32"), 4))
    p.setBrush(QtCore.Qt.NoBrush)
    p.drawArc(18, 20, 28, 28, 180 * 16, 180 * 16)     # arco
    p.drawLine(32, 48, 32, 56)                         # haste
    p.end()
    return QtGui.QIcon(pix)


def main() -> int:
    app = QtWidgets.QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    platform = base.get_platform()
    pill = Pill()
    controller = Controller(platform, pill)

    settings_win = SettingsWindow()

    # ── tray ──────────────────────────────────────────────────────────────────
    tray = QtWidgets.QSystemTrayIcon(_tray_icon())
    tray.setToolTip("mr-whisper")
    menu = QtWidgets.QMenu()

    act_settings = menu.addAction("Settings…")
    act_settings.triggered.connect(lambda: (settings_win.show(), settings_win.raise_(),
                                            settings_win.activateWindow()))
    act_pause = menu.addAction("Pause")
    act_pause.setCheckable(True)

    def toggle_pause(checked):
        controller.paused = checked
        act_pause.setText("Paused" if checked else "Pause")
    act_pause.toggled.connect(toggle_pause)

    menu.addSeparator()
    menu.addAction("Quit").triggered.connect(app.quit)
    tray.setContextMenu(menu)
    tray.show()

    # abre settings no 1º uso (sem chave configurada ainda)
    if not any(config.get(k) for k in ("GROQ_API_KEY", "OPENAI_API_KEY", "OPENROUTER_KEY")):
        settings_win.show()
        tray.showMessage("mr-whisper", "Add an API key in Settings to start.",
                         QtWidgets.QSystemTrayIcon.Information, 5000)
    else:
        print(f"transcrição na nuvem: {cloud._resolve_stt_provider()}", flush=True)

    # ── hotkey em thread ──────────────────────────────────────────────────────
    hotkey = platform.make_hotkey(controller.press, controller.release, controller.cancel)
    threading.Thread(target=hotkey.run, daemon=True).start()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
