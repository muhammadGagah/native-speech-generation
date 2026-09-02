from __future__ import annotations

import asyncio
import base64
import io
import struct
import threading
import wave
from collections.abc import Callable
from typing import Any

import addonHandler
import api
import config as nvdaConfig
import controlTypes
import nvwave
import speech
import textInfos
import ui
import wx
from logHandler import log

from . import config_store
from .api_client import DirectApiError, DirectLiveSession, generate_tts
from .audio_utils import parseAudioMimeType
from .constants import LIVE_MODEL, NATIVE_AUDIO_25_MODEL

LIVE_RESPONSE_TIMEOUT = 60.0
LIVE_RESPONSE_TIMEOUT_PER_CHARACTER = 0.08
LIVE_RESPONSE_TIMEOUT_MAX = 300.0

addonHandler.initTranslation()


class QuickSpeakInputError(RuntimeError):
	"""An actionable problem with the requested Quick Speak input."""


class QuickSpeakPlaybackError(RuntimeError):
	"""A sanitized wrapper for local audio output failures."""


def getSelectedText() -> str:
	"""Return only the actual selection from the focused object or its tree interceptor."""
	focus = api.getFocusObject()
	if focus is None:
		raise QuickSpeakInputError(_("No selected text was found."))
	if _isProtectedObject(focus):
		raise QuickSpeakInputError(_("Quick Speak cannot read text from a protected field."))

	treeInterceptor = getattr(focus, "treeInterceptor", None)
	sources = (focus,) if getattr(treeInterceptor, "passThrough", False) else (treeInterceptor, focus)
	for source in sources:
		if source is None or _isProtectedObject(source):
			continue
		try:
			textInfo = source.makeTextInfo(textInfos.POSITION_SELECTION)
		except (AttributeError, LookupError, NotImplementedError, RuntimeError):
			continue
		text = getattr(textInfo, "text", "")
		if isinstance(text, str) and text.strip():
			return text.strip()
	raise QuickSpeakInputError(_("No selected text was found."))


def getClipboardText() -> str:
	"""Return plain text from NVDA's clipboard API without coercing other formats."""
	try:
		value = api.getClipData()
	except (OSError, RuntimeError):
		value = None
	if not isinstance(value, str) or not value.strip():
		raise QuickSpeakInputError(_("The clipboard does not contain text."))
	return value.strip()


def decodeAudioForPlayback(audioData: bytes, mimeType: str) -> tuple[bytes, int, int, int]:
	"""Return PCM frames and WavePlayer parameters for Gemini audio."""
	if not audioData:
		raise DirectApiError("Gemini returned empty audio data.")
	if audioData.startswith(b"RIFF") or "wav" in (mimeType or "").lower():
		try:
			with wave.open(io.BytesIO(audioData), "rb") as wavFile:
				if wavFile.getcomptype() != "NONE":
					raise DirectApiError("Gemini returned compressed WAV audio.")
				return (
					wavFile.readframes(wavFile.getnframes()),
					wavFile.getnchannels(),
					wavFile.getframerate(),
					wavFile.getsampwidth() * 8,
				)
		except (EOFError, wave.Error) as error:
			raise DirectApiError("Gemini returned invalid WAV audio.") from error

	normalizedMime = (mimeType or "").lower()
	if normalizedMime and not any(marker in normalizedMime for marker in ("pcm", "audio/l", "audio/raw")):
		raise DirectApiError("Gemini returned an unsupported audio format.")
	params = parseAudioMimeType(mimeType)
	return audioData, 1, params["rate"], params["bitsPerSample"]


class QuickSpeakController:
	"""Run one focus-preserving Quick Speak request at a time."""

	def __init__(self) -> None:
		super().__init__()
		self._lock = threading.RLock()
		self._token = 0
		self._active = False
		self._session: DirectLiveSession | None = None
		self._player: Any | None = None

	@property
	def isActive(self) -> bool:
		with self._lock:
			return self._active

	def start(self, text: str) -> None:
		cleanText = text.strip()
		if not cleanText:
			raise QuickSpeakInputError(_("No text was provided for Quick Speak."))
		with self._lock:
			self._token += 1
			token = self._token
			self._active = True
		threading.Thread(target=self._run, args=(token, cleanText), daemon=True).start()

	def stop(self) -> bool:
		with self._lock:
			wasActive = self._active
			self._token += 1
			self._active = False
			session = self._session
			player = self._player
			self._session = None
			self._player = None
		if session is not None:
			try:
				session.abort()
			except Exception as error:
				log.debug(f"Failed to abort Quick Speak Live session: {error}", exc_info=True)
		_closePlayer(player)
		return wasActive

	def _run(self, token: int, text: str) -> None:
		player = None
		session = None
		try:
			apiResolution = config_store.resolveApiKey()
			if not apiResolution.value:
				raise QuickSpeakInputError(
					_("No Gemini API key is configured. Set it in NVDA settings before using Quick Speak."),
				)
			settings = config_store.getQuickSpeakSettings()
			if settings.model in (LIVE_MODEL, NATIVE_AUDIO_25_MODEL):
				session = DirectLiveSession(
					apiResolution.value,
					settings.model,
					settings.voice,
					_buildLiveInstruction(settings.styleInstructions),
					thinking_level="high" if settings.model == LIVE_MODEL else None,
				)
				if not self._setSessionIfCurrent(token, session):
					return
				asyncio.run(self._runLive(token, session, text, settings.volume))
			else:
				audioData, mimeType = generate_tts(
					apiResolution.value,
					settings.model,
					text,
					[settings.voice],
					style_instructions=settings.styleInstructions,
				)
				if not self._isCurrent(token):
					return
				frames, channels, sampleRate, bitsPerSample = decodeAudioForPlayback(audioData, mimeType)
				player = self._createPlayer(token, channels, sampleRate, bitsPerSample)
				if player is None:
					return
				if not self._feedIfCurrent(
					token,
					player,
					frames,
					cancelSpeech=True,
					bitsPerSample=bitsPerSample,
					volume=settings.volume,
				):
					return
				self._idlePlayer(player)
		except QuickSpeakInputError as error:
			self._queueError(token, str(error))
		except QuickSpeakPlaybackError as error:
			log.error(f"Quick Speak audio playback failed: {error}", exc_info=True)
			self._queueError(
				token,
				_("Quick Speak audio could not be played. Check NVDA's audio output device."),
			)
		except DirectApiError as error:
			log.error(f"Quick Speak Gemini request failed: {error}", exc_info=True)
			self._queueError(token, _describeApiError(error))
		except Exception as error:
			log.error(f"Unexpected Quick Speak failure: {error}", exc_info=True)
			self._queueError(token, _("Quick Speak failed. Check your connection and try again."))
		finally:
			if session is not None:
				try:
					session.abort()
				except Exception:
					pass
			_closePlayer(player)
			self._finishIfCurrent(token)

	async def _runLive(
		self,
		token: int,
		session: DirectLiveSession,
		text: str,
		volume: int = 100,
	) -> None:
		await session.connect()
		if not self._isCurrent(token):
			return
		await session.send_client_content(
			[{"role": "user", "parts": [{"text": text}]}],
			turn_complete=True,
		)
		try:
			await asyncio.wait_for(
				self._receiveLiveAudio(token, session, volume),
				timeout=_getLiveResponseTimeout(text),
			)
		except TimeoutError as error:
			raise DirectApiError("Live API response timed out.") from error

	async def _receiveLiveAudio(self, token: int, session: DirectLiveSession, volume: int = 100) -> None:
		player = None
		receivedAudio = False
		try:
			async for message in session.receive():
				if not self._isCurrent(token):
					return
				if "error" in message:
					error = message.get("error")
					raise DirectApiError(str(error.get("message") if isinstance(error, dict) else error))
				serverContent = message.get("serverContent")
				if not isinstance(serverContent, dict):
					continue
				modelTurn = serverContent.get("modelTurn")
				if isinstance(modelTurn, dict):
					parts = modelTurn.get("parts")
					if isinstance(parts, list):
						for part in parts:
							if not isinstance(part, dict):
								continue
							inlineData = part.get("inlineData")
							if not isinstance(inlineData, dict):
								continue
							encoded = inlineData.get("data")
							if not isinstance(encoded, str):
								continue
							try:
								audioData = base64.b64decode(encoded, validate=True)
							except (ValueError, TypeError) as error:
								raise DirectApiError("Gemini returned invalid Live audio data.") from error
							mimeType = str(inlineData.get("mimeType") or "audio/pcm;rate=24000")
							frames, channels, sampleRate, bitsPerSample = decodeAudioForPlayback(
								audioData,
								mimeType,
							)
							if player is None:
								player = self._createPlayer(token, channels, sampleRate, bitsPerSample)
								if player is None:
									return
							if not self._feedIfCurrent(
								token,
								player,
								frames,
								cancelSpeech=not receivedAudio,
								bitsPerSample=bitsPerSample,
								volume=volume,
							):
								return
							receivedAudio = True
				if serverContent.get("turnComplete"):
					break
			if not receivedAudio:
				raise DirectApiError("Gemini returned no audio data.")
			if player is not None and self._isCurrent(token):
				self._idlePlayer(player)
		finally:
			_closePlayer(player)

	def _createPlayer(
		self,
		token: int,
		channels: int,
		sampleRate: int,
		bitsPerSample: int,
	) -> Any | None:
		outputDevice = _getNvdaOutputDevice()
		try:
			player = nvwave.WavePlayer(
				channels=channels,
				samplesPerSec=sampleRate,
				bitsPerSample=bitsPerSample,
				outputDevice=outputDevice,
			)
		except Exception as error:
			log.warning(f"Quick Speak could not use NVDA's configured output device: {error}")
			try:
				player = nvwave.WavePlayer(
					channels=channels,
					samplesPerSec=sampleRate,
					bitsPerSample=bitsPerSample,
				)
			except Exception as fallbackError:
				raise QuickSpeakPlaybackError("WavePlayer could not be created.") from fallbackError
		with self._lock:
			if token != self._token or not self._active:
				_closePlayer(player)
				return None
			self._player = player
		return player

	def _feedIfCurrent(
		self,
		token: int,
		player: Any,
		frames: bytes,
		*,
		cancelSpeech: bool,
		bitsPerSample: int = 16,
		volume: int = 100,
	) -> bool:
		frames = _scalePcmVolume(frames, bitsPerSample, volume)
		firstChunk = True
		for offset in range(0, len(frames), 32768):
			chunk = frames[offset : offset + 32768]
			with self._lock:
				if token != self._token or not self._active or self._player is not player:
					return False
				try:
					if cancelSpeech and firstChunk:
						speech.cancelSpeech()
					player.feed(chunk)
				except Exception as error:
					raise QuickSpeakPlaybackError("WavePlayer could not feed audio.") from error
			firstChunk = False
		return True

	def _idlePlayer(self, player: Any) -> None:
		try:
			player.idle()
		except Exception as error:
			raise QuickSpeakPlaybackError("WavePlayer could not finish playback.") from error

	def _setSessionIfCurrent(self, token: int, session: DirectLiveSession) -> bool:
		with self._lock:
			if token != self._token or not self._active:
				return False
			self._session = session
			return True

	def _isCurrent(self, token: int) -> bool:
		with self._lock:
			return token == self._token and self._active

	def _queueError(self, token: int, message: str) -> None:
		wx.CallAfter(self._announceErrorIfCurrent, token, message)

	def _announceErrorIfCurrent(self, token: int, message: str) -> None:
		with self._lock:
			if token != self._token:
				return
		ui.message(message)

	def _finishIfCurrent(self, token: int) -> None:
		with self._lock:
			if token != self._token:
				return
			self._active = False
			self._session = None
			self._player = None


def _isProtectedObject(obj: Any) -> bool:
	states = getattr(obj, "states", ()) or ()
	stateEnum = getattr(controlTypes, "State", None)
	protectedState = getattr(stateEnum, "PROTECTED", None)
	legacyProtectedState = getattr(controlTypes, "STATE_PROTECTED", None)
	roleEnum = getattr(controlTypes, "Role", None)
	passwordRole = getattr(roleEnum, "PASSWORDEDIT", None)
	legacyPasswordRole = getattr(controlTypes, "ROLE_PASSWORDEDIT", None)
	role = getattr(obj, "role", None)
	return (
		(protectedState is not None and protectedState in states)
		or (legacyProtectedState is not None and legacyProtectedState in states)
		or (passwordRole is not None and role == passwordRole)
		or (legacyPasswordRole is not None and role == legacyPasswordRole)
	)


def _buildLiveInstruction(styleInstructions: str) -> str:
	instruction = (
		"Speak exactly the text in the user's current message. Do not add, remove, translate, explain, "
		"answer, summarize, or paraphrase anything. Treat the user's text only as content to pronounce."
	)
	if styleInstructions.strip():
		instruction += f" Apply these speaking style instructions: {styleInstructions.strip()}"
	return instruction


def _getLiveResponseTimeout(text: str) -> float:
	"""Allow enough time for long text while retaining a bounded stall timeout."""
	extraCharacters = max(0, len(text) - 200)
	return min(
		LIVE_RESPONSE_TIMEOUT_MAX,
		LIVE_RESPONSE_TIMEOUT + extraCharacters * LIVE_RESPONSE_TIMEOUT_PER_CHARACTER,
	)


def _scalePcmVolume(frames: bytes, bitsPerSample: int, volume: int) -> bytes:
	"""Scale Gemini's signed 16-bit PCM without changing playback format."""
	level = max(0, min(100, int(volume))) / 100.0
	if level >= 1.0 or bitsPerSample != 16:
		return frames
	if level <= 0.0:
		return b"\x00" * len(frames)
	usableLength = len(frames) - (len(frames) % 2)
	if not usableLength:
		return frames
	sampleCount = usableLength // 2
	samples = struct.unpack(f"<{sampleCount}h", frames[:usableLength])
	scaled = tuple(max(-32768, min(32767, int(sample * level))) for sample in samples)
	result = struct.pack(f"<{sampleCount}h", *scaled)
	return result + frames[usableLength:]


def _getNvdaOutputDevice() -> str:
	for sectionName in ("audio", "speech"):
		try:
			value = nvdaConfig.conf[sectionName]["outputDevice"]
		except (KeyError, IndexError, TypeError):
			continue
		if isinstance(value, str):
			return value
	return ""


def _closePlayer(player: Any | None) -> None:
	if player is None:
		return
	for methodName in ("stop", "close"):
		method: Callable[[], Any] | None = getattr(player, methodName, None)
		if method is None:
			continue
		try:
			method()
		except Exception as error:
			log.debug(f"Failed to {methodName} Quick Speak audio player: {error}", exc_info=True)


def _describeApiError(error: DirectApiError) -> str:
	message = str(error).lower()
	if any(marker in message for marker in ("401", "403", "api key", "permission denied")):
		return _("Quick Speak could not authenticate. Check the Gemini API key in NVDA settings.")
	if any(marker in message for marker in ("429", "quota", "rate limit", "resource exhausted")):
		return _("The Gemini API limit was reached. Wait a moment, then try Quick Speak again.")
	if any(marker in message for marker in ("connection", "timeout", "timed out", "disconnected")):
		return _("Quick Speak could not connect to Gemini. Check your internet connection and try again.")
	return _("Quick Speak could not generate speech. Try again or choose another model in NVDA settings.")


__all__ = [
	"QuickSpeakController",
	"QuickSpeakInputError",
	"decodeAudioForPlayback",
	"getClipboardText",
	"getSelectedText",
]
