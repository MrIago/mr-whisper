#!/usr/bin/env python3
"""mr-whisper, app de bandeja cross-platform (Linux/macOS/Windows).

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

from core import config, cloud, translate
from platforms import base
from ui.pill import Pill
from ui.settings import SettingsWindow
from ui.tray import TrayIcon
from ui.commands_window import CommandsWindow
from ui.notes_window import NotesWindow

HERE = Path(__file__).parent
MIN_HOLD = 0.3


def _friendly_error(exc: Exception) -> str:
    """Traduz erros técnicos de STT em mensagem curta e humana."""
    s = str(exc).lower()
    if "429" in s or "rate" in s or "limit" in s or "quota" in s:
        return "Daily free limit reached. Try later, or add another provider in Settings"
    if "401" in s or "invalid" in s or "auth" in s or "key" in s:
        return "Invalid API key. Check it in Settings"
    if "timeout" in s or "network" in s or "connection" in s or "resolve" in s:
        return "No internet connection"
    return "Transcription failed. Check Settings"


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
    sig_history = QtCore.Signal()         # nova transcrição entrou no histórico

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
        self.history: list[str] = []  # últimas transcrições (mais recente no fim)

        self.sig_listening.connect(pill.show_listening)
        self.sig_level.connect(pill.set_level)
        self.sig_transcribing.connect(pill.show_transcribing)
        self.sig_hide.connect(pill.hide_pill)

    def compute_state(self) -> str:
        """O estado do tray derivado das flags ATUAIS. Lido pelo slot na UI no
        momento de renderizar, nunca um valor pré-computado que possa chegar
        stale (era isso que travava o spinner)."""
        with self.lock:
            if self.paused:
                return "paused"
            if self.recording:
                return "recording"
            if self.transcribing:
                return "transcribing"
            return "idle"

    def _refresh_tray(self) -> None:
        # dispara o recompute na UI thread (o valor é lido lá, sempre fresco).
        self.sig_tray_state.emit("")

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
            # comando de voz? (translate/rewrite/dump, built-in ou customizado)
            is_dump = translate.is_dump(text) if text else False
            if text and translate.parse(text):
                self.sig_transcribing.emit()
                text = translate.maybe_transform(text)
            self.sig_hide.emit()
            if is_dump:
                self.sig_notify.emit("mr-whisper", "Note saved 📝")
                return
            # checa cancelamento SOB LOCK, imediatamente antes de colar, evita
            # colar um texto depois de o usuário ter apertado ESC.
            with self.lock:
                if self._cancel or not text:
                    return
            auto = (config.get("MRWHISPER_AUTO_PASTE", "1") or "1") != "0"
            shortcut = config.get("MRWHISPER_PASTE_SHORTCUT", "ctrl+v") or "ctrl+v"
            pasted = self.delivery.deliver(text, paste=auto, shortcut=shortcut)
            print(f"entregue ({len(text)} chars, paste={auto}→{pasted}, {shortcut})", flush=True)
            with self.lock:
                self.history.append(text)
                self.history[:] = self.history[-10:]  # guarda as últimas 10
            self.sig_history.emit()
            if not pasted:
                # auto-paste desligado, ou o compositor (Wayland) bloqueou a
                # injeção de teclas → o texto está no clipboard.
                self.sig_notify.emit("mr-whisper", f"Copied. Press {shortcut.replace(chr(43), chr(43)).title()} to paste")
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


def _check_platform_setup(platform, tray) -> None:
    """No 1º uso, detecta e avisa pré-requisitos de plataforma que, se faltando,
    fazem o app parecer 'quebrado' (nada acontece ao ditar)."""
    warn = None
    if platform.name == "linux":
        # sem acesso a teclado (grupo input) → hold-to-talk não dispara
        try:
            from platforms import linux as _lx
            if not _lx._find_keyboards():
                warn = ("Keyboard access needed: add yourself to the 'input' group "
                        "(sudo usermod -aG input $USER) and log out/in.")
            elif _lx._is_wayland():
                import os
                sock = os.path.join(os.environ.get("XDG_RUNTIME_DIR", ""), ".ydotool_socket")
                if not _lx._have("ydotool") or not os.path.exists(sock):
                    warn = ("On Wayland, auto-paste needs a one-time setup: run "
                            "run/setup-linux-wayland.sh. Until then it copies to the clipboard.")
        except Exception:
            pass
    # macOS: as permissões (Accessibility/Input Monitoring/Mic) o SO pede sozinho
    # na 1ª tentativa; se pynput falhar silencioso, o balão de erro do press()/mic
    # já orienta. (Não há como checar permissão sem tentar.)
    if warn:
        tray.showMessage("mr-whisper setup", warn,
                         QtWidgets.QSystemTrayIcon.Warning, 10000)


def main() -> int:
    # No Linux, força o Qt a usar XWayland (xcb) em vez de Wayland nativo: sob
    # Wayland nativo o compositor IGNORA move() da janela, então a pill flutuante
    # ia pro canto e "descia" a cada uso. Via xcb o posicionamento funciona.
    # (Respeita QT_QPA_PLATFORM se o usuário já tiver setado.)
    if sys.platform.startswith("linux") and not os.environ.get("QT_QPA_PLATFORM"):
        os.environ["QT_QPA_PLATFORM"] = "xcb"

    app = QtWidgets.QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    platform = base.get_platform()
    pill = Pill()
    controller = Controller(platform, pill)

    settings_win = SettingsWindow()
    commands_win = CommandsWindow()
    notes_win = NotesWindow()

    # ── tray ──────────────────────────────────────────────────────────────────
    tray = TrayIcon()
    tray.setToolTip("mr-whisper")
    # o estado é SEMPRE recomputado do controller na UI thread, nunca um valor
    # que possa ter chegado fora de ordem (fixa o spinner travado).
    controller.sig_tray_state.connect(lambda _: tray.set_state(controller.compute_state()))
    controller.sig_notify.connect(
        lambda title, msg: tray.showMessage(title, msg,
                                            QtWidgets.QSystemTrayIcon.Information, 4000))
    menu = QtWidgets.QMenu()

    # dica de uso (hold-to-talk) sempre visível no topo
    hint = menu.addAction("Hold Ctrl+Alt+Space to dictate")
    hint.setEnabled(False)

    # histórico das últimas transcrições, clicar recopia pro clipboard
    hist_menu = menu.addMenu("Recent")

    def rebuild_history():
        hist_menu.clear()
        items = list(reversed(controller.history))
        if not items:
            a = hist_menu.addAction("(nothing yet)")
            a.setEnabled(False)
            return
        for txt in items:
            label = (txt[:50] + "…") if len(txt) > 50 else txt
            act = hist_menu.addAction(label.replace("\n", " "))
            # clicar recopia pro clipboard (paste=False só copia, nos 3 OS)
            act.triggered.connect(
                lambda _=False, t=txt: controller.delivery.deliver(t, paste=False))
    controller.sig_history.connect(rebuild_history)
    rebuild_history()

    # tutorial dos comandos de voz
    menu.addAction("Voice commands…").triggered.connect(
        lambda: (commands_win.show(), commands_win.raise_(), commands_win.activateWindow()))

    # notas salvas pelo comando "new dump"
    menu.addAction("Notes…").triggered.connect(
        lambda: (notes_win.show(), notes_win.raise_(), notes_win.activateWindow()))

    menu.addSeparator()
    act_settings = menu.addAction("Settings…")
    act_settings.triggered.connect(lambda: (settings_win.show(), settings_win.raise_(),
                                            settings_win.activateWindow()))
    act_pause = menu.addAction("Pause")
    act_pause.setCheckable(True)

    def toggle_pause(checked):
        controller.paused = checked
        act_pause.setText("Paused" if checked else "Pause")
        tray.set_state(controller.compute_state())
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

    # aviso de setup por plataforma (permissões / Wayland) no 1º uso
    _check_platform_setup(platform, tray)

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
