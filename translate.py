#!/usr/bin/env python3
"""auto-translate do mr-whisper.

Se "auto translate {idioma}" aparece no começo da transcrição (não precisa ser
o caractere 0 — o whisper às vezes deixa um resquício antes, tipo "é... auto
translate spanish ..."), descartamos tudo que vem ANTES do comando e traduzimos
tudo que vem DEPOIS do idioma (via Groq/OpenRouter — ver cloud.py) antes de
colar. Senão, devolve o texto intacto. Falha de tradução nunca te deixa sem
nada: cai pro texto original.

Exemplos que disparam:
  "auto translate spanish. hello world"          → "hola mundo"
  "é, auto translate to português, good night"   → "boa noite"  (resquício cortado)
  "auto translate japonês meu nome é iago"       → tradução em japonês
"""
from __future__ import annotations

import re

import cloud

# Janela do começo onde procuramos o gatilho (preâmbulo/resquício cabe aqui).
_SEARCH_WINDOW = 160

# só pra LOCALIZAR onde "auto translate" começa (dentro da janela inicial).
_COMMAND_START = re.compile(r"auto[\s\-]+translate", re.IGNORECASE)

# "auto translate" tolerante a: caixa, hífen, pontuação que o whisper insere,
# e conectores opcionais (to / para / pra). Captura idioma e o restante.
# Aplicado com .match(text, pos) → ancora na posição do comando (sem ^).
_TRIGGER = re.compile(
    r"""auto[\s\-]+translate              # "auto translate" / "auto-translate"
                                           #   (exige separador → "autotranslate" não vale)
        [\s,:;.]+                          # pontuação/espaço após o comando
        (?:(?:to|para|pra)\s+)?            # conector opcional ("to"/"para"/"pra")
        (?P<lang>[^\s,.:;!?]+)             # idioma = 1 palavra (spanish, japonês…)
        [\s,.:;!?]+                        # separador antes do conteúdo
        (?P<rest>.+)$                      # o que traduzir
    """,
    re.IGNORECASE | re.VERBOSE | re.DOTALL,
)


def parse(text: str) -> tuple[str, str] | None:
    """Retorna (idioma, conteúdo) se o gatilho aparece nos primeiros ~100 chars;
    senão None. Tudo antes do comando é descartado; traduz tudo após o idioma."""
    text = text or ""
    # localiza o início de "auto translate" só na janela inicial — assim um
    # "auto translate" dito no meio de uma fala longa (não comando) não dispara.
    head = _COMMAND_START.search(text[:_SEARCH_WINDOW])
    if not head:
        return None
    # aplica o gatilho a partir do comando, sobre o texto COMPLETO (rest inteiro).
    m = _TRIGGER.match(text, head.start())
    if not m:
        return None
    lang = m.group("lang").strip()
    rest = m.group("rest").strip()
    if not lang or not rest:
        return None
    return lang, rest


def maybe_translate(text: str, log=print) -> str:
    """Aplica auto-translate se o gatilho estiver presente. Sempre retorna texto
    colável: a tradução em sucesso, ou o conteúdo original em falha."""
    parsed = parse(text)
    if not parsed:
        return text
    lang, rest = parsed
    try:
        out = cloud.translate_cloud(rest, lang)
        if out:
            log(f"auto-translate → {lang}: {out!r}")
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
