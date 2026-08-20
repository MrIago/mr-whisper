#!/usr/bin/env python3
"""Notas de voz do mr-whisper (o comando "new dump").

Lista as notas salvas; cada linha mostra botões Copy/Delete ao passar o mouse.
No topo: Copy all e Clear all. Sem configurar caminho, as notas vivem num JSON
do app (ver core/dump).
"""
from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from core import dump


class _NoteRow(QtWidgets.QFrame):
    """Uma nota; os botões Copy/Delete só aparecem no hover."""

    def __init__(self, note: dict, on_copy, on_delete) -> None:
        super().__init__()
        self.setFrameShape(QtWidgets.QFrame.StyledPanel)
        h = QtWidgets.QHBoxLayout(self)
        h.setContentsMargins(12, 8, 8, 8)

        col = QtWidgets.QVBoxLayout()
        col.setSpacing(2)
        t = QtWidgets.QLabel(note.get("time", ""))
        t.setStyleSheet("color:#888; font-size:11px;")
        col.addWidget(t)
        txt = QtWidgets.QLabel(note.get("text", ""))
        txt.setWordWrap(True)
        col.addWidget(txt)
        h.addLayout(col, 1)

        self._btns = QtWidgets.QWidget()
        bl = QtWidgets.QHBoxLayout(self._btns)
        bl.setContentsMargins(0, 0, 0, 0)
        copy = QtWidgets.QPushButton("Copy")
        copy.clicked.connect(on_copy)
        bl.addWidget(copy)
        dele = QtWidgets.QPushButton("Delete")
        dele.clicked.connect(on_delete)
        bl.addWidget(dele)
        self._btns.setVisible(False)
        h.addWidget(self._btns)

    def enterEvent(self, e):
        self._btns.setVisible(True)

    def leaveEvent(self, e):
        self._btns.setVisible(False)


class NotesWindow(QtWidgets.QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("mr-whisper · Notes")
        self.setMinimumSize(520, 460)
        self._build()

    def _build(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        head = QtWidgets.QHBoxLayout()
        title = QtWidgets.QLabel("Notes")
        title.setStyleSheet("font-size:16px; font-weight:600;")
        head.addWidget(title)
        head.addStretch(1)
        self.copy_all = QtWidgets.QPushButton("Copy all")
        self.copy_all.clicked.connect(self._copy_all)
        head.addWidget(self.copy_all)
        self.clear_all = QtWidgets.QPushButton("Clear all")
        self.clear_all.clicked.connect(self._clear_all)
        head.addWidget(self.clear_all)
        layout.addLayout(head)

        sub = QtWidgets.QLabel('Say "new dump ..." while dictating to add a note.')
        sub.setStyleSheet("color:#888;")
        layout.addWidget(sub)

        self.scroll = QtWidgets.QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.inner = QtWidgets.QWidget()
        self.vbox = QtWidgets.QVBoxLayout(self.inner)
        self.vbox.setSpacing(8)
        self.vbox.addStretch(1)
        self.scroll.setWidget(self.inner)
        layout.addWidget(self.scroll, 1)

    def showEvent(self, e):
        self._reload()
        super().showEvent(e)

    # ── dados ─────────────────────────────────────────────────────────────────
    def _reload(self) -> None:
        # limpa as linhas atuais
        while self.vbox.count() > 1:
            item = self.vbox.takeAt(0)
            if item.widget():
                item.widget().setParent(None)
        notes = dump.load()
        empty = not notes
        self.copy_all.setEnabled(not empty)
        self.clear_all.setEnabled(not empty)
        if empty:
            lbl = QtWidgets.QLabel("No notes yet.")
            lbl.setStyleSheet("color:#888;")
            self.vbox.insertWidget(0, lbl)
            return
        # mais recente no topo
        for i in range(len(notes) - 1, -1, -1):
            row = _NoteRow(notes[i],
                          on_copy=lambda _=False, idx=i: self._copy_one(idx),
                          on_delete=lambda _=False, idx=i: self._delete_one(idx))
            self.vbox.insertWidget(self.vbox.count() - 1, row)

    def _copy_one(self, index: int) -> None:
        notes = dump.load()
        if 0 <= index < len(notes):
            QtWidgets.QApplication.clipboard().setText(notes[index]["text"])

    def _delete_one(self, index: int) -> None:
        dump.delete(index)
        self._reload()

    def _copy_all(self) -> None:
        QtWidgets.QApplication.clipboard().setText(dump.all_text())

    def _clear_all(self) -> None:
        if QtWidgets.QMessageBox.question(
                self, "Clear all notes", "Delete all notes? This cannot be undone."
        ) == QtWidgets.QMessageBox.Yes:
            dump.clear()
            self._reload()
