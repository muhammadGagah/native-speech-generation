"""Small direct Gemini REST and Live WebSocket client.

This module deliberately uses only the Python standard library so the add-on
does not load the google-genai SDK (or its transitive dependency tree).
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import socket
import ssl
import struct
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import AsyncIterator, Iterable
from dataclasses import dataclass, field
from typing import Any


REST_URL = "https://generativelanguage.googleapis.com/v1beta"
LIVE_HOST = "generativelanguage.googleapis.com"
LIVE_PATH = "/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent"


class DirectApiError(RuntimeError):
	"""Raised when a direct Gemini API request fails."""


def _json_request(url: str, api_key: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
	data = json.dumps(payload).encode("utf-8")
	request = urllib.request.Request(
		url,
		data=data,
		headers={
			"x-goog-api-key": api_key,
			"Content-Type": "application/json",
			"User-Agent": "NativeSpeechGeneration-NVDA-Addon",
		},
		method="POST",
	)
	try:
		with urllib.request.urlopen(request, timeout=timeout) as response:
			return json.loads(response.read().decode("utf-8"))
	except urllib.error.HTTPError as error:
		detail = error.read().decode("utf-8", errors="replace")
		raise DirectApiError(f"Gemini API HTTP {error.code}: {detail[:500]}") from error
	except TimeoutError as error:
		raise DirectApiError(f"Gemini API request timed out after {timeout:g} seconds.") from error
	except (urllib.error.URLError, OSError) as error:
		raise DirectApiError(f"Gemini API connection failed: {error}") from error


def _find_audio(value: Any) -> tuple[bytes, str] | None:
	if isinstance(value, dict):
		for key in ("output_audio", "outputAudio"):
			found = _find_audio(value.get(key))
			if found:
				return found
		for key in ("data", "inlineData", "inline_data"):
			candidate = value.get(key)
			if isinstance(candidate, str) and key == "data":
				try:
					return base64.b64decode(candidate), str(
						value.get("mime_type") or value.get("mimeType") or ""
					)
				except (ValueError, TypeError):
					pass
			if isinstance(candidate, dict):
				found = _find_audio(candidate)
				if found:
					return found
		for item in value.values():
			found = _find_audio(item)
			if found:
				return found
	elif isinstance(value, list):
		for item in value:
			found = _find_audio(item)
			if found:
				return found
	return None


def generate_tts(
	api_key: str,
	model: str,
	text: str,
	voice_names: Iterable[str],
	*,
	speaker_names: Iterable[str] | None = None,
	temperature: float = 1.0,
	style_instructions: str = "",
	timeout: float | None = None,
) -> tuple[bytes, str]:
	"""Generate PCM/audio bytes using the direct Interactions API.

	Older models are supported through the legacy generateContent fallback.
	"""
	voices = [str(voice).strip() for voice in voice_names if str(voice).strip()]
	speakers = [str(name).strip() for name in (speaker_names or []) if str(name).strip()]
	if not voices:
		raise DirectApiError("At least one voice is required.")
	input_text = f"{style_instructions.strip()}\n{text}" if style_instructions.strip() else text
	request_timeout = timeout if timeout is not None else min(600.0, max(90.0, len(input_text) / 5 * (1.5 if len(voices) > 1 else 1.0)))
	speech_config: Any
	if len(voices) == 1:
		speech_config = [{"voice": voices[0]}]
	else:
		if len(speakers) != len(voices):
			speakers = [f"Speaker{i + 1}" for i in range(len(voices))]
		speech_config = [{"speaker": speaker, "voice": voice} for speaker, voice in zip(speakers, voices)]
	payload = {
		"model": model,
		"input": input_text,
		"response_format": {"type": "audio"},
		"generation_config": {
			"temperature": temperature,
			"speech_config": speech_config,
		},
	}
	try:
		response = _json_request(f"{REST_URL}/interactions", api_key, payload, request_timeout)
		found = _find_audio(response)
		if found:
			return found
	except DirectApiError as error:
		if "HTTP 400" not in str(error) and "HTTP 404" not in str(error):
			raise

	legacy_payload = {
		"contents": [{"role": "user", "parts": [{"text": input_text}]}],
		"generationConfig": {
			"temperature": temperature,
			"responseModalities": ["AUDIO"],
			"speechConfig": (
				{"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voices[0]}}}
				if len(voices) == 1
				else {
					"multiSpeakerVoiceConfig": {
						"speakerVoiceConfigs": [
							{"speaker": speaker, "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}}
							for speaker, voice in zip(speakers, voices)
						]
					}
				}
			),
		},
	}
	response = _json_request(
		f"{REST_URL}/models/{urllib.parse.quote(model, safe='')}:generateContent",
		api_key,
		legacy_payload,
		request_timeout,
	)
	found = _find_audio(response)
	if not found:
		raise DirectApiError("Gemini returned no audio data.")
	return found


class _MinimalWebSocket:
	"""RFC 6455 client sufficient for the Gemini Live JSON protocol."""

	def __init__(self, host: str, path: str, *, timeout: float = 30.0) -> None:
		super().__init__()
		self.host = host
		self.path = path
		self.timeout = timeout
		self.sock: socket.socket | ssl.SSLSocket | None = None
		self._recv_buf = b""
		self.closed = False
		self.close_reason = ""
		self._send_lock = threading.Lock()

	def connect(self) -> None:
		if self.closed:
			raise DirectApiError("Live WebSocket was closed before connecting.")
		proxy_url = None
		if not urllib.request.proxy_bypass(self.host):
			proxy_url = urllib.request.getproxies().get("https") or urllib.request.getproxies().get("http")
		if proxy_url:
			proxy = urllib.parse.urlparse(proxy_url if "://" in proxy_url else f"http://{proxy_url}")
			if proxy.scheme.lower().startswith("socks"):
				raise DirectApiError("SOCKS proxies are not supported for Gemini Live connections.")
			raw = self._openTcpConnection(proxy.hostname or "", proxy.port or 80)
			connect = f"CONNECT {self.host}:443 HTTP/1.1\r\nHost: {self.host}:443\r\n"
			if proxy.username:
				auth = base64.b64encode(f"{proxy.username}:{proxy.password or ''}".encode()).decode()
				connect += f"Proxy-Authorization: Basic {auth}\r\n"
			raw.sendall(f"{connect}\r\n".encode("ascii"))
			proxy_response = b""
			while b"\r\n\r\n" not in proxy_response:
				chunk = raw.recv(4096)
				if not chunk:
					raise DirectApiError("WebSocket proxy tunnel closed.")
				proxy_response += chunk
			if b" 200 " not in proxy_response.split(b"\r\n", 1)[0]:
				raise DirectApiError(f"WebSocket proxy tunnel failed: {proxy_response[:200]!r}")
		else:
			raw = self._openTcpConnection(self.host, 443)
		if self.closed:
			raw.close()
			raise DirectApiError("Live WebSocket was closed while connecting.")
		self.sock = ssl.create_default_context().wrap_socket(raw, server_hostname=self.host)
		if self.closed:
			self.sock.close()
			raise DirectApiError("Live WebSocket was closed while connecting.")
		key = base64.b64encode(os.urandom(16)).decode("ascii")
		handshake = (
			f"GET {self.path} HTTP/1.1\r\nHost: {self.host}\r\n"
			"Upgrade: websocket\r\nConnection: Upgrade\r\n"
			f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n"
		)
		self.sock.sendall(handshake.encode("ascii"))
		response = b""
		while b"\r\n\r\n" not in response:
			chunk = self.sock.recv(4096)
			if not chunk:
				raise DirectApiError("Live WebSocket handshake closed.")
			response += chunk
		if not response.startswith(b"HTTP/1.1 101"):
			raise DirectApiError(f"Live WebSocket handshake failed: {response[:200]!r}")
		expected_accept = base64.b64encode(
			hashlib.sha1(f"{key}258EAFA5-E914-47DA-95CA-C5AB0DC85B11".encode("ascii")).digest(),
		).decode("ascii")
		if f"sec-websocket-accept: {expected_accept}".lower().encode("ascii") not in response.lower():
			raise DirectApiError("Live WebSocket handshake signature is invalid.")
		self._recv_buf = response.split(b"\r\n\r\n", 1)[1]
		self.sock.settimeout(1.0)

	def _openTcpConnection(self, host: str, port: int) -> socket.socket:
		lastError: OSError | None = None
		try:
			addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
		except OSError as error:
			raise DirectApiError(f"Live WebSocket address lookup failed: {error}") from error
		for addressFamily, socketType, protocol, _canonicalName, socketAddress in addresses:
			if self.closed:
				raise DirectApiError("Live WebSocket was closed while connecting.")
			candidate = socket.socket(addressFamily, socketType, protocol)
			candidate.settimeout(self.timeout)
			self.sock = candidate
			try:
				candidate.connect(socketAddress)
				return candidate
			except OSError as error:
				lastError = error
				try:
					candidate.close()
				except OSError:
					pass
				if self.closed:
					raise DirectApiError("Live WebSocket was closed while connecting.") from error
				self.sock = None
		raise DirectApiError(f"Live WebSocket connection failed: {lastError}")

	def _send_frame(self, opcode: int, payload: bytes) -> None:
		if self.closed or self.sock is None:
			return
		mask = os.urandom(4)
		length = len(payload)
		header = bytearray([0x80 | opcode])
		if length < 126:
			header.append(0x80 | length)
		elif length < 65536:
			header.extend((0x80 | 126,))
			header.extend(struct.pack(">H", length))
		else:
			header.extend((0x80 | 127,))
			header.extend(struct.pack(">Q", length))
		header.extend(mask)
		masked = bytes(byte ^ mask[i % 4] for i, byte in enumerate(payload))
		with self._send_lock:
			if not self.closed:
				self.sock.sendall(bytes(header) + masked)

	def send_json(self, payload: dict[str, Any]) -> None:
		self._send_frame(1, json.dumps(payload, separators=(",", ":")).encode("utf-8"))

	def _recv_exact(self, size: int, deadline: float | None) -> bytes:
		while len(self._recv_buf) < size:
			if self.closed or self.sock is None:
				raise DirectApiError("Live WebSocket is closed.")
			if deadline is not None and time.monotonic() >= deadline:
				raise TimeoutError
			try:
				chunk = self.sock.recv(65536)
				if not chunk:
					raise DirectApiError("Live WebSocket disconnected.")
				self._recv_buf += chunk
			except socket.timeout:
				if deadline is not None and time.monotonic() >= deadline:
					raise TimeoutError
				continue
		data, self._recv_buf = self._recv_buf[:size], self._recv_buf[size:]
		return data

	def recv_json(self, timeout: float | None = None) -> dict[str, Any] | None:
		deadline = time.monotonic() + timeout if timeout is not None else None
		fragments = bytearray()
		while True:
			first, second = self._recv_exact(2, deadline)
			finished = bool(first & 0x80)
			opcode = first & 0x0F
			if second & 0x80:
				raise DirectApiError("Live WebSocket sent an invalid masked server frame.")
			length = second & 0x7F
			if length == 126:
				length = struct.unpack(">H", self._recv_exact(2, deadline))[0]
			elif length == 127:
				length = struct.unpack(">Q", self._recv_exact(8, deadline))[0]
			payload = self._recv_exact(length, deadline) if length else b""
			if opcode == 8:
				if len(payload) >= 2:
					code = struct.unpack(">H", payload[:2])[0]
					reason = payload[2:].decode("utf-8", errors="replace")
					self.close_reason = f"{code} {reason}".strip()
				self.abort()
				return None
			if opcode == 9:
				self._send_frame(10, payload)
				continue
			if opcode in (1, 2):
				fragments = bytearray(payload)
			elif opcode == 0 and fragments:
				fragments.extend(payload)
			else:
				continue
			if finished:
				return json.loads(fragments.decode("utf-8"))

	def close(self) -> None:
		if self.closed:
			return
		try:
			self._send_frame(8, b"")
		except Exception:
			pass
		self.abort()

	def abort(self) -> None:
		if self.closed:
			return
		self.closed = True
		try:
			if self.sock:
				self.sock.shutdown(socket.SHUT_RDWR)
		except Exception:
			pass
		try:
			if self.sock:
				self.sock.close()
		except Exception:
			pass


@dataclass
class DirectLiveSession:
	api_key: str
	model: str
	voice_name: str
	system_instruction: str
	thinking_level: str | None = "minimal"
	use_google_search: bool = False
	_ws: _MinimalWebSocket = field(init=False)
	_closed: bool = field(init=False, default=False)

	def __post_init__(self) -> None:
		path = f"{LIVE_PATH}?key={urllib.parse.quote(self.api_key, safe='')}"
		self._ws = _MinimalWebSocket(LIVE_HOST, path)
		self._closed = False

	async def connect(self, history: list[dict[str, Any]] | None = None) -> None:
		await asyncio.to_thread(self._ws.connect)
		setup: dict[str, Any] = {
			"setup": {
				"model": self.model if self.model.startswith("models/") else f"models/{self.model}",
				"generationConfig": {
					"responseModalities": ["AUDIO"],
					"speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": self.voice_name}}},
				},
				"systemInstruction": {"parts": [{"text": self.system_instruction}]},
				"realtimeInputConfig": {"automaticActivityDetection": {"disabled": False}},
				"inputAudioTranscription": {},
				"outputAudioTranscription": {},
			},
		}
		if self.thinking_level:
			setup["setup"]["generationConfig"]["thinkingConfig"] = {
				"thinkingLevel": self.thinking_level,
			}
		if self.use_google_search:
			setup["setup"]["tools"] = [{"googleSearch": {}}]
		await asyncio.to_thread(self._ws.send_json, setup)
		while True:
			try:
				message = await asyncio.to_thread(self._ws.recv_json, 15.0)
			except TimeoutError as error:
				raise DirectApiError("Live API setup timed out.") from error
			if message is None:
				raise DirectApiError("Live API closed before setup completed.")
			if "error" in message:
				error = message.get("error")
				raise DirectApiError(str(error.get("message") if isinstance(error, dict) else error))
			if message.get("setupComplete") is not None:
				break
		if history:
			await self.send_client_content(history, turn_complete=False)

	async def send_realtime_input(self, *, audio: bytes | None = None, video: str | None = None) -> None:
		if audio is not None:
			message = {
				"realtimeInput": {
					"audio": {
						"mimeType": "audio/pcm;rate=16000",
						"data": base64.b64encode(audio).decode("ascii"),
					}
				}
			}
		elif video:
			message = {"realtimeInput": {"video": {"mimeType": "image/jpeg", "data": video}}}
		else:
			return
		await asyncio.to_thread(self._ws.send_json, message)

	async def send_client_content(self, turns: list[dict[str, Any]], turn_complete: bool = False) -> None:
		await asyncio.to_thread(
			self._ws.send_json, {"clientContent": {"turns": turns, "turnComplete": turn_complete}}
		)

	async def receive(self) -> AsyncIterator[dict[str, Any]]:
		while not self._closed:
			try:
				message = await asyncio.to_thread(self._ws.recv_json, 1.0)
			except TimeoutError:
				continue
			if message is None:
				if not self._closed:
					reason = getattr(self._ws, "close_reason", "")
					detail = f": {reason}" if reason else "."
					raise DirectApiError(f"Live WebSocket disconnected{detail}")
				break
			if "error" in message:
				error = message.get("error")
				raise DirectApiError(str(error.get("message") if isinstance(error, dict) else error))
			yield message

	async def close(self) -> None:
		self._closed = True
		await asyncio.to_thread(self._ws.close)

	def abort(self) -> None:
		"""Close the socket immediately, including during a blocking connect."""
		self._closed = True
		abort = getattr(self._ws, "abort", None)
		if abort is not None:
			abort()
		else:
			self._ws.close()


__all__ = ["DirectApiError", "DirectLiveSession", "generate_tts"]
