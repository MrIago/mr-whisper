#!/usr/bin/env bash
# Instala e roda o mr-whisper no macOS a partir do código-fonte (roda nativo em
# Intel e Apple Silicon). Uso:
#   curl -fsSL https://raw.githubusercontent.com/MrIago/mr-whisper/main/run/install-mac.sh | bash
set -e

echo "▸ mr-whisper — instalação (macOS)"

# 1. Homebrew (se faltar)
if ! command -v brew >/dev/null 2>&1; then
  echo "▸ instalando Homebrew…"
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
fi

# 2. Python + git
command -v python3 >/dev/null 2>&1 || brew install python
command -v git >/dev/null 2>&1 || brew install git

# 3. baixar/atualizar o repo em ~/mr-whisper
DIR="$HOME/mr-whisper"
if [ -d "$DIR/.git" ]; then
  echo "▸ atualizando $DIR…"; git -C "$DIR" pull --ff-only
else
  echo "▸ clonando em $DIR…"; git clone https://github.com/MrIago/mr-whisper.git "$DIR"
fi

# 4. dependências
echo "▸ instalando dependências…"
python3 -m pip install --user -q -r "$DIR/requirements.txt"

# 5. rodar
echo "▸ pronto. abrindo o app (ícone 🎙️ na barra de menu)…"
echo "  Se o macOS pedir permissões (Microfone, Acessibilidade, Input Monitoring),"
echo "  libere em System Settings › Privacy & Security e rode de novo:"
echo "    python3 $DIR/app.py"
exec python3 "$DIR/app.py"
