from __future__ import annotations

import builtins
import importlib.util
import sys
import types
import unittest
from collections.abc import Callable
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
INSTALL_TASKS_PATH = REPO_ROOT / "addon" / "installTasks.py"


class _Log:
	def debug(self, *_args: object, **_kwargs: object) -> None:
		pass

	def warning(self, *_args: object, **_kwargs: object) -> None:
		pass


class _MainFrame:
	def __init__(self) -> None:
		super().__init__()
		self.prePopupCalls = 0
		self.postPopupCalls = 0

	def prePopup(self) -> None:
		self.prePopupCalls += 1

	def postPopup(self) -> None:
		self.postPopupCalls += 1


def _translate(message: str) -> str:
	return message


def _callAfter(function: Callable[..., Any], *args: object, **kwargs: object) -> Any:
	return function(*args, **kwargs)


def _loadInstallTasks(
	*,
	currentPath: Path,
	installedPaths: tuple[Path, ...] = (),
	otherInstalledPaths: tuple[Path, ...] = (),
	useModernDialog: bool = True,
) -> tuple[Any, list[tuple[str, str, int]], _MainFrame]:
	builtins._ = _translate

	addonHandler = types.ModuleType("addonHandler")
	addonHandler.initTranslation = lambda: None
	currentAddon = types.SimpleNamespace(name="NativeSpeechGeneration", path=str(currentPath))
	addonHandler.getCodeAddon = lambda: currentAddon
	addonHandler.getAvailableAddons = lambda: [
		currentAddon,
		*(types.SimpleNamespace(name="NativeSpeechGeneration", path=str(path)) for path in installedPaths),
		*(types.SimpleNamespace(name="OtherAddon", path=str(path)) for path in otherInstalledPaths),
	]
	sys.modules["addonHandler"] = addonHandler

	logHandler = types.ModuleType("logHandler")
	logHandler.log = _Log()
	sys.modules["logHandler"] = logHandler

	messages: list[tuple[str, str, int]] = []
	mainFrame = _MainFrame()
	gui = types.ModuleType("gui")
	gui.__path__ = []
	gui.mainFrame = mainFrame

	def messageBox(message: str, title: str, style: int, **_kwargs: object) -> None:
		messages.append((message, title, style))

	gui.messageBox = messageBox
	sys.modules["gui"] = gui
	if useModernDialog:
		guiMessage = types.ModuleType("gui.message")

		class MessageDialog:
			@classmethod
			def alert(cls, message: str, title: str, **_kwargs: object) -> None:
				messages.append((message, title, 0))

		guiMessage.MessageDialog = MessageDialog
		sys.modules["gui.message"] = guiMessage
	else:
		sys.modules.pop("gui.message", None)

	wx = types.ModuleType("wx")
	wx.OK = 1
	wx.ICON_WARNING = 2
	wx.CallAfter = _callAfter
	sys.modules["wx"] = wx

	moduleName = "nsg_install_tasks_under_test"
	sys.modules.pop(moduleName, None)
	spec = importlib.util.spec_from_file_location(moduleName, INSTALL_TASKS_PATH)
	assert spec is not None
	assert spec.loader is not None
	module = importlib.util.module_from_spec(spec)
	sys.modules[moduleName] = module
	spec.loader.exec_module(module)
	return module, messages, mainFrame


class InstallTasksTests(unittest.TestCase):
	def testFreshInstallDoesNotShowUpdateWarning(self) -> None:
		with TemporaryDirectory() as tempDir:
			addonsDir = Path(tempDir)
			pendingDir = addonsDir / "NativeSpeechGeneration.pendingInstall"
			pendingDir.mkdir()
			module, messages, mainFrame = _loadInstallTasks(
				currentPath=pendingDir,
				otherInstalledPaths=(addonsDir / "OtherAddon",),
			)
			module.__file__ = str(pendingDir / "installTasks.py")
			module.onInstall()

		self.assertEqual([], messages)
		self.assertEqual(0, mainFrame.prePopupCalls)
		self.assertEqual(0, mainFrame.postPopupCalls)

	def testUpdateShowsWarningAndPreservesExistingLibraries(self) -> None:
		with TemporaryDirectory() as tempDir:
			addonsDir = Path(tempDir)
			pendingDir = addonsDir / "NativeSpeechGeneration.pendingInstall"
			existingAddonDir = addonsDir / "NativeSpeechGeneration"
			existingLib = existingAddonDir / "globalPlugins" / "NativeSpeechGeneration" / "lib"
			pendingDir.mkdir()
			existingLib.mkdir(parents=True)
			(existingLib / "dependency.txt").write_text("preserved", encoding="utf-8")
			module, messages, mainFrame = _loadInstallTasks(
				currentPath=pendingDir,
				installedPaths=(existingAddonDir,),
			)
			module.__file__ = str(pendingDir / "installTasks.py")

			module.onInstall()

			newLib = pendingDir / "globalPlugins" / "NativeSpeechGeneration" / "lib"
			self.assertEqual("preserved", (newLib / "dependency.txt").read_text(encoding="utf-8"))

		self.assertEqual(1, len(messages))
		self.assertIn("WebSocket", messages[0][0])
		self.assertEqual("Native Speech Generation updated", messages[0][1])
		self.assertEqual(1, mainFrame.prePopupCalls)
		self.assertEqual(1, mainFrame.postPopupCalls)

	def testUpdateWithoutExistingLibrariesStillShowsWarning(self) -> None:
		with TemporaryDirectory() as tempDir:
			addonsDir = Path(tempDir)
			pendingDir = addonsDir / "NativeSpeechGeneration.pendingInstall"
			existingAddonDir = addonsDir / "NativeSpeechGeneration"
			pendingDir.mkdir()
			existingAddonDir.mkdir()
			module, messages, _mainFrame = _loadInstallTasks(
				currentPath=pendingDir,
				installedPaths=(existingAddonDir,),
				useModernDialog=False,
			)
			module.__file__ = str(pendingDir / "installTasks.py")

			module.onInstall()

		self.assertEqual(1, len(messages))


if __name__ == "__main__":
	unittest.main()
