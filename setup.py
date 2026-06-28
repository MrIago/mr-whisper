#!/usr/bin/env python3
"""Setup interativo do mr-whisper — multiplataforma (Windows/Linux/Mac).

Roda determinístico: detecta o ambiente, decide o que perguntar, valida as
chaves de verdade antes de salvar. Fluxo:

1. Transcrição: detecta GPU (nvidia-smi) e se faster-whisper está instalado.
   - Sem GPU                → nem oferece local; vai direto pro Groq (nuvem).
   - GPU + tudo pronto      → pergunta: local (offline) ou Groq.
   - GPU mas falta algo     → mostra os comandos exatos por OS p/ instalar,
                              e oferece Groq agora (ou local depois de instalar).
2. Se escolher Groq: pede GROQ_API_KEY e VALIDA com um request real.
3. Tradução (auto-translate): pergunta se reusa a mesma chave Groq ou usa
   OpenRouter; valida a chave escolhida.

Tudo salvo em ~/.config/mr-whisper/.env (ver config.py). Re-rode quando quiser.
"""
from __future__ import annotations

import shutil
import subprocess
import sys

import config


def ask(prompt: str) -> str:
    try:
        return input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        print("\n(cancelado)")
        sys.exit(1)


def ask_choice(prompt: str, options: dict[str, str]) -> str:
    """Pergunta com opções rotuladas (key→descrição). Retorna a key escolhida."""
    print(prompt)
    keys = list(options)
    for i, k in enumerate(keys, 1):
        print(f"  {i}) {options[k]}")
    while True:
        ans = ask("> ").lower()
        if ans in options:
            return ans
        if ans.isdigit() and 1 <= int(ans) <= len(keys):
            return keys[int(ans) - 1]
        print("opção inválida.")


# ---- detecção de ambiente ----

def has_gpu() -> bool:
    if not shutil.which("nvidia-smi"):
        return False
    try:
        r = subprocess.run(["nvidia-smi"], capture_output=True, timeout=5)
        return r.returncode == 0
    except (subprocess.SubprocessError, OSError):
        return False


def has_faster_whisper() -> bool:
    try:
        import faster_whisper  # noqa: F401
        return True
    except Exception:
        return False


def install_hints() -> None:
    """Comandos por OS pra deixar a transcrição local pronta (GPU+CUDA)."""
    print("\nPra usar a transcrição LOCAL você precisa de:")
    print("  • faster-whisper (pip)")
    print("  • CUDA runtime compatível com a sua GPU NVIDIA\n")
    print("Instale o pacote Python (todos os OS):")
    print("  pip install faster-whisper\n")
    if sys.platform.startswith("linux"):
        print("CUDA no Linux: instale o toolkit da sua distro ou via NVIDIA:")
        print("  https://developer.nvidia.com/cuda-downloads")
    elif sys.platform == "win32":
        print("CUDA no Windows: baixe o instalador NVIDIA:")
        print("  https://developer.nvidia.com/cuda-downloads")
        print("  (e o driver NVIDIA mais recente)")
    elif sys.platform == "darwin":
        print("⚠️  macOS não tem CUDA (sem GPU NVIDIA). Use a transcrição via Groq.")
    print("\nDepois de instalar, re-rode: python setup.py")


# ---- passos ----

def setup_transcription() -> str:
    """Configura o backend de transcrição. Retorna 'local' ou 'groq'."""
    print("\n── 1/2 · Transcrição ──")
    gpu = has_gpu()
    fw = has_faster_whisper()

    if not gpu:
        print("Nenhuma GPU NVIDIA detectada → transcrição LOCAL não compensa.")
        print("Vamos usar o Groq (nuvem, grátis ~8h/dia, sem GPU).")
        setup_groq_key()
        config.set_values({"MRWHISPER_STT": "groq"})
        return "groq"

    if gpu and fw:
        choice = ask_choice(
            "GPU + faster-whisper prontos. Como transcrever?",
            {
                "instant": "instant — modelo pequeno, sensação imediata (boa precisão)",
                "pro": "pro — large-v3-turbo, máxima precisão (um pouco mais lento)",
                "groq": "groq — nuvem (grátis ~8h/dia; útil se quiser poupar a GPU)",
            },
        )
        if choice == "groq":
            setup_groq_key()
        config.set_values({"MRWHISPER_STT": choice})
        return choice

    # GPU mas falta faster-whisper (ou CUDA)
    print("GPU detectada, mas a transcrição local ainda não está pronta.")
    install_hints()
    choice = ask_choice(
        "\nO que fazer agora?",
        {
            "groq": "usar Groq agora (nuvem) — funciona já",
            "instant": "vou instalar o que falta e usar local instant (re-rode depois)",
            "pro": "vou instalar o que falta e usar local pro (re-rode depois)",
        },
    )
    if choice == "groq":
        setup_groq_key()
    config.set_values({"MRWHISPER_STT": choice})
    return choice


def setup_groq_key() -> None:
    """Pede e valida a GROQ_API_KEY (se ainda não houver uma válida)."""
    import cloud

    existing = config.get("GROQ_API_KEY")
    if existing:
        ok, why = cloud.validate_groq(existing)
        if ok:
            print("✓ GROQ_API_KEY já configurada e válida.")
            return
        print(f"GROQ_API_KEY existente não validou ({why}). Vamos trocar.")

    print("\nPegue uma chave grátis em: https://console.groq.com/keys")
    while True:
        key = ask("Cole a GROQ_API_KEY: ")
        if not key:
            print("vazio — tente de novo.")
            continue
        ok, why = cloud.validate_groq(key)
        if ok:
            config.set_values({"GROQ_API_KEY": key})
            print("✓ GROQ_API_KEY válida e salva.")
            return
        print(f"✗ {why} — tente de novo.")


def setup_openrouter_key() -> None:
    import cloud

    print("\nPegue uma chave em: https://openrouter.ai/keys")
    while True:
        key = ask("Cole a OPENROUTER_KEY: ")
        if not key:
            print("vazio — tente de novo.")
            continue
        ok, why = cloud.validate_openrouter(key)
        if ok:
            config.set_values({"OPENROUTER_KEY": key})
            print("✓ OPENROUTER_KEY válida e salva.")
            return
        print(f"✗ {why} — tente de novo.")


def setup_translation(stt_backend: str) -> None:
    """Configura o backend de tradução do auto-translate."""
    print("\n── 2/2 · Tradução (auto-translate) ──")
    print('Diga "auto translate {idioma}" no início da fala pra traduzir antes de colar.')

    has_groq = bool(config.get("GROQ_API_KEY"))
    if has_groq:
        choice = ask_choice(
            "Qual backend pra traduzir?",
            {
                "groq": "Groq — reusa a chave que você já configurou (llama-3.1-8b)",
                "openrouter": "OpenRouter — modelo barato dedicado (ex: Gemini Flash)",
            },
        )
    else:
        print("Sem chave Groq → tradução via OpenRouter.")
        choice = "openrouter"

    if choice == "openrouter" and not config.get("OPENROUTER_KEY"):
        setup_openrouter_key()
    if choice == "groq" and not config.get("GROQ_API_KEY"):
        setup_groq_key()

    config.set_values({"MRWHISPER_TRANSLATE": choice})
    print(f"✓ tradução via {choice}.")


def status() -> None:
    print("\n── mr-whisper · configuração atual ──")
    print(f"  arquivo: {config.CONFIG_FILE}")
    print(f"  transcrição (MRWHISPER_STT):   {config.get('MRWHISPER_STT', '(não definido)')}")
    print(f"  tradução   (MRWHISPER_TRANSLATE): {config.get('MRWHISPER_TRANSLATE', '(não definido)')}")
    print(f"  GROQ_API_KEY:  {'✅' if config.get('GROQ_API_KEY') else '⚪'}")
    print(f"  OPENROUTER_KEY: {'✅' if config.get('OPENROUTER_KEY') else '⚪'}")


def main() -> int:
    if "--status" in sys.argv:
        status()
        return 0
    print("╭─ mr-whisper setup ─────────────────────────────╮")
    print("│ transcrição (local/Groq) + auto-translate      │")
    print("╰────────────────────────────────────────────────╯")
    stt = setup_transcription()
    setup_translation(stt)
    status()
    print("\n✓ Tudo pronto. Inicie o daemon com: ./start.sh  (ou python daemon.py)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
