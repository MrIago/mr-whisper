#!/usr/bin/env python3
"""VoiceFlow daemon — ditado por voz system-wide (estilo Wispr Flow) p/ Linux/X11.

Arquitetura (anti-travamento):
- daemon (este): só evdev + estado + widget. Nunca carrega o modelo.
- transcribe_worker.py --serve: subprocesso separado com o modelo quente.
  A transcrição pesada roda LÁ, então o widget/evdev nunca congelam.
- widget.py: pill flutuante com waveform.

Controles:
- Segura Ctrl+Alt+Espaço → grava (hold-to-talk). Solta → transcreve + digita.
- ESC durante a transcrição → aborta (mata a request, esconde o widget).
- Auto-detect de idioma (mistura pt/en).
"""
from __future__ import annotations

import audioop
import os
import selectors
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import wave
from pathlib import Path

import evdev
from evdev import ecodes

import config
import dump
import translate

# ---- config ----
ARECORD_DEVICE = os.environ.get("VOICEFLOW_MIC", "default")
HERE = Path(__file__).parent
LOG = HERE / "daemon.log"
ASR_SOCK = "/tmp/mr-whisper-asr.sock"
TYPE_DELAY = os.environ.get("VOICEFLOW_TYPE_DELAY", "12")  # ms entre chars (0 grudava)

CTRL_KEYS = {ecodes.KEY_LEFTCTRL, ecodes.KEY_RIGHTCTRL}
ALT_KEYS = {ecodes.KEY_LEFTALT, ecodes.KEY_RIGHTALT}
TRIGGER_KEY = ecodes.KEY_SPACE
CANCEL_KEY = ecodes.KEY_ESC
MIN_HOLD = 0.3


def log(msg: str) -> None:
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


class Widget:
    def __init__(self) -> None:
        self.proc: subprocess.Popen | None = None
        self._start()

    def _start(self) -> None:
        try:
            self.proc = subprocess.Popen(
                [sys.executable, str(HERE / "widget.py")],
                stdin=subprocess.PIPE, text=True,
            )
        except Exception as exc:
            log(f"widget não iniciou: {exc}")
            self.proc = None

    def send(self, cmd: str) -> None:
        if not self.proc or self.proc.poll() is not None:
            self._start()
        if self.proc and self.proc.stdin:
            try:
                self.proc.stdin.write(cmd + "\n")
                self.proc.stdin.flush()
            except (BrokenPipeError, OSError):
                self._start()


class Recorder:
    def __init__(self, widget: Widget) -> None:
        self.widget = widget
        self.proc: subprocess.Popen | None = None
        self.wav_path: str | None = None
        self.started_at = 0.0
        self._stop_meter = threading.Event()

    def start(self) -> None:
        fd, path = tempfile.mkstemp(prefix="mr-whisper-", suffix=".wav")
        os.close(fd)
        self.wav_path = path
        self.started_at = time.time()
        self.proc = subprocess.Popen(
            ["arecord", "-D", ARECORD_DEVICE, "-f", "S16_LE", "-r", "16000",
             "-c", "1", "-t", "wav", path],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        self._stop_meter.clear()
        threading.Thread(target=self._meter, args=(path,), daemon=True).start()
        log(f"gravando → {path}")

    def _meter(self, path: str) -> None:
        last = 0
        time.sleep(0.12)
        while not self._stop_meter.is_set():
            try:
                with open(path, "rb") as f:
                    f.seek(last)
                    chunk = f.read()
                    last += len(chunk)
                if len(chunk) >= 2:
                    rms = audioop.rms(chunk[: len(chunk) - (len(chunk) % 2)], 2)
                    self.widget.send(f"level {min(1.0, rms / 8000.0):.3f}")
            except OSError:
                pass
            time.sleep(0.05)

    def stop(self) -> str | None:
        self._stop_meter.set()
        if not self.proc:
            return None
        self.proc.send_signal(signal.SIGINT)
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        path = self.wav_path
        self.proc = None
        self.wav_path = None
        return path


def wav_duration(path: str) -> float:
    try:
        with wave.open(path, "rb") as w:
            return w.getnframes() / float(w.getframerate() or 16000)
    except Exception:
        return 0.0


class ASRClient:
    """Fala com o transcribe_worker --serve via socket. Cancelável."""

    def __init__(self) -> None:
        self.proc: subprocess.Popen | None = None
        self._sock: socket.socket | None = None
        self._cancelled = False

    def start_server(self) -> None:
        env = dict(os.environ)
        self.proc = subprocess.Popen(
            [sys.executable, str(HERE / "transcribe_worker.py"), "--serve"],
            stdout=subprocess.PIPE, text=True, env=env,
        )
        # espera o ASR_READY
        assert self.proc.stdout
        for line in self.proc.stdout:
            if "ASR_READY" in line:
                log("modelo ASR pronto.")
                break
        threading.Thread(target=self._drain, daemon=True).start()

    def _drain(self) -> None:
        if self.proc and self.proc.stdout:
            for _ in self.proc.stdout:
                pass

    def transcribe(self, wav: str) -> str | None:
        """Bloqueia até o resultado; retorna None se cancelado."""
        self._cancelled = False
        try:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.settimeout(120)
            s.connect(ASR_SOCK)
            self._sock = s
            s.sendall(wav.encode("utf-8"))
            data = b""
            while True:
                chunk = s.recv(8192)
                if not chunk:
                    break
                data += chunk
            self._sock = None
            s.close()
            if self._cancelled:
                return None
            text = data.decode("utf-8", "replace")
            if text.startswith("\x00ERR:"):
                log(f"erro ASR: {text[5:]}")
                return ""
            return text
        except (OSError, socket.timeout) as exc:
            if self._cancelled:
                return None
            log(f"falha ASR socket: {exc}")
            return ""

    def cancel(self) -> None:
        self._cancelled = True
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass
        # mata o servidor (libera GPU) e religa — garante abortar trabalho preso
        if self.proc:
            try:
                self.proc.terminate()
                self.proc.wait(timeout=3)
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass
        log("transcrição cancelada — reiniciando ASR")
        self.start_server()


class CloudASRClient:
    """Transcrição via nuvem (Groq/OpenAI). Mesma interface do ASRClient, mas
    sem subprocesso/modelo local. Usado quando MRWHISPER_STT=groq."""

    def __init__(self) -> None:
        self.proc = None  # compat com cleanup() do daemon
        self._cancelled = False

    def start_server(self) -> None:
        log("transcrição via nuvem (Groq) — sem modelo local.")

    def transcribe(self, wav: str) -> str | None:
        self._cancelled = False
        try:
            import cloud
            text = cloud.transcribe_cloud(wav)
            if self._cancelled:
                return None
            return text
        except Exception as exc:
            if self._cancelled:
                return None
            log(f"falha STT nuvem: {exc}")
            return ""

    def cancel(self) -> None:
        # request HTTP não é interrompível aqui; marca e ignora o resultado.
        self._cancelled = True


# WM_CLASS (lowercase) de apps que usam Ctrl+Shift+V em vez de Ctrl+V.
TERMINAL_CLASSES = (
    "terminal", "gnome-terminal", "konsole", "xterm", "rxvt", "urxvt",
    "alacritty", "kitty", "wezterm", "st-256color", "tilix", "terminator",
    "foot", "xfce4-terminal", "guake", "yakuake", "ptyxis",
)


def _window_is_terminal(wid: str) -> bool:
    """True se a janela (por id) é um terminal (usa Ctrl+Shift+V pra colar)."""
    if not wid:
        return False
    try:
        out = subprocess.run(
            ["xprop", "-id", wid, "WM_CLASS"], capture_output=True, text=True, timeout=1
        ).stdout.lower()
    except (subprocess.SubprocessError, OSError):
        return False
    cls = out.split("=", 1)[1] if "=" in out else ""
    # VS Code tem terminal embutido, mas a classe é "code" — Ctrl+V funciona lá.
    return any(t in cls for t in TERMINAL_CLASSES)


def deliver_via_clipboard(text: str) -> None:
    """Copia o texto pro clipboard e cola na janela ativa, preservando o
    clipboard anterior. Usa Ctrl+Shift+V em terminais, Ctrl+V no resto.

    Pega a classe da janela ativa só pra decidir o atalho de colar; NÃO reativa
    a janela (windowactivate fazia o cursor interno do campo se perder). O foco
    nunca saiu do campo de texto, então colamos direto no foco atual.
    """
    # 1. captura a janela alvo agora (a que está focada quando soltamos a fala)
    try:
        wid = subprocess.run(
            ["xdotool", "getactivewindow"], capture_output=True, text=True, timeout=1
        ).stdout.strip()
    except (subprocess.SubprocessError, OSError):
        wid = ""

    is_term = _window_is_terminal(wid)

    # 2. coloca nosso texto no clipboard via gdbus/St.Clipboard (não xclip).
    #    Usamos o canal que o GNOME Shell "vê" nativamente, pra a extensão
    #    Clipboard Indicator selecionar nosso texto (igual a um Ctrl+C humano).
    #    NÃO restauramos o clipboard anterior: a restauração era justamente o
    #    que revertia a seleção (o texto ia só pro histórico, não como atual).
    _set_clipboard(text)
    time.sleep(0.18)  # deixa a extensão processar o owner-changed e selecionar

    # 3. cola — SEM windowactivate. Você nunca tirou o foco do campo de texto
    #    (só falou), então reativar a janela só fazia o cursor interno do
    #    editor/terminal se perder. Mandamos o paste direto no foco atual.
    # Solta modificadores que o X possa achar que ainda estão pressionados —
    # ao soltar Ctrl+Alt+Espaço, o estado do X dessincroniza do físico e o
    # Ctrl+V sintético colide com Ctrl/Alt "presos" → paste não dispara.
    subprocess.run(["xdotool", "keyup", "ctrl", "alt", "shift", "super"], check=False)
    time.sleep(0.05)
    # Ctrl+Shift+V sempre: terminais exigem, e editores/browsers aceitam como
    # "colar sem formatação". Mais universal que escolher por tipo de janela.
    combo = os.environ.get("VOICEFLOW_PASTE", "ctrl+shift+v")
    subprocess.run(["xdotool", "key", "--clearmodifiers", combo], check=False)


def _set_clipboard(text: str) -> None:
    """Escreve no clipboard. xclip é confiável pra ownership X11; mantemos ele,
    mas sem restaurar depois (o que sabotava a seleção da extensão)."""
    subprocess.run(
        ["xclip", "-selection", "clipboard"],
        input=text.encode("utf-8"), check=False,
    )


class VoiceFlow:
    def __init__(self) -> None:
        self.widget = Widget()
        stt = (config.get("MRWHISPER_STT", "local") or "local").lower()
        if stt == "groq":
            self.asr = CloudASRClient()
        else:
            self.asr = ASRClient()
        log(f"iniciando ASR (backend: {stt})…")
        self.asr.start_server()
        self.recorder = Recorder(self.widget)
        self.recording = False
        self.transcribing = False
        self.lock = threading.Lock()

    def press(self) -> None:
        with self.lock:
            if self.recording or self.transcribing:
                return
            self.recording = True
            self.recorder.start()
            self.widget.send("listening")

    def release(self) -> None:
        with self.lock:
            if not self.recording:
                return
            self.recording = False
            held = time.time() - self.recorder.started_at
            wav = self.recorder.stop()
            if held < MIN_HOLD or not wav:
                self.widget.send("hide")
                self._rm(wav)
                return
            self.transcribing = True
            self.widget.send("transcribing")
            threading.Thread(target=self._process, args=(wav,), daemon=True).start()

    def cancel(self) -> None:
        with self.lock:
            if not self.transcribing:
                return
            self.asr.cancel()
            self.transcribing = False
            self.widget.send("hide")

    def _process(self, wav: str) -> None:
        try:
            if wav_duration(wav) < 0.25:
                self.widget.send("hide")
                return
            t0 = time.time()
            text = self.asr.transcribe(wav)
            if text is None:  # cancelado
                return
            log(f"transcrito ({time.time()-t0:.1f}s): {text!r}")
            # dump: se a fala começa com "new dump"/"novo dump", salva a nota no
            # arquivo de dump em vez de colar. Não toca no clipboard.
            note = dump.parse(text) if text else None
            if note is not None:
                dump.save(note, log=log)
                self.widget.send("hide")
                return
            # auto-translate: se o texto começa com "auto translate {idioma}",
            # traduz o resto antes de colar (Groq/OpenRouter). Falha → original.
            if text and translate.parse(text):
                self.widget.send("transcribing")  # mantém o dock durante a tradução
                text = translate.maybe_translate(text, log=log)
            # esconde o dock antes de colar e cola — sem animação de paste
            # (o xdotool congela o X e travava o shimmer; não compensava).
            self.widget.send("hide")
            if text:
                self._type(text)
        finally:
            with self.lock:
                self.transcribing = False
            self._rm(wav)

    def _type(self, text: str) -> None:
        # Entrega via clipboard + paste (estilo Wispr): instantâneo mesmo em
        # textos longos, sem travar o input do X com centenas de keystrokes.
        deliver_via_clipboard(text)
        log(f"colado ({len(text)} chars)")

    @staticmethod
    def _rm(path: str | None) -> None:
        if path:
            try:
                os.unlink(path)
            except OSError:
                pass


def find_keyboards() -> list[evdev.InputDevice]:
    kbs = []
    for path in evdev.list_devices():
        try:
            d = evdev.InputDevice(path)
            keys = d.capabilities().get(ecodes.EV_KEY, [])
            if ecodes.KEY_SPACE in keys and ecodes.KEY_A in keys:
                kbs.append(d)
        except Exception:
            pass
    return kbs


def main() -> int:
    vf = VoiceFlow()
    keyboards = find_keyboards()
    if not keyboards:
        log("ERRO: nenhum teclado evdev acessível (grupo 'input'? relogar?).")
    else:
        log(f"escutando {len(keyboards)} teclado(s): {[k.name for k in keyboards]}")

    held = {"ctrl": False, "alt": False, "space": False}
    active = False

    def update():
        nonlocal active
        combo = held["ctrl"] and held["alt"] and held["space"]
        if combo and not active:
            active = True
            vf.press()
        elif not combo and active:
            active = False
            vf.release()

    sel = selectors.DefaultSelector()
    for kb in keyboards:
        sel.register(kb, selectors.EVENT_READ)

    def cleanup(*_):
        try:
            vf.widget.send("quit")
            if vf.asr.proc:
                vf.asr.proc.terminate()
        except Exception:
            pass
        sys.exit(0)

    signal.signal(signal.SIGTERM, cleanup)
    signal.signal(signal.SIGINT, cleanup)

    while True:
        for key, _ in sel.select(timeout=1):
            try:
                for event in key.fileobj.read():
                    if event.type != ecodes.EV_KEY:
                        continue
                    pressed = event.value in (1, 2)
                    code = event.code
                    if code in CTRL_KEYS:
                        held["ctrl"] = pressed
                    elif code in ALT_KEYS:
                        held["alt"] = pressed
                    elif code == TRIGGER_KEY:
                        held["space"] = pressed
                    elif code == CANCEL_KEY and event.value == 1:
                        vf.cancel()
                        continue
                    else:
                        continue
                    update()
            except OSError:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
