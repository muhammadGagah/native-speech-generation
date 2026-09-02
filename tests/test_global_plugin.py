from __future__ import annotations

import builtins
import importlib.util
import sys
import types
import unittest
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


def _loadGlobalPlugin() -> tuple[Any, types.SimpleNamespace]:
	def translate(message: str) -> str:
		return message

	builtins._ = translate
	state = types.SimpleNamespace(writable=True, secure=False, messages=[], callLater=[])

	addonHandler = types.ModuleType("addonHandler")
	addonHandler.initTranslation = lambda: None
	sys.modules["addonHandler"] = addonHandler

	globalPluginHandler = types.ModuleType("globalPluginHandler")

	class BaseGlobalPlugin:
		def __init__(self) -> None:
			super().__init__()
			self.baseTerminated = False

		def terminate(self) -> None:
			self.baseTerminated = True

	globalPluginHandler.GlobalPlugin = BaseGlobalPlugin
	sys.modules["globalPluginHandler"] = globalPluginHandler

	gui = types.ModuleType("gui")
	gui.settingsDialogs = types.SimpleNamespace(
		NVDASettingsDialog=types.SimpleNamespace(categoryClasses=[]),
	)
	gui.mainFrame = types.SimpleNamespace()
	sys.modules["gui"] = gui

	ui = types.ModuleType("ui")
	ui.message = state.messages.append
	sys.modules["ui"] = ui

	wx = types.ModuleType("wx")
	wx.Event = object

	class Timer:
		def __init__(self) -> None:
			super().__init__()
			self.stopped = False

		def Stop(self) -> None:
			self.stopped = True

	def callLater(_delay: int, callback: Any, *args: object) -> Timer:
		timer = Timer()
		state.callLater.append((callback, args, timer))
		return timer

	wx.CallLater = callLater
	sys.modules["wx"] = wx

	logHandler = types.ModuleType("logHandler")
	logHandler.log = _Log()
	sys.modules["logHandler"] = logHandler

	scriptHandler = types.ModuleType("scriptHandler")

	def script(**_kwargs: object) -> Any:
		def decorate(function: Any) -> Any:
			return function

		return decorate

	scriptHandler.script = script
	sys.modules["scriptHandler"] = scriptHandler

	packageName = "nsg_plugin_under_test"
	corePackage = types.ModuleType(f"{packageName}.core")
	corePackage.__path__ = [str(ADDON_PACKAGE / "core")]
	sys.modules[f"{packageName}.core"] = corePackage

	configStore = types.ModuleType(f"{packageName}.core.config_store")
	sys.modules[configStore.__name__] = configStore

	nvdaCompat = types.ModuleType(f"{packageName}.core.nvda_compat")
	nvdaCompat.shouldWriteToDisk = lambda: state.writable
	nvdaCompat.isSecureMode = lambda: state.secure
	sys.modules[nvdaCompat.__name__] = nvdaCompat

	quickSpeak = types.ModuleType(f"{packageName}.core.quick_speak")

	class QuickSpeakInputError(RuntimeError):
		pass

	class QuickSpeakController:
		def __init__(self) -> None:
			super().__init__()

	quickSpeak.QuickSpeakController = QuickSpeakController
	quickSpeak.QuickSpeakInputError = QuickSpeakInputError
	quickSpeak.getSelectedText = lambda: "selection"
	quickSpeak.getClipboardText = lambda: "clipboard"
	sys.modules[quickSpeak.__name__] = quickSpeak

	moduleName = packageName
	sys.modules.pop(moduleName, None)
	spec = importlib.util.spec_from_file_location(
		moduleName,
		ADDON_PACKAGE / "__init__.py",
		submodule_search_locations=[str(ADDON_PACKAGE)],
	)
	assert spec is not None and spec.loader is not None
	module = importlib.util.module_from_spec(spec)
	sys.modules[moduleName] = module
	spec.loader.exec_module(module)
	return module, state


class _Controller:
	def __init__(self, stopResults: list[bool] | None = None) -> None:
		super().__init__()
		self.stopResults = list(stopResults or [])
		self.started: list[str] = []
		self.stopCount = 0

	def stop(self) -> bool:
		self.stopCount += 1
		return self.stopResults.pop(0) if self.stopResults else False

	def start(self, text: str) -> None:
		self.started.append(text)


class GlobalPluginTests(unittest.TestCase):
	def testGestureDebouncesAutoRepeatAndLaterStopsActiveWork(self) -> None:
		pluginModule, state = _loadGlobalPlugin()
		plugin = object.__new__(pluginModule.GlobalPlugin)
		controller = _Controller([False, True])
		plugin._quickSpeakController = controller
		plugin._quickSpeakHeldKeys = set()
		plugin._quickSpeakKeyTimers = {}
		gesture = types.SimpleNamespace(vkCode=69)
		providerCalls: list[bool] = []

		def provideText() -> str:
			providerCalls.append(True)
			return "through"

		plugin._handleQuickSpeakGesture(gesture, provideText)
		plugin._handleQuickSpeakGesture(gesture, provideText)
		with mock.patch.object(pluginModule, "_isKeyDown", return_value=False):
			callback, args, _timer = state.callLater.pop(0)
			callback(*args)
		plugin._handleQuickSpeakGesture(gesture, provideText)

		self.assertEqual(controller.started, ["through"])
		self.assertEqual(controller.stopCount, 2)
		self.assertEqual(providerCalls, [True])

	def testRestrictedModeDoesNotReadOrStartQuickSpeak(self) -> None:
		pluginModule, state = _loadGlobalPlugin()
		state.writable = False
		plugin = object.__new__(pluginModule.GlobalPlugin)
		controller = _Controller()
		plugin._quickSpeakController = controller
		plugin._quickSpeakHeldKeys = set()
		plugin._quickSpeakKeyTimers = {}
		providerCalls: list[bool] = []
		gesture = types.SimpleNamespace(vkCode=70)

		plugin._handleQuickSpeakGesture(gesture, lambda: providerCalls.append(True) or "text")
		plugin._handleQuickSpeakGesture(gesture, lambda: providerCalls.append(True) or "text")

		self.assertEqual(controller.stopCount, 0)
		self.assertEqual(controller.started, [])
		self.assertEqual(providerCalls, [])
		self.assertEqual(state.messages, ["Quick Speak is unavailable in this NVDA mode."])

	def testRemappedKeyboardGestureTracksItsActualVirtualKey(self) -> None:
		pluginModule, state = _loadGlobalPlugin()
		plugin = object.__new__(pluginModule.GlobalPlugin)
		controller = _Controller()
		plugin._quickSpeakController = controller
		plugin._quickSpeakHeldKeys = set()
		plugin._quickSpeakKeyTimers = {}
		gesture = types.SimpleNamespace(vkCode=84)

		plugin._handleQuickSpeakGesture(gesture, lambda: "text")

		self.assertEqual(plugin._quickSpeakHeldKeys, {84})
		callback, args, _timer = state.callLater.pop(0)
		with mock.patch.object(pluginModule, "_isKeyDown", return_value=False) as keyState:
			callback(*args)
		keyState.assert_called_once_with(84)
		self.assertEqual(plugin._quickSpeakHeldKeys, set())

	def testTerminateStopsQuickSpeakBeforeBaseTermination(self) -> None:
		pluginModule, _state = _loadGlobalPlugin()
		plugin = object.__new__(pluginModule.GlobalPlugin)
		controller = _Controller()
		plugin._quickSpeakController = controller
		plugin._quickSpeakHeldKeys = {69}
		timer = types.SimpleNamespace(stopped=False)
		timer.Stop = lambda: setattr(timer, "stopped", True)
		plugin._quickSpeakKeyTimers = {69: timer}
		plugin.dialog = None
		plugin._settingsPanelClass = None
		plugin.menuItem = None
		plugin.baseTerminated = False

		plugin.terminate()

		self.assertEqual(controller.stopCount, 1)
		self.assertTrue(timer.stopped)
		self.assertEqual(plugin._quickSpeakKeyTimers, {})
		self.assertEqual(plugin._quickSpeakHeldKeys, set())
		self.assertTrue(plugin.baseTerminated)


if __name__ == "__main__":
	unittest.main()
