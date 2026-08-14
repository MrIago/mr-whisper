#!/usr/bin/env python3
"""Config do mr-whisper — lê/grava chaves e preferências de forma multiplataforma.

Espelha o padrão da skill `studio` (config.mjs): segredos e prefs ficam em
`~/.config/mr-whisper/.env` (privado), com fallback pra variável de ambiente.
Assim a transcrição via Groq e a tradução via Groq/OpenRouter funcionam em
Windows/Linux/Mac sem editar o shell.

  python config.py GROQ_API_KEY=gsk_...        # salva
  python config.py                             # lista o que está salvo

Chaves/prefs conhecidas:
- GROQ_API_KEY          — transcrição e/ou tradução via Groq
- OPENAI_API_KEY        — transcrição e/ou tradução via OpenAI
- OPENROUTER_KEY        — transcrição e/ou tradução via OpenRouter
- MRWHISPER_STT_PROVIDER — provider de transcrição: "groq" | "openai" | "openrouter"
- MRWHISPER_TRANSLATE   — backend dos comandos LLM: "groq" | "openrouter"
- MRWHISPER_DUMP_FILE   — arquivo de notas do comando "new dump" (default:
                          ~/Documentos/Notas/dump.md)
"""
from __future__ import annotations

import os
from pathlib import Path

CONFIG_FILE = Path.home() / ".config" / "mr-whisper" / ".env"


def _read_file() -> dict[str, str]:
    if not CONFIG_FILE.exists():
        return {}
    out: dict[str, str] = {}
    for raw in CONFIG_FILE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, val = line.partition("=")
        k = k.strip()
        val = val.strip()
        if len(val) >= 2 and val[0] in "\"'" and val[-1] == val[0]:
            val = val[1:-1]
        out[k] = val
    return out


def get(name: str, default: str | None = None) -> str | None:
    """Resolve env var > ~/.config/mr-whisper/.env > default."""
    env = os.environ.get(name)
    if env and env.strip():
        return env.strip()
    v = _read_file().get(name)
    return v.strip() if v and v.strip() else default


def set_values(pairs: dict[str, str]) -> None:
    """Grava pares no .env (mescla com o que já existe). Cria o dir se faltar."""
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    cur = _read_file()
    for k, v in pairs.items():
        if v:
            cur[k] = v
    body = (
        "# mr-whisper config — segredos e prefs, mantenha privado\n"
        + "\n".join(f"{k}={v}" for k, v in cur.items())
        + "\n"
    )
    CONFIG_FILE.write_text(body, encoding="utf-8")
    # 0600: só o dono lê (best-effort; em Windows é no-op silencioso).
    try:
        os.chmod(CONFIG_FILE, 0o600)
    except OSError:
        pass


# CLI: python config.py GROQ_API_KEY=gsk_...
if __name__ == "__main__":
    import sys

    pairs: dict[str, str] = {}
    for arg in sys.argv[1:]:
        if "=" in arg:
            k, _, v = arg.partition("=")
            pairs[k.strip()] = v.strip()
    if pairs:
        set_values(pairs)
        print(f"✓ salvo em {CONFIG_FILE}: {', '.join(pairs)}")
    else:
        cur = _read_file()
        if not cur:
            print("(nada salvo ainda) — uso: python config.py GROQ_API_KEY=gsk_...")
        else:
            for k in cur:
                shown = "set" if "KEY" in k else cur[k]
                print(f"{k}={shown}")
