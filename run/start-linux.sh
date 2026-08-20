#!/usr/bin/env bash
# Inicia o mr-whisper como serviço systemd --user, herdando o ambiente gráfico
# (DISPLAY/XAUTHORITY/dbus) da sessão, necessário para o widget Qt e o paste.
set -e
HERE="$(cd "$(dirname "$0")/.." && pwd)"
systemctl --user import-environment DISPLAY XAUTHORITY XDG_RUNTIME_DIR DBUS_SESSION_BUS_ADDRESS 2>/dev/null || true
systemctl --user stop mr-whisper 2>/dev/null || true
exec systemd-run --user --unit=mr-whisper --collect \
  --setenv=DISPLAY="${DISPLAY:-:1}" \
  "$(command -v python3)" "$HERE/app.py"
