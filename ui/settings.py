#!/usr/bin/env python3
"""Janela de configuração (BYOK) do mr-whisper, sem terminal.

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


# mapa: nomes de modificador do parser (core.config.hotkey_combo espera
# ctrl/alt/shift/cmd/super) por OS. No Mac, Alt = Option e Meta = Command.
def _mod_names() -> dict:
    import sys
    if sys.platform == "darwin":
        # rótulos amigáveis do Mac
        return {"ctrl": "Control", "alt": "Option", "shift": "Shift",
                "cmd": "Command", "super": "Command"}
    return {"ctrl": "Ctrl", "alt": "Alt", "shift": "Shift",
            "cmd": "Cmd", "super": "Super"}


class _HotkeyCapture(QtWidgets.QPushButton):
    """Botão que captura um atalho ao vivo: clica, segura as teclas, elas
    aparecem, e emite o combo (ex: 'ctrl+alt+space'). Só aceita combo com ao
    menos um modificador + uma tecla comum (o mesmo que o parser exige)."""
    captured = QtCore.Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._combo = ""
        self._capturing = False
        self._mods: set[str] = set()
        self._key = ""
        self.setCheckable(True)
        self.clicked.connect(self._toggle)
        self.setFocusPolicy(QtCore.Qt.StrongFocus)
        self._render()

    # texto salvo → mostrado
    def set_combo(self, combo: str) -> None:
        self._combo = (combo or "").lower()
        self._render()

    def _label_for(self, combo: str) -> str:
        if not combo:
            return "not set"
        names = _mod_names()
        parts = [p for p in combo.split("+") if p]
        out = []
        for p in parts:
            if p in names:
                out.append(names[p])
            else:
                out.append(p.capitalize() if len(p) > 1 else p.upper())
        return " + ".join(out)

    def _render(self) -> None:
        if self._capturing:
            live = self._live_combo()
            self.setText(f"{self._label_for(live)}   (press keys, Esc to cancel)"
                         if live else "press the keys   (Esc to cancel)")
            self.setStyleSheet("text-align:left; padding:6px; color:#4a9; "
                               "border:1px solid #4a9;")
        else:
            self.setText(f"{self._label_for(self._combo)}    (click to change)")
            self.setStyleSheet("text-align:left; padding:6px;")

    def _toggle(self) -> None:
        self._capturing = self.isChecked()
        self._mods.clear()
        self._key = ""
        self._render()
        if self._capturing:
            self.grabKeyboard()
        else:
            self.releaseKeyboard()

    # ── captura ──────────────────────────────────────────────────────────────
    _QT_MOD = {
        QtCore.Qt.Key_Control: "ctrl",
        QtCore.Qt.Key_Alt: "alt",
        QtCore.Qt.Key_AltGr: "alt",
        QtCore.Qt.Key_Shift: "shift",
        QtCore.Qt.Key_Meta: "cmd",
    }
    # teclas comuns cujo nome o parser/plataformas reconhecem
    _QT_KEY = {
        QtCore.Qt.Key_Space: "space",
        QtCore.Qt.Key_Return: "enter",
        QtCore.Qt.Key_Enter: "enter",
        QtCore.Qt.Key_Tab: "tab",
        QtCore.Qt.Key_Backspace: "backspace",
        QtCore.Qt.Key_CapsLock: "capslock",
    }

    def _key_name(self, ev) -> str | None:
        k = ev.key()
        if k in self._QT_MOD:
            return None
        if k in self._QT_KEY:
            return self._QT_KEY[k]
        # letras/números: usa o texto
        t = ev.text().strip().lower()
        if t and t.isprintable() and len(t) == 1 and t.isalnum():
            return t
        # F1..F12
        if QtCore.Qt.Key_F1 <= k <= QtCore.Qt.Key_F12:
            return f"f{k - QtCore.Qt.Key_F1 + 1}"
        return None

    def _live_combo(self) -> str:
        mods = "+".join(m for m in ("ctrl", "alt", "shift", "cmd", "super")
                        if m in self._mods)
        if self._key:
            return f"{mods}+{self._key}" if mods else self._key
        return mods

    def keyPressEvent(self, ev) -> None:
        if not self._capturing:
            return super().keyPressEvent(ev)
        if ev.key() == QtCore.Qt.Key_Escape:
            self.setChecked(False)
            self._toggle()
            return
        if ev.key() in self._QT_MOD:
            self._mods.add(self._QT_MOD[ev.key()])
            self._render()
            return
        name = self._key_name(ev)
        if name:
            self._key = name
            # combo completo? precisa de ao menos 1 modificador + tecla comum.
            if self._mods:
                combo = self._live_combo()
                self._combo = combo
                self._capturing = False
                self.setChecked(False)
                self.releaseKeyboard()
                self._render()
                self.captured.emit(combo)
            else:
                # sem modificador ainda: mostra, mas não salva (parser recusaria)
                self._render()
        ev.accept()

    def keyReleaseEvent(self, ev) -> None:
        if not self._capturing:
            return super().keyReleaseEvent(ev)
        if ev.key() in self._QT_MOD and not ev.isAutoRepeat():
            self._mods.discard(self._QT_MOD[ev.key()])
            self._render()
        ev.accept()


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
        self.key_edit.setPlaceholderText("paste your API key")
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
            "Say a keyword at the start of your speech to transform it (translate, "
            "rewrite, save a note). See them all in the tray menu, under "
            "\"Voice commands\"."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color:#888;")
        layout.addWidget(info)

        # backend LLM (motor dos comandos de voz)
        lrow = QtWidgets.QHBoxLayout()
        lrow.addWidget(QtWidgets.QLabel("LLM backend:"))
        self.llm = QtWidgets.QComboBox()
        self.llm.addItem("Groq (gpt-oss-120b)", "groq")
        self.llm.addItem("OpenRouter (Gemini Flash)", "openrouter")
        self.llm.currentIndexChanged.connect(self._save_llm)
        lrow.addWidget(self.llm, 1)
        layout.addLayout(lrow)

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

        # ── Hotkey ────────────────────────────────────────────────────────────
        layout.addSpacing(8)
        hk_title = QtWidgets.QLabel("Hotkey")
        hk_title.setStyleSheet("font-size:16px; font-weight:600;")
        layout.addWidget(hk_title)

        hkrow = QtWidgets.QHBoxLayout()
        hkrow.addWidget(QtWidgets.QLabel("Hold to dictate:"))
        # capturador: clica, aperta as teclas, elas aparecem, e salva.
        self.hotkey = _HotkeyCapture()
        self.hotkey.captured.connect(self._save_hotkey)
        hkrow.addWidget(self.hotkey, 1)
        layout.addLayout(hkrow)

        hint = QtWidgets.QLabel("Click the box, then hold the keys you want "
                                "(at least one of Ctrl/Alt/Shift/Cmd plus one key). "
                                "Hold it to speak, release to paste; Esc cancels. "
                                "A new hotkey takes effect after you quit and reopen.")
        hint.setWordWrap(True)
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
        self.lang.setCurrentIndex(max(0, self.lang.findData(config.get("MRWHISPER_LANG", "") or "")))
        # pasting
        self.auto_paste.setChecked((config.get("MRWHISPER_AUTO_PASTE", "1") or "1") != "0")
        sc = config.get("MRWHISPER_PASTE_SHORTCUT", "ctrl+v") or "ctrl+v"
        self.paste_shortcut.setCurrentIndex(max(0, self.paste_shortcut.findData(sc)))
        # hotkey (default por OS): mostra o combo salvo no capturador
        import sys as _sys
        hk_default = "alt+space" if _sys.platform == "darwin" else "ctrl+alt+space"
        hk = (config.get("MRWHISPER_HOTKEY", hk_default) or hk_default).lower()
        self.hotkey.set_combo(hk)
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
        self.status.setText("validating")
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
            self._set_status(True, "✓ valid, saved")
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

    def _save_hotkey(self, combo: str) -> None:
        if getattr(self, "_loading", False):
            return
        if combo:
            config.set_values({"MRWHISPER_HOTKEY": combo})

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
            self.paste_hint.setText("Off, the text is copied; paste it yourself when ready.")
            self.paste_shortcut.setEnabled(False)
