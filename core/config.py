#!/usr/bin/env python3
"""Config do mr-whisper, lê/grava chaves e preferências de forma multiplataforma.

Espelha o padrão da skill `studio` (config.mjs): segredos e prefs ficam em
`~/.config/mr-whisper/.env` (privado), com fallback pra variável de ambiente.
Assim a transcrição via Groq e a tradução via Groq/OpenRouter funcionam em
Windows/Linux/Mac sem editar o shell.

  python config.py GROQ_API_KEY=gsk_...        # salva
  python config.py                             # lista o que está salvo

Chaves/prefs conhecidas:
- GROQ_API_KEY         , transcrição e/ou tradução via Groq
- OPENAI_API_KEY       , transcrição e/ou tradução via OpenAI
- OPENROUTER_KEY       , transcrição e/ou tradução via OpenRouter
- MRWHISPER_STT_PROVIDER, provider de transcrição: "groq" | "openai" | "openrouter"
- MRWHISPER_LANG       , trava o idioma da transcrição (ex: "pt", "en"); vazio = auto
- MRWHISPER_TRANSLATE  , backend dos comandos LLM: "groq" | "openrouter"
- MRWHISPER_DUMP_FILE  , arquivo de notas do comando "new dump" (default:
                          ~/Documentos/Notas/dump.md)
- MRWHISPER_PASTE_SHORTCUT, atalho de colar: "ctrl+v" (default) | "ctrl+shift+v"
- MRWHISPER_AUTO_PASTE  , colar automático após transcrever: "1" (default) | "0"
                          (se "0", só copia pro clipboard, você cola manualmente)
- MRWHISPER_HOTKEY      , atalho hold-to-talk (ex: "ctrl+alt+space", "alt+r", ou só
                          modificadores, mínimo 2: "ctrl+alt"). Default:
                          Linux/Windows = "ctrl+alt+space"; macOS = "ctrl+alt"
                          (Control+Option, sem tecla: não digita nada enquanto
                          segura e não conflita com Spotlight/Raycast/ChatGPT).
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


def default_hotkey() -> str:
    """Atalho padrão por OS. No macOS é SÓ modificadores (Control+Option): segurar
    uma tecla comum digita ela sem parar no app em foco (Option+Espaço enchia o
    texto de espaços) e Option+Espaço ainda conflita com Raycast/ChatGPT/Claude.
    Modificador sozinho não digita nada. Nos demais, Ctrl+Alt+Espaço."""
    import sys
    return "ctrl+alt" if sys.platform == "darwin" else "ctrl+alt+space"


def hotkey_combo() -> tuple[set[str], str]:
    """Atalho hold-to-talk parseado: (set de modificadores, tecla). Ex:
    ({"ctrl","alt"}, "space"). A tecla pode ser "" quando o atalho é só de
    modificadores (mínimo 2, ex: ctrl+alt). Default: ver default_hotkey()."""
    default = default_hotkey()
    raw = (get("MRWHISPER_HOTKEY", default) or default).lower()
    parts = [p.strip() for p in raw.replace(" ", "").split("+") if p.strip()]
    _MODS = ("ctrl", "alt", "shift", "cmd", "super")
    # a tecla pode estar em qualquer posição (as pills salvam na ordem do clique,
    # ex: "ctrl+space+alt"): modificador é o que está em _MODS, tecla é o resto.
    mods = {p for p in parts if p in _MODS}
    keys = [p for p in parts if p not in _MODS]
    # válido: (>=1 modificador + 1 tecla) OU (>=2 modificadores, sem tecla).
    if mods and len(keys) == 1:
        return mods, keys[0]
    if len(mods) >= 2 and not keys:
        return mods, ""
    # inválido (sem modificador, 2 teclas, 1 modificador sozinho): volta pro default
    dparts = default.split("+")
    dmods = {p for p in dparts if p in _MODS}
    dkeys = [p for p in dparts if p not in _MODS]
    return dmods, (dkeys[0] if dkeys else "")


def hotkey_label() -> str:
    """Atalho atual em texto amigável, com os nomes de tecla do OS: no macOS
    "Control + Option", no Windows "Ctrl + Alt + Space" etc."""
    import sys
    if sys.platform == "darwin":
        names = {"ctrl": "Control", "alt": "Option", "shift": "Shift",
                 "cmd": "Command", "super": "Command"}
    elif sys.platform == "win32":
        names = {"ctrl": "Ctrl", "alt": "Alt", "shift": "Shift",
                 "cmd": "Win", "super": "Win"}
    else:
        names = {"ctrl": "Ctrl", "alt": "Alt", "shift": "Shift",
                 "cmd": "Super", "super": "Super"}
    mods, key = hotkey_combo()
    parts = [names[m] for m in ("ctrl", "alt", "shift", "cmd", "super") if m in mods]
    if key:
        parts.append(key.upper() if len(key) == 1 else key.capitalize())
    return " + ".join(dict.fromkeys(parts))


def set_values(pairs: dict[str, str]) -> None:
    """Grava pares no .env (mescla com o que já existe). Cria o dir se faltar."""
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    cur = _read_file()
    for k, v in pairs.items():
        if v:
            cur[k] = v
    body = (
        "# mr-whisper config, segredos e prefs, mantenha privado\n"
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
            print("(nada salvo ainda), uso: python config.py GROQ_API_KEY=gsk_...")
        else:
            for k in cur:
                shown = "set" if "KEY" in k else cur[k]
                print(f"{k}={shown}")
