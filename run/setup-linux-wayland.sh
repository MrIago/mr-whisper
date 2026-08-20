#!/usr/bin/env bash
# Configura o auto-paste do mr-whisper no Linux WAYLAND (GNOME, KDE, etc).
#
# No Wayland o compositor bloqueia injeção de teclas sintéticas por segurança —
# xdotool não cola. A solução é o ydotool + seu daemon (ydotoold), que injeta
# via /dev/uinput. Este script instala tudo e configura o acesso sem root.
#
# Rode UMA vez:  bash run/setup-linux-wayland.sh   (vai pedir a senha do sudo)
# Em X11 você NÃO precisa disto (xclip/xdotool já funcionam).
set -e

echo "▸ mr-whisper — setup do auto-paste no Wayland"

# 1. ydotool com daemon. O pacote do Ubuntu (0.1.8) NÃO tem o daemon e é
#    errático — compilamos a versão atual se o ydotoold não existir.
if ! command -v ydotoold >/dev/null 2>&1; then
  echo "▸ compilando ydotool (com daemon)…"
  sudo apt-get install -y git cmake gcc build-essential
  tmp="$(mktemp -d)"
  git clone --depth 1 https://github.com/ReimuNotMoe/ydotool.git "$tmp"
  ( cd "$tmp" && mkdir build && cd build && cmake .. -DBUILD_DOCS=OFF && make -j"$(nproc)" \
    && sudo install -m755 ydotool ydotoold /usr/local/bin/ )
  rm -rf "$tmp"
fi

# 2. acesso ao /dev/uinput sem root (grupo input + udev rule)
if ! id -nG "$USER" | grep -qw input; then
  echo "▸ adicionando você ao grupo 'input' (relogar depois)…"
  sudo usermod -aG input "$USER"
fi
echo 'KERNEL=="uinput", GROUP="input", MODE="0660", OPTIONS+="static_node=uinput"' \
  | sudo tee /etc/udev/rules.d/80-uinput.rules >/dev/null
sudo udevadm control --reload-rules && sudo udevadm trigger
sudo modprobe uinput
sudo chgrp input /dev/uinput 2>/dev/null || true
sudo chmod 660 /dev/uinput 2>/dev/null || true

# 3. ydotoold como serviço do usuário (sobe sozinho, socket acessível)
mkdir -p "$HOME/.config/systemd/user"
cat > "$HOME/.config/systemd/user/ydotoold.service" <<'EOF'
[Unit]
Description=ydotoold — daemon do ydotool (paste no Wayland)

[Service]
ExecStart=/usr/local/bin/ydotoold --socket-path=%t/.ydotool_socket --socket-own=%U:%G
Restart=always

[Install]
WantedBy=default.target
EOF
systemctl --user daemon-reload
systemctl --user enable --now ydotoold

echo "✓ pronto. Auto-paste no Wayland habilitado."
echo "  Se você acabou de entrar no grupo 'input', faça logout/login uma vez."
