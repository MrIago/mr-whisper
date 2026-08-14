# PyInstaller spec — mr-whisper (cross-platform).
# Build local:  pyinstaller mr-whisper.spec
# O CI (.github/workflows/build.yml) roda isto em Linux/macOS/Windows e empacota
# o resultado em AppImage / .dmg / .exe.
import os
import sys
from PyInstaller.utils.hooks import collect_submodules

# macOS: buildar universal2 (Intel + Apple Silicon) num só binário, via env do CI.
# Fora do macOS o valor é ignorado.
_TARGET_ARCH = os.environ.get("MRW_MAC_ARCH") or None

hidden = []
# platforms/ é importado dinamicamente por sys.platform → força a inclusão.
hidden += ["platforms.linux", "platforms.macos", "platforms.windows",
           "platforms._portable"]
# libs de I/O que o PyInstaller às vezes não detecta:
hidden += collect_submodules("sounddevice")
hidden += collect_submodules("pynput")

a = Analysis(
    ["app.py"],
    pathex=["."],
    binaries=[],
    datas=[],
    hiddenimports=hidden,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "faster_whisper", "torch", "numpy.testing"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="mr-whisper",
    console=False,           # app de bandeja, sem janela de terminal
    disable_windowed_traceback=False,
    target_arch=_TARGET_ARCH,  # universal2 no CI macOS; None nos outros
    icon=None,
)
coll = COLLECT(
    exe, a.binaries, a.datas,
    name="mr-whisper",
)

# macOS: empacota como .app
if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="mr-whisper.app",
        icon=None,
        bundle_identifier="com.mriago.mr-whisper",
        info_plist={
            "LSUIElement": True,  # app de bandeja (sem ícone no Dock)
            "NSMicrophoneUsageDescription":
                "mr-whisper records your voice to transcribe it.",
        },
    )
