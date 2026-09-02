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
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
ADDON_PACKAGE = REPO_ROOT / "addon" / "globalPlugins" / "NativeSpeechGeneration"


class _Log:
	def debug(self, *_args: object, **_kwargs: object) -> None:
		pass

	def error(self, *_args: object, **_kwargs: object) -> None:
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
			devices: list[dict[str, object]] = [
				{"index": 2, "name": "MME microphone", "maxInputChannels": 1, "maxOutputChannels": 0},
				{"index": 7, "name": "WASAPI speakers", "maxInputChannels": 0, "maxOutputChannels": 2},
			]

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
			devices = [
				{"index": 2, "name": "First microphone", "maxInputChannels": 1, "maxOutputChannels": 0},
				{"index": 7, "name": "Default microphone", "maxInputChannels": 1, "maxOutputChannels": 0},
			]

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
		def saveSettings(inputDevice: str, outputDevice: str, volume: int) -> None:
			saved.append((inputDevice, outputDevice, volume))

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

		def saveSettings(inputDevice: str, outputDevice: str, volume: int) -> None:
			saved.append((inputDevice, outputDevice, volume))

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

		def saveSettings(inputDevice: str, outputDevice: str, volume: int) -> None:
			saved.append((inputDevice, outputDevice, volume))

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


if __name__ == "__main__":
	unittest.main()
