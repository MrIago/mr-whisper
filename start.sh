#!/usr/bin/env bash
# Inicia o daemon do mr-whisper como serviço systemd --user, herdando o
# ambiente gráfico (DISPLAY/XAUTHORITY/dbus) da sessão — necessário para o
# widget GTK e o xdotool funcionarem.
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
systemctl --user import-environment DISPLAY XAUTHORITY XDG_RUNTIME_DIR DBUS_SESSION_BUS_ADDRESS 2>/dev/null || true
systemctl --user stop mr-whisper 2>/dev/null || true
exec systemd-run --user --unit=mr-whisper --collect \
  --setenv=DISPLAY="${DISPLAY:-:1}" \
  /usr/bin/python3 "$HERE/daemon.py"
