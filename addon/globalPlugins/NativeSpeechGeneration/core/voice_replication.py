"""Create a stored replicated voice from reference and consent recordings."""

from __future__ import annotations

import base64
import io
import wave

from .api_client import DirectApiError
from .tts_requests import STRUCTURED_TTS_MODELS
from .voice_library import Voice, createStoredVoice

__all__ = ["DirectApiError", "RecordingError", "createReplicatedVoice", "readRecording"]

MAX_RECORDING_BYTES = 4 * 1024 * 1024


class RecordingError(ValueError):
	def __init__(self, field: str):
		super().__init__("Invalid replication recording.")
		self.field = field


def readRecording(path: str, field: str) -> str:
	"""Bound reads and validate PCM before encoding; never retain audio on disk."""
	try:
		with open(path, "rb") as source:
			data = source.read(MAX_RECORDING_BYTES + 1)
		if len(data) > MAX_RECORDING_BYTES:
			raise ValueError
		with wave.open(io.BytesIO(data), "rb") as audio:
			frames = audio.getnframes()
			if (
				audio.getnchannels() != 1
				or audio.getsampwidth() != 2
				or audio.getframerate() != 24000
				or audio.getcomptype() != "NONE"
				or frames <= 0
				or (field == "source" and not 10 <= frames / 24000 <= 30)
				or (field == "consent" and frames / 24000 > 60)
				or len(audio.readframes(frames)) != frames * 2
			):
				raise ValueError
	except (OSError, ValueError, EOFError, wave.Error):
		raise RecordingError(field) from None
	return base64.b64encode(data).decode("ascii")


def createReplicatedVoice(apiKey: str, model: str, name: str, sourcePath: str, consentPath: str) -> Voice:
	"""Submit both recordings once; Google performs speaker and consent verification."""
	if not name.strip() or len(name.strip()) > 100 or model not in STRUCTURED_TTS_MODELS:
		raise ValueError("Invalid replication input.")
	source = readRecording(sourcePath, "source")
	consent = readRecording(consentPath, "consent")
	voice = {
		"type": "replicated",
		"model": model,
		"display_name": name.strip(),
		"replicated": {
			"source_audio": {"mime_type": "audio/wav", "data": source},
			"consent_audio": {"mime_type": "audio/wav", "data": consent},
		},
	}
	return createStoredVoice(apiKey, voice, label="Voice replication")
