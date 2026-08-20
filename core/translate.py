#!/usr/bin/env python3
"""Comandos de voz do mr-whisper, o executor.

Detecta um comando na fala (ver core/commands.py: built-in + customizados) e o
executa antes de colar. O que vem ANTES da keyword é contexto (nunca colado); o
que vem DEPOIS é a mensagem. Falha (rede/chave) nunca te deixa sem nada: cai
pra mensagem original.

Tipos de comando:
- translate → traduz/localiza pro idioma falado (cloud.translate_cloud)
- rewrite   → aplica o prompt livre do comando (cloud.rewrite_cloud)
- dump      → salva a mensagem no arquivo de notas (dump.save), não cola

O app chama parse()/maybe_transform(); ambos delegam pro core/commands.
"""
from __future__ import annotations

from . import cloud, commands, dump


def parse(text: str) -> dict | None:
    """True-ish se há um comando na fala. Retorna o dict de commands.match()
    (cmd, context, message[, lang]) ou None. O app usa só pra saber SE há
    comando (mostra o dock durante o LLM)."""
    return commands.match(text)


def maybe_transform(text: str, log=print) -> str:
    """Executa o comando detectado. Sempre retorna texto colável (o resultado,
    ou a mensagem original em falha). Para 'dump', salva e retorna "" (nada a
    colar), o app trata string vazia como "não cola"."""
    p = commands.match(text)
    if not p:
        return text
    cmd, ctx, msg = p["cmd"], p["context"], p["message"]
    kind = cmd["type"]
    try:
        if kind == "dump":
            ok = dump.save(msg, log=log)
            log(f"dump {'ok' if ok else 'falhou'}: {msg!r}")
            return ""  # não cola
        if kind == "translate":
            out = cloud.translate_cloud(msg, p["lang"], context=ctx)
            tag = f"translate → {p['lang']}"
        else:  # rewrite (context/adjust/customizados)
            out = cloud.rewrite_cloud(msg, cmd.get("prompt", ""), context=ctx)
            tag = f"rewrite:{cmd.get('id', '?')}"
        if out:
            log(f"cmd {tag} (ctx={ctx!r}): {out!r}")
            return out
        log(f"cmd {tag} retornou vazio, colando mensagem original")
    except Exception as exc:  # rede/key/HTTP, nunca derruba o ditado
        log(f"cmd {kind} falhou ({exc}), colando mensagem original")
    return msg


def is_dump(text: str) -> bool:
    """True se o comando detectado é um 'dump' (o app esconde a pill sem colar)."""
    p = commands.match(text)
    return bool(p and p["cmd"]["type"] == "dump")


# CLI de teste: python -m core.translate "auto adjust é tipo isso aí"
if __name__ == "__main__":
    import sys

    s = " ".join(sys.argv[1:]) or "auto translate spanish hello world"
    print(maybe_transform(s))
