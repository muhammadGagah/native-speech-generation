import os

from logHandler import log

from .vendor_loader import load_runtime, runtime_scope

_CORE_DIR = os.path.dirname(os.path.abspath(__file__))
_PKG_DIR = os.path.dirname(_CORE_DIR)
_LIB_DIR = os.path.join(_PKG_DIR, "lib")
_RUNTIME = load_runtime(_LIB_DIR)

genai = _RUNTIME.genai
types = _RUNTIME.types
pyaudio = _RUNTIME.pyaudio
VENDOR_VERSIONS = dict(_RUNTIME.versions)
GENAI_IMPORT_ERROR = _RUNTIME.genaiError
PYAUDIO_IMPORT_ERROR = _RUNTIME.pyaudioError

GENAI_AVAILABLE = _RUNTIME.genaiAvailable
PYAUDIO_AVAILABLE = _RUNTIME.pyaudioAvailable

__all__ = [
	"GENAI_AVAILABLE",
	"GENAI_IMPORT_ERROR",
	"PYAUDIO_AVAILABLE",
	"PYAUDIO_IMPORT_ERROR",
	"VENDOR_VERSIONS",
	"genai",
	"getRuntimeScope",
	"pyaudio",
	"types",
]

if not GENAI_AVAILABLE:
	log.warning("google-genai not available via isolated vendor loader")
if not PYAUDIO_AVAILABLE:
	log.warning("PyAudio not available via isolated vendor loader")


def getRuntimeScope():
	return runtime_scope(_RUNTIME)
