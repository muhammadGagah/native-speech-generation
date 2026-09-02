import os

from logHandler import log

from .vendor_loader import load_runtime, runtime_scope

_CORE_DIR = os.path.dirname(os.path.abspath(__file__))
_PKG_DIR = os.path.dirname(_CORE_DIR)
_RUNTIME = load_runtime(os.path.join(_PKG_DIR, "lib"))

pyaudio = _RUNTIME.pyaudio
PYAUDIO_IMPORT_ERROR = _RUNTIME.pyaudioError
PYAUDIO_AVAILABLE = _RUNTIME.pyaudioAvailable

if not PYAUDIO_AVAILABLE:
	log.warning("PyAudio not available via isolated vendor loader")


def getRuntimeScope():
	return runtime_scope(_RUNTIME)


__all__ = ["PYAUDIO_AVAILABLE", "PYAUDIO_IMPORT_ERROR", "getRuntimeScope", "pyaudio"]
