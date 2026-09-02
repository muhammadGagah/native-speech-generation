from __future__ import annotations

import builtins
import importlib.util
import sys
import tempfile
import types
import unittest
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
LIB_UPDATER_PATH = REPO_ROOT / "addon" / "globalPlugins" / "NativeSpeechGeneration" / "lib_updater.py"


class _Log:
	def debug(self, *_args: object, **_kwargs: object) -> None:
		pass

	def error(self, *_args: object, **_kwargs: object) -> None:
		pass

	def info(self, *_args: object, **_kwargs: object) -> None:
		pass

	def warning(self, *_args: object, **_kwargs: object) -> None:
		pass


class _ProgressDialog:
	def __init__(self, *_args: object, **_kwargs: object) -> None:
		super().__init__()

	def Destroy(self) -> None:
		pass

	def Update(self, *_args: object, **_kwargs: object) -> None:
		pass


def _translate(message: str) -> str:
	return message


def _callAfter(function: Callable[..., Any], *args: object, **kwargs: object) -> Any:
	return function(*args, **kwargs)


def _callLater(_delay: object, function: Callable[..., Any], *args: object, **kwargs: object) -> Any:
	return function(*args, **kwargs)


def _messageBox(*_args: object, **_kwargs: object) -> int:
	return 1


def _installNvdaStubs() -> None:
	builtins._ = _translate

	addonHandler = types.ModuleType("addonHandler")
	addonHandler.initTranslation = lambda: None
	sys.modules["addonHandler"] = addonHandler

	core = types.ModuleType("core")
	core.restart = lambda: None
	sys.modules["core"] = core

	gui = types.ModuleType("gui")
	gui.mainFrame = object()
	gui.messageBox = _messageBox
	sys.modules["gui"] = gui

	logHandler = types.ModuleType("logHandler")
	logHandler.log = _Log()
	sys.modules["logHandler"] = logHandler

	wx = types.ModuleType("wx")
	wx.CallAfter = _callAfter
	wx.CallLater = _callLater
	wx.MessageBox = _messageBox
	wx.ProgressDialog = _ProgressDialog
	wx.OK = 1
	wx.CANCEL = 2
	wx.ICON_ERROR = 4
	wx.ICON_INFORMATION = 8
	wx.PD_APP_MODAL = 16
	wx.PD_AUTO_HIDE = 32
	sys.modules["wx"] = wx

	buildVersion = types.ModuleType("buildVersion")
	buildVersion.version = "2026.1"
	sys.modules["buildVersion"] = buildVersion


def _loadLibUpdater() -> Any:
	_installNvdaStubs()
	moduleName = "nsg_lib_updater_under_test"
	sys.modules.pop(moduleName, None)
	spec = importlib.util.spec_from_file_location(moduleName, LIB_UPDATER_PATH)
	assert spec is not None
	assert spec.loader is not None
	module = importlib.util.module_from_spec(spec)
	sys.modules[moduleName] = module
	spec.loader.exec_module(module)
	return module


class LibUpdaterTests(unittest.TestCase):
	libUpdater: Any = None

	def setUp(self) -> None:
		self.libUpdater = _loadLibUpdater()

	def testRuntimeWheelSelectionUsesPythonAndArchitecture(self) -> None:
		self.assertEqual(
			self.libUpdater.getRuntimeAssetName((3, 11), 32),
			"PyAudio-0.2.14-cp311-cp311-win32.whl",
		)
		self.assertEqual(
			self.libUpdater.getRuntimeAssetName((3, 13), 64),
			"PyAudio-0.2.14-cp313-cp313-win_amd64.whl",
		)
		with self.assertRaises(self.libUpdater.LibraryUpdateError):
			self.libUpdater.getRuntimeAssetName((3, 13), 128)

	def testApprovedPyAudioWheelsArePinned(self) -> None:
		wheel32 = "PyAudio-0.2.14-cp311-cp311-win32.whl"
		wheel64 = "PyAudio-0.2.14-cp313-cp313-win_amd64.whl"
		metadata = {
			"urls": [
				{
					"filename": wheel32,
					"url": f"https://example.test/{wheel32}",
					"digests": {"sha256": self.libUpdater.APPROVED_LIBRARY_SHA256[wheel32]},
				},
				{
					"filename": wheel64,
					"url": f"https://example.test/{wheel64}",
					"digests": {"sha256": self.libUpdater.APPROVED_LIBRARY_SHA256[wheel64]},
				},
			],
		}
		def readMetadata(_url: str) -> dict[str, Any]:
			return metadata

		self.libUpdater._readJsonUrl = readMetadata

		lib32 = self.libUpdater.getApprovedLibraryAsset(wheel32)
		lib64 = self.libUpdater.getApprovedLibraryAsset(wheel64)

		self.assertEqual(lib32.version, "0.2.14")
		self.assertEqual(lib32.source, "pypi")
		self.assertEqual(
			lib32.sha256,
			"506b32a595f8693811682ab4b127602d404df7dfc453b499c91a80d0f7bad289",
		)
		self.assertEqual(lib64.version, "0.2.14")
		self.assertEqual(lib64.source, "pypi")
		self.assertEqual(
			lib64.sha256,
			"692d8c1446f52ed2662120bcd9ddcb5aa2b71f38bda31e58b19fb4672fffba69",
		)

	def testPyAudioMetadataChecksumMustMatchPinnedValue(self) -> None:
		wheel = "PyAudio-0.2.14-cp313-cp313-win_amd64.whl"
		def readBadMetadata(_url: str) -> dict[str, Any]:
			return {
				"urls": [
					{
						"filename": wheel,
						"url": "https://example.test/wheel",
						"digests": {"sha256": "0" * 64},
					},
				],
			}

		self.libUpdater._readJsonUrl = readBadMetadata
		with self.assertRaisesRegex(self.libUpdater.LibraryUpdateError, "checksum metadata"):
			self.libUpdater.getApprovedLibraryAsset(wheel)

	def testCurrentInstallRejectsLegacyDependencyFiles(self) -> None:
		with tempfile.TemporaryDirectory() as tempDir:
			self.libUpdater.LIB_DIR = tempDir
			pythonTag, platformTag = self.libUpdater._getRuntimeTags()
			pyaudioDir = Path(tempDir, "pyaudio")
			pyaudioDir.mkdir()
			Path(pyaudioDir, "__init__.py").write_text("", encoding="utf-8")
			Path(pyaudioDir, f"_portaudio.{pythonTag}-{platformTag}.pyd").write_bytes(b"")
			Path(tempDir, "anyio").mkdir()
			self.assertFalse(self.libUpdater._isCurrentLibraryInstall())
			Path(tempDir, "anyio").rmdir()
			Path(tempDir, "PyAudio-0.2.14.dist-info").mkdir()
			self.assertTrue(self.libUpdater._isCurrentLibraryInstall())

	def testUnsafeZipMembersAreRejected(self) -> None:
		with tempfile.TemporaryDirectory() as tempDir:
			zipPath = Path(tempDir) / "unsafe.zip"
			with zipfile.ZipFile(zipPath, "w") as archive:
				archive.writestr("../evil.txt", "no")

			with zipfile.ZipFile(zipPath, "r") as archive:
				with self.assertRaises(self.libUpdater.LibraryUpdateError):
					self.libUpdater._validateZipMembers(archive, tempDir)


if __name__ == "__main__":
	unittest.main()
