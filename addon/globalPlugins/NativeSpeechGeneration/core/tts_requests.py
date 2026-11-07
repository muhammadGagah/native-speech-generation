"""Structured Gemini 3.8 TTS requests, independent of NVDA and the network."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

FLASH_38_TTS_MODEL = "gemini-3.8-flash-tts"
FLASH_LITE_38_TTS_MODEL = "gemini-3.8-flash-lite-tts"
STRUCTURED_TTS_MODELS = (FLASH_LITE_38_TTS_MODEL, FLASH_38_TTS_MODEL)


class SpeechInputError(ValueError):
	"""A preflight error the GUI can translate without parsing exception text."""

	def __init__(self, reason: str, *, speakerIndex: int | None = None, lineNumber: int | None = None):
		super().__init__(reason)
		self.reason = reason
		self.speakerIndex = speakerIndex
		self.lineNumber = lineNumber


@dataclass(frozen=True)
class SpeechTurn:
	text: str
	speaker: str | None = None


def parseSpeechTurns(text: str, speakerNames: Sequence[str] = ()) -> list[SpeechTurn]:
	"""Parse one labeled turn per nonblank line, or preserve single-speaker text.

	Speaker labels are case-sensitive and may not contain colons or line breaks.
	Requiring a label on every line avoids guessing who should read a continuation.
	Only the first colon separates the label; punctuation and vocal tags stay intact.
	"""
	if not text.strip():
		raise SpeechInputError("emptyText")
	if not speakerNames:
		return [SpeechTurn(text)]
	if len(speakerNames) != 2:
		raise SpeechInputError("speakerCount")
	seenNames: set[str] = set()
	for index, name in enumerate(speakerNames):
		if not name.strip() or name != name.strip() or any(char in name for char in ":\r\n"):
			raise SpeechInputError("invalidSpeakerName", speakerIndex=index)
		if name.casefold() in seenNames:
			raise SpeechInputError("duplicateSpeakerName", speakerIndex=index)
		seenNames.add(name.casefold())
	turns: list[SpeechTurn] = []
	for lineNumber, line in enumerate(text.splitlines(), start=1):
		if not line.strip():
			continue
		label, separator, utterance = line.partition(":")
		if not separator or label.strip() not in speakerNames:
			raise SpeechInputError("invalidSpeakerLabel", lineNumber=lineNumber)
		if not utterance.strip():
			raise SpeechInputError("emptyTurn", lineNumber=lineNumber)
		turns.append(SpeechTurn(utterance.strip(), label.strip()))
	return turns


def buildTtsPayload(
	model: str,
	text: str,
	voiceNames: Sequence[str],
	*,
	speakerNames: Sequence[str] = (),
	styleInstructions: str = "",
	temperature: float = 1.0,
) -> dict[str, Any]:
	"""Build an Interactions request without mixing directions into the transcript."""
	if len(voiceNames) not in (1, 2) or any(not voice.strip() for voice in voiceNames):
		raise SpeechInputError("voiceCount")
	if len(voiceNames) == 2 and len(speakerNames) != 2:
		raise SpeechInputError("speakerCount")
	if len(voiceNames) == 1 and speakerNames:
		raise SpeechInputError("speakerCount")
	turns = parseSpeechTurns(text, speakerNames)
	content: list[dict[str, Any]] = []
	for turn in turns:
		metadata = {"type": "speech_metadata"}
		if turn.speaker is not None:
			metadata["speaker"] = turn.speaker
		if styleInstructions.strip():
			metadata["style"] = styleInstructions.strip()
		part: dict[str, Any] = {"type": "text", "text": turn.text}
		if len(metadata) > 1:
			part["annotations"] = [metadata]
		content.append(part)
	speechConfig: Any = [{"voice": voiceNames[0]}]
	if len(voiceNames) == 2:
		speechConfig = {
			"mode": "conversational",
			"speakers": [
				{"speaker": speaker, "voice": voice} for speaker, voice in zip(speakerNames, voiceNames)
			],
		}
	return {
		"model": model,
		"input": [{"type": "user_input", "content": content}],
		"response_format": {"type": "audio", "mime_type": "audio/wav"},
		"generation_config": {"temperature": temperature, "speech_config": speechConfig},
	}
