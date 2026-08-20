#!/usr/bin/env python3
"""Notas de voz do mr-whisper (comando "new dump").

Quando você fala "new dump ..." (ou "novo dump ..."), o resto NÃO vai pro
clipboard: vira uma nota guardada pelo app. As notas ficam num JSON do próprio
app (~/.config/mr-whisper/notes.json) e você as gerencia pela tela Notes (ver,
copiar, apagar uma ou todas). Sem configurar caminho.

Cada nota: {"time": "2026-08-20 18:09", "text": "..."}.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from . import config

NOTES_FILE = Path(config.CONFIG_FILE).parent / "notes.json"


def load() -> list[dict]:
    """Lista de notas (mais recente por último). [] se não houver."""
    if NOTES_FILE.exists():
        try:
            data = json.loads(NOTES_FILE.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data
        except (OSError, ValueError):
            pass
    return []


def _write(notes: list[dict]) -> bool:
    try:
        NOTES_FILE.parent.mkdir(parents=True, exist_ok=True)
        NOTES_FILE.write_text(json.dumps(notes, ensure_ascii=False, indent=2),
                              encoding="utf-8")
        return True
    except OSError:
        return False


def save(text: str, log=print) -> bool:
    """Anexa uma nota nova. True se gravou."""
    text = (text or "").strip()
    if not text:
        return False
    notes = load()
    notes.append({"time": time.strftime("%Y-%m-%d %H:%M"), "text": text})
    ok = _write(notes)
    log(f"nota salva ({len(text)} chars)" if ok else "falha ao salvar nota")
    return ok


def delete(index: int) -> bool:
    """Apaga a nota na posição `index` (na ordem de load())."""
    notes = load()
    if 0 <= index < len(notes):
        notes.pop(index)
        return _write(notes)
    return False


def clear() -> bool:
    """Apaga todas as notas."""
    return _write([])


def all_text() -> str:
    """Todas as notas como texto (pra 'copiar tudo')."""
    return "\n".join(f"[{n['time']}] {n['text']}" for n in load())


if __name__ == "__main__":
    import sys
    if sys.argv[1:]:
        save(" ".join(sys.argv[1:]))
    for n in load():
        print(f"[{n['time']}] {n['text']}")
