#!/usr/bin/env python3
"""Setup interativo do mr-whisper, cross-platform (Linux/macOS/Windows).

Só nuvem: escolhe o provider de transcrição (Groq / OpenAI / OpenRouter), valida
a chave com um request real, e configura o backend dos comandos de LLM
(translate/context/adjust). Sem GPU, sem modelo local.

  python setup.py            # fluxo interativo
  python setup.py --status   # mostra a config atual

Tudo salvo em ~/.config/mr-whisper/.env (ver core/config.py).
"""
from __future__ import annotations

import sys

from core import config, cloud

PROVIDERS = {
    "groq": ("GROQ_API_KEY", "https://console.groq.com/keys",
             "grátis ~8h/dia, rápido, ótimo multilíngue", cloud.validate_groq),
    "openai": ("OPENAI_API_KEY", "https://platform.openai.com/api-keys",
               "whisper-1 / gpt-4o-transcribe (pago)", cloud.validate_openai),
    "openrouter": ("OPENROUTER_KEY", "https://openrouter.ai/keys",
                   "modelo multimodal (Gemini) via OpenRouter", cloud.validate_openrouter),
}


def ask(prompt: str) -> str:
    try:
        return input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        print("\n(cancelado)")
        sys.exit(1)


def ask_choice(prompt: str, options: dict[str, str]) -> str:
    print(prompt)
    keys = list(options)
    for i, k in enumerate(keys, 1):
        print(f"  {i}) {options[k]}")
    while True:
        a = ask("> ").lower()
        if a in options:
            return a
        if a.isdigit() and 1 <= int(a) <= len(keys):
            return keys[int(a) - 1]
        print("opção inválida.")


def setup_key(provider: str) -> bool:
    """Pede e valida a chave do provider (se ainda não houver uma válida)."""
    key_name, url, _desc, validate = PROVIDERS[provider]
    existing = config.get(key_name)
    if existing:
        ok, why = validate(existing)
        if ok:
            print(f"✓ {key_name} já configurada e válida.")
            return True
        print(f"{key_name} existente não validou ({why}). Vamos trocar.")
    print(f"\nPegue a chave em: {url}")
    while True:
        key = ask(f"Cole a {key_name}: ")
        if not key:
            print("vazio, tente de novo.")
            continue
        ok, why = validate(key)
        if ok:
            config.set_values({key_name: key})
            print(f"✓ {key_name} válida e salva.")
            return True
        print(f"✗ {why}, tente de novo.")


def setup_transcription() -> str:
    print("\n── 1/2 · Transcrição (nuvem) ──")
    provider = ask_choice(
        "Qual provider pra transcrever?",
        {k: f"{k}, {PROVIDERS[k][2]}" for k in PROVIDERS},
    )
    setup_key(provider)
    config.set_values({"MRWHISPER_STT_PROVIDER": provider})
    return provider


def setup_llm(stt_provider: str) -> None:
    """Backend dos comandos auto translate/context/adjust (Groq ou OpenRouter)."""
    print("\n── 2/2 · Comandos de voz (translate / context / adjust) ──")
    print('Ex: "auto translate english ...", "auto context ...", "auto adjust ...".')
    # se o provider de STT já serve de LLM (groq/openrouter), reusa por padrão.
    if stt_provider in ("groq", "openrouter"):
        choice = ask_choice(
            "Qual backend pros comandos de LLM?",
            {stt_provider: f"{stt_provider}, reusa a chave que você já configurou",
             "other": "escolher outro"},
        )
        backend = stt_provider if choice == stt_provider else None
    else:
        backend = None

    if backend is None:
        backend = ask_choice("Backend do LLM:", {
            "groq": "Groq, llama-3.3-70b (rápido, grátis)",
            "openrouter": "OpenRouter, Gemini Flash",
        })
        setup_key(backend)

    config.set_values({"MRWHISPER_TRANSLATE": backend})
    print(f"✓ comandos de LLM via {backend}.")


def status() -> None:
    print("\n── mr-whisper · configuração ──")
    print(f"  arquivo: {config.CONFIG_FILE}")
    print(f"  STT provider (MRWHISPER_STT_PROVIDER): {config.get('MRWHISPER_STT_PROVIDER', '(auto)')}")
    print(f"  LLM backend  (MRWHISPER_TRANSLATE):    {config.get('MRWHISPER_TRANSLATE', '(auto)')}")
    for _, (key_name, *_rest) in PROVIDERS.items():
        print(f"  {key_name}: {'✅' if config.get(key_name) else '⚪'}")
    print(f"  dump file (MRWHISPER_DUMP_FILE): {config.get('MRWHISPER_DUMP_FILE', '~/Documentos/Notas/dump.md')}")


def main() -> int:
    if "--status" in sys.argv:
        status()
        return 0
    print("╭─ mr-whisper setup ─────────────────────────────╮")
    print("│ cloud STT (groq/openai/openrouter) + commands  │")
    print("╰────────────────────────────────────────────────╯")
    provider = setup_transcription()
    setup_llm(provider)
    status()
    print("\n✓ Pronto. Inicie: run/start-<seu-os>.  (Linux: bash run/start-linux.sh)")
    print("  Instale as libs de I/O: pip install PySide6 sounddevice pynput pyperclip")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
