#!/usr/bin/env python3
"""mr-whisper daemon — ditado por voz system-wide, cross-platform (Linux/Mac/Win).

Arquitetura:
- core/       → lógica portável: config, transcrição na nuvem (groq/openai/
                openrouter), comandos de LLM (translate/context/adjust), dump.
- platforms/  → I/O por SO (áudio, teclado hold-to-talk, paste). O daemon fala
                só com a interface platforms/base.py — não sabe o SO.
- widget_qt.py → pill flutuante (Qt), processo próprio, comandos via stdin.

Fluxo: segura Ctrl+Alt+Espaço → grava; solta → transcreve na nuvem → (comando?
dump/translate/context/adjust) → cola. ESC cancela.
"""
from __future__ import annotations

import subprocess
import sys
import threading
import time
import wave
from pathlib import Path

from core import config, cloud, dump, translate
from platforms import base

HERE = Path(__file__).parent
LOG = HERE / "daemon.log"
MIN_HOLD = 0.3


def log(msg: str) -> None:
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def wav_duration(path: str) -> float:
    try:
        with wave.open(path, "rb") as w:
            return w.getnframes() / float(w.getframerate() or 16000)
    except Exception:
        return 0.0


class Widget:
    """Controla o processo do widget Qt (widget_qt.py) via stdin."""

    def __init__(self) -> None:
        self.proc: subprocess.Popen | None = None
        self._start()

    def _start(self) -> None:
        try:
            self.proc = subprocess.Popen(
                [sys.executable, str(HERE / "widget_qt.py")],
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


class VoiceFlow:
    def __init__(self, platform: base.Platform) -> None:
        self.widget = Widget()
        self.recorder = platform.make_recorder(
            lambda lvl: self.widget.send(f"level {lvl:.3f}")
        )
        self.delivery = platform.make_delivery()
        provider = cloud._resolve_stt_provider()
        log(f"transcrição na nuvem: {provider}")
        self.recording = False
        self.transcribing = False
        self._cancel = False
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
            self._cancel = False
            self.widget.send("transcribing")
            threading.Thread(target=self._process, args=(wav,), daemon=True).start()

    def cancel(self) -> None:
        with self.lock:
            if not self.transcribing:
                return
            self._cancel = True
            self.transcribing = False
            self.widget.send("hide")

    def _process(self, wav: str) -> None:
        try:
            if wav_duration(wav) < 0.25:
                self.widget.send("hide")
                return
            t0 = time.time()
            try:
                text = cloud.transcribe_cloud(wav)
            except Exception as exc:
                log(f"falha STT: {exc}")
                self.widget.send("hide")
                return
            if self._cancel:
                return
            log(f"transcrito ({time.time()-t0:.1f}s): {text!r}")
            # dump: "new dump"/"novo dump" → salva a nota no arquivo, não cola.
            note = dump.parse(text) if text else None
            if note is not None:
                dump.save(note, log=log)
                self.widget.send("hide")
                return
            # comandos de LLM: translate/context/adjust transformam antes de colar.
            if text and translate.parse(text):
                self.widget.send("transcribing")  # mantém o dock durante o LLM
                text = translate.maybe_transform(text, log=log)
            self.widget.send("hide")
            if text and not self._cancel:
                self.delivery.deliver(text)
                log(f"colado ({len(text)} chars)")
        finally:
            with self.lock:
                self.transcribing = False
            self._rm(wav)

    @staticmethod
    def _rm(path: str | None) -> None:
        if path:
            try:
                import os
                os.unlink(path)
            except OSError:
                pass


def main() -> int:
    platform = base.get_platform()
    log(f"mr-whisper iniciando (plataforma: {platform.name})…")
    vf = VoiceFlow(platform)
    hotkey = platform.make_hotkey(vf.press, vf.release, vf.cancel)
    try:
        hotkey.run()  # bloqueia no loop de eventos de teclado
    except KeyboardInterrupt:
        pass
    finally:
        vf.widget.send("quit")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
