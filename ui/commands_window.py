#!/usr/bin/env python3
"""Editor de comandos de voz do mr-whisper.

Uma linha por comando: liga/desliga, palavras-chave (vírgula separa sinônimos),
tipo (rewrite/translate/dump) e o prompt livre. Você diz a palavra-chave no meio
da fala e o comando processa o que vem depois. Salva em commands.json.
"""
from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from core import commands

TYPES = [
    ("rewrite", "Rewrite — apply the prompt to what you said"),
    ("translate", "Translate — first word after the keyword is the target language"),
    ("dump", "Save note — append to your notes file instead of pasting"),
]


class CommandsWindow(QtWidgets.QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("mr-whisper · Voice commands")
        self.setMinimumSize(640, 460)
        self._build()
        self._reload()

    def _build(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        intro = QtWidgets.QLabel(
            "Say a keyword at the start of your dictation and it transforms the "
            "rest.\nExample — a command “work email” with prompt “rewrite as a "
            "professional email” turns\nyour casual speech into an email before "
            "pasting."
        )
        intro.setStyleSheet("color:#888;")
        layout.addWidget(intro)

        # área rolável com os comandos
        self.scroll = QtWidgets.QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.inner = QtWidgets.QWidget()
        self.vbox = QtWidgets.QVBoxLayout(self.inner)
        self.vbox.setSpacing(10)
        self.vbox.addStretch(1)
        self.scroll.setWidget(self.inner)
        layout.addWidget(self.scroll, 1)

        # botões
        row = QtWidgets.QHBoxLayout()
        add = QtWidgets.QPushButton("+ Add command")
        add.clicked.connect(self._add_blank)
        row.addWidget(add)
        reset = QtWidgets.QPushButton("Reset to defaults")
        reset.clicked.connect(self._reset)
        row.addWidget(reset)
        row.addStretch(1)
        save = QtWidgets.QPushButton("Save")
        save.setDefault(True)
        save.clicked.connect(self._save)
        row.addWidget(save)
        layout.addLayout(row)

        self._rows: list[dict] = []

    # ── construção das linhas ──────────────────────────────────────────────────
    def _reload(self) -> None:
        for r in self._rows:
            r["frame"].setParent(None)
        self._rows.clear()
        for cmd in commands.load():
            self._add_row(cmd)

    def _add_blank(self) -> None:
        self._add_row({"id": "", "type": "rewrite", "enabled": True,
                       "keywords": [], "prompt": ""})

    def _add_row(self, cmd: dict) -> None:
        frame = QtWidgets.QFrame()
        frame.setFrameShape(QtWidgets.QFrame.StyledPanel)
        fl = QtWidgets.QGridLayout(frame)
        fl.setContentsMargins(12, 10, 12, 10)

        enabled = QtWidgets.QCheckBox("On")
        enabled.setChecked(cmd.get("enabled", True))
        fl.addWidget(enabled, 0, 0)

        keywords = QtWidgets.QLineEdit(", ".join(cmd.get("keywords", [])))
        keywords.setPlaceholderText("keywords (comma-separated synonyms)")
        fl.addWidget(QtWidgets.QLabel("Keywords:"), 0, 1)
        fl.addWidget(keywords, 0, 2)

        typ = QtWidgets.QComboBox()
        for tid, label in TYPES:
            typ.addItem(label, tid)
        typ.setCurrentIndex(max(0, [t[0] for t in TYPES].index(cmd.get("type", "rewrite"))
                                if cmd.get("type", "rewrite") in [t[0] for t in TYPES] else 0))
        fl.addWidget(QtWidgets.QLabel("Type:"), 1, 1)
        fl.addWidget(typ, 1, 2)

        prompt = QtWidgets.QPlainTextEdit(cmd.get("prompt", ""))
        prompt.setPlaceholderText("prompt — how to transform the text "
                                  "(only for Rewrite; ignored for Translate/Save)")
        prompt.setFixedHeight(56)
        fl.addWidget(QtWidgets.QLabel("Prompt:"), 2, 1)
        fl.addWidget(prompt, 2, 2)

        rm = QtWidgets.QPushButton("Remove")
        rm.clicked.connect(lambda: self._remove(frame))
        fl.addWidget(rm, 0, 3)

        # prompt só faz sentido pra rewrite
        def sync_prompt():
            prompt.setEnabled(typ.currentData() == "rewrite")
        typ.currentIndexChanged.connect(sync_prompt)
        sync_prompt()

        self.vbox.insertWidget(self.vbox.count() - 1, frame)
        self._rows.append({"frame": frame, "id": cmd.get("id", ""),
                           "enabled": enabled, "keywords": keywords,
                           "type": typ, "prompt": prompt})

    def _remove(self, frame) -> None:
        self._rows = [r for r in self._rows if r["frame"] is not frame]
        frame.setParent(None)

    def _reset(self) -> None:
        commands.save([dict(c) for c in commands.DEFAULTS])
        self._reload()

    def _save(self) -> None:
        out = []
        for i, r in enumerate(self._rows):
            kws = [k.strip() for k in r["keywords"].text().split(",") if k.strip()]
            if not kws:
                continue  # sem keyword = comando inválido, ignora
            out.append({
                "id": r["id"] or f"custom{i}",
                "type": r["type"].currentData(),
                "enabled": r["enabled"].isChecked(),
                "keywords": kws,
                "prompt": r["prompt"].toPlainText().strip(),
            })
        commands.save(out)
        self.close()
