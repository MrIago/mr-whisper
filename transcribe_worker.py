#!/usr/bin/env python3
"""Worker de transcrição isolado — roda como subprocesso por gravação.

Mantém o trabalho pesado (faster-whisper) FORA do processo do daemon, pra que
o widget/evdev nunca congelem durante a transcrição. O daemon pode matar este
processo (SIGTERM) pra abortar (ESC).

Uso: transcribe_worker.py <wav_path>
Imprime o texto transcrito em stdout (uma linha). Exit 0 com texto, 0 vazio se
nada captado, !=0 em erro.

O modelo é mantido quente entre chamadas via um servidor persistente
(server mode) pra evitar recarregar a cada uso — ver --serve.
"""
import os
import sys
import socket
import signal

MODEL_NAME = os.environ.get("VOICEFLOW_MODEL", "large-v3-turbo")
MODEL_ID = os.environ.get(
    "VOICEFLOW_MODEL_ID", "deepdml/faster-whisper-large-v3-turbo-ct2"
)
DEVICE = os.environ.get("VOICEFLOW_DEVICE", "cuda")
COMPUTE_TYPE = os.environ.get("VOICEFLOW_COMPUTE", "int8_float16")
SERVE_SOCK = "/tmp/mr-whisper-asr.sock"


def load_model():
    from faster_whisper import WhisperModel
    try:
        return WhisperModel(MODEL_ID, device=DEVICE, compute_type=COMPUTE_TYPE)
    except Exception:
        return WhisperModel(MODEL_ID, device="cpu", compute_type="int8")


def transcribe(model, wav: str) -> str:
    segments, _info = model.transcribe(
        wav, language=None, beam_size=1, vad_filter=True,
        condition_on_previous_text=False,
    )
    return " ".join(s.text.strip() for s in segments).strip()


def serve():
    """Servidor ASR: mantém o modelo quente, transcreve sob demanda via socket.

    Protocolo: cliente conecta, envia o caminho do wav (utf-8), recebe o texto.
    """
    if os.path.exists(SERVE_SOCK):
        os.unlink(SERVE_SOCK)
    model = load_model()
    print("ASR_READY", flush=True)  # sinaliza ao daemon que o modelo carregou

    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(SERVE_SOCK)
    srv.listen(4)
    os.chmod(SERVE_SOCK, 0o600)

    def cleanup(*_):
        try:
            os.unlink(SERVE_SOCK)
        except OSError:
            pass
        sys.exit(0)

    signal.signal(signal.SIGTERM, cleanup)
    signal.signal(signal.SIGINT, cleanup)

    while True:
        conn, _ = srv.accept()
        with conn:
            wav = conn.recv(4096).decode("utf-8", "replace").strip()
            if not wav:
                continue
            try:
                text = transcribe(model, wav)
            except Exception as exc:
                conn.sendall(f"\x00ERR:{exc}".encode())
                continue
            conn.sendall(text.encode("utf-8"))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--serve":
        serve()
    else:
        m = load_model()
        print(transcribe(m, sys.argv[1]))
