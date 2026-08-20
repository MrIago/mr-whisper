#!/usr/bin/env python3
"""Comandos de voz do mr-whisper (fixos).

Você diz um comando no meio da fala; tudo ANTES vira contexto (ajuda o LLM,
nunca é colado), tudo DEPOIS é a mensagem processada. Falha (rede/chave) nunca
te deixa sem nada: cai pra mensagem original.

Comandos:
- "auto translate {idioma} ..."  traduz/localiza pro idioma (troca idioma).
- "auto context ..."             reescreve no mesmo idioma, ajustando o tom ao
                                 contexto (não traduz).
- "auto adjust ..."              limpa vícios de fala, ajusta pontuação, mantém
                                 a mensagem.
- "new dump ..."                 salva a mensagem nas suas notas (ver core/dump),
                                 não cola.

Detecção tolerante (caixa, hífen, pontuação do whisper, variantes PT/EN).
"""
from __future__ import annotations

import re

from . import cloud, dump

# ── auto translate {idioma} ───────────────────────────────────────────────────
_TRANSLATE = re.compile(
    r"""auto[\s\-]*translate
        [\s,:;.]+
        (?:(?:to|para|pra)\s+)?
        (?P<lang>[^\s,.:;!?]+)
        [\s,.:;!?]+
        (?P<rest>.+)$
    """,
    re.IGNORECASE | re.VERBOSE | re.DOTALL,
)
# ── auto context ──────────────────────────────────────────────────────────────
_CONTEXT = re.compile(
    r"auto[\s\-]*context(?:o|ualize|ualiza|ualise)?[\s,:;.!?]+(?P<rest>.+)$",
    re.IGNORECASE | re.DOTALL,
)
# ── auto adjust ───────────────────────────────────────────────────────────────
_ADJUST = re.compile(
    r"auto[\s\-]*(?:adjust|ajust(?:e|a|ar)?)[\s,:;.!?]+(?P<rest>.+)$",
    re.IGNORECASE | re.DOTALL,
)
# ── new dump ──────────────────────────────────────────────────────────────────
_DUMP = re.compile(
    r"(?:new|novo)[\s\-]*dump[\s,:;.!?]+(?P<rest>.+)$",
    re.IGNORECASE | re.DOTALL,
)


def parse(text: str) -> dict | None:
    """Detecta o 1º comando na fala. Retorna
    {kind, context, message[, lang]} ou None."""
    text = (text or "").strip()
    if not text:
        return None
    cands = []
    if (m := _TRANSLATE.search(text)):
        cands.append((m.start(), "translate", m))
    if (m := _CONTEXT.search(text)):
        cands.append((m.start(), "context", m))
    if (m := _ADJUST.search(text)):
        cands.append((m.start(), "adjust", m))
    if (m := _DUMP.search(text)):
        cands.append((m.start(), "dump", m))
    if not cands:
        return None

    start, kind, m = min(cands, key=lambda c: c[0])
    rest = m.group("rest").strip()
    if not rest:
        return None
    out = {"kind": kind, "context": text[:start].strip(), "message": rest}
    if kind == "translate":
        lang = m.group("lang").strip()
        if not lang:
            return None
        out["lang"] = lang
    return out


def is_dump(text: str) -> bool:
    p = parse(text)
    return bool(p and p["kind"] == "dump")


def maybe_transform(text: str, log=print) -> str:
    """Executa o comando. Sempre retorna texto colável (o resultado, ou a
    mensagem original em falha). 'dump' salva e retorna "" (o app não cola)."""
    p = parse(text)
    if not p:
        return text
    kind, ctx, msg = p["kind"], p["context"], p["message"]
    try:
        if kind == "dump":
            dump.save(msg, log=log)
            return ""
        if kind == "translate":
            out = cloud.translate_cloud(msg, p["lang"], context=ctx)
        elif kind == "context":
            out = cloud.context_cloud(msg, context=ctx)
        else:  # adjust
            out = cloud.adjust_cloud(msg)
        if out:
            log(f"cmd {kind} (ctx={ctx!r}): {out!r}")
            return out
        log(f"cmd {kind} vazio, colando original")
    except Exception as exc:
        log(f"cmd {kind} falhou ({exc}), colando original")
    return msg


if __name__ == "__main__":
    import sys
    print(maybe_transform(" ".join(sys.argv[1:]) or "auto translate spanish hello"))
