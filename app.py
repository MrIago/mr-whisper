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
from ui.tray import TrayIcon

HERE = Path(__file__).parent
MIN_HOLD = 0.3


def _friendly_error(exc: Exception) -> str:
    """Traduz erros técnicos de STT em mensagem curta e humana."""
    s = str(exc).lower()
    if "429" in s or "rate" in s or "limit" in s or "quota" in s:
        return "Daily free limit reached — try later or add another provider in Settings"
    if "401" in s or "invalid" in s or "auth" in s or "key" in s:
        return "Invalid API key — check it in Settings"
    if "timeout" in s or "network" in s or "connection" in s or "resolve" in s:
        return "No internet connection"
    return "Transcription failed — check Settings"


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
    sig_tray_state = QtCore.Signal(str)   # idle | recording | transcribing
    sig_notify = QtCore.Signal(str, str)  # (title, message) → balão do tray

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

    def _refresh_tray(self) -> None:
        """Emite o estado do tray DERIVADO das flags atuais — nunca emissões
        soltas. Elimina a race que travava o spinner (a ordem de chegada de
        'transcribing'/'idle' entre threads não importa: o estado é o fato)."""
        with self.lock:
            if self.paused:
                state = "paused"
            elif self.recording:
                state = "recording"
            elif self.transcribing:
                state = "transcribing"
            else:
                state = "idle"
        self.sig_tray_state.emit(state)

    # chamados pela thread do hotkey
    def press(self) -> None:
        with self.lock:
            if self.paused or self.recording or self.transcribing:
                return
            self.recording = True
        # start() fora do lock (pode falhar/bloquear). Try/except evita o
        # estado-morto: se o mic falha, reseta recording e avisa.
        try:
            self.recorder.start()
        except Exception as exc:
            with self.lock:
                self.recording = False
            self.sig_hide.emit()
            self._refresh_tray()
            self.sig_notify.emit("mr-whisper", f"Microphone error: {exc}")
            return
        self.sig_listening.emit()
        self._refresh_tray()

    def release(self) -> None:
        with self.lock:
            if not self.recording:
                return
            self.recording = False
            started_at = self.recorder.started_at
        # stop() FORA do lock: proc.wait(timeout=5) bloquearia o teclado global.
        held = time.time() - started_at
        try:
            wav = self.recorder.stop()
        except Exception as exc:
            self.sig_hide.emit()
            self._refresh_tray()
            self.sig_notify.emit("mr-whisper", f"Recording error: {exc}")
            return
        if held < MIN_HOLD or not wav:
            self.sig_hide.emit()
            self._refresh_tray()
            self._rm(wav)
            return
        with self.lock:
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
        self._refresh_tray()

    def _process(self, wav: str) -> None:
        self._refresh_tray()
        try:
            if wav_duration(wav) < 0.25:
                self.sig_hide.emit()
                return
            try:
                text = cloud.transcribe_cloud(wav)
            except Exception as exc:
                self.sig_hide.emit()
                self.sig_notify.emit("mr-whisper", _friendly_error(exc))
                print(f"STT falhou: {exc}", flush=True)
                return
            if self._cancel:
                return
            print(f"transcrito: {text!r}", flush=True)
            note = dump.parse(text) if text else None
            if note is not None:
                ok = dump.save(note)
                self.sig_hide.emit()
                self.sig_notify.emit("mr-whisper",
                                     "Note saved 📝" if ok else "Could not write your notes file")
                return
            if text and translate.parse(text):
                self.sig_transcribing.emit()
                text = translate.maybe_transform(text)
            self.sig_hide.emit()
            # checa cancelamento SOB LOCK, imediatamente antes de colar — evita
            # colar um texto depois de o usuário ter apertado ESC.
            with self.lock:
                if self._cancel or not text:
                    return
            auto = (config.get("MRWHISPER_AUTO_PASTE", "1") or "1") != "0"
            shortcut = config.get("MRWHISPER_PASTE_SHORTCUT", "ctrl+v") or "ctrl+v"
            pasted = self.delivery.deliver(text, paste=auto, shortcut=shortcut)
            print(f"entregue ({len(text)} chars, paste={auto}→{pasted}, {shortcut})", flush=True)
            if not pasted:
                # auto-paste desligado, ou o compositor (Wayland) bloqueou a
                # injeção de teclas → o texto está no clipboard.
                self.sig_notify.emit("mr-whisper", f"Copied — press {shortcut.replace('+', '+').title()} to paste")
        finally:
            with self.lock:
                self.transcribing = False
            self._refresh_tray()
            self._rm(wav)

    @staticmethod
    def _rm(path) -> None:
        if path:
            try:
                os.unlink(path)
            except OSError:
                pass


def main() -> int:
    app = QtWidgets.QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    platform = base.get_platform()
    pill = Pill()
    controller = Controller(platform, pill)

    settings_win = SettingsWindow()

    # ── tray ──────────────────────────────────────────────────────────────────
    tray = TrayIcon()
    tray.setToolTip("mr-whisper")
    controller.sig_tray_state.connect(tray.set_state)
    controller.sig_notify.connect(
        lambda title, msg: tray.showMessage(title, msg,
                                            QtWidgets.QSystemTrayIcon.Information, 4000))
    menu = QtWidgets.QMenu()

    act_settings = menu.addAction("Settings…")
    act_settings.triggered.connect(lambda: (settings_win.show(), settings_win.raise_(),
                                            settings_win.activateWindow()))
    act_pause = menu.addAction("Pause")
    act_pause.setCheckable(True)

    def toggle_pause(checked):
        controller.paused = checked
        act_pause.setText("Paused" if checked else "Pause")
        tray.set_state("paused" if checked else "idle")
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
