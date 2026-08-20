#!/usr/bin/env python3
"""Janela de configuração (BYOK) do mr-whisper — sem terminal.

Escolhe o provider de transcrição, cola e VALIDA a chave ao vivo, define o
backend dos comandos de LLM e o arquivo de notas. Salva via core.config.
100% BYOK: nenhuma chave embutida; ensina a pegar a sua (grátis no Groq).
"""
from __future__ import annotations

import threading

from PySide6 import QtCore, QtWidgets

from core import config, cloud

PROVIDERS = {
    "groq": {
        "label": "Groq  ·  free tier ~8h/day  (recommended)",
        "key": "GROQ_API_KEY",
        "url": "https://console.groq.com/keys",
        "validate": cloud.validate_groq,
    },
    "openai": {
        "label": "OpenAI  ·  paid",
        "key": "OPENAI_API_KEY",
        "url": "https://platform.openai.com/api-keys",
        "validate": cloud.validate_openai,
    },
    "openrouter": {
        "label": "OpenRouter  ·  pay-per-use",
        "key": "OPENROUTER_KEY",
        "url": "https://openrouter.ai/keys",
        "validate": cloud.validate_openrouter,
    },
}


class SettingsWindow(QtWidgets.QWidget):
    # resultado da validação (vem de thread) → UI
    _validated = QtCore.Signal(bool, str)

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("mr-whisper · Settings")
        self.setMinimumWidth(460)
        self._validated.connect(self._on_validated)
        self._build()
        self._load()

    def _build(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        title = QtWidgets.QLabel("Transcription")
        title.setStyleSheet("font-size:16px; font-weight:600;")
        layout.addWidget(title)

        # provider
        row = QtWidgets.QHBoxLayout()
        row.addWidget(QtWidgets.QLabel("Provider:"))
        self.provider = QtWidgets.QComboBox()
        for pid, meta in PROVIDERS.items():
            self.provider.addItem(meta["label"], pid)
        self.provider.currentIndexChanged.connect(self._on_provider_change)
        row.addWidget(self.provider, 1)
        layout.addLayout(row)

        # link pra pegar a chave
        self.get_key_link = QtWidgets.QLabel()
        self.get_key_link.setOpenExternalLinks(True)
        self.get_key_link.setStyleSheet("color:#4a9;")
        layout.addWidget(self.get_key_link)

        # campo da chave
        krow = QtWidgets.QHBoxLayout()
        self.key_edit = QtWidgets.QLineEdit()
        self.key_edit.setPlaceholderText("paste your API key…")
        self.key_edit.setEchoMode(QtWidgets.QLineEdit.Password)
        krow.addWidget(self.key_edit, 1)
        self.validate_btn = QtWidgets.QPushButton("Validate & Save")
        self.validate_btn.clicked.connect(self._on_validate)
        krow.addWidget(self.validate_btn)
        layout.addLayout(krow)

        self.status = QtWidgets.QLabel("")
        layout.addWidget(self.status)

        # idioma da transcrição (trava se você fala sempre o mesmo)
        lgrow = QtWidgets.QHBoxLayout()
        lgrow.addWidget(QtWidgets.QLabel("Language:"))
        self.lang = QtWidgets.QComboBox()
        self.lang.addItem("Auto-detect", "")
        for code, name in (("pt", "Portuguese"), ("en", "English"), ("es", "Spanish"),
                           ("fr", "French"), ("de", "German"), ("it", "Italian"),
                           ("ja", "Japanese"), ("zh", "Chinese")):
            self.lang.addItem(name, code)
        self.lang.currentIndexChanged.connect(self._save_lang)
        lgrow.addWidget(self.lang, 1)
        layout.addLayout(lgrow)
        lang_hint = QtWidgets.QLabel("Lock it if you always dictate one language "
                                     "(Auto sometimes guesses wrong on short clips).")
        lang_hint.setStyleSheet("color:#888;")
        lang_hint.setWordWrap(True)
        layout.addWidget(lang_hint)

        layout.addSpacing(8)
        cmds = QtWidgets.QLabel("Voice commands")
        cmds.setStyleSheet("font-size:16px; font-weight:600;")
        layout.addWidget(cmds)
        info = QtWidgets.QLabel(
            'Say a command at the start of your dictation:\n'
            '  • "auto translate {language} …"  — translate + localize\n'
            '  • "auto context …"  — rewrite for tone (same language)\n'
            '  • "auto adjust …"  — clean filler, fix punctuation\n'
            '  • "new dump …"  — append to your notes file instead of pasting'
        )
        info.setStyleSheet("color:#888;")
        layout.addWidget(info)

        # backend LLM
        lrow = QtWidgets.QHBoxLayout()
        lrow.addWidget(QtWidgets.QLabel("LLM backend:"))
        self.llm = QtWidgets.QComboBox()
        self.llm.addItem("Groq  ·  llama-3.3-70b", "groq")
        self.llm.addItem("OpenRouter  ·  Gemini Flash", "openrouter")
        self.llm.currentIndexChanged.connect(self._save_llm)
        lrow.addWidget(self.llm, 1)
        layout.addLayout(lrow)

        # arquivo de dump
        drow = QtWidgets.QHBoxLayout()
        drow.addWidget(QtWidgets.QLabel("Notes file:"))
        self.dump_edit = QtWidgets.QLineEdit()
        self.dump_edit.editingFinished.connect(self._save_dump)
        drow.addWidget(self.dump_edit, 1)
        layout.addLayout(drow)

        # ── Pasting ──────────────────────────────────────────────────────────
        layout.addSpacing(8)
        paste_title = QtWidgets.QLabel("Pasting")
        paste_title.setStyleSheet("font-size:16px; font-weight:600;")
        layout.addWidget(paste_title)

        self.auto_paste = QtWidgets.QCheckBox("Paste automatically after transcribing")
        self.auto_paste.toggled.connect(self._save_paste)
        layout.addWidget(self.auto_paste)

        self.paste_hint = QtWidgets.QLabel("")
        self.paste_hint.setStyleSheet("color:#888;")
        layout.addWidget(self.paste_hint)

        srow = QtWidgets.QHBoxLayout()
        srow.addWidget(QtWidgets.QLabel("Paste shortcut:"))
        self.paste_shortcut = QtWidgets.QComboBox()
        self.paste_shortcut.addItem("Ctrl+V  (most apps & terminals)", "ctrl+v")
        self.paste_shortcut.addItem("Ctrl+Shift+V  (old terminals)", "ctrl+shift+v")
        self.paste_shortcut.currentIndexChanged.connect(self._save_paste)
        srow.addWidget(self.paste_shortcut, 1)
        layout.addLayout(srow)

        layout.addSpacing(8)
        hint = QtWidgets.QLabel("Hold  Ctrl + Alt + Space  to dictate. Esc cancels.")
        hint.setStyleSheet("color:#888;")
        layout.addWidget(hint)

    # ── estado ────────────────────────────────────────────────────────────────
    def _current_provider(self) -> str:
        return self.provider.currentData()

    def _load(self) -> None:
        self._loading = True
        prov = config.get("MRWHISPER_STT_PROVIDER", "groq") or "groq"
        idx = max(0, self.provider.findData(prov))
        self.provider.setCurrentIndex(idx)
        self._on_provider_change()
        llm = config.get("MRWHISPER_TRANSLATE", "groq") or "groq"
        self.llm.setCurrentIndex(max(0, self.llm.findData(llm)))
        self.dump_edit.setText(config.get("MRWHISPER_DUMP_FILE", "~/Documentos/Notas/dump.md"))
        self.lang.setCurrentIndex(max(0, self.lang.findData(config.get("MRWHISPER_LANG", "") or "")))
        # pasting
        self.auto_paste.setChecked((config.get("MRWHISPER_AUTO_PASTE", "1") or "1") != "0")
        sc = config.get("MRWHISPER_PASTE_SHORTCUT", "ctrl+v") or "ctrl+v"
        self.paste_shortcut.setCurrentIndex(max(0, self.paste_shortcut.findData(sc)))
        self._loading = False
        self._update_paste_hint()

    def _on_provider_change(self) -> None:
        meta = PROVIDERS[self._current_provider()]
        self.get_key_link.setText(f'Get a key: <a href="{meta["url"]}">{meta["url"]}</a>')
        has = config.get(meta["key"])
        self.key_edit.setText(has or "")
        self.status.setText("✓ key saved" if has else "no key yet")
        self.status.setStyleSheet("color:#4a9;" if has else "color:#888;")

    def _on_validate(self) -> None:
        key = self.key_edit.text().strip()
        if not key:
            self._set_status(False, "paste a key first")
            return
        self.validate_btn.setEnabled(False)
        self.status.setText("validating…")
        self.status.setStyleSheet("color:#888;")
        meta = PROVIDERS[self._current_provider()]

        def work():
            ok, why = meta["validate"](key)
            self._validated.emit(ok, why)

        threading.Thread(target=work, daemon=True).start()

    @QtCore.Slot(bool, str)
    def _on_validated(self, ok: bool, why: str) -> None:
        self.validate_btn.setEnabled(True)
        prov = self._current_provider()
        meta = PROVIDERS[prov]
        if ok:
            config.set_values({meta["key"]: self.key_edit.text().strip(),
                               "MRWHISPER_STT_PROVIDER": prov})
            self._set_status(True, "✓ valid — saved")
        else:
            self._set_status(False, f"✗ {why}")

    def _set_status(self, ok: bool, msg: str) -> None:
        self.status.setText(msg)
        self.status.setStyleSheet("color:#4a9;" if ok else "color:#d66;")

    def _save_llm(self) -> None:
        if getattr(self, "_loading", False):
            return
        config.set_values({"MRWHISPER_TRANSLATE": self.llm.currentData()})

    def _save_lang(self) -> None:
        if getattr(self, "_loading", False):
            return
        config.set_values({"MRWHISPER_LANG": self.lang.currentData()})

    def _save_dump(self) -> None:
        v = self.dump_edit.text().strip()
        if v:
            config.set_values({"MRWHISPER_DUMP_FILE": v})

    def _save_paste(self) -> None:
        if getattr(self, "_loading", False):
            return
        config.set_values({
            "MRWHISPER_AUTO_PASTE": "1" if self.auto_paste.isChecked() else "0",
            "MRWHISPER_PASTE_SHORTCUT": self.paste_shortcut.currentData(),
        })
        self._update_paste_hint()

    def _update_paste_hint(self) -> None:
        if self.auto_paste.isChecked():
            self.paste_hint.setText("")
            self.paste_shortcut.setEnabled(True)
        else:
            self.paste_hint.setText("Off — the text is copied; paste it yourself when ready.")
            self.paste_shortcut.setEnabled(False)
