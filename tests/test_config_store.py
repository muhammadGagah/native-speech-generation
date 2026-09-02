from __future__ import annotations

import builtins
import importlib.util
import sys
import types
import unittest
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
CORE_DIR = REPO_ROOT / "addon" / "globalPlugins" / "NativeSpeechGeneration" / "core"


class _Log:
	def debug(self, *_args: object, **_kwargs: object) -> None:
		pass

	def info(self, *_args: object, **_kwargs: object) -> None:
		pass

	def warning(self, *_args: object, **_kwargs: object) -> None:
		pass

	def error(self, *_args: object, **_kwargs: object) -> None:
		pass


class _FakeConfig(dict[str, dict[str, Any]]):
	def __init__(self) -> None:
		super().__init__()
		self.spec: dict[str, dict[str, str]] = {}
		self.saved = False

	def __getitem__(self, key: str) -> dict[str, Any]:
		if key not in self:
			self[key] = {}
		return super().__getitem__(key)

	def save(self) -> None:
		self.saved = True


def _loadConfigStore(*, writable: bool = True) -> tuple[Any, _FakeConfig]:
	def translate(message: str) -> str:
		return message

	builtins._ = translate
	fakeConfig = _FakeConfig()
	config = types.ModuleType("config")
	config.conf = fakeConfig
	config.save = fakeConfig.save
	sys.modules["config"] = config

	logHandler = types.ModuleType("logHandler")
	logHandler.log = _Log()
	sys.modules["logHandler"] = logHandler

	packageName = "nsg_config_under_test"
	package = types.ModuleType(packageName)
	package.__path__ = [str(CORE_DIR.parent)]
	sys.modules[packageName] = package
	corePackage = types.ModuleType(f"{packageName}.core")
	corePackage.__path__ = [str(CORE_DIR)]
	sys.modules[f"{packageName}.core"] = corePackage

	nvdaCompat = types.ModuleType(f"{packageName}.core.nvda_compat")

	def shouldWriteToDisk() -> bool:
		return writable

	nvdaCompat.shouldWriteToDisk = shouldWriteToDisk
	sys.modules[nvdaCompat.__name__] = nvdaCompat

	constantsName = f"{packageName}.core.constants"
	constantsSpec = importlib.util.spec_from_file_location(constantsName, CORE_DIR / "constants.py")
	assert constantsSpec is not None and constantsSpec.loader is not None
	constants = importlib.util.module_from_spec(constantsSpec)
	sys.modules[constantsName] = constants
	constantsSpec.loader.exec_module(constants)

	moduleName = f"{packageName}.core.config_store"
	spec = importlib.util.spec_from_file_location(moduleName, CORE_DIR / "config_store.py")
	assert spec is not None and spec.loader is not None
	module = importlib.util.module_from_spec(spec)
	sys.modules[moduleName] = module
	spec.loader.exec_module(module)
	return module, fakeConfig


class ConfigStoreTests(unittest.TestCase):
	def testQuickSpeakDefaultsUseRecommendedLiveModel(self) -> None:
		configStore, _fakeConfig = _loadConfigStore()

		settings = configStore.getQuickSpeakSettings()

		self.assertEqual(settings.model, "gemini-3.1-flash-live-preview")
		self.assertEqual(settings.voice, "Kore")
		self.assertEqual(settings.styleInstructions, "")
		self.assertEqual(settings.volume, 80)

	def testNativeAudioModelIsAcceptedForQuickSpeak(self) -> None:
		configStore, _fakeConfig = _loadConfigStore()

		configStore.setQuickSpeakSettings(
			"gemini-2.5-flash-native-audio-preview-12-2025",
			"Kore",
			"",
		)

		self.assertEqual(
			configStore.getQuickSpeakSettings().model, "gemini-2.5-flash-native-audio-preview-12-2025"
		)

	def testInvalidQuickSpeakValuesFallBackSafely(self) -> None:
		configStore, fakeConfig = _loadConfigStore()
		section = fakeConfig["NativeSpeechGeneration"]
		section["quickSpeakModel"] = "removed-model"
		section["quickSpeakVoice"] = "removed-voice"
		section["quickSpeakStyle"] = "  British English pronunciation  "

		settings = configStore.getQuickSpeakSettings()

		self.assertEqual(settings.model, "gemini-3.1-flash-live-preview")
		self.assertEqual(settings.voice, "Kore")
		self.assertEqual(settings.styleInstructions, "British English pronunciation")
		self.assertEqual(settings.volume, 80)

	def testQuickSpeakVolumeIsClampedAndPersisted(self) -> None:
		configStore, fakeConfig = _loadConfigStore()

		configStore.setQuickSpeakSettings("gemini-3.1-flash-live-preview", "Kore", "", 125)

		self.assertEqual(fakeConfig["NativeSpeechGeneration"]["quickSpeakVolume"], 100)
		self.assertEqual(configStore.getQuickSpeakSettings().volume, 100)

	def testQuickSpeakSettingsAreNotWrittenInRestrictedMode(self) -> None:
		configStore, fakeConfig = _loadConfigStore(writable=False)

		configStore.setQuickSpeakSettings(
			"gemini-3.1-flash-tts-preview",
			"Zephyr",
			"American English pronunciation",
		)

		self.assertNotIn("quickSpeakModel", fakeConfig["NativeSpeechGeneration"])

	def testTalkWithAISettingsPersistAndClampVolume(self) -> None:
		configStore, fakeConfig = _loadConfigStore()

		configStore.setTalkWithAISettings("USB microphone", "USB speakers", 150)
		settings = configStore.getTalkWithAISettings()

		self.assertEqual(settings.inputDevice, "USB microphone")
		self.assertEqual(settings.outputDevice, "USB speakers")
		self.assertEqual(settings.volume, 100)
		self.assertEqual(fakeConfig["NativeSpeechGeneration"]["talkWithAIVolume"], 100)
		self.assertTrue(fakeConfig.saved)

	def testTalkWithAISettingsAreNotWrittenInRestrictedMode(self) -> None:
		configStore, fakeConfig = _loadConfigStore(writable=False)

		configStore.setTalkWithAISettings("microphone", "speakers", 70)

		self.assertNotIn("talkWithAIInputDevice", fakeConfig["NativeSpeechGeneration"])


if __name__ == "__main__":
	unittest.main()
