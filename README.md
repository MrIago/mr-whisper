# mr-whisper 🎙️

**System-wide voice dictation — cross-platform, free-tier, private-ish.** A [Wispr Flow](https://wisprflow.ai/) alternative that runs on **Linux, macOS and Windows**.

Hold a hotkey, speak, release. Your speech is transcribed in the cloud (Groq / OpenAI / OpenRouter — your key, your choice) and pasted into whatever text field is focused — terminal, editor, browser, any app. On top of plain dictation it can **translate**, **rewrite for tone**, **clean up filler**, or **save quick notes** — all by voice.

![Python](https://img.shields.io/badge/python-3.10+-blue.svg)
![Platform](https://img.shields.io/badge/platform-Linux%20%C2%B7%20macOS%20%C2%B7%20Windows-orange.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)

---

## Demo

https://github.com/user-attachments/assets/d6d28e50-0b61-4729-8d9e-31074602c61e

> _Hold `Ctrl+Alt+Space`, speak in Portuguese or English (mixed is fine), release. The text appears where your cursor is._ ▸ 🎤 waveform reacts to your voice ▸ ⟳ transcribing ▸ ✓ text pasted at the cursor.

## Why

Wispr Flow is great but it's paid (~$15/mo) and has no Linux build. I wanted the same "press, talk, it types" experience on every OS I use — for free, on Groq's generous free tier — plus voice commands Wispr doesn't have (translate, rewrite, quick-notes). So I built it.

## How it works

```
core/        portable logic — config, cloud STT, LLM commands, quick-notes
platforms/   per-OS I/O behind one interface (audio · hotkey · paste)
  ├─ linux.py    arecord · evdev · xclip/xdotool (X11)
  ├─ macos.py    sounddevice · pynput · pbcopy + Cmd+V
  └─ windows.py  sounddevice · pynput · clipboard + Ctrl+V
widget_qt.py floating pill (PySide6/Qt) — live waveform, then a spinner
daemon.py    thin orchestrator: detects the OS, wires core + platform + widget
```

The daemon talks only to the platform interface, so the same flow runs
everywhere. Transcription is cloud-only (no GPU, no local model) — that's what
makes it work identically on the three OSes. **Text delivery** is clipboard +
paste (instant even for long text).

## Requirements

- Python 3.10+
- A cloud key for transcription (any one): **Groq** (free tier — recommended), OpenAI, or OpenRouter.
- I/O libraries (all OSes):

```bash
pip install PySide6 sounddevice pynput pyperclip requests
```

**Linux** also uses X11 tools and evdev (raw key access needs the `input` group):

```bash
sudo apt install xdotool xclip
sudo usermod -aG input $USER   # then re-login
```

**macOS**: grant Terminal (or your launcher) **Accessibility**, **Input
Monitoring** and **Microphone** in System Settings → Privacy & Security.

## Setup

```bash
python setup.py          # pick STT provider, paste + validate your key
python setup.py --status # show current config
```

## Run

```bash
bash run/start-linux.sh        # Linux — systemd --user service
bash run/start-macos.sh        # macOS — foreground (LaunchAgent for autostart)
run\start-windows.ps1          # Windows — foreground (Task Scheduler for autostart)
```

**Usage:** hold `Ctrl+Alt+Space`, speak, release. `ESC` cancels mid-transcription.

## Voice features

### Transcription providers

Pick one with `MRWHISPER_STT_PROVIDER` (or in `setup.py`):

| Provider | Endpoint | Notes |
|---|---|---|
| `groq` | Whisper `large-v3-turbo` | **free tier ~8h/day**, fast, great multilingual — recommended |
| `openai` | Whisper `whisper-1` | paid |
| `openrouter` | Gemini (multimodal) | pay-per-use, one key for STT + commands |

All cloud, so no GPU and identical behavior on every OS.

### Auto-translate

Say **"auto translate {language}"** in your dictation and the rest is
**localized** into that language before it's pasted — any language, just say it:

> _"auto translate spanish — good morning everyone"_ → pastes **"buenos días a todos"**

It's not a literal translation — an LLM **adapts** the text: idiomatic
expressions become their native equivalent, and the tone/register (technical,
formal, casual) is matched to the situation.

**Speak context first.** Anything you say *before* "auto translate" is treated
as context for the model (to pick the right tone) and is **never** pasted:

> _"I'm replying to someone on LinkedIn, auto translate english, e aí, bora marcar uma call"_
> → pastes a polished, professional English message — the LinkedIn note is dropped.

It runs through a cheap LLM. By default it **reuses your Groq key**
(`llama-3.3-70b-versatile`); the setup can also point it at **OpenRouter** (e.g.
Gemini Flash) if you prefer. If the translation call fails (offline / no key),
your original words are pasted instead — you never lose the dictation.

### Rewrite in place — "auto context" & "auto adjust"

Same idea as auto-translate, but they **stay in your language**:

- **"auto context"** — rewrites what follows to read naturally and hit the right
  tone/register for the situation. Speak context first (never pasted):
  > _"texting my boss about a raise, auto context, hey man, let's bump up my salary?"_
  > → pastes **"I'd like to discuss the possibility of a salary adjustment."**
- **"auto adjust"** — the lightest touch: strips filler and speech tics
  (_"uh, um, like, you know"_), fixes punctuation and grammar, but **keeps your
  words and meaning**:
  > _"auto adjust, so, uh, like, the thing is, you know, we need to ship this by friday"_
  > → pastes **"The thing is, we need to ship this by Friday."**

All three (`translate` / `context` / `adjust`) share the same LLM and fall back
to your original words on any failure. Keywords are tolerant (case, hyphen,
glued, and PT variants like "auto contexto" / "auto ajusta").

Keys and preferences are stored in `~/.config/mr-whisper/.env` (private).

### Quick notes — "new dump"

Start your dictation with **"new dump"** (or **"novo dump"**) and the rest isn't
pasted — it's appended, with a timestamp, to your personal notes file. Perfect
for jotting a quick idea mid-task without leaving the window:

> _"new dump — cache the transcription by wav hash"_ → appends to `dump.md`:
> `- [2026-06-27 20:23] cache the transcription by wav hash`

Point it at your file with `MRWHISPER_DUMP_FILE` (default
`~/Documentos/Notas/dump.md`). The folder is created if missing.

```bash
python -m core.config MRWHISPER_DUMP_FILE=/path/to/your/notes.md
```

## Configuration

| Env var | Default | Description |
|---|---|---|
| `MRWHISPER_STT_PROVIDER` | auto | `groq`, `openai`, or `openrouter` (auto = first key found) |
| `MRWHISPER_TRANSLATE` | auto | LLM backend for voice commands: `groq` or `openrouter` |
| `GROQ_API_KEY` | — | Groq STT and/or commands ([get one](https://console.groq.com/keys)) |
| `OPENAI_API_KEY` | — | OpenAI STT ([get one](https://platform.openai.com/api-keys)) |
| `OPENROUTER_KEY` | — | OpenRouter STT and/or commands ([get one](https://openrouter.ai/keys)) |
| `MRWHISPER_DUMP_FILE` | `~/Documentos/Notas/dump.md` | notes file for the "new dump" command |
| `VOICEFLOW_MIC` | `default` | Linux only — ALSA capture device for `arecord` |
| `VOICEFLOW_PASTE` | `ctrl+shift+v` | Linux only — paste shortcut for `xdotool` |

> These are usually set by `python setup.py` (saved to `~/.config/mr-whisper/.env`), but env vars override the file.

## Roadmap

- [x] Cloud transcription (Groq / OpenAI / OpenRouter — no GPU)
- [x] Auto-translate ("auto translate {language}" → translated before paste)
- [x] Rewrite commands ("auto context" adapts tone · "auto adjust" cleans filler)
- [x] Quick notes ("new dump" → appended to your notes file instead of pasted)
- [x] Cross-platform: Linux, macOS, Windows (one platform interface)
- [ ] Wayland support (`ydotool`/portal-based input)
- [ ] Configurable hotkey + tray settings UI
- [ ] Push-to-talk vs toggle modes

## Tech stack

Python · Groq / OpenAI / OpenRouter (cloud STT + LLM) · PySide6 (Qt widget) · pynput · sounddevice · pyperclip · evdev / arecord / xdotool (Linux path) · systemd / LaunchAgent / Task Scheduler

## License

MIT © [Iago Lima Toledo](https://github.com/MrIago)
