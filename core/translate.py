#!/usr/bin/env python3
"""Comandos de voz do mr-whisper que passam a fala por um LLM antes de colar.

Três comandos, todos com a mesma ideia: o que você fala ANTES do comando é
CONTEXTO (ajusta tom/registro, nunca é colado); o que vem DEPOIS é a mensagem
processada. Detecção tolerante (caixa, hífen, pontuação do whisper, PT/EN).

- "auto translate {idioma} ..."  → traduz/localiza pro idioma (troca idioma).
- "auto context ..."             → reescreve no MESMO idioma, adaptando tom ao
                                    contexto (não traduz).
- "auto adjust ..."              → só limpa: tira vícios de fala, ajusta
                                    pontuação/gramática, mantém a mensagem.

O regex só DETECTA o comando; o trabalho fica no LLM (ver cloud.py). Falha
(rede/chave) nunca te deixa sem nada: cai pra mensagem original.

Exemplos:
  "auto translate spanish, bom dia pessoal"        → "buenos días a todos"
  "vou responder no LinkedIn, auto context, e aí"  → mesma língua, tom profissional
  "auto adjust, é, tipo, então o lance é o seguinte" → "Então, o lance é o seguinte."
"""
from __future__ import annotations

import re

from . import cloud

# ── auto translate {idioma} — captura o idioma-alvo + a mensagem ──────────────
_TRANSLATE = re.compile(
    r"""auto[\s\-]*translate              # "auto translate"/"autotranslate"
        [\s,:;.]+                          # pontuação/espaço após o comando
        (?:(?:to|para|pra)\s+)?            # conector opcional
        (?P<lang>[^\s,.:;!?]+)             # idioma = 1 palavra (spanish, japonês…)
        [\s,.:;!?]+                        # separador antes do conteúdo
        (?P<rest>.+)$                      # a mensagem a traduzir
    """,
    re.IGNORECASE | re.VERBOSE | re.DOTALL,
)

# ── auto context / auto adjust — só a mensagem depois do comando ──────────────
# "context": aceita context/contexto/contextualize/contextualiza (EN/PT).
_CONTEXT = re.compile(
    r"""auto[\s\-]*context(?:o|ualize|ualiza|ualise)?
        [\s,:;.!?]+
        (?P<rest>.+)$
    """,
    re.IGNORECASE | re.VERBOSE | re.DOTALL,
)
# "adjust": aceita adjust/ajuste/ajusta/ajustar.
_ADJUST = re.compile(
    r"""auto[\s\-]*(?:adjust|ajust(?:e|a|ar)?)
        [\s,:;.!?]+
        (?P<rest>.+)$
    """,
    re.IGNORECASE | re.VERBOSE | re.DOTALL,
)


def parse(text: str) -> dict | None:
    """Detecta o 1º comando que aparecer na fala. Retorna um dict:
    {kind: 'translate'|'context'|'adjust', context, message[, lang]} ou None.

    `context` = tudo antes do comando (nunca colado). `message` = tudo depois.
    Se houver mais de um comando, vence o que aparece PRIMEIRO na fala."""
    text = (text or "").strip()
    if not text:
        return None

    candidates = []
    if (m := _TRANSLATE.search(text)):
        candidates.append((m.start(), "translate", m))
    if (m := _CONTEXT.search(text)):
        candidates.append((m.start(), "context", m))
    if (m := _ADJUST.search(text)):
        candidates.append((m.start(), "adjust", m))
    if not candidates:
        return None

    start, kind, m = min(candidates, key=lambda c: c[0])
    rest = m.group("rest").strip()
    if not rest:
        return None
    ctx = text[:start].strip()
    out = {"kind": kind, "context": ctx, "message": rest}
    if kind == "translate":
        lang = m.group("lang").strip()
        if not lang:
            return None
        out["lang"] = lang
    return out


def maybe_transform(text: str, log=print) -> str:
    """Aplica o comando (translate/context/adjust) se houver. Sempre retorna
    texto colável: o resultado em sucesso, ou a mensagem original em falha."""
    p = parse(text)
    if not p:
        return text
    kind, ctx, msg = p["kind"], p["context"], p["message"]
    try:
        if kind == "translate":
            out = cloud.translate_cloud(msg, p["lang"], context=ctx)
            tag = f"translate → {p['lang']}"
        elif kind == "context":
            out = cloud.context_cloud(msg, context=ctx)
            tag = "context"
        else:
            out = cloud.adjust_cloud(msg)
            tag = "adjust"
        if out:
            log(f"auto-{tag} (ctx={ctx!r}): {out!r}")
            return out
        log(f"auto-{kind} retornou vazio — colando original")
    except Exception as exc:  # rede/key/HTTP — nunca derruba o ditado
        log(f"auto-{kind} falhou ({exc}) — colando original")
    return msg


# CLI de teste: python translate.py "auto adjust é tipo isso aí"
if __name__ == "__main__":
    import sys

    s = " ".join(sys.argv[1:]) or "auto translate spanish hello world"
    print(maybe_transform(s))
