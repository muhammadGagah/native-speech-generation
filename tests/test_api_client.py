from __future__ import annotations

import asyncio
import base64
import importlib.util
import sys
import threading
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
API_CLIENT_PATH = REPO_ROOT / "addon" / "globalPlugins" / "NativeSpeechGeneration" / "core" / "api_client.py"


def _loadApiClient() -> Any:
	moduleName = "nsg_api_client_under_test"
	sys.modules.pop(moduleName, None)
	spec = importlib.util.spec_from_file_location(moduleName, API_CLIENT_PATH)
	assert spec is not None and spec.loader is not None
	module = importlib.util.module_from_spec(spec)
	sys.modules[moduleName] = module
	spec.loader.exec_module(module)
	return module


class ApiClientTests(unittest.TestCase):
	def testMultiSpeakerPayloadPreservesNamesAndVoices(self) -> None:
		apiClient = _loadApiClient()
		requests: list[dict[str, Any]] = []

		def fakeRequest(_url: str, _key: str, payload: dict[str, Any], _timeout: float) -> dict[str, Any]:
			requests.append(payload)
			return {
				"output_audio": {
					"data": base64.b64encode(b"pcm").decode(),
					"mime_type": "audio/L16;rate=24000",
				},
			}

		apiClient._json_request = fakeRequest
		data, mimeType = apiClient.generate_tts(
			"key",
			"model",
			"Alice: Hello\nBob: Hi",
			["Kore", "Puck"],
			speaker_names=["Alice", "Bob"],
		)

		self.assertEqual(data, b"pcm")
		self.assertEqual(mimeType, "audio/L16;rate=24000")
		self.assertEqual(
			requests[0]["generation_config"]["speech_config"],
			[{"speaker": "Alice", "voice": "Kore"}, {"speaker": "Bob", "voice": "Puck"}],
		)

	def testLongMultiSpeakerGenerationUsesAdaptiveTimeout(self) -> None:
		apiClient = _loadApiClient()
		timeouts: list[float] = []

		def fakeRequest(_url: str, _key: str, _payload: dict[str, Any], timeout: float) -> dict[str, Any]:
			timeouts.append(timeout)
			return {
				"output_audio": {
					"data": base64.b64encode(b"pcm").decode(),
					"mime_type": "audio/L16;rate=24000",
				},
			}

		apiClient._json_request = fakeRequest
		apiClient.generate_tts("key", "model", "x" * 1000, ["Kore", "Puck"])
		apiClient.generate_tts("key", "model", "short", ["Kore"], timeout=12.0)

		self.assertEqual([300.0, 12.0], timeouts)

	def testLiveVideoMessageUsesRealtimeInput(self) -> None:
		apiClient = _loadApiClient()
		sent: list[dict[str, Any]] = []

		class FakeWebSocket:
			def send_json(self, message: dict[str, Any]) -> None:
				sent.append(message)

		session = apiClient.DirectLiveSession("key", "model", "Kore", "Help the user")
		session._ws = FakeWebSocket()

		asyncio.run(session.send_realtime_input(video="jpeg-base64"))

		self.assertEqual(
			sent,
			[{"realtimeInput": {"video": {"mimeType": "image/jpeg", "data": "jpeg-base64"}}}],
		)

	def testLiveSetupUsesCurrentProtocolSchema(self) -> None:
		apiClient = _loadApiClient()
		sent: list[dict[str, Any]] = []

		class FakeWebSocket:
			def connect(self) -> None:
				pass

			def send_json(self, message: dict[str, Any]) -> None:
				sent.append(message)

			def recv_json(self, _timeout: float) -> dict[str, Any]:
				return {"setupComplete": {}}

		session = apiClient.DirectLiveSession(
			"key",
			"gemini-live",
			"Kore",
			"Help the user",
			thinking_level="low",
			use_google_search=True,
		)
		session._ws = FakeWebSocket()

		asyncio.run(session.connect())

		self.assertEqual(
			sent[0],
			{
				"setup": {
					"model": "models/gemini-live",
					"generationConfig": {
						"responseModalities": ["AUDIO"],
						"speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": "Kore"}}},
						"thinkingConfig": {"thinkingLevel": "low"},
					},
					"systemInstruction": {"parts": [{"text": "Help the user"}]},
					"realtimeInputConfig": {"automaticActivityDetection": {"disabled": False}},
					"inputAudioTranscription": {},
					"outputAudioTranscription": {},
					"tools": [{"googleSearch": {}}],
				},
			},
		)

	def testLiveSetupOmitsThinkingConfigWhenUnsupported(self) -> None:
		apiClient = _loadApiClient()
		sent: list[dict[str, Any]] = []

		class FakeWebSocket:
			def connect(self) -> None:
				pass

			def send_json(self, message: dict[str, Any]) -> None:
				sent.append(message)

			def recv_json(self, _timeout: float) -> dict[str, Any]:
				return {"setupComplete": {}}

		session = apiClient.DirectLiveSession(
			"key",
			"gemini-2.5-flash-native-audio-preview-12-2025",
			"Kore",
			"Help the user",
			thinking_level=None,
		)
		session._ws = FakeWebSocket()

		asyncio.run(session.connect())

		self.assertNotIn("thinkingConfig", sent[0]["setup"]["generationConfig"])

	def testWebSocketReadsBufferedAndFragmentedFrames(self) -> None:
		apiClient = _loadApiClient()
		webSocket = apiClient._MinimalWebSocket("example.com", "/")
		webSocket.sock = object()
		webSocket._recv_buf = b'\x01\x06{"ok":\x80\x05true}'

		self.assertEqual(webSocket.recv_json(), {"ok": True})

	def testWebSocketReadsBinaryJsonFrame(self) -> None:
		apiClient = _loadApiClient()
		webSocket = apiClient._MinimalWebSocket("example.com", "/")
		webSocket.sock = object()
		webSocket._recv_buf = b'\x82\x14{"setupComplete":{}}'

		self.assertEqual(webSocket.recv_json(), {"setupComplete": {}})

	def testLiveSetupTimeoutIsReportedAsApiError(self) -> None:
		apiClient = _loadApiClient()

		class FakeWebSocket:
			def connect(self) -> None:
				pass

			def send_json(self, _message: dict[str, Any]) -> None:
				pass

			def recv_json(self, _timeout: float) -> dict[str, Any]:
				raise TimeoutError

		session = apiClient.DirectLiveSession("key", "model", "Kore", "Help")
		session._ws = FakeWebSocket()

		with self.assertRaisesRegex(apiClient.DirectApiError, "setup timed out"):
			asyncio.run(session.connect())

	def testUnexpectedLiveSocketCloseIsAnError(self) -> None:
		apiClient = _loadApiClient()

		class FakeWebSocket:
			def recv_json(self, _timeout: float) -> None:
				return None

		session = apiClient.DirectLiveSession("key", "model", "Kore", "Help")
		session._ws = FakeWebSocket()

		async def receiveOne() -> None:
			async for _message in session.receive():
				pass

		with self.assertRaisesRegex(apiClient.DirectApiError, "disconnected"):
			asyncio.run(receiveOne())

	def testLiveTopLevelErrorIsRaised(self) -> None:
		apiClient = _loadApiClient()

		class FakeWebSocket:
			def recv_json(self, _timeout: float) -> dict[str, Any]:
				return {"error": {"message": "permission denied"}}

		session = apiClient.DirectLiveSession("key", "model", "Kore", "Help")
		session._ws = FakeWebSocket()

		async def receiveOne() -> None:
			async for _message in session.receive():
				pass

		with self.assertRaisesRegex(apiClient.DirectApiError, "permission denied"):
			asyncio.run(receiveOne())

	def testWebSocketCloseReasonIsReported(self) -> None:
		apiClient = _loadApiClient()

		class FakeSocket:
			def shutdown(self, _how: int) -> None:
				pass

			def close(self) -> None:
				pass

		webSocket = apiClient._MinimalWebSocket("example.com", "/")
		webSocket.sock = FakeSocket()
		payload = b"\x03\xf0policy violation"
		webSocket._recv_buf = bytes((0x88, len(payload))) + payload

		self.assertIsNone(webSocket.recv_json())
		self.assertEqual(webSocket.close_reason, "1008 policy violation")

	def testLiveAbortSynchronouslyClosesSocket(self) -> None:
		apiClient = _loadApiClient()

		class FakeWebSocket:
			closed = False

			def close(self) -> None:
				self.closed = True

		session = apiClient.DirectLiveSession("key", "model", "Kore", "Help")
		session._ws = FakeWebSocket()

		session.abort()

		self.assertTrue(session._closed)
		self.assertTrue(session._ws.closed)

	def testSocketCloseInterruptsConnectingTcpSocket(self) -> None:
		apiClient = _loadApiClient()
		connectStarted = threading.Event()
		closed = threading.Event()

		class FakeSocket:
			def settimeout(self, _timeout: float) -> None:
				pass

			def connect(self, _address: object) -> None:
				connectStarted.set()
				closed.wait(2.0)
				raise OSError("closed")

			def shutdown(self, _how: int) -> None:
				closed.set()

			def close(self) -> None:
				closed.set()

		with (
			mock.patch.object(
				apiClient.socket,
				"getaddrinfo",
				return_value=[(2, 1, 6, "", ("127.0.0.1", 443))],
			),
			mock.patch.object(apiClient.socket, "socket", return_value=FakeSocket()),
		):
			webSocket = apiClient._MinimalWebSocket("example.com", "/")
			errors: list[BaseException] = []

			def connect() -> None:
				try:
					webSocket._openTcpConnection("example.com", 443)
				except BaseException as error:
					errors.append(error)

			thread = threading.Thread(target=connect)
			thread.start()
			self.assertTrue(connectStarted.wait(1.0))
			webSocket.abort()
			thread.join(1.0)

		self.assertFalse(thread.is_alive())
		self.assertTrue(errors)
		self.assertIn("closed while connecting", str(errors[0]))

	def testSocksProxyFailsWithActionableError(self) -> None:
		apiClient = _loadApiClient()
		webSocket = apiClient._MinimalWebSocket("example.com", "/")

		with (
			mock.patch.object(apiClient.urllib.request, "proxy_bypass", return_value=False),
			mock.patch.object(
				apiClient.urllib.request, "getproxies", return_value={"https": "socks5://localhost:1080"}
			),
			self.assertRaisesRegex(apiClient.DirectApiError, "SOCKS proxies are not supported"),
		):
			webSocket.connect()


if __name__ == "__main__":
	unittest.main()
