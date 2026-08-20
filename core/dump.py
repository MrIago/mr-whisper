#!/usr/bin/env python3
"""dump do mr-whisper, captura rápida de notas por voz.

Quando você começa a fala com "new dump" (ou "novo dump"), o resto NÃO vai pro
clipboard: é anexado ao seu arquivo de dump (um markdown), com data/hora. Ideal
pra jogar uma ideia/nota mental no meio de outra coisa, sem trocar de janela.

Onde salva: config MRWHISPER_DUMP_FILE (ver config.py). Default:
~/Documentos/Notas/dump.md, cada um aponta pro seu arquivo.

Exemplos que disparam:
  "new dump, lembrar de revisar o PR do auth amanhã"
  "novo dump ideia: cachear a transcrição por hash do wav"
"""
from __future__ import annotations

import re
import time
from pathlib import Path

from . import config

# "new dump" / "novo dump" no começo (tolerante a caixa, pontuação do whisper e
# ao whisper grudar "newdump"). Captura o resto como a nota.
_TRIGGER = re.compile(
    r"""^\s*(?:new|novo)[\s\-]*dump   # "new dump" / "novo dump" / "newdump"
        [\s,:;.!?]+                    # pontuação/espaço após o comando
        (?P<note>.+)$                  # a nota a salvar
    """,
    re.IGNORECASE | re.VERBOSE | re.DOTALL,
)

_DEFAULT_FILE = "~/Documentos/Notas/dump.md"


def dump_path() -> Path:
    """Caminho do arquivo de dump (config MRWHISPER_DUMP_FILE, com ~ expandido)."""
    raw = config.get("MRWHISPER_DUMP_FILE", _DEFAULT_FILE) or _DEFAULT_FILE
    return Path(raw).expanduser()


def parse(text: str) -> str | None:
    """Retorna a nota (texto após o comando) se a fala começa com o gatilho."""
    m = _TRIGGER.match(text or "")
    if not m:
        return None
    note = m.group("note").strip()
    return note or None


def save(note: str, log=print) -> bool:
    """Anexa a nota ao arquivo de dump como um item com timestamp. True se ok."""
    path = dump_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y-%m-%d %H:%M")
        entry = f"- [{stamp}] {note}\n"
        with open(path, "a", encoding="utf-8") as f:
            f.write(entry)
        log(f"dump → {path}: {note!r}")
        return True
    except OSError as exc:
        log(f"dump falhou ({exc})")
        return False


# CLI de teste: python dump.py "new dump minha ideia"
if __name__ == "__main__":
    import sys

    s = " ".join(sys.argv[1:]) or "new dump exemplo de nota"
    note = parse(s)
    print("nota:", note)
    if note:
        save(note)
