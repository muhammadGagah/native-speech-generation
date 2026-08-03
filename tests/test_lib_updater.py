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

	def testNvdaVersionParsingAndRuntimeAssetSelection(self) -> None:
		self.assertEqual(self.libUpdater.parseNvdaVersion("2026.1"), (2026, 1, 0))
		self.assertEqual(self.libUpdater.parseNvdaVersion("NVDA 2025.3.3"), (2025, 3, 3))
		self.assertIsNone(self.libUpdater.parseNvdaVersion("alpha"))
		self.assertEqual(self.libUpdater.getRuntimeAssetName("2026.1"), "lib64.zip")
		self.assertEqual(self.libUpdater.getRuntimeAssetName("2025.3.3"), "lib.zip")
		self.assertEqual(self.libUpdater.getRuntimeAssetName("not-a-version"), "lib.zip")

	def testApprovedLibraryAssetsArePinned(self) -> None:
		lib32 = self.libUpdater.getApprovedLibraryAsset("lib.zip")
		lib64 = self.libUpdater.getApprovedLibraryAsset("lib64.zip")

		self.assertEqual(lib32.version, "2.2.0")
		self.assertEqual(lib32.source, "approved")
		self.assertEqual(
			lib32.sha256,
			"96140636befa9880fbe48efc309f71f6057e80f48a7e58299d9657287df76d90",
		)
		self.assertEqual(lib64.version, "2.2.0")
		self.assertEqual(lib64.source, "approved")
		self.assertEqual(
			lib64.sha256,
			"f8082c18d503454728b8d7ab97dbc407cd74c8ee086f6e2a6fde27dff9945b37",
		)

	def testLatestLibraryAssetUsesGithubDigest(self) -> None:
		checksum = "d" * 64
		release = {
			"tag_name": "2.3.0",
			"assets": [
				{
					"name": "lib64.zip",
					"browser_download_url": "https://example.test/lib64.zip",
					"digest": f"sha256:{checksum}",
				},
			],
		}

		def readJson(_url: str) -> dict[str, Any]:
			return release

		self.libUpdater._readJsonUrl = readJson

		asset = self.libUpdater.getLatestVerifiedLibraryAsset("lib64.zip")

		self.assertEqual(asset.version, "2.3.0")
		self.assertEqual(asset.name, "lib64.zip")
		self.assertEqual(asset.url, "https://example.test/lib64.zip")
		self.assertEqual(asset.sha256, checksum)
		self.assertEqual(asset.source, "github")

	def testResolveLibraryAssetUsesLatestReleaseByDefault(self) -> None:
		checksum = "e" * 64
		release = {
			"tag_name": "2.3.0",
			"assets": [
				{
					"name": "lib64.zip",
					"browser_download_url": "https://example.test/lib64.zip",
					"digest": f"sha256:{checksum}",
				},
			],
		}

		def readJson(_url: str) -> dict[str, Any]:
			return release

		self.libUpdater._readJsonUrl = readJson

		asset = self.libUpdater._resolveLibraryAsset()

		self.assertEqual(asset.version, "2.3.0")
		self.assertEqual(asset.sha256, checksum)
		self.assertEqual(asset.source, "github")

	def testResolveLibraryAssetFallbackIsSkippedForForcedLatest(self) -> None:
		def fail(_url: str) -> dict[str, Any]:
			raise OSError("offline")

		self.libUpdater._readJsonUrl = fail

		asset = self.libUpdater._resolveLibraryAsset()

		self.assertEqual(asset.version, "2.2.0")
		self.assertEqual(asset.name, "lib64.zip")
		self.assertEqual(asset.source, "approved")
		with self.assertRaises(OSError):
			self.libUpdater._resolveLibraryAsset(forceLatest=True)

	def testReleaseAssetDigestCanBeParsedForMaintainerChecks(self) -> None:
		checksum = "a" * 64
		asset = {
			"name": "lib.zip",
			"browser_download_url": "https://example.test/lib.zip",
			"digest": f"sha256:{checksum}",
		}
		release = {"assets": [asset]}

		self.assertEqual(self.libUpdater._findReleaseChecksum(release, "lib.zip", asset), checksum)

	def testChecksumTextRequiresMatchingAssetWhenReadingChecksumsFile(self) -> None:
		checksum = "b" * 64
		checksumText = f"{checksum}  lib64.zip\n{'c' * 64}  lib.zip\n"

		self.assertEqual(
			self.libUpdater._parseChecksumText(checksumText, "lib64.zip", allowFallback=False),
			checksum,
		)
		self.assertEqual(
			self.libUpdater._parseChecksumText(checksumText, "missing.zip", allowFallback=False),
			"",
		)

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
