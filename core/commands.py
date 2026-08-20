#!/usr/bin/env python3
"""Comandos de voz do mr-whisper, built-in + customizados pelo usuário.

Um comando = palavras-chave (com sinônimos) + um tipo de ação. Você diz a
palavra-chave no meio da fala; tudo ANTES vira contexto (ajuda o LLM, nunca é
colado), tudo DEPOIS é a mensagem processada.

Tipos:
- rewrite   → manda a mensagem pro LLM com o `prompt` do comando (reescrever,
              limpar, formatar, resumir…, prompt livre). NÃO troca idioma salvo
              se o prompt pedir.
- translate → traduz/localiza; a 1ª palavra depois da keyword é o idioma-alvo.
- dump      → salva a mensagem no arquivo de notas em vez de colar.

Os 4 comandos originais (auto translate/context/adjust, new dump) são os
DEFAULTS, já vêm prontos, mas você pode editar keyword/prompt, desligar, ou
criar novos. Ficam em ~/.config/mr-whisper/commands.json; se o arquivo não
existe, usamos os defaults (e o usuário nunca fica sem os comandos básicos).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from . import config

COMMANDS_FILE = Path(config.CONFIG_FILE).parent / "commands.json"

# Prompt de reescrita usado pelos defaults "context" e "adjust".
_CONTEXT_PROMPT = (
    "Rewrite the message in its OWN language (never translate) so it reads the "
    "way a fluent native would write it for the situation: fix grammar and word "
    "order, swap clumsy phrasing for natural expressions, and match the tone and "
    "register (technical, formal, casual) to the context."
)
_ADJUST_PROMPT = (
    "Lightly clean up the message in its OWN language: remove filler words and "
    "speech tics, fix punctuation and capitalization, correct obvious grammar "
    "slips. Keep the same words and meaning, this is a cleanup, NOT a rewrite."
)

# Comandos padrão (o usuário pode editar/desligar/adicionar por cima).
DEFAULTS = [
    {"id": "translate", "type": "translate", "enabled": True,
     "keywords": ["auto translate", "autotranslate", "auto traduzir"], "prompt": ""},
    {"id": "context", "type": "rewrite", "enabled": True,
     "keywords": ["auto context", "auto contexto", "auto contextualize"],
     "prompt": _CONTEXT_PROMPT},
    {"id": "adjust", "type": "rewrite", "enabled": True,
     "keywords": ["auto adjust", "auto ajustar", "auto ajusta", "auto ajuste"],
     "prompt": _ADJUST_PROMPT},
    {"id": "dump", "type": "dump", "enabled": True,
     "keywords": ["new dump", "novo dump", "newdump"], "prompt": ""},
]


def load() -> list[dict]:
    """Lê os comandos do JSON, ou devolve os DEFAULTS se não houver arquivo."""
    if COMMANDS_FILE.exists():
        try:
            data = json.loads(COMMANDS_FILE.read_text(encoding="utf-8"))
            if isinstance(data, list) and data:
                return data
        except (OSError, ValueError):
            pass
    return [dict(c) for c in DEFAULTS]


def save(commands: list[dict]) -> None:
    COMMANDS_FILE.parent.mkdir(parents=True, exist_ok=True)
    COMMANDS_FILE.write_text(json.dumps(commands, ensure_ascii=False, indent=2),
                             encoding="utf-8")


def _keyword_regex(keyword: str) -> re.Pattern:
    """Regex tolerante pra uma keyword: espaço/hífen flexível, pontuação do
    whisper depois. Captura o resto da fala em `rest`."""
    # cada palavra da keyword vira \b<palavra>\b, separadas por espaço/hífen
    parts = [re.escape(w) for w in keyword.split()]
    core = r"[\s\-]*".join(parts)
    return re.compile(core + r"[\s,:;.!?]+(?P<rest>.+)$",
                      re.IGNORECASE | re.DOTALL)


def match(text: str, commands: list[dict] | None = None) -> dict | None:
    """Acha o 1º comando (por posição na fala) cuja keyword aparece. Retorna:
    {cmd, context, message[, lang]} ou None.
    - context = tudo antes da keyword (nunca colado)
    - message = tudo depois da keyword (e, pra translate, sem o idioma)
    """
    text = (text or "").strip()
    if not text:
        return None
    commands = commands if commands is not None else load()

    best = None  # (start_pos, cmd, match)
    for cmd in commands:
        if not cmd.get("enabled", True):
            continue
        for kw in cmd.get("keywords", []):
            m = _keyword_regex(kw).search(text)
            if m and (best is None or m.start() < best[0]):
                best = (m.start(), cmd, m)
    if best is None:
        return None

    start, cmd, m = best
    rest = m.group("rest").strip()
    if not rest:
        return None
    out = {"cmd": cmd, "context": text[:start].strip(), "message": rest}

    # translate: a 1ª palavra depois da keyword é o idioma
    if cmd["type"] == "translate":
        m2 = re.match(r"(?:(?:to|para|pra)\s+)?(?P<lang>[^\s,.:;!?]+)[\s,.:;!?]+(?P<msg>.+)$",
                      rest, re.IGNORECASE | re.DOTALL)
        if not m2:
            return None
        out["lang"] = m2.group("lang").strip()
        out["message"] = m2.group("msg").strip()
        if not out["lang"] or not out["message"]:
            return None
    return out
