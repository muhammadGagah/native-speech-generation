from __future__ import annotations

import base64
import builtins
import importlib.util
import io
import sys
import types
import unittest
import wave
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
QUICK_SPEAK_PATH = (
	REPO_ROOT / "addon" / "globalPlugins" / "NativeSpeechGeneration" / "core" / "quick_speak.py"
)


class _Log:
	def debug(self, *_args: object, **_kwargs: object) -> None:
		pass

	def error(self, *_args: object, **_kwargs: object) -> None:
		pass

	def warning(self, *_args: object, **_kwargs: object) -> None:
		pass


class _FakePlayer:
	def __init__(self, **kwargs: Any) -> None:
		super().__init__()
		self.kwargs = kwargs
		self.fed: list[bytes] = []
		self.idled = False
		self.stopped = False
		self.closed = False

	def feed(self, data: bytes) -> None:
		self.fed.append(data)

	def idle(self) -> None:
		self.idled = True

	def stop(self) -> None:
		self.stopped = True

	def close(self) -> None:
		self.closed = True


def _loadQuickSpeak() -> tuple[Any, types.SimpleNamespace]:
	def translate(message: str) -> str:
		return message

	builtins._ = translate
	state = types.SimpleNamespace(
		focus=None,
		clipboard=None,
		messages=[],
		cancelCount=0,
		players=[],
		callAfter=[],
		liveSessionArgs=[],
		quickSpeakSettings=types.SimpleNamespace(
			model="tts-model",
			voice="Kore",
			styleInstructions="",
			volume=80,
		),
	)

	addonHandler = types.ModuleType("addonHandler")
	addonHandler.initTranslation = lambda: None
	sys.modules["addonHandler"] = addonHandler

	api = types.ModuleType("api")
	api.getFocusObject = lambda: state.focus
	api.getClipData = lambda: state.clipboard
	sys.modules["api"] = api

	nvdaConfig = types.ModuleType("config")
	nvdaConfig.conf = {"audio": {"outputDevice": "nvda-device"}}
	sys.modules["config"] = nvdaConfig

	protected = object()
	passwordEdit = object()
	controlTypes = types.ModuleType("controlTypes")
	controlTypes.State = types.SimpleNamespace(PROTECTED=protected)
	controlTypes.Role = types.SimpleNamespace(PASSWORDEDIT=passwordEdit)
	sys.modules["controlTypes"] = controlTypes

	nvwave = types.ModuleType("nvwave")

	def makePlayer(**kwargs: Any) -> _FakePlayer:
		player = _FakePlayer(**kwargs)
		state.players.append(player)
		return player

	nvwave.WavePlayer = makePlayer
	sys.modules["nvwave"] = nvwave

	speech = types.ModuleType("speech")

	def cancelSpeech() -> None:
		state.cancelCount += 1

	speech.cancelSpeech = cancelSpeech
	sys.modules["speech"] = speech

	textInfos = types.ModuleType("textInfos")
	textInfos.POSITION_SELECTION = "selection"
	sys.modules["textInfos"] = textInfos

	ui = types.ModuleType("ui")
	ui.message = state.messages.append
	sys.modules["ui"] = ui

	wx = types.ModuleType("wx")

	def callAfter(callback: Any, *args: object) -> None:
		state.callAfter.append((callback, args))

	wx.CallAfter = callAfter
	sys.modules["wx"] = wx

	logHandler = types.ModuleType("logHandler")
	logHandler.log = _Log()
	sys.modules["logHandler"] = logHandler

	packageName = "nsg_quick_under_test"
	package = types.ModuleType(packageName)
	package.__path__ = [str(QUICK_SPEAK_PATH.parent.parent)]
	sys.modules[packageName] = package
	corePackage = types.ModuleType(f"{packageName}.core")
	corePackage.__path__ = [str(QUICK_SPEAK_PATH.parent)]
	sys.modules[f"{packageName}.core"] = corePackage

	configStore = types.ModuleType(f"{packageName}.core.config_store")

	def resolveApiKey() -> Any:
		return types.SimpleNamespace(value="key")

	def getQuickSpeakSettings() -> Any:
		return state.quickSpeakSettings

	configStore.resolveApiKey = resolveApiKey
	configStore.getQuickSpeakSettings = getQuickSpeakSettings
	sys.modules[configStore.__name__] = configStore

	apiClient = types.ModuleType(f"{packageName}.core.api_client")

	class DirectApiError(RuntimeError):
		pass

	class DirectLiveSession:
		def __init__(self, *args: object, **kwargs: object) -> None:
			super().__init__()
			state.liveSessionArgs.append((args, kwargs))

		def abort(self) -> None:
			pass

		async def connect(self) -> None:
			pass

		async def send_client_content(
			self,
			_turns: list[dict[str, Any]],
			turn_complete: bool,
		) -> None:
			pass

		async def receive(self) -> Any:
			yield {
				"serverContent": {
					"modelTurn": {
						"parts": [
							{
								"inlineData": {
									"data": base64.b64encode(b"\x03\x04").decode("ascii"),
									"mimeType": "audio/pcm;rate=24000",
								},
							},
						],
					},
					"turnComplete": True,
				},
			}

	apiClient.DirectApiError = DirectApiError
	apiClient.DirectLiveSession = DirectLiveSession

	def generateTts(*_args: object, **_kwargs: object) -> tuple[bytes, str]:
		return b"\x01\x02", "audio/L16;rate=24000"

	apiClient.generate_tts = generateTts
	sys.modules[apiClient.__name__] = apiClient

	audioUtils = types.ModuleType(f"{packageName}.core.audio_utils")

	def parseAudioMimeType(_mime: str) -> dict[str, int]:
		return {"rate": 24000, "bitsPerSample": 16}

	audioUtils.parseAudioMimeType = parseAudioMimeType
	sys.modules[audioUtils.__name__] = audioUtils

	constants = types.ModuleType(f"{packageName}.core.constants")
	constants.LIVE_MODEL = "live-model"
	constants.NATIVE_AUDIO_25_MODEL = "native-audio-model"
	sys.modules[constants.__name__] = constants

	moduleName = f"{packageName}.core.quick_speak"
	sys.modules.pop(moduleName, None)
	spec = importlib.util.spec_from_file_location(moduleName, QUICK_SPEAK_PATH)
	assert spec is not None and spec.loader is not None
	module = importlib.util.module_from_spec(spec)
	sys.modules[moduleName] = module
	spec.loader.exec_module(module)
	state.protected = protected
	state.passwordEdit = passwordEdit
	return module, state


class _TextSource:
	def __init__(
		self,
		text: str,
		*,
		states: tuple[object, ...] = (),
		role: object | None = None,
		passThrough: bool = False,
	) -> None:
		super().__init__()
		self.text = text
		self.states = states
		self.role = role
		self.passThrough = passThrough
		self.requests: list[str] = []

	def makeTextInfo(self, position: str) -> Any:
		self.requests.append(position)
		return types.SimpleNamespace(text=self.text)


class QuickSpeakTests(unittest.TestCase):
	def testTreeInterceptorSelectionWins(self) -> None:
		quickSpeak, state = _loadQuickSpeak()
		focus = _TextSource("focus selection")
		focus.treeInterceptor = _TextSource("document selection")
		state.focus = focus

		self.assertEqual(quickSpeak.getSelectedText(), "document selection")
		self.assertEqual(focus.requests, [])

	def testProtectedSelectionIsRejectedBeforeTextAccess(self) -> None:
		quickSpeak, state = _loadQuickSpeak()
		focus = _TextSource("secret", states=(state.protected,))
		state.focus = focus

		with self.assertRaisesRegex(quickSpeak.QuickSpeakInputError, "protected"):
			quickSpeak.getSelectedText()
		self.assertEqual(focus.requests, [])

	def testFocusModeUsesFocusedControlSelection(self) -> None:
		quickSpeak, state = _loadQuickSpeak()
		focus = _TextSource("focused edit selection")
		focus.treeInterceptor = _TextSource("stale browse selection", passThrough=True)
		state.focus = focus

		self.assertEqual(quickSpeak.getSelectedText(), "focused edit selection")
		self.assertEqual(focus.treeInterceptor.requests, [])

	def testSelectionDoesNotFallbackToObjectValue(self) -> None:
		quickSpeak, state = _loadQuickSpeak()
		focus = _TextSource("")
		focus.value = "entire document"
		state.focus = focus

		with self.assertRaisesRegex(quickSpeak.QuickSpeakInputError, "No selected text"):
			quickSpeak.getSelectedText()

	def testClipboardAcceptsOnlyNonEmptyText(self) -> None:
		quickSpeak, state = _loadQuickSpeak()
		state.clipboard = {"image": b"data"}
		with self.assertRaisesRegex(quickSpeak.QuickSpeakInputError, "clipboard"):
			quickSpeak.getClipboardText()

		state.clipboard = "  through  "
		self.assertEqual(quickSpeak.getClipboardText(), "through")

	def testWavAudioIsDecodedInMemory(self) -> None:
		quickSpeak, _state = _loadQuickSpeak()
		wavBuffer = io.BytesIO()
		with wave.open(wavBuffer, "wb") as wavFile:
			wavFile.setnchannels(1)
			wavFile.setsampwidth(2)
			wavFile.setframerate(24000)
			wavFile.writeframes(b"\x01\x02")

		frames, channels, rate, bits = quickSpeak.decodeAudioForPlayback(
			wavBuffer.getvalue(),
			"audio/wav",
		)

		self.assertEqual((frames, channels, rate, bits), (b"\x01\x02", 1, 24000, 16))

	def testPcmVolumeScaling(self) -> None:
		quickSpeak, _state = _loadQuickSpeak()

		self.assertEqual(quickSpeak._scalePcmVolume(b"\x00\x40\x00\xc0", 16, 50), b"\x00\x20\x00\xe0")
		self.assertEqual(quickSpeak._scalePcmVolume(b"\x00\x40", 16, 0), b"\x00\x00")
		self.assertEqual(quickSpeak._scalePcmVolume(b"\x00\x40", 8, 50), b"\x00\x40")

	def testTtsPlaybackUsesNvdaDeviceWithoutTemporaryFile(self) -> None:
		quickSpeak, state = _loadQuickSpeak()
		controller = quickSpeak.QuickSpeakController()
		controller._token = 1
		controller._active = True

		controller._run(1, "through")

		self.assertEqual(state.cancelCount, 1)
		self.assertEqual(state.players[0].kwargs["outputDevice"], "nvda-device")
		self.assertEqual(state.players[0].fed, [b"\x9a\x01"])
		self.assertTrue(state.players[0].idled)
		self.assertEqual(state.liveSessionArgs, [])
		self.assertFalse(controller.isActive)

	def testLiveModelUsesHighThinkingByDefault(self) -> None:
		quickSpeak, state = _loadQuickSpeak()
		state.quickSpeakSettings.model = "live-model"
		state.quickSpeakSettings.styleInstructions = "British English pronunciation"
		controller = quickSpeak.QuickSpeakController()
		controller._token = 1
		controller._active = True

		controller._run(1, "through")

		self.assertEqual(len(state.liveSessionArgs), 1)
		args, kwargs = state.liveSessionArgs[0]
		self.assertEqual(
			args[:4],
			(
				"key",
				"live-model",
				"Kore",
				quickSpeak._buildLiveInstruction("British English pronunciation"),
			),
		)
		self.assertEqual(kwargs, {"thinking_level": "high"})
		self.assertFalse(controller.isActive)

	def testNativeAudioModelUsesLiveSessionWithoutThinkingOverride(self) -> None:
		quickSpeak, state = _loadQuickSpeak()
		state.quickSpeakSettings.model = "native-audio-model"
		controller = quickSpeak.QuickSpeakController()
		controller._token = 1
		controller._active = True

		controller._run(1, "hello")

		self.assertEqual(len(state.liveSessionArgs), 1)
		_args, kwargs = state.liveSessionArgs[0]
		self.assertEqual(kwargs, {"thinking_level": None})
		self.assertFalse(controller.isActive)

	def testStopInvalidatesQueuedErrorsAndClosesResources(self) -> None:
		quickSpeak, state = _loadQuickSpeak()
		controller = quickSpeak.QuickSpeakController()
		controller._token = 4
		controller._active = True
		player = _FakePlayer()

		class Session:
			aborted = False

			def abort(self) -> None:
				self.aborted = True

		session = Session()
		controller._player = player
		controller._session = session
		controller._queueError(4, "stale error")

		self.assertTrue(controller.stop())
		for callback, args in state.callAfter:
			callback(*args)

		self.assertTrue(session.aborted)
		self.assertTrue(player.stopped)
		self.assertTrue(player.closed)
		self.assertEqual(state.messages, [])

	def testStaleFeedCannotCancelSpeechOrPlayAudio(self) -> None:
		quickSpeak, state = _loadQuickSpeak()
		controller = quickSpeak.QuickSpeakController()
		controller._token = 7
		controller._active = True
		player = _FakePlayer()
		controller._player = player
		controller.stop()

		self.assertFalse(controller._feedIfCurrent(7, player, b"old audio", cancelSpeech=True))
		self.assertEqual(state.cancelCount, 0)
		self.assertEqual(player.fed, [])

	def testPlaybackFailureGetsActionableAudioError(self) -> None:
		quickSpeak, state = _loadQuickSpeak()

		class BrokenPlayer(_FakePlayer):
			def feed(self, data: bytes) -> None:
				del data
				raise OSError("device disconnected")

		controller = quickSpeak.QuickSpeakController()
		controller._token = 3
		controller._active = True

		def makeBrokenPlayer(**_kwargs: object) -> BrokenPlayer:
			return BrokenPlayer()

		quickSpeak.nvwave.WavePlayer = makeBrokenPlayer

		controller._run(3, "through")
		for callback, args in state.callAfter:
			callback(*args)

		self.assertEqual(
			state.messages,
			["Quick Speak audio could not be played. Check NVDA's audio output device."],
		)

	def testLiveAudioStopsAtTurnComplete(self) -> None:
		quickSpeak, state = _loadQuickSpeak()
		controller = quickSpeak.QuickSpeakController()
		controller._token = 2
		controller._active = True

		class Session:
			def __init__(self) -> None:
				super().__init__()
				self.turns: list[dict[str, Any]] = []
				self.turnComplete = False

			async def connect(self) -> None:
				pass

			async def send_client_content(self, turns: list[dict[str, Any]], turn_complete: bool) -> None:
				self.turns = turns
				self.turnComplete = turn_complete

			async def receive(self) -> Any:
				yield {
					"serverContent": {
						"modelTurn": {
							"parts": [
								{
									"inlineData": {
										"data": base64.b64encode(b"\x03\x04").decode("ascii"),
										"mimeType": "audio/pcm;rate=24000",
									},
								},
							],
						},
						"turnComplete": True,
					},
				}

		import asyncio

		session = Session()
		asyncio.run(controller._runLive(2, session, "thought"))

		self.assertTrue(session.turnComplete)
		self.assertEqual(state.players[0].fed, [b"\x03\x04"])
		self.assertEqual(state.cancelCount, 1)

	def testLiveAudioHasOverallResponseTimeout(self) -> None:
		quickSpeak, _state = _loadQuickSpeak()
		controller = quickSpeak.QuickSpeakController()
		controller._token = 2
		controller._active = True
		quickSpeak.LIVE_RESPONSE_TIMEOUT = 0.01

		class Session:
			async def connect(self) -> None:
				pass

			async def send_client_content(self, _turns: list[dict[str, Any]], turn_complete: bool) -> None:
				pass

			async def receive(self) -> Any:
				await quickSpeak.asyncio.sleep(1)
				if False:
					yield {}

		with self.assertRaisesRegex(quickSpeak.DirectApiError, "response timed out"):
			quickSpeak.asyncio.run(controller._runLive(2, Session(), "thought"))

	def testLiveResponseTimeoutScalesForLongText(self) -> None:
		quickSpeak, _state = _loadQuickSpeak()

		self.assertEqual(quickSpeak._getLiveResponseTimeout("short"), 60.0)
		self.assertGreater(quickSpeak._getLiveResponseTimeout("x" * 1000), 60.0)
		self.assertEqual(quickSpeak._getLiveResponseTimeout("x" * 10000), 300.0)


if __name__ == "__main__":
	unittest.main()
