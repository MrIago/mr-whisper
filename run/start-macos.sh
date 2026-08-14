#!/usr/bin/env bash
# Inicia o mr-whisper no macOS (foreground). Para autostart no login, instale o
# LaunchAgent: copie run/mr-whisper.plist para ~/Library/LaunchAgents/ e rode
#   launchctl load ~/Library/LaunchAgents/com.mriago.mr-whisper.plist
#
# Permissões (System Settings → Privacy & Security), uma vez:
#   Accessibility + Input Monitoring (pynput) e Microphone (sounddevice).
set -e
HERE="$(cd "$(dirname "$0")/.." && pwd)"
exec python3 "$HERE/app.py"
