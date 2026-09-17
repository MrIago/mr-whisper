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

# só Groq por enquanto: uma chave, grátis, transcreve e roda os comandos de voz.
PROVIDERS = {
    "groq": {
        "label": "Groq  ·  free tier ~8h/day",
        "key": "GROQ_API_KEY",
        "url": "https://console.groq.com/keys",
        "validate": cloud.validate_groq,
    },
}


# rótulos de modificador POR OS. O parser (core.config.hotkey_combo) entende
# ctrl/alt/shift/cmd/super. Cada OS tem seu 4º modificador e seus nomes:
#   Mac    → Control, Option, Shift, Command  (cmd)
#   Windows→ Ctrl, Alt, Shift, Win            (super = tecla Windows)
#   Linux  → Ctrl, Alt, Shift, Super          (super = tecla Windows/Meta)
def _mod_names() -> dict:
    import sys
    if sys.platform == "darwin":
        return {"ctrl": "Control", "alt": "Option", "shift": "Shift", "cmd": "Command"}
    if sys.platform == "win32":
        return {"ctrl": "Ctrl", "alt": "Alt", "shift": "Shift", "super": "Win"}
    return {"ctrl": "Ctrl", "alt": "Alt", "shift": "Shift", "super": "Super"}


# catálogo de teclas oferecidas como pills. valor salvo (o que o parser/plataformas
# entendem) → rótulo mostrado. Modificadores (por OS) primeiro, depois teclas.
def _mod_pills() -> list[tuple[str, str]]:
    return list(_mod_names().items())


def _key_pills() -> list[tuple[str, str]]:
    pills: list[tuple[str, str]] = [
        ("space", "Space"), ("enter", "Enter"), ("tab", "Tab"),
        ("backspace", "Backspace"),
    ]
    pills += [(c, c.upper()) for c in "abcdefghijklmnopqrstuvwxyz"]
    pills += [(d, d) for d in "0123456789"]
    pills += [(f"f{i}", f"F{i}") for i in range(1, 13)]
    # símbolos comuns (o valor é o próprio caractere)
    for sym in (",", ".", "/", ";", "'", "[", "]", "\\", "-", "=", "`"):
        pills.append((sym, sym))
    return pills


class _Pill(QtWidgets.QLabel):
    """Uma pill clicável. Mostra o rótulo e, quando selecionada, a ordem: 'Ctrl (1)'."""
    clicked = QtCore.Signal(str)

    def __init__(self, value: str, label: str) -> None:
        super().__init__()
        self.value = value
        self._label = label
        self._order = 0  # 0 = não selecionada
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self.setAlignment(QtCore.Qt.AlignCenter)
        self._render()

    def set_order(self, order: int) -> None:
        self._order = order
        self._render()

    def _render(self) -> None:
        if self._order:
            self.setText(f"{self._label} ({self._order})")
            self.setStyleSheet(
                "padding:4px 9px; border-radius:11px; border:1px solid #9acd32; "
                "background:#9acd32; color:#1a1a1f; font-weight:600;")
        else:
            self.setText(self._label)
            self.setStyleSheet(
                "padding:4px 9px; border-radius:11px; border:1px solid #555; "
                "color:#ddd;")

    def mousePressEvent(self, ev) -> None:
        self.clicked.emit(self.value)
        ev.accept()


class _HotkeyCapture(QtWidgets.QWidget):
    """Monta o atalho por CLIQUE em pills, sem capturar teclado (que brigava com
    o Qt). Clicar numa pill a adiciona ao combo na ordem do clique (Ctrl (1),
    Alt (2), Space (3)); clicar de novo remove e reordena o resto. Ao mudar,
    aparecem Salvar/Cancelar. Só salva combo com >=1 modificador + 1 tecla comum
    (a mesma regra do parser)."""
    captured = QtCore.Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._saved = ""          # combo persistido
        self._order: list[str] = []  # values na ordem de clique
        self._pills: dict[str, _Pill] = {}
        self._build()

    def _build(self) -> None:
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        self.preview = QtWidgets.QLabel()
        self.preview.setStyleSheet("font-weight:600;")
        root.addWidget(self.preview)

        # linha dos modificadores
        modbox = _FlowRow()
        for value, label in _mod_pills():
            p = _Pill(value, label)
            p.clicked.connect(self._on_pill)
            self._pills[value] = p
            modbox.add(p)
        root.addWidget(modbox)

        # teclas comuns: fluem em várias linhas (o scroll é o da janela toda).
        keybox = _FlowRow()
        for value, label in _key_pills():
            p = _Pill(value, label)
            p.clicked.connect(self._on_pill)
            self._pills[value] = p
            keybox.add(p)
        root.addWidget(keybox)

        # salvar / cancelar (só aparecem quando há mudança)
        btns = QtWidgets.QHBoxLayout()
        btns.addStretch(1)
        self.cancel_btn = QtWidgets.QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self._cancel)
        self.save_btn = QtWidgets.QPushButton("Save")
        self.save_btn.clicked.connect(self._save)
        btns.addWidget(self.cancel_btn)
        btns.addWidget(self.save_btn)
        root.addLayout(btns)
        self._btns_row = (self.cancel_btn, self.save_btn)

    # API usada pela janela
    def set_combo(self, combo: str) -> None:
        self._saved = (combo or "").lower()
        # só mantém valores que têm pill neste OS (um combo salvo em outro OS,
        # ex: cmd+space vindo do Mac, não teria pill aqui; ignora o que falta).
        self._order = [p for p in self._saved.split("+")
                       if p and p in self._pills]
        self._sync()

    def _current(self) -> str:
        return "+".join(self._order)

    def _on_pill(self, value: str) -> None:
        if value in self._order:
            self._order.remove(value)          # desmarca e reordena o resto
        else:
            self._order.append(value)          # marca no fim da ordem
        self._sync()

    def _sync(self) -> None:
        # atualiza a ordem visual em cada pill
        for value, pill in self._pills.items():
            pill.set_order(self._order.index(value) + 1 if value in self._order else 0)
        cur = self._current()
        self.preview.setText("Shortcut: " + (self._label_for(cur) if cur else "none yet"))
        changed = cur != self._saved
        for b in self._btns_row:
            b.setVisible(changed)
        # valida pro Save: (>=1 modificador + 1 tecla) OU (>=2 modificadores,
        # sem tecla). Mesma regra de core.config.hotkey_combo.
        _MODS = {"ctrl", "alt", "shift", "cmd", "super"}
        mods = {v for v in self._order if v in _MODS}
        keys = [v for v in self._order if v not in _MODS]
        self.save_btn.setEnabled((bool(mods) and len(keys) == 1)
                                 or (len(mods) >= 2 and not keys))

    def _label_for(self, combo: str) -> str:
        names = _mod_names()
        out = []
        for p in combo.split("+"):
            if not p:
                continue
            out.append(names.get(p, p.upper() if len(p) == 1 else p.capitalize()))
        return " + ".join(out)

    def _save(self) -> None:
        cur = self._current()
        self._saved = cur
        self._sync()
        self.captured.emit(cur)

    def _cancel(self) -> None:
        self._order = [p for p in self._saved.split("+") if p]
        self._sync()


class _FlowRow(QtWidgets.QWidget):
    """Container simples que embrulha as pills em várias linhas."""
    def __init__(self) -> None:
        super().__init__()
        self._lay = _FlowLayout(self)

    def add(self, w) -> None:
        self._lay.addWidget(w)


class _FlowLayout(QtWidgets.QLayout):
    """Layout que quebra os itens em linhas conforme a largura (wrap)."""
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._items: list = []
        self.setContentsMargins(0, 0, 0, 0)
        self.setSpacing(6)

    def addItem(self, item) -> None:
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, i):
        return self._items[i] if 0 <= i < len(self._items) else None

    def takeAt(self, i):
        return self._items.pop(i) if 0 <= i < len(self._items) else None

    def expandingDirections(self):
        return QtCore.Qt.Orientations(QtCore.Qt.Orientation(0))

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width) -> int:
        return self._do_layout(QtCore.QRect(0, 0, width, 0), True)

    def setGeometry(self, rect) -> None:
        super().setGeometry(rect)
        self._do_layout(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QtCore.QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        return size + QtCore.QSize(2, 2)

    def _do_layout(self, rect, test_only) -> int:
        x, y = rect.x(), rect.y()
        line_h = 0
        space = self.spacing()
        for item in self._items:
            w = item.sizeHint().width()
            h = item.sizeHint().height()
            if x + w > rect.right() and line_h > 0:
                x = rect.x()
                y += line_h + space
                line_h = 0
            if not test_only:
                item.setGeometry(QtCore.QRect(QtCore.QPoint(x, y), item.sizeHint()))
            x += w + space
            line_h = max(line_h, h)
        return y + line_h - rect.y()


class SettingsWindow(QtWidgets.QWidget):
    # resultado da validação (vem de thread) → UI
    _validated = QtCore.Signal(bool, str)

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("mr-whisper · Settings")
        self.setMinimumWidth(480)
        self.resize(520, 720)
        self._validated.connect(self._on_validated)
        self._build()
        self._load()

    def _build(self) -> None:
        # a janela inteira rola (scroll único no diálogo, não por seção).
        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        outer.addWidget(scroll)
        content = QtWidgets.QWidget()
        scroll.setWidget(content)

        layout = QtWidgets.QVBoxLayout(content)
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

        # os comandos de voz rodam no mesmo Groq da transcrição (só uma chave).

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
        # O valor salvo é o mesmo nos 3 OS ("ctrl+v" | "ctrl+shift+v"); só o
        # Shift importa pra plataforma, que usa o modificador de colar do SO
        # (Command no macOS, Ctrl nos demais). O rótulo mostra a tecla real.
        import sys as _sys
        if _sys.platform == "darwin":
            self.paste_shortcut.addItem("Command+V  (standard)", "ctrl+v")
            self.paste_shortcut.addItem("Command+Shift+V  (paste and match style)",
                                        "ctrl+shift+v")
        else:
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

        layout.addWidget(QtWidgets.QLabel("Hold to dictate:"))
        # monta o atalho clicando nas pills, na ordem do clique.
        self.hotkey = _HotkeyCapture()
        self.hotkey.captured.connect(self._save_hotkey)
        layout.addWidget(self.hotkey)

        hint = QtWidgets.QLabel("Click the keys in order to build the shortcut, "
                                "then Save. Use one modifier plus a key, or two "
                                "modifiers alone (nothing gets typed while you "
                                "hold them). Hold it to speak, release to paste. "
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
        # só Groq: garante que o motor dos comandos aponta pro Groq (evita ficar
        # preso num backend antigo sem chave, que quebrava a tradução).
        if (config.get("MRWHISPER_TRANSLATE", "groq") or "groq") != "groq":
            config.set_values({"MRWHISPER_TRANSLATE": "groq"})
        self.lang.setCurrentIndex(max(0, self.lang.findData(config.get("MRWHISPER_LANG", "") or "")))
        # pasting
        self.auto_paste.setChecked((config.get("MRWHISPER_AUTO_PASTE", "1") or "1") != "0")
        sc = config.get("MRWHISPER_PASTE_SHORTCUT", "ctrl+v") or "ctrl+v"
        self.paste_shortcut.setCurrentIndex(max(0, self.paste_shortcut.findData(sc)))
        # hotkey (default por OS): mostra o combo salvo no capturador
        hk_default = config.default_hotkey()
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
