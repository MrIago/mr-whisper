#!/usr/bin/env python3
"""Wizard de primeiro uso do mr-whisper.

Passo a passo bonito no 1º uso: boas-vindas, chave (Groq em destaque, grátis),
permissões por OS, e os comandos de voz. Emite `finished` ao concluir. Só a
chave é obrigatória; os outros passos são informativos.
"""
from __future__ import annotations

import sys
import threading

from PySide6 import QtCore, QtGui, QtWidgets

from core import config, cloud


class Wizard(QtWidgets.QWidget):
    finished = QtCore.Signal()
    _validated = QtCore.Signal(bool, str)

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Welcome to mr-whisper")
        self.setFixedSize(560, 520)
        self.setWindowFlags(QtCore.Qt.Window | QtCore.Qt.WindowStaysOnTopHint)
        self._validated.connect(self._on_validated)
        self._key_ok = bool(config.get("GROQ_API_KEY") or config.get("OPENAI_API_KEY")
                            or config.get("OPENROUTER_KEY"))
        self._build()

    # ── layout ────────────────────────────────────────────────────────────────
    def _build(self) -> None:
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        self.stack = QtWidgets.QStackedWidget()
        self.stack.addWidget(self._page_welcome())
        self.stack.addWidget(self._page_key())
        self.stack.addWidget(self._page_permissions())
        self.stack.addWidget(self._page_commands())
        root.addWidget(self.stack, 1)

        # rodapé: passos + botões
        foot = QtWidgets.QHBoxLayout()
        foot.setContentsMargins(24, 12, 24, 20)
        self.dots = QtWidgets.QLabel()
        self.dots.setStyleSheet("color:#666; font-size:18px;")
        foot.addWidget(self.dots)
        foot.addStretch(1)
        self.back_btn = QtWidgets.QPushButton("Back")
        self.back_btn.clicked.connect(self._back)
        foot.addWidget(self.back_btn)
        self.next_btn = QtWidgets.QPushButton("Next")
        self.next_btn.setDefault(True)
        self.next_btn.clicked.connect(self._next)
        foot.addWidget(self.next_btn)
        root.addLayout(foot)

        self.stack.currentChanged.connect(self._sync_footer)
        self._sync_footer()

    def _header(self, title: str, subtitle: str) -> QtWidgets.QVBoxLayout:
        v = QtWidgets.QVBoxLayout()
        v.setContentsMargins(40, 36, 40, 12)
        t = QtWidgets.QLabel(title)
        t.setStyleSheet("font-size:24px; font-weight:800;")
        v.addWidget(t)
        s = QtWidgets.QLabel(subtitle)
        s.setWordWrap(True)
        s.setStyleSheet("color:#9aa; font-size:14px;")
        v.addWidget(s)
        return v

    # ── páginas ───────────────────────────────────────────────────────────────
    def _page_welcome(self) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget()
        v = self._header("Welcome to mr-whisper",
                         "Voice dictation anywhere. Hold a hotkey, speak, release, "
                         "and your words are typed where your cursor is.")
        body = QtWidgets.QLabel(
            "The whole app is one gesture:\n\n"
            "Hold the hotkey (Ctrl+Alt+Space, or Option+Space on Mac).\n"
            "Speak while you hold it.\n"
            "Release, and the text lands where your cursor is.\n\n"
            "It lives in the tray. This short setup gets you there.")
        body.setStyleSheet("font-size:14px; line-height:1.5;")
        body.setWordWrap(True)
        v.addWidget(body)
        v.addStretch(1)
        w = QtWidgets.QWidget(); w.setLayout(v)
        return w

    def _page_key(self) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget()
        v = self._header("Add a transcription key",
                         "mr-whisper transcribes in the cloud. Groq has a generous "
                         "free tier and is the easiest to start with.")
        # provider (Groq default; avançado esconde os outros)
        prow = QtWidgets.QHBoxLayout()
        prow.addWidget(QtWidgets.QLabel("Provider:"))
        self.provider = QtWidgets.QComboBox()
        self.provider.addItem("Groq  ·  free tier, recommended", "groq")
        self.provider.addItem("OpenAI  ·  paid", "openai")
        self.provider.addItem("OpenRouter  ·  pay-per-use", "openrouter")
        self.provider.currentIndexChanged.connect(self._on_provider)
        prow.addWidget(self.provider, 1)
        v.addLayout(prow)

        self.get_link = QtWidgets.QLabel()
        self.get_link.setOpenExternalLinks(True)
        self.get_link.setStyleSheet("color:#4a9;")
        v.addWidget(self.get_link)

        krow = QtWidgets.QHBoxLayout()
        self.key_edit = QtWidgets.QLineEdit()
        self.key_edit.setPlaceholderText("paste your API key here")
        self.key_edit.setEchoMode(QtWidgets.QLineEdit.Password)
        krow.addWidget(self.key_edit, 1)
        self.validate_btn = QtWidgets.QPushButton("Validate")
        self.validate_btn.clicked.connect(self._validate)
        krow.addWidget(self.validate_btn)
        v.addLayout(krow)

        self.key_status = QtWidgets.QLabel("✓ a key is already set" if self._key_ok else "")
        self.key_status.setStyleSheet("color:#4a9;" if self._key_ok else "color:#888;")
        v.addWidget(self.key_status)
        v.addStretch(1)
        self._on_provider()
        w = QtWidgets.QWidget(); w.setLayout(v)
        return w

    def _page_permissions(self) -> QtWidgets.QWidget:
        v = self._header("Grant permissions",
                         "mr-whisper needs OS permission to hear you and to type "
                         "for you. Grant these once, then relaunch.")
        if sys.platform == "darwin":
            txt = ("macOS · System Settings > Privacy & Security:\n\n"
                   "• Microphone, so it can hear you\n"
                   "• Accessibility, so it can send the paste\n"
                   "• Input Monitoring, so it can read the hotkey\n\n"
                   "Add mr-whisper to each list, then quit and reopen the app.")
        elif sys.platform == "win32":
            txt = ("Windows:\n\n"
                   "• Allow Microphone access in Settings > Privacy > Microphone.\n"
                   "That's it. The hotkey and paste work without extra setup.")
        else:
            txt = ("Linux:\n\n"
                   "• Be in the 'input' group for the hotkey:\n"
                   "    sudo usermod -aG input $USER   (then log out/in)\n"
                   "• On Wayland, run run/setup-linux-wayland.sh once so auto-paste "
                   "works (otherwise the text is copied and you press Ctrl+V).")
        body = QtWidgets.QLabel(txt)
        body.setWordWrap(True)
        body.setStyleSheet("font-size:14px; line-height:1.5;")
        v.addWidget(body)
        v.addStretch(1)
        w = QtWidgets.QWidget(); w.setLayout(v)
        return w

    def _page_commands(self) -> QtWidgets.QWidget:
        v = self._header("Voice commands",
                         "Say a keyword at the start of your speech to transform it. "
                         "Everything before the keyword is context and isn't pasted.")
        body = QtWidgets.QLabel(
            '• "auto translate spanish, good morning"  →  translates it\n'
            '• "auto context, ..."  →  rewrites for the right tone\n'
            '• "auto adjust, ..."  →  cleans filler and fixes punctuation\n'
            '• "new dump, ..."  →  saves a note instead of pasting\n\n'
            "Change the hotkey and paste behavior anytime in Settings, "
            "from the tray menu. That's the whole setup.")
        body.setWordWrap(True)
        body.setStyleSheet("font-size:14px; line-height:1.5;")
        v.addWidget(body)
        v.addStretch(1)
        w = QtWidgets.QWidget(); w.setLayout(v)
        return w

    # ── navegação ───────────────────────────────────────────────────────────────
    def _sync_footer(self) -> None:
        i = self.stack.currentIndex()
        n = self.stack.count()
        self.dots.setText("  ".join("●" if j == i else "○" for j in range(n)))
        self.back_btn.setVisible(i > 0)
        self.next_btn.setText("Finish" if i == n - 1 else "Next")

    def _back(self) -> None:
        self.stack.setCurrentIndex(max(0, self.stack.currentIndex() - 1))

    def _next(self) -> None:
        i = self.stack.currentIndex()
        # no passo da chave, exige uma chave válida pra avançar
        if i == 1 and not self._key_ok:
            self.key_status.setText("Add and validate a key to continue "
                                    "(or paste one you already have).")
            self.key_status.setStyleSheet("color:#d66;")
            return
        if i == self.stack.count() - 1:
            self.finished.emit()
            self.close()
            return
        self.stack.setCurrentIndex(i + 1)

    # ── validação da chave ──────────────────────────────────────────────────────
    def _providers(self):
        return {
            "groq": ("GROQ_API_KEY", "https://console.groq.com/keys", cloud.validate_groq),
            "openai": ("OPENAI_API_KEY", "https://platform.openai.com/api-keys", cloud.validate_openai),
            "openrouter": ("OPENROUTER_KEY", "https://openrouter.ai/keys", cloud.validate_openrouter),
        }

    def _on_provider(self) -> None:
        pid = self.provider.currentData()
        _key, url, _v = self._providers()[pid]
        self.get_link.setText(f'Get a free key: <a href="{url}">{url}</a>')
        existing = config.get(self._providers()[pid][0])
        self.key_edit.setText(existing or "")

    def _validate(self) -> None:
        key = self.key_edit.text().strip()
        if not key:
            self.key_status.setText("paste a key first")
            self.key_status.setStyleSheet("color:#d66;")
            return
        self.validate_btn.setEnabled(False)
        self.key_status.setText("validating…")
        self.key_status.setStyleSheet("color:#888;")
        pid = self.provider.currentData()
        validate = self._providers()[pid][2]

        def work():
            ok, why = validate(key)
            self._validated.emit(ok, why)
        threading.Thread(target=work, daemon=True).start()

    @QtCore.Slot(bool, str)
    def _on_validated(self, ok: bool, why: str) -> None:
        self.validate_btn.setEnabled(True)
        pid = self.provider.currentData()
        key_name = self._providers()[pid][0]
        if ok:
            config.set_values({key_name: self.key_edit.text().strip(),
                               "MRWHISPER_STT_PROVIDER": pid})
            self._key_ok = True
            self.key_status.setText("✓ valid and saved")
            self.key_status.setStyleSheet("color:#4a9;")
        else:
            self.key_status.setText(f"✗ {why}")
            self.key_status.setStyleSheet("color:#d66;")
