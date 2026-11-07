"""Explicit creation of persistent Gemini designed voices. Never retry a POST."""

from __future__ import annotations

import re
from typing import Any

from .api_client import DirectApiError
from .tts_requests import STRUCTURED_TTS_MODELS
from .voice_library import Voice, createStoredVoice

__all__ = [
	"REMIX_MODEL",
	"DirectApiError",
	"canRemix",
	"createDesignedVoice",
	"createRemixedVoice",
	"validateDesign",
	"validateRemix",
]

# The only documented creation model for remixes; the result works with every 3.8 TTS model.
REMIX_MODEL = "gemini-3.8-flash-tts"
MAX_INSTRUCTION_LENGTH = 2000


def validateDesign(name: str, description: str, language: str) -> str | None:
	if not name.strip() or len(name.strip()) > 100:
		return "name"
	if not description.strip() or len(description.strip()) > 2000:
		return "description"
	if language.strip() and not re.fullmatch(r"[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*", language.strip()):
		return "language"
	return None


def createDesignedVoice(
	apiKey: str,
	model: str,
	name: str,
	description: str,
	language: str = "",
	gender: str = "",
) -> Voice:
	"""Create once; transport failures can still mean the server saved the voice."""
	if validateDesign(name, description, language) or model not in STRUCTURED_TTS_MODELS:
		raise ValueError("Invalid voice design input.")
	if gender not in ("", "female", "male", "neutral"):
		raise ValueError("Invalid voice gender.")
	voice: dict[str, Any] = {
		"type": "prompted",
		"model": model,
		"display_name": name.strip(),
		"prompted": {"input": description.strip()},
	}
	if language.strip():
		voice["language_code"] = language.strip()
	if gender:
		voice["gender"] = gender
	return createStoredVoice(
		apiKey,
		voice,
		label="Voice design",
		language_code=language.strip(),
		gender=gender,
	)


def canRemix(voice: Voice) -> bool:
	"""Prebuilt, catalog, designed, and remixed voices are documented remix sources; replicated are not."""
	return voice.type in ("prebuilt", "prompted") and bool(voice.id.strip())


def validateRemix(name: str, instructions: str) -> str | None:
	if len(name.strip()) > 100:
		return "name"
	if not instructions.strip() or len(instructions.strip()) > MAX_INSTRUCTION_LENGTH:
		return "instructions"
	return None


def createRemixedVoice(apiKey: str, baseVoice: Voice, name: str, instructions: str) -> Voice:
	"""Store a new voice derived from baseVoice; the base voice is never modified.

	The name is optional because display_name is not documented for remixes; it is
	sent only when the user provides one.
	"""
	if validateRemix(name, instructions) or not canRemix(baseVoice):
		raise ValueError("Invalid voice remix input.")
	voice: dict[str, Any] = {
		"type": "prompted",
		"model": REMIX_MODEL,
		"prompted": {"base_voice": baseVoice.id.strip(), "input": instructions.strip()},
	}
	if name.strip():
		voice["display_name"] = name.strip()
	# Remixes keep the base language unless asked otherwise. Accent, gender, and the
	# rest are what remixing changes, so they come only from the server response.
	return createStoredVoice(apiKey, voice, label="Voice remix", language_code=baseVoice.language)
