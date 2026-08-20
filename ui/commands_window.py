#!/usr/bin/env python3
"""Tutorial dos comandos de voz do mr-whisper (só leitura).

Lista os comandos fixos com um exemplo de cada. Você diz o comando no começo da
fala e ele transforma o resto antes de colar (menos "new dump", que salva nas
suas notas).
"""
from __future__ import annotations

from PySide6 import QtCore, QtWidgets

COMMANDS = [
    ("auto translate {language}", "Translate and localize into that language.",
     '"auto translate spanish, good morning everyone"  →  "buenos días a todos"'),
    ("auto context", "Rewrite in the same language, matching the tone to what you "
     "said before the command.",
     '"replying to my boss, auto context, hey bump up my salary?"  →  a polite, '
     'professional version'),
    ("auto adjust", "Light cleanup: remove filler (uh, um, like), fix punctuation "
     "and grammar, keep your words.",
     '"auto adjust, so, uh, we need to ship this friday"  →  "We need to ship '
     'this Friday."'),
    ("new dump", "Save what you say as a note instead of pasting it. See them in "
     "Notes (tray menu).",
     '"new dump, remember to review the auth PR"  →  saved to your notes'),
]


class CommandsWindow(QtWidgets.QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("mr-whisper · Voice commands")
        self.setMinimumWidth(560)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        top = QtWidgets.QLabel(
            "Say one of these at the <b>start</b> of your dictation. Everything "
            "before the command is used as context and never pasted; everything "
            "after it is transformed.")
        top.setWordWrap(True)
        top.setTextFormat(QtCore.Qt.RichText)
        top.setStyleSheet("color:#aaa;")
        layout.addWidget(top)

        for name, what, example in COMMANDS:
            card = QtWidgets.QFrame()
            card.setFrameShape(QtWidgets.QFrame.StyledPanel)
            v = QtWidgets.QVBoxLayout(card)
            v.setContentsMargins(14, 12, 14, 12)
            v.setSpacing(4)

            title = QtWidgets.QLabel(name)
            title.setStyleSheet("font-size:15px; font-weight:700; color:#9acd32;")
            v.addWidget(title)

            desc = QtWidgets.QLabel(what)
            desc.setWordWrap(True)
            v.addWidget(desc)

            ex = QtWidgets.QLabel(example)
            ex.setWordWrap(True)
            ex.setStyleSheet("color:#888; font-style:italic;")
            v.addWidget(ex)

            layout.addWidget(card)

        layout.addStretch(1)
