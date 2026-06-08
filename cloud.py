#!/usr/bin/env python3
"""Clientes de nuvem do mr-whisper (HTTP puro via requests, sem SDK).

Espelha o padrão da skill `studio`:
- transcrição → Groq (preferido, grátis ~8h/dia, sem GPU) / OpenAI whisper-1.
- tradução    → Groq (chat completions, llama-3.1-8b-instant) / OpenRouter.

Sem GPU? a transcrição roda na nuvem. A tradução do auto-translate sempre é
nuvem (LLM barato). Tudo lê as chaves de config.get (env ou ~/.config/.env).
"""
from __future__ import annotations

import json
import os
import requests

from config import get

GROQ_STT_ENDPOINT = "https://api.groq.com/openai/v1/audio/transcriptions"
GROQ_CHAT_ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODELS_ENDPOINT = "https://api.groq.com/openai/v1/models"
OPENAI_STT_ENDPOINT = "https://api.openai.com/v1/audio/transcriptions"
OPENROUTER_CHAT_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"

GROQ_STT_MODEL = get("MRWHISPER_GROQ_STT_MODEL", "whisper-large-v3-turbo")
GROQ_LLM_MODEL = get("MRWHISPER_GROQ_LLM_MODEL", "llama-3.1-8b-instant")
OPENROUTER_LLM_MODEL = get("MRWHISPER_OR_MODEL", "google/gemini-2.5-flash")


# ---- validação de chave (usada pelo setup) ----

def validate_groq(key: str) -> tuple[bool, str]:
    """True + '' se a chave Groq autentica; False + motivo caso contrário."""
    try:
        r = requests.get(
            GROQ_MODELS_ENDPOINT,
            headers={"Authorization": f"Bearer {key}"},
            timeout=15,
        )
    except requests.RequestException as exc:
        return False, f"falha de rede: {exc}"
    if r.status_code == 200:
        return True, ""
    if r.status_code == 401:
        return False, "chave inválida (401)"
    return False, f"HTTP {r.status_code}: {r.text[:120]}"


def validate_openrouter(key: str) -> tuple[bool, str]:
    """True + '' se a chave OpenRouter autentica."""
    try:
        r = requests.get(
            "https://openrouter.ai/api/v1/key",
            headers={"Authorization": f"Bearer {key}"},
            timeout=15,
        )
    except requests.RequestException as exc:
        return False, f"falha de rede: {exc}"
    if r.status_code == 200:
        return True, ""
    if r.status_code == 401:
        return False, "chave inválida (401)"
    return False, f"HTTP {r.status_code}: {r.text[:120]}"


# ---- transcrição na nuvem ----

def transcribe_cloud(wav_path: str) -> str:
    """Transcreve um wav via Groq (ou OpenAI). Lança em erro de config/HTTP."""
    if get("GROQ_API_KEY"):
        endpoint, key, model = GROQ_STT_ENDPOINT, get("GROQ_API_KEY"), GROQ_STT_MODEL
        backend = "groq"
    elif get("OPENAI_API_KEY"):
        endpoint, key, model = OPENAI_STT_ENDPOINT, get("OPENAI_API_KEY"), "whisper-1"
        backend = "openai"
    else:
        raise RuntimeError(
            "transcrição na nuvem precisa de GROQ_API_KEY (ou OPENAI_API_KEY). "
            "Rode: python setup.py"
        )

    name = os.path.basename(wav_path)
    with open(wav_path, "rb") as f:
        files = {"file": (name, f, "audio/wav")}
        data = {"model": model, "response_format": "json", "temperature": "0"}
        r = requests.post(
            endpoint,
            headers={"Authorization": f"Bearer {key}"},
            files=files,
            data=data,
            timeout=120,
        )
    if not r.ok:
        raise RuntimeError(f"STT {backend} HTTP {r.status_code}: {r.text[:160]}")
    return (r.json().get("text") or "").strip()


# ---- tradução na nuvem ----

def _chat(endpoint: str, key: str, model: str, system: str, user: str,
          extra_headers: dict | None = None) -> str:
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.2,
        "max_completion_tokens": 2048,
        "stream": False,
    }
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if extra_headers:
        headers.update(extra_headers)
    r = requests.post(endpoint, headers=headers, data=json.dumps(body), timeout=60)
    if not r.ok:
        raise RuntimeError(f"chat HTTP {r.status_code}: {r.text[:160]}")
    d = r.json()
    return (d["choices"][0]["message"]["content"] or "").strip()


def translate_cloud(text: str, target_lang: str) -> str:
    """Traduz `text` pra `target_lang` via Groq ou OpenRouter (conforme config).

    Default de backend: groq (reusa a chave da transcrição). Lança em erro.
    """
    system = (
        "You are a translation engine. Translate the user's text into "
        f"{target_lang}. Output ONLY the translation — no quotes, no notes, "
        "no preamble. Preserve the original meaning, tone and formatting."
    )
    backend = (get("MRWHISPER_TRANSLATE", "groq") or "groq").lower()

    if backend == "openrouter":
        key = get("OPENROUTER_KEY")
        if not key:
            raise RuntimeError("MRWHISPER_TRANSLATE=openrouter mas falta OPENROUTER_KEY")
        return _chat(
            OPENROUTER_CHAT_ENDPOINT, key, OPENROUTER_LLM_MODEL, system, text,
            extra_headers={"HTTP-Referer": "https://github.com/MrIago/mr-whisper",
                           "X-Title": "mr-whisper"},
        )

    # default: groq
    key = get("GROQ_API_KEY")
    if not key:
        raise RuntimeError("tradução via Groq precisa de GROQ_API_KEY. Rode: python setup.py")
    return _chat(GROQ_CHAT_ENDPOINT, key, GROQ_LLM_MODEL, system, text)
