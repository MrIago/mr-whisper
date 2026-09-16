#!/usr/bin/env python3
"""Checagem de atualização do mr-whisper.

Consulta a última release no GitHub e compara com a versão embutida. Não instala
nada (no macOS o Gatekeeper impede auto-instalar): apenas informa que há versão
nova e prepara o comando/URL pra o usuário atualizar. Best-effort: qualquer
falha (sem rede, rate limit) retorna "sem update", nunca quebra o app.
"""
from __future__ import annotations

import sys

import requests

from .version import __version__

REPO = "MrIago/mr-whisper"
RELEASES_PAGE = f"https://github.com/{REPO}/releases/latest"
PROJECT_PAGE = "https://mriago.com/projects/mr-whisper"


def _parse(v: str) -> tuple[int, ...]:
    v = v.strip().lstrip("vV")
    parts = []
    for p in v.split("."):
        num = "".join(ch for ch in p if ch.isdigit())
        parts.append(int(num) if num else 0)
    return tuple(parts) or (0,)


def latest_version() -> str | None:
    """Tag da última release (ex: '1.0.8'), ou None em falha."""
    try:
        r = requests.get(
            f"https://api.github.com/repos/{REPO}/releases/latest",
            headers={"Accept": "application/vnd.github+json",
                     "User-Agent": "mr-whisper"},
            timeout=8,
        )
        if not r.ok:
            return None
        tag = r.json().get("tag_name")
        return tag.lstrip("vV") if isinstance(tag, str) else None
    except requests.RequestException:
        return None


def check() -> str | None:
    """Retorna a versão nova se houver uma MAIOR que a atual; senão None."""
    latest = latest_version()
    if latest and _parse(latest) > _parse(__version__):
        return latest
    return None


def update_command() -> str:
    """Comando que atualiza a instalação a partir do código-fonte (o caminho que
    funciona no macOS sem Gatekeeper/assinatura). Colável no terminal."""
    if sys.platform == "darwin":
        return ("cd ~/mr-whisper 2>/dev/null && git pull && "
                "pip3 install -r requirements.txt && echo 'Reopen mr-whisper.'")
    if sys.platform == "win32":
        return "cd %USERPROFILE%\\mr-whisper && git pull && pip install -r requirements.txt"
    return ("cd ~/mr-whisper 2>/dev/null && git pull && "
            "pip install -r requirements.txt")
