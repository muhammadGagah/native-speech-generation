from __future__ import annotations

import asyncio
import builtins
import contextlib
import importlib.util
import queue
import sys
import threading
import types
import unittest
from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
ADDON_PACKAGE = REPO_ROOT / "addon" / "globalPlugins" / "NativeSpeechGeneration"


class _Log:
	def debug(self, *_args: object, **_kwargs: object) -> None:
		pass

	def error(self, *_args: object, **_kwargs: object) -> None:
		pass

	def exception(self, *_args: object, **_kwargs: object) -> None:
		pass

	def info(self, *_args: object, **_kwargs: object) -> None:
		pass

	def warning(self, *_args: object, **_kwargs: object) -> None:
		pass


class _Window:
	pass


def _installCommonStubs() -> None:
	def translate(message: str) -> str:
		return message

	builtins._ = translate

	addonHandler = types.ModuleType("addonHandler")
	addonHandler.initTranslation = lambda: None
	sys.modules["addonHandler"] = addonHandler

	logHandler = types.ModuleType("logHandler")
	logHandler.log = _Log()
	sys.modules["logHandler"] = logHandler

	wx = types.ModuleType("wx")
	for name in (
		"Dialog",
		"StaticText",
		"Button",
		"ToggleButton",
		"BoxSizer",
		"Choice",
		"CheckBox",
		"Slider",
		"Window",
		"Event",
	):
		setattr(wx, name, _Window)
	wx.NOT_FOUND = -1
	wx.EVT_CHOICE = object()
	sys.modules["wx"] = wx


def _loadAudioUtils() -> Any:
	_installCommonStubs()
	moduleName = "nsg_audio_utils_under_test"
	sys.modules.pop(moduleName, None)
	spec = importlib.util.spec_from_file_location(moduleName, ADDON_PACKAGE / "core" / "audio_utils.py")
	assert spec is not None and spec.loader is not None
	module = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(module)
	return module


def _loadTalkWithAI() -> Any:
	_installCommonStubs()

	ui = types.ModuleType("ui")

	def announce(_message: str) -> None:
		pass

	ui.message = announce
	sys.modules["ui"] = ui

	packageName = "nsg_runtime_under_test"
	package = types.ModuleType(packageName)
	package.__path__ = [str(ADDON_PACKAGE)]
	sys.modules[packageName] = package
	corePackage = types.ModuleType(f"{packageName}.core")
	corePackage.__path__ = [str(ADDON_PACKAGE / "core")]
	sys.modules[f"{packageName}.core"] = corePackage

	audioRuntime = types.ModuleType(f"{packageName}.core.audio_runtime")
	audioRuntime.PYAUDIO_AVAILABLE = True
	audioRuntime.PYAUDIO_IMPORT_ERROR = None
	audioRuntime.pyaudio = types.SimpleNamespace(paInt16=8)
	audioRuntime.getRuntimeScope = contextlib.nullcontext
	sys.modules[audioRuntime.__name__] = audioRuntime

	moduleName = f"{packageName}.talkWithAI"
	spec = importlib.util.spec_from_file_location(moduleName, ADDON_PACKAGE / "talkWithAI.py")
	assert spec is not None and spec.loader is not None
	module = importlib.util.module_from_spec(spec)
	sys.modules[moduleName] = module
	spec.loader.exec_module(module)
	return module


class RuntimeRegressionTests(unittest.TestCase):
	def testConversationModelChangesControlThinkingWithoutMovingFocus(self) -> None:
		talkWithAI = _loadTalkWithAI()
		dialog = object.__new__(talkWithAI.TalkWithAIDialog)

		class Choice:
			selection = 0
			shown = True
			items: tuple[str, ...] = ()

			def GetSelection(self):
				return self.selection

			def SetSelection(self, value):
				self.selection = value

			def SetItems(self, items):
				self.items = tuple(items)

			def Show(self, shown):
				self.shown = shown

			def GetParent(self):
				return types.SimpleNamespace(Layout=lambda: None)

		dialog.thinkingChoice = Choice()
		dialog.thinkingLabel = Choice()
		dialog.Layout = lambda: None
		dialog._allThinkingChoices = [(v, v) for v in ("minimal", "low", "medium", "high")]
		dialog._preferredThinkingLevel = "minimal"
		dialog.modelChoices = [
			(v, v)
			for v in (talkWithAI.LIVE_38_MODEL, talkWithAI.LIVE_38_EXTENDED_MODEL, talkWithAI.LIVE_MODEL)
		]
		dialog.modelChoice = Choice()
		event = types.SimpleNamespace(Skip=lambda: None)
		for index, expectedLevel, shown, count in (
			(0, None, False, 4),
			(1, "low", True, 3),
			(2, "minimal", True, 4),
		):
			dialog.modelChoice.selection = index
			dialog._onModelChange(event)
			self.assertEqual(dialog._getSelectedThinkingLevel(), expectedLevel)
			self.assertEqual(dialog.thinkingChoice.shown, shown)
			self.assertEqual(dialog.thinkingLabel.shown, shown)
			self.assertEqual(len(dialog.thinkingChoice.items), count)
		# A chosen high level survives switching to the model without configurable thinking and back.
		dialog.thinkingChoice.selection = 3
		dialog._onThinkingChange(event)
		dialog.modelChoice.selection = 0
		dialog._onModelChange(event)
		self.assertIsNone(dialog._getSelectedThinkingLevel())
		dialog.modelChoice.selection = 1
		dialog._onModelChange(event)
		self.assertEqual(dialog._getSelectedThinkingLevel(), "high")

	def testExtendedThinkingReceivesAudioAfterTurnComplete(self) -> None:
		talkWithAI = _loadTalkWithAI()
		dialog = object.__new__(talkWithAI.TalkWithAIDialog)

		def isCurrent(sessionId: int) -> bool:
			return sessionId == 1

		dialog._isSessionCurrent = isCurrent
		dialog._interactionStatus = None
		dialog._rememberConversationTurn = mock.Mock()
		audio = []
		statuses = []
		dialog._queueAudioData = audio.append
		dialog.updateStatus = statuses.append

		def callAfter(callback: Callable[..., Any], *args: Any) -> Any:
			return callback(*args)

		talkWithAI.wx.CallAfter = callAfter

		class Session:
			async def receive(self):
				yield {"serverContent": {"turnComplete": True}, "interaction_status": "IN_PROGRESS"}
				yield {"serverContent": {"modelTurn": {"parts": [{"inlineData": {"data": "cGNt"}}]}}}
				yield {"interaction_status": "IDLE"}

		dialog.session = Session()
		asyncio.run(dialog.receiveLoop(dialog.session, 1))
		self.assertEqual(audio, [b"pcm"])
		self.assertEqual(statuses, ["AI processing", "AI ready for input"])
		dialog._reportInteractionStatus(1, "IDLE", dialog.session)
		dialog._reportInteractionStatus(0, "IN_PROGRESS", dialog.session)
		self.assertEqual(len(statuses), 2)

	def testReconnectClearsDedupAndRejectsOldConnectionCallbacks(self) -> None:
		talkWithAI = _loadTalkWithAI()
		dialog = object.__new__(talkWithAI.TalkWithAIDialog)

		def isCurrent(sessionId: int) -> bool:
			return sessionId == 1

		dialog._isSessionCurrent = isCurrent
		dialog._interactionStatus = "IDLE"
		oldSession = object()
		dialog.session = object()
		dialog.updateStatus = mock.Mock()
		dialog._playSoundEffect = mock.Mock()
		dialog._reportConnected(1, dialog.session)
		dialog.updateStatus.assert_called_once_with("Connected", announce=True)
		self.assertIsNone(dialog._interactionStatus)
		dialog.updateStatus.reset_mock()
		dialog._reportInteractionStatus(1, "IDLE", dialog.session)
		dialog.updateStatus.assert_called_once_with("AI ready for input")
		dialog.updateStatus.reset_mock()
		dialog._reportInteractionStatus(1, "IN_PROGRESS", oldSession)
		dialog._reportConnected(1, oldSession)
		dialog._reportConnected(0, dialog.session)
		dialog.updateStatus.assert_not_called()
		self.assertEqual(dialog._interactionStatus, "IDLE")

	def testResetDoesNotStealFocusAfterUserMovesAwayDuringStop(self) -> None:
		talkWithAI = _loadTalkWithAI()
		for focusTarget, isActive, expected in (
			("volume", True, False),
			("mic", True, True),
			("none", False, False),
		):
			with self.subTest(focusTarget=focusTarget):
				dialog = object.__new__(talkWithAI.TalkWithAIDialog)
				dialog._isClosing = False
				dialog._restoreConnectFocus = True
				dialog._devicesLoaded = True
				dialog.compatibilityError = None
				dialog._sessionHadError = False
				dialog.connectBtn = mock.Mock()
				dialog.disconnectBtn = mock.Mock()
				dialog.micBtn = mock.Mock()
				dialog.volSlider = mock.Mock()
				dialog.googleSearchCb = mock.Mock()
				dialog.modelChoice = mock.Mock()
				dialog.deviceSizer = mock.Mock()
				dialog.deviceSizer.GetChildren.return_value = []
				dialog._updateThinkingControls = mock.Mock()
				dialog.Layout = mock.Mock()
				dialog.updateStatus = mock.Mock()
				dialog.IsActive = lambda: isActive
				focus = {"volume": dialog.volSlider, "mic": dialog.micBtn, "none": None}[focusTarget]
				talkWithAI.wx.Window.FindFocus = lambda: focus
				dialog.resetUi()
				self.assertEqual(dialog.connectBtn.SetFocus.called, expected)
				dialog.modelChoice.Enable.assert_called_once()
				dialog._updateThinkingControls.assert_called_once()

	def testDeviceLoadingDoesNotMoveFocusOffMicrophone(self) -> None:
		talkWithAI = _loadTalkWithAI()
		dialog = object.__new__(talkWithAI.TalkWithAIDialog)
		dialog._isClosing = False
		dialog._persistedInputDevice = ""
		dialog._persistedOutputDevice = ""
		dialog.compatibilityError = None
		dialog.inputChoice = mock.Mock()
		dialog.outputChoice = mock.Mock()
		dialog.connectBtn = mock.Mock()
		dialog.micBtn = mock.Mock()
		dialog.micBtn.HasFocus.return_value = True
		dialog.updateStatus = mock.Mock()
		dialog._applyDeviceLists([{"name": "Mic", "index": 1}], [{"name": "Speakers", "index": 2}])
		dialog.connectBtn.Enable.assert_called_once()
		dialog.connectBtn.SetFocus.assert_not_called()
		dialog.inputChoice.SetSelection.assert_called_once_with(0)
		dialog.outputChoice.SetSelection.assert_called_once_with(0)
		dialog.updateStatus.assert_called_once_with("Audio devices loaded", announce=True)

	def testAudioSavePathKeepsGeneratedFormat(self) -> None:
		audioUtils = _loadAudioUtils()
		self.assertEqual(
			audioUtils.normalizeAudioSavePath("generated.wav", "saved"),
			"saved.wav",
		)
		self.assertEqual(
			audioUtils.normalizeAudioSavePath("generated.wav", "saved.WAV"),
			"saved.WAV",
		)
		with self.assertRaises(ValueError):
			audioUtils.normalizeAudioSavePath("generated.wav", "saved.mp3")

	def testDeviceEnumerationUsesGlobalPortAudioIndexes(self) -> None:
		talkWithAI = _loadTalkWithAI()

		class FakePyAudio:
			terminated = False
			devices: tuple[dict[str, Any], ...] = (
				{"index": 2, "name": "MME microphone", "maxInputChannels": 1, "maxOutputChannels": 0},
				{"index": 7, "name": "WASAPI speakers", "maxInputChannels": 0, "maxOutputChannels": 2},
			)

			def get_device_count(self) -> int:
				return len(self.devices)

			def get_device_info_by_index(self, index: int) -> dict[str, Any]:
				return self.devices[index]

			def terminate(self) -> None:
				self.terminated = True

		fakePyAudio = FakePyAudio()
		talkWithAI.pyaudio = types.SimpleNamespace(PyAudio=lambda: fakePyAudio, paInt16=8)
		dialog = object.__new__(talkWithAI.TalkWithAIDialog)

		self.assertEqual(dialog._getDeviceList(input=True), [{"index": 2, "name": "MME microphone"}])
		self.assertEqual(dialog._getDeviceList(input=False), [{"index": 7, "name": "WASAPI speakers"}])
		self.assertTrue(fakePyAudio.terminated)

	def testDeviceEnumerationPrioritizesSystemDefault(self) -> None:
		talkWithAI = _loadTalkWithAI()

		class FakePyAudio:
			devices: tuple[dict[str, Any], ...] = (
				{"index": 2, "name": "First microphone", "maxInputChannels": 1, "maxOutputChannels": 0},
				{"index": 7, "name": "Default microphone", "maxInputChannels": 1, "maxOutputChannels": 0},
			)

			def get_default_input_device_info(self) -> dict[str, int]:
				return {"index": 7}

			def get_device_count(self) -> int:
				return len(self.devices)

			def get_device_info_by_index(self, index: int) -> dict[str, Any]:
				return self.devices[index]

			def terminate(self) -> None:
				pass

		talkWithAI.pyaudio = types.SimpleNamespace(PyAudio=FakePyAudio, paInt16=8)
		dialog = object.__new__(talkWithAI.TalkWithAIDialog)

		self.assertEqual(dialog._getDeviceList(input=True)[0]["index"], 7)

	def testPersistedAudioDeviceSelectionUsesNameAndFallsBackToDefault(self) -> None:
		talkWithAI = _loadTalkWithAI()
		devices = [
			{"index": 7, "name": "Default microphone"},
			{"index": 2, "name": "USB microphone"},
		]

		self.assertEqual(talkWithAI.TalkWithAIDialog._findDeviceSelection(devices, "USB microphone"), 1)
		self.assertEqual(talkWithAI.TalkWithAIDialog._findDeviceSelection(devices, "Missing device"), 0)

	def testTalkWithAIPersistentSettingsSaveCurrentSelections(self) -> None:
		talkWithAI = _loadTalkWithAI()
		dialog = object.__new__(talkWithAI.TalkWithAIDialog)
		dialog._persistedInputDevice = "old microphone"
		dialog._persistedOutputDevice = "old speakers"
		dialog._inputDeviceSelectionDirty = True
		dialog._outputDeviceSelectionDirty = True
		dialog.inputDevices = [{"index": 4, "name": "USB microphone"}]
		dialog.outputDevices = [{"index": 9, "name": "USB speakers"}]
		dialog.inputChoice = types.SimpleNamespace(GetSelection=lambda: 0)
		dialog.outputChoice = types.SimpleNamespace(GetSelection=lambda: 0)
		dialog.volSlider = types.SimpleNamespace(GetValue=lambda: 65)
		saved: list[tuple[str, str, int]] = []

		def saveSettings(inputDevice: str, outputDevice: str, volume: int, **modelSettings: Any) -> None:
			saved.append((inputDevice, outputDevice, volume))

		dialog.selectedModel = talkWithAI.LIVE_MODEL
		dialog._preferredThinkingLevel = "minimal"
		talkWithAI.config_store.setTalkWithAISettings = saveSettings

		dialog._savePersistentSettings()

		self.assertEqual(saved, [("USB microphone", "USB speakers", 65)])

	def testTalkWithAIPersistentSettingsSaveDefaultsWhenUnset(self) -> None:
		talkWithAI = _loadTalkWithAI()
		dialog = object.__new__(talkWithAI.TalkWithAIDialog)
		dialog._persistedInputDevice = ""
		dialog._persistedOutputDevice = ""
		dialog._inputDeviceSelectionDirty = False
		dialog._outputDeviceSelectionDirty = False
		dialog.inputDevices = [{"index": 4, "name": "Default microphone"}]
		dialog.outputDevices = [{"index": 9, "name": "Default speakers"}]
		dialog.inputChoice = types.SimpleNamespace(GetSelection=lambda: 0)
		dialog.outputChoice = types.SimpleNamespace(GetSelection=lambda: 0)
		dialog.volSlider = types.SimpleNamespace(GetValue=lambda: 80)
		saved: list[tuple[str, str, int]] = []

		def saveSettings(inputDevice: str, outputDevice: str, volume: int, **modelSettings: Any) -> None:
			saved.append((inputDevice, outputDevice, volume))

		dialog.selectedModel = talkWithAI.LIVE_MODEL
		dialog._preferredThinkingLevel = "minimal"
		talkWithAI.config_store.setTalkWithAISettings = saveSettings
		dialog._savePersistentSettings()

		self.assertEqual(saved, [("Default microphone", "Default speakers", 80)])

	def testTalkWithAIPersistentSettingsKeepUnavailableDevice(self) -> None:
		talkWithAI = _loadTalkWithAI()
		dialog = object.__new__(talkWithAI.TalkWithAIDialog)
		dialog._persistedInputDevice = "Disconnected microphone"
		dialog._persistedOutputDevice = "Disconnected speakers"
		dialog._inputDeviceSelectionDirty = False
		dialog._outputDeviceSelectionDirty = False
		dialog.inputDevices = [{"index": 4, "name": "Current microphone"}]
		dialog.outputDevices = [{"index": 9, "name": "Current speakers"}]
		dialog.inputChoice = types.SimpleNamespace(GetSelection=lambda: 0)
		dialog.outputChoice = types.SimpleNamespace(GetSelection=lambda: 0)
		dialog.volSlider = types.SimpleNamespace(GetValue=lambda: 70)
		saved: list[tuple[str, str, int]] = []

		def saveSettings(inputDevice: str, outputDevice: str, volume: int, **modelSettings: Any) -> None:
			saved.append((inputDevice, outputDevice, volume))

		dialog.selectedModel = talkWithAI.LIVE_MODEL
		dialog._preferredThinkingLevel = "minimal"
		talkWithAI.config_store.setTalkWithAISettings = saveSettings
		dialog._savePersistentSettings()

		self.assertEqual(saved, [("Disconnected microphone", "Disconnected speakers", 70)])

	def testTalkWithAICloseAlwaysDestroysWhenSettingsSaveFails(self) -> None:
		talkWithAI = _loadTalkWithAI()
		dialog = object.__new__(talkWithAI.TalkWithAIDialog)
		dialog._isClosing = False
		dialog._sessionId = 0
		dialog.sessionActive = True
		dialog.isPlaying = True
		dialog.loop = None
		dialog.audioQueue = queue.Queue()
		dialog._stopScreenCapture = lambda: None
		dialog._savePersistentSettings = lambda: (_ for _ in ()).throw(RuntimeError("save failed"))

		def ignoreCleanupFailure(_action: str, _error: BaseException) -> None:
			pass

		dialog._logCleanupFailure = ignoreCleanupFailure
		dialog._clearSessionHistory = lambda: None
		dialog._flushAudioQueue = lambda: None
		dialog._stopAudioPlayer = lambda: None
		dialog._closeAudioResources = lambda: None
		dialog.IsModal = lambda: False
		dialog.Destroy = lambda: setattr(dialog, "destroyed", True)

		dialog.onClose(types.SimpleNamespace())

		self.assertTrue(dialog._isClosing)
		self.assertTrue(dialog.destroyed)

	def testPlaybackFlushInvalidatesBufferedAudio(self) -> None:
		talkWithAI = _loadTalkWithAI()
		dialog = object.__new__(talkWithAI.TalkWithAIDialog)
		dialog.audioQueue = queue.Queue()
		dialog.audioQueue.put(b"old audio")
		dialog._playbackGeneration = 4

		dialog._flushAudioQueue()

		self.assertEqual(dialog._playbackGeneration, 5)
		self.assertTrue(dialog.audioQueue.empty())

	def testInterruptionFlushesPortAudioBuffer(self) -> None:
		talkWithAI = _loadTalkWithAI()

		class Stream:
			def __init__(self) -> None:
				super().__init__()
				self.stopped = False
				self.started = False

			def is_active(self) -> bool:
				return True

			def stop_stream(self) -> None:
				self.stopped = True

			def start_stream(self) -> None:
				self.started = True

		dialog = object.__new__(talkWithAI.TalkWithAIDialog)
		dialog.audioQueue = queue.Queue()
		dialog.audioQueue.put(b"buffered")
		dialog._playbackGeneration = 0
		dialog.outputStream = Stream()
		dialog.outputLock = threading.Lock()

		def ignoreCleanupFailure(_action: str, _error: BaseException) -> None:
			pass

		dialog._logCleanupFailure = ignoreCleanupFailure

		dialog._handleServerContent({"interrupted": True})

		self.assertTrue(dialog.audioQueue.empty())
		self.assertTrue(dialog.outputStream.stopped)
		self.assertTrue(dialog.outputStream.started)

	def testPersistentSessionErrorDisablesFutureConnection(self) -> None:
		talkWithAI = _loadTalkWithAI()
		dialog = object.__new__(talkWithAI.TalkWithAIDialog)
		dialog._isClosing = False
		dialog._sessionId = 3
		dialog._sessionHadError = False
		dialog.compatibilityError = None
		reported: list[str] = []

		def recordError(message: str) -> None:
			reported.append(message)

		dialog.reportError = recordError
		dialog._reportSessionError(3, "unsupported runtime", persistent=True)

		self.assertTrue(dialog._sessionHadError)
		self.assertEqual(dialog.compatibilityError, "unsupported runtime")
		self.assertEqual(reported, ["unsupported runtime"])

	def testPlaybackFailureEndsPlayerState(self) -> None:
		talkWithAI = _loadTalkWithAI()
		talkWithAI.BUFFER_THRESHOLD = 1

		class BrokenStream:
			def is_active(self) -> bool:
				return True

			def write(self, _data: bytes) -> None:
				raise OSError("device disconnected")

		dialog = object.__new__(talkWithAI.TalkWithAIDialog)
		dialog._sessionId = 1
		dialog.sessionActive = True
		dialog._isClosing = False
		dialog.isPlaying = True
		dialog._audioPlayerThread = threading.current_thread()
		dialog._playbackGeneration = 0
		dialog.audioQueue = queue.Queue()
		dialog.audioQueue.put(b"\x00\x00")
		dialog.outputStream = BrokenStream()
		dialog.volume = 100
		dialog.lastBufferAdjustAt = 0.0
		failures: list[BaseException] = []

		def recordFailure(_sessionId: int, error: BaseException) -> None:
			failures.append(error)

		dialog._failSessionFromAudioWorker = recordFailure

		dialog._audioPlayerWorker(1)

		self.assertFalse(dialog.isPlaying)
		self.assertEqual(len(failures), 1)

	def testCleanupClosesDirectLiveSession(self) -> None:
		talkWithAI = _loadTalkWithAI()
		dialog = object.__new__(talkWithAI.TalkWithAIDialog)
		closed: list[bool] = []

		class Session:
			async def close(self) -> None:
				closed.append(True)

		dialog._sessionId = 1
		dialog.sessionActive = True
		dialog.isPlaying = False
		dialog.session = Session()
		dialog._sessionTask = None
		dialog.audioQueue = queue.Queue()
		dialog._playbackGeneration = 0
		dialog._audioPlayerThread = None
		dialog.inputStream = None
		dialog.outputStream = None
		dialog.audioInterface = None
		dialog._screenCaptureWorker = None
		asyncio.run(dialog.cleanupAsync(1))

		self.assertEqual(closed, [True])
		self.assertIsNone(dialog.session)

	def testReceiveLoopSuppressesSocketCloseAfterDisconnect(self) -> None:
		talkWithAI = _loadTalkWithAI()
		dialog = object.__new__(talkWithAI.TalkWithAIDialog)
		dialog._sessionId = 1
		dialog.sessionActive = False
		dialog._isClosing = False

		class ClosedSocketError(OSError):
			winerror = 10038

		class Session:
			async def receive(self) -> Any:
				raise ClosedSocketError("An operation was attempted on something that is not a socket")
				yield {}

		asyncio.run(dialog.receiveLoop(Session(), 1))

	def testInactiveOutputStreamIsReportedAsPlaybackFailure(self) -> None:
		talkWithAI = _loadTalkWithAI()
		dialog = object.__new__(talkWithAI.TalkWithAIDialog)
		dialog.outputStream = types.SimpleNamespace(is_active=lambda: False)
		with self.assertRaises(RuntimeError):
			dialog._writeAudioChunk(b"audio")

	def testPermanentSessionErrorsDoNotRetry(self) -> None:
		talkWithAI = _loadTalkWithAI()
		dialog = object.__new__(talkWithAI.TalkWithAIDialog)

		class UnauthorizedError(RuntimeError):
			status_code = 401

		self.assertTrue(dialog._isPermanentSessionError(UnauthorizedError("bad key")))
		self.assertFalse(dialog._isPermanentSessionError(RuntimeError("temporary network failure")))
		apiClient = sys.modules["nsg_runtime_under_test.core.api_client"]
		for code, status, expected in (
			(400, "INVALID_ARGUMENT", True),
			(None, "INVALID_ARGUMENT", True),
			(403, "PERMISSION_DENIED", True),
			(429, "RESOURCE_EXHAUSTED", False),
			(503, "UNAVAILABLE", False),
		):
			with self.subTest(code=code, status=status):
				error = apiClient.DirectApiError.fromResponse(
					{
						"code": code,
						"status": status,
						"message": "thinkingLevel is not supported for this model",
					},
				)
				self.assertEqual(dialog._isPermanentSessionError(error), expected)


if __name__ == "__main__":
	unittest.main()
