"""Gemini voice catalog and credential-scoped local metadata storage."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .api_client import REST_URL, DirectApiError
from .constants import FALLBACK_VOICES, VOICE_SAMPLE_BASE

USER_AGENT = "NativeSpeechGeneration-NVDA-Addon"
CACHE_TTL = 24 * 60 * 60
MAX_CATALOG_PAGES = 100
MAX_SAMPLE_BYTES = 8 * 1024 * 1024
# Exact prebuilt names observed in AI Studio's catalog and verified on 2026-09-28.
# Do not extrapolate this path to regional catalog IDs or custom voices.
EXTENDED_SAMPLE_NAMES = [
	"Lumi",
	"Bodi",
	"Varo",
	"Sola",
	"Nika",
	"Zeno",
	"Tavi",
	"Koda",
	"Rina",
	"Mako",
	"Ludo",
	"Kira",
	"Brio",
	"Rami",
	"Veda",
	"Jori",
	"Enzo",
	"Zali",
	"Riko",
	"Sami",
	"Tari",
	"Neno",
	"Gero",
	"Olin",
	"Daro",
	"Fola",
	"Hali",
	"Milo",
	"Lora",
	"Arlo",
	"Finn",
	"Cleo",
	"Enya",
	"Jett",
	"Nyla",
	"Knox",
	"Tova",
	"Elio",
	"Cruz",
	"Zuri",
]
EXTENDED_SAMPLE_IDS = {
	identifier: f"en-us-{name.lower()}"
	for name in EXTENDED_SAMPLE_NAMES
	for identifier in (name.casefold(), f"en-us-{name.lower()}")
}


@dataclass(frozen=True)
class Voice:
	id: str
	displayName: str
	type: str = "prebuilt"
	language: str = ""
	accent: str = ""
	gender: str = ""
	description: str = ""
	pitch: str = ""
	persona: str = ""
	context: str = ""

	@classmethod
	def fromApi(cls, item: dict[str, Any], **fallbacks: str) -> Voice:
		"""Map an API voice resource to catalog metadata, ignoring non-string fields."""

		def field(name: str) -> str:
			value = item.get(name)
			return value if isinstance(value, str) else fallbacks.get(name, "")

		identifier = item["id"]
		return cls(
			id=identifier,
			displayName=field("display_name") or identifier,
			type=field("type") or "prebuilt",
			language=field("language_code"),
			accent=field("accent"),
			gender=field("gender"),
			description=field("description"),
			pitch=field("pitch"),
			persona=field("persona"),
			context=field("context"),
		)


def builtInVoices() -> list[Voice]:
	return [Voice(name, name) for name in FALLBACK_VOICES]


def fetchVoiceSample(apiKey: str, voice: Voice) -> bytes | None:
	"""Retrieve existing audio only; unsupported voices never trigger synthesis."""
	headers = {"User-Agent": USER_AGENT}
	if voice.type == "prompted":
		url = f"{REST_URL}/voices/{urllib.parse.quote(voice.id, safe='')}"
		headers["x-goog-api-key"] = apiKey
	elif voice.type == "prebuilt":
		name = next((name for name in FALLBACK_VOICES if name.casefold() == voice.id.casefold()), None)
		if name is not None:
			url = f"{VOICE_SAMPLE_BASE}/{name}.wav"
		elif voice.id.casefold() in EXTENDED_SAMPLE_IDS:
			url = f"{VOICE_SAMPLE_BASE}/daikon/{EXTENDED_SAMPLE_IDS[voice.id.casefold()]}.wav"
		else:
			return None
	else:
		return None
	request = urllib.request.Request(url, headers=headers, method="GET")
	try:
		with urllib.request.urlopen(request, timeout=15) as response:
			data = response.read(MAX_SAMPLE_BYTES + 1)
		if len(data) > MAX_SAMPLE_BYTES:
			raise DirectApiError("Voice sample is too large.")
		if voice.type == "prompted":
			result = json.loads(data.decode("utf-8"))
			if not isinstance(result, dict) or result.get("id") != voice.id:
				raise DirectApiError("Invalid voice sample response.")
			sample = result.get("sample_audio")
			if not sample:
				return None
			if not isinstance(sample, dict) or sample.get("mime_type") != "audio/wav":
				raise DirectApiError("Unsupported voice sample format.")
			encoded = sample.get("data")
			if not isinstance(encoded, str):
				raise DirectApiError("Invalid voice sample data.")
			data = base64.b64decode(encoded, validate=True)
		if not data:
			return None
		if data[:4] != b"RIFF" or data[8:12] != b"WAVE":
			raise DirectApiError("Invalid WAV sample.")
		return data
	except urllib.error.HTTPError as error:
		if error.code == 404:
			return None
		raise DirectApiError(f"Voice sample HTTP {error.code}", code=error.code) from None
	except (OSError, ValueError, binascii.Error) as error:
		raise DirectApiError("Unable to retrieve the voice sample.") from error


def filterVoices(
	voices: list[Voice],
	search: str = "",
	voiceType: str = "",
	languageCode: str | None = None,
	*,
	gender: str | None = None,
	pitch: str | None = None,
	persona: str | None = None,
	context: str | None = None,
) -> list[Voice]:
	terms = search.casefold().split()
	return [
		voice
		for voice in voices
		if (not voiceType or voice.type == voiceType)
		and (languageCode is None or voice.language.strip().casefold() == languageCode.strip().casefold())
		and all(
			selected is None or value.strip().casefold() == selected.strip().casefold()
			for value, selected in (
				(voice.gender, gender),
				(voice.pitch, pitch),
				(voice.persona, persona),
				(voice.context, context),
			)
		)
		and _matchesTerms(voice, terms)
	]


def _matchesTerms(voice: Voice, terms: list[str]) -> bool:
	if not terms:
		return True
	text = _searchText(voice)
	return all(term in text for term in terms)


def _searchText(voice: Voice) -> str:
	"""Every searchable field, casefolded, so each search term is a plain substring test."""
	return (
		f"{voice.id} {voice.displayName} {voice.language} {voice.accent} {voice.gender} "
		f"{voice.description} {voice.pitch} {voice.persona} {voice.context}"
	).casefold()


def _getCatalogPage(apiKey: str, pageToken: str) -> dict[str, Any]:
	parameters = {"page_size": "100"}
	if pageToken:
		parameters["page_token"] = pageToken
	request = urllib.request.Request(
		f"{REST_URL}/voices?{urllib.parse.urlencode(parameters)}",
		headers={"x-goog-api-key": apiKey, "User-Agent": USER_AGENT},
		method="GET",
	)
	try:
		with urllib.request.urlopen(request, timeout=30) as response:
			data = response.read(MAX_SAMPLE_BYTES + 1)
		if len(data) > MAX_SAMPLE_BYTES:
			raise DirectApiError("Voice library response is too large.")
		result = json.loads(data.decode("utf-8"))
	except urllib.error.HTTPError as error:
		# Do not expose the API key, URL, or server-echoed request data in logs/UI.
		raise DirectApiError(f"Voice library HTTP {error.code}", code=error.code) from None
	except (OSError, ValueError) as error:
		raise DirectApiError("Unable to load the voice library.") from error
	if not isinstance(result, dict) or result.get("error"):
		raise DirectApiError("Invalid voice library response.")
	return result


def fetchVoices(apiKey: str) -> list[Voice]:
	"""Fetch every page before replacing a cached catalog; never publish a partial list."""
	voices: dict[str, Voice] = {}
	pageToken = ""
	seenTokens: set[str] = set()
	for _page in range(MAX_CATALOG_PAGES):
		page = _getCatalogPage(apiKey, pageToken)
		items = page.get("voices", [])
		if not isinstance(items, list):
			raise DirectApiError("Invalid voice library list.")
		for item in items:
			if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item["id"].strip():
				raise DirectApiError("Invalid voice identifier in library.")
			voice = Voice.fromApi(item)
			voices[voice.id] = voice
		pageToken = page.get("next_page_token", "")
		if not pageToken:
			return list(voices.values())
		if not isinstance(pageToken, str) or pageToken in seenTokens:
			raise DirectApiError("Invalid voice library pagination.")
		seenTokens.add(pageToken)
	raise DirectApiError("Voice library pagination limit reached.")


def createStoredVoice(apiKey: str, voice: dict[str, Any], *, label: str, **fallbacks: str) -> Voice:
	"""POST one stored voice exactly once and keep only its catalog metadata.

	Never retry: a transport failure can still mean the server saved the voice.
	Errors never include the API key, request body, or server-echoed data.
	"""
	voiceType = voice["type"]
	request = urllib.request.Request(
		f"{REST_URL}/voices",
		data=json.dumps({"store": True, "voice": voice}).encode("utf-8"),
		headers={"x-goog-api-key": apiKey, "Content-Type": "application/json", "User-Agent": USER_AGENT},
		method="POST",
	)
	try:
		with urllib.request.urlopen(request, timeout=120) as response:
			data = response.read(MAX_SAMPLE_BYTES + 1)
		if len(data) > MAX_SAMPLE_BYTES:
			raise DirectApiError(f"{label} response is too large.")
		result = json.loads(data.decode("utf-8"))
	except urllib.error.HTTPError as error:
		raise DirectApiError(f"{label} HTTP {error.code}", code=error.code) from None
	except (OSError, ValueError):
		raise DirectApiError(f"Unable to confirm {label.lower()}.") from None
	if (
		not isinstance(result, dict)
		or result.get("error")
		or not isinstance(result.get("id"), str)
		or not result["id"].startswith("voice_")
		or len(result["id"]) <= len("voice_")
		or result.get("type", voiceType) != voiceType
	):
		raise DirectApiError(f"Invalid {label.lower()} response.")
	# Force the requested type; never keep a returned key, prompt, or audio.
	return Voice.fromApi(
		{**result, "type": voiceType},
		display_name=voice.get("display_name", ""),
		**fallbacks,
	)


class VoiceLibraryStore:
	"""Store metadata and selections separately, without persisting API keys or audio.

	The caller supplies NVDA's configuration directory only when disk writes are
	permitted. A None directory disables persistence.
	"""

	def __init__(self, apiKey: str, configPath: str | None) -> None:
		super().__init__()
		self.scope = hashlib.sha256(apiKey.encode("utf-8")).hexdigest()
		self.directory = Path(configPath) / "NativeSpeechGeneration" if configPath else None

	def _read(self, kind: str) -> dict[str, Any]:
		if self.directory is None:
			return {}
		try:
			value = json.loads((self.directory / f"{kind}-{self.scope}.json").read_text(encoding="utf-8"))
			return value if isinstance(value, dict) and value.get("version") == 1 else {}
		except (OSError, ValueError):
			return {}

	def _write(self, kind: str, value: dict[str, Any]) -> bool:
		if self.directory is None:
			return False
		tempPath: str | None = None
		try:
			self.directory.mkdir(parents=True, exist_ok=True)
			with tempfile.NamedTemporaryFile(
				mode="w",
				encoding="utf-8",
				dir=self.directory,
				delete=False,
			) as temp:
				tempPath = temp.name
				json.dump({"version": 1, **value}, temp, ensure_ascii=False)
			os.replace(tempPath, self.directory / f"{kind}-{self.scope}.json")
			return True
		except OSError:
			return False
		finally:
			if tempPath and os.path.exists(tempPath):
				try:
					os.remove(tempPath)
				except OSError:
					pass

	@staticmethod
	def _decodeVoice(value: Any) -> Voice | None:
		if not isinstance(value, dict) or not value.get("id") or not value.get("displayName"):
			return None
		if any(not isinstance(item, str) for item in value.values()):
			return None
		try:
			return Voice(**value)
		except TypeError:
			return None

	def readCatalog(self) -> tuple[list[Voice], bool]:
		value = self._read("voices")
		items = value.get("voices")
		if not isinstance(items, list):
			return [], False
		voices = [self._decodeVoice(item) for item in items]
		if any(voice is None for voice in voices):
			return [], False
		try:
			age = time.time() - float(value["fetchedAt"])
		except (KeyError, TypeError, ValueError):
			return [], False
		return [voice for voice in voices if voice is not None], (
			0 <= age < CACHE_TTL and value.get("catalogVersion") == 2
		)

	def writeCatalog(self, voices: list[Voice]) -> bool:
		return self._write(
			"voices",
			{"catalogVersion": 2, "fetchedAt": time.time(), "voices": [asdict(voice) for voice in voices]},
		)

	def rememberCreatedVoice(self, voice: Voice) -> bool:
		catalog, fresh = self.readCatalog()
		voices = [voice, *(item for item in catalog if item.id != voice.id)]
		# Adding a single result must neither make an absent or expired catalog look
		# complete nor extend the lifetime of the catalog it is added to.
		fetchedAt = self._read("voices").get("fetchedAt", 0) if fresh else 0
		return self._write(
			"voices",
			{
				"catalogVersion": 2,
				"fetchedAt": fetchedAt,
				"voices": [asdict(item) for item in voices],
			},
		)

	def readSelections(self) -> dict[str, Voice]:
		value = self._read("selections")
		result: dict[str, Voice] = {}
		for target in ("single", "speaker1", "speaker2"):
			voice = self._decodeVoice(value.get(target))
			if voice is not None:
				result[target] = voice
		return result

	def writeSelections(self, voices: dict[str, Voice]) -> bool:
		return self._write("selections", {target: asdict(voice) for target, voice in voices.items()})
