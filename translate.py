#!/usr/bin/env python3
"""auto-translate do mr-whisper.

Quando você diz "auto translate {idioma}" na fala, o LLM:
1. trata TUDO que vem antes do comando como CONTEXTO/instrução (ex: "vou
   responder uma pessoa no LinkedIn") — usa pra acertar tom/registro, mas
   nunca coloca isso na saída;
2. traduz o que vem DEPOIS do idioma de forma ADAPTADA (localização natural):
   troca expressões por equivalentes idiomáticos, ajusta o registro
   (técnico/formal/casual) ao contexto detectado — não traduz literal.

O regex aqui só DETECTA o gatilho e o idioma; o trabalho de separar
contexto/mensagem e adaptar fica com o LLM (ver cloud.py).

Falha de tradução nunca te deixa sem nada: cai pro texto original.

Exemplos:
  "auto translate spanish, bom dia pessoal"                 → "buenos días a todos"
  "vou responder no LinkedIn, auto translate inglês, ..."   → tom profissional, EN
"""
from __future__ import annotations

import re

import cloud

# Janela do começo onde procuramos o gatilho. Como o que vem antes do comando
# agora é CONTEXTO (não lixo a cortar), damos uma folga generosa pra você poder
# falar uma instrução antes do "auto translate".
_SEARCH_WINDOW = 300

# Detecta "auto translate {idioma}" + captura idioma e onde o comando começa.
# Tolerante a caixa, hífen, pontuação do whisper e conector opcional (to/para/pra).
_TRIGGER = re.compile(
    r"""auto[\s\-]+translate              # "auto translate" / "auto-translate"
        [\s,:;.]+                          # pontuação/espaço após o comando
        (?:(?:to|para|pra)\s+)?            # conector opcional
        (?P<lang>[^\s,.:;!?]+)             # idioma = 1 palavra (spanish, japonês…)
        [\s,.:;!?]+                        # separador antes do conteúdo
        (?P<rest>.+)$                      # a mensagem a traduzir
    """,
    re.IGNORECASE | re.VERBOSE | re.DOTALL,
)


def parse(text: str) -> tuple[str, str, str] | None:
    """Se houver gatilho na janela inicial, retorna (idioma, contexto, mensagem):
    - idioma  : idioma-alvo falado
    - contexto: tudo dito ANTES do comando (instrução pro LLM; pode ser "")
    - mensagem: tudo DEPOIS do idioma (o que será traduzido/adaptado)
    Senão, None."""
    text = (text or "").strip()
    # só dispara se o comando começa dentro da janela inicial (evita disparar
    # com "auto translate" mencionado lá no meio de uma fala longa).
    head = _TRIGGER.search(text[:_SEARCH_WINDOW])
    if not head:
        return None
    # re-casa no texto COMPLETO a partir do comando, pra `rest` pegar tudo.
    m = _TRIGGER.search(text, head.start())
    if not m:
        return None
    lang = m.group("lang").strip()
    rest = m.group("rest").strip()
    context = text[: m.start()].strip()
    if not lang or not rest:
        return None
    return lang, context, rest


def maybe_translate(text: str, log=print) -> str:
    """Aplica auto-translate se o gatilho estiver presente. Sempre retorna texto
    colável: a tradução adaptada em sucesso, ou a mensagem original em falha."""
    parsed = parse(text)
    if not parsed:
        return text
    lang, context, rest = parsed
    try:
        out = cloud.translate_cloud(rest, lang, context=context)
        if out:
            log(f"auto-translate → {lang} (ctx={context!r}): {out!r}")
            return out
        log("auto-translate retornou vazio — colando original")
    except Exception as exc:  # rede/key/HTTP — nunca derruba o ditado
        log(f"auto-translate falhou ({exc}) — colando original")
    return rest


# CLI de teste: python translate.py "auto translate spanish hello world"
if __name__ == "__main__":
    import sys

    s = " ".join(sys.argv[1:]) or "auto translate spanish hello world"
    print(maybe_translate(s))
