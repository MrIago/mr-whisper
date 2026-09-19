# CLAUDE.md

Instructions for Claude Code (or any coding agent) working in this repository.
The most common job is **installing or updating mr-whisper for the person at
this computer**. That is the first half of this file. Notes for changing the
code are at the end.

mr-whisper is a system-wide voice dictation app. Hold a hotkey, speak, release,
and the transcribed text is pasted where the cursor is. It lives in the tray or
menu bar, transcribes in the cloud with Groq (one free API key), and runs on
Linux, macOS and Windows.

## How to help someone install it

Do the work yourself and only stop to ask the person when a step needs them:
pasting their API key, clicking something in the OS privacy settings, or testing
the hotkey with their own voice. Show the output of each step.

1. Detect the OS and follow the matching section below.
2. Install from source into `~/mr-whisper` (`%USERPROFILE%\mr-whisper` on
   Windows). Source installs update with `git pull`, and on macOS they avoid the
   Gatekeeper warning that the unsigned `.dmg` triggers.
3. Configure the Groq key (section "The API key").
4. Set up launch at login.
5. Test with the person (section "The test that matters").

If a previous copy exists, **remove or stop it first**. Two copies running show
up as two microphone icons and fight over the hotkey.

### The API key

The app needs one key, from Groq, and the free tier is enough:
https://console.groq.com/keys

Never invent a key and never reuse one from another machine. Ask the person for
theirs, then write `~/.config/mr-whisper/.env` (on Windows:
`%USERPROFILE%\.config\mr-whisper\.env`):

```
GROQ_API_KEY=<the key they gave you>
MRWHISPER_STT_PROVIDER=groq
MRWHISPER_TRANSLATE=groq
```

If the file already exists, keep the existing `GROQ_API_KEY` and only make sure
the two `groq` lines are right. `MRWHISPER_TRANSLATE=openrouter` without an
OpenRouter key is a known way for the voice commands to break.

Alternatively, skip the file: on first launch with no key the app opens a short
setup wizard where the person pastes and validates the key themselves.

### macOS

Works on Apple Silicon and Intel.

Remove an old `.dmg` install if there is one: quit it from the microphone icon
in the menu bar, delete `mr-whisper.app` from `/Applications`, and unload any
old LaunchAgent (`ls ~/Library/LaunchAgents/ | grep -i whisper`).

Install:

```bash
curl -fsSL https://raw.githubusercontent.com/MrIago/mr-whisper/main/run/install-mac.sh | bash
```

That installs Homebrew, Python and git if missing, clones the repo to
`~/mr-whisper`, installs the dependencies and launches the app. If `pip` refuses
with `externally-managed-environment` (Homebrew Python), run the dependency step
yourself with the override:
`python3 -m pip install --user --break-system-packages -r ~/mr-whisper/requirements.txt`

Check that the native bridges import, because paste, focus handling and the
smooth animation depend on them:

```bash
python3 -c "import objc, Quartz; from AppKit import NSWorkspace; from Foundation import NSProcessInfo; print('pyobjc ok')"
```

If that fails: `python3 -m pip install --user pyobjc-framework-Cocoa pyobjc-framework-Quartz`.

Permissions. macOS asks for these once. Walk the person through System Settings
> Privacy & Security and have them enable the entry for the Python or terminal
that runs the app in each list, then restart the app:

- Microphone, so it can hear
- Accessibility, so it can send the paste
- Input Monitoring, so it can read the hotkey

Without Accessibility and Input Monitoring the app looks dead: no reaction to
the hotkey and no paste, with no error shown.

Launch at login: copy `run/mr-whisper.plist` to
`~/Library/LaunchAgents/com.mriago.mr-whisper.plist` and edit the two paths in
it. Use the **absolute path of the Python that has the packages** (the output of
`command -v python3`, usually `/opt/homebrew/bin/python3`), not the
`/usr/bin/python3` in the template, and the absolute path of `app.py`. Then:

```bash
launchctl load ~/Library/LaunchAgents/com.mriago.mr-whisper.plist
```

The plist uses `KeepAlive`, so to stop or update the app you must
`launchctl unload` it first. Killing the process alone makes launchd restart it.

Default hotkey: hold **Control + Option**, with no other key. The app has no
Dock icon, only the microphone in the menu bar. That is expected.

### Windows

Install Python 3 (python.org, tick "Add to PATH") and Git if missing, then:

```powershell
git clone https://github.com/MrIago/mr-whisper.git $env:USERPROFILE\mr-whisper
cd $env:USERPROFILE\mr-whisper
python -m pip install -r requirements.txt
```

Allow microphone access in Settings > Privacy & security > Microphone (desktop
apps must be allowed). The hotkey and the paste need no extra permission.

Run it without a console window:

```powershell
pythonw $env:USERPROFILE\mr-whisper\app.py
```

Launch at login: create a shortcut in the Startup folder (`shell:startup`) whose
target is the absolute path of `pythonw.exe` followed by the absolute path of
`app.py`, with "Start in" set to the repo folder.

Default hotkey: hold **Ctrl + Alt + Space**.

Known limit: dictating into a program that runs as Administrator does not work
from a normal session, because Windows blocks synthetic input into elevated
windows. That is a Windows rule, not an app bug.

### Linux

```bash
git clone https://github.com/MrIago/mr-whisper.git ~/mr-whisper
cd ~/mr-whisper
python3 -m pip install --user -r requirements.txt
sudo apt install alsa-utils xclip xdotool wl-clipboard
```

The hotkey reads the keyboard through evdev, so the user must be in the `input`
group: `sudo usermod -aG input $USER`, then log out and back in. Until they do,
nothing reacts to the hotkey.

On **Wayland** the compositor blocks synthetic key presses, so auto-paste needs
a one-time setup that installs ydotool with its daemon:

```bash
bash ~/mr-whisper/run/setup-linux-wayland.sh
```

Without it the text is still copied to the clipboard and the person pastes it
themselves. On X11 this step is not needed.

Start it: `bash ~/mr-whisper/run/start-linux.sh` (runs as a `systemd --user`
unit and inherits the graphical session).

Launch at login: create `~/.config/autostart/mr-whisper.desktop` with
`Exec=/bin/bash /home/<user>/mr-whisper/run/start-linux.sh` (absolute path).
Point it at the repo, never at a copied binary, so a reboot always runs the
current code.

Default hotkey: hold **Ctrl + Alt + Space**.

### The test that matters

After installing or updating, test with the person, in this order:

1. Exactly one process is running (`pgrep -fl mr-whisper`, or Task Manager on
   Windows) and there is one microphone icon.
2. They click into a text field (a notes app, a browser search box), hold the
   hotkey, speak a sentence, and release **without clicking anything else**.
3. While they speak, the floating pill shows a waveform. On release it shrinks
   into a circle with a spinner, then shows a "copied" icon.
4. The text appears in the field on its own, the cursor never left the field,
   nothing was typed while they held the hotkey, and the app is still running
   afterwards.

### Updating

```bash
cd ~/mr-whisper && git pull --ff-only
python3 -m pip install --user -q -r requirements.txt
python3 -c "from core.version import __version__; print(__version__)"
```

Stop the app before updating and start it again afterwards, the same way it
normally starts on that machine (on macOS: `launchctl unload`, update,
`launchctl load`). Compare the printed version with the latest release:
https://github.com/MrIago/mr-whisper/releases/latest

### Troubleshooting

| Symptom | Likely cause |
|---|---|
| Nothing happens on the hotkey (macOS) | Accessibility or Input Monitoring not granted to the Python that runs the app |
| Nothing happens on the hotkey (Linux) | user not in the `input` group, or did not log out and back in |
| Text is copied but not pasted (Linux) | Wayland without `run/setup-linux-wayland.sh` |
| Voice commands (auto translate) do nothing | `MRWHISPER_TRANSLATE` is not `groq`, or the key is invalid |
| Two microphone icons | two copies running: an old installed binary plus the repo |
| App restarts right after being killed (macOS) | the LaunchAgent has `KeepAlive`; `launchctl unload` it |
| App crashes after transcribing (macOS) | version older than 1.0.10; update |
| Text field loses focus while speaking (macOS) | version older than 1.0.12; update |
| Holding the hotkey types spaces | version older than 1.0.10 (macOS) or 1.0.13 (Windows); update |
| Worked once, then the hotkey stops responding while the app stays open (macOS) | version older than 1.0.14; macOS disabled the keyboard tap after a slow callback. Update |

To see who holds the focus on macOS while the hotkey is held:

```bash
sleep 4; osascript -e 'tell application "System Events" to get name of first process whose frontmost is true'
```

macOS crash reports live in `~/Library/Logs/DiagnosticReports/` (look for
`Python`). On Linux the log is `journalctl --user -u mr-whisper -n 50`.

## Using the app

- Hold the hotkey, speak, release. `Esc` cancels.
- The hotkey is changed in Settings > Hotkey by clicking the keys in order and
  pressing Save. Valid combos are one modifier plus a key, or two or more
  modifiers alone. It takes effect after quitting and reopening the app.
- Voice commands, said at the start of the speech. Anything said before the
  command is context for the model and is never pasted:
  - `auto translate <language>, ...` translates into that language
  - `auto context, ...` rewrites in the same language for the right tone
  - `auto adjust, ...` removes filler words and fixes punctuation
  - `reescreva, ...` rewrites in the same language with a light, friendly tone
  - `new dump, ...` saves a note instead of pasting (see Notes in the tray menu)

## If you are changing the code

- `core/` is portable logic (config, cloud calls, voice commands, updater).
  `platforms/` holds the per-OS I/O behind one interface (`base.py`): `linux.py`
  uses evdev, arecord and xdotool/ydotool; macOS and Windows share
  `_portable.py` (sounddevice, pynput, pyperclip). `ui/` is the PySide6 tray
  app. `app.py` wires them together.
- macOS native calls (AppKit, TSM, anything pyobjc) must run on the main thread
  or be thread-safe by design. An off-main-thread call crashed the app with
  SIGTRAP, and a native crash cannot be caught with try/except. The paste uses
  plain Quartz key events for this reason.
- The pill animation is driven by elapsed time, not by frame count. Keep it that
  way: macOS delays the timers of background apps.
- The tray icon is static per state. Do not animate it with `setIcon`; GNOME's
  indicator throttles updates and freezes on a frame. Animation belongs in the
  pill.
- User-facing strings are in English, with no em dashes and no emojis.
- Releasing: bump `core/version.py`, commit, then push a `vX.Y.Z` tag. The tag
  triggers `.github/workflows/build.yml`, which builds the four installers and
  publishes the release. If the release job fails on upload with a network
  timeout, download the artifacts of that run with `gh run download` and upload
  them with `gh release upload`.
- There is no automated test suite. Verify changes by running the app and, for
  code that only runs on another OS, by simulating the platform module before
  asking someone on that OS to test.
