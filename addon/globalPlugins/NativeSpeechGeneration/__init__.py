import ctypes
import os
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import addonHandler
import globalPluginHandler
import gui
import ui
import wx
from logHandler import log
from scriptHandler import script

from .core import config_store
from .core.nvda_compat import isSecureMode, shouldWriteToDisk
from .core.quick_speak import (
	QuickSpeakController,
	QuickSpeakInputError,
	getClipboardText,
	getSelectedText,
)

addonHandler.initTranslation()

if TYPE_CHECKING:

	def _(msg: str) -> str:
		return msg


pkgDir = os.path.dirname(os.path.abspath(__file__))


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
	"""NVDA global plugin entrypoint for Native Speech Generation."""

	def __init__(self) -> None:
		super().__init__()
		self.dialog = None
		self.menuItem = None
		self._settingsPanelClass = None
		self._libsAvailable = False
		self._quickSpeakController = QuickSpeakController()
		self._quickSpeakHeldKeys: set[int] = set()
		self._quickSpeakKeyTimers: dict[int, Any] = {}
		self._initializeAddonState()

	def _initializeAddonState(self) -> None:
		self._libsAvailable = os.path.isdir(self._getLibraryDirectory())
		canWriteToDisk = shouldWriteToDisk()
		if canWriteToDisk:
			self._runDependencyStartupCleanup()
		if not canWriteToDisk or isSecureMode():
			return
		if not self._libsAvailable:
			wx.CallAfter(self._checkAndInstallDependencies)
			return

		config_store.prepareConfigForStartup(persist=True)
		self._registerSettingsPanel()
		self._registerToolsMenuItem()

	def _getLibraryDirectory(self) -> str:
		try:
			from . import lib_updater

			return lib_updater.LIB_DIR
		except Exception as error:
			log.error(f"Failed to resolve Native Speech Generation library directory: {error}", exc_info=True)
			return os.path.join(pkgDir, "lib")

	def _runDependencyStartupCleanup(self) -> None:
		try:
			from . import lib_updater

			lib_updater.initialize()
		except Exception as error:
			log.error(
				f"Failed to initialize Native Speech Generation dependency updater: {error}",
				exc_info=True,
			)

	def _checkAndInstallDependencies(self) -> None:
		try:
			from . import lib_updater

			lib_updater.checkAndInstallDependencies(forceReinstall=False)
		except Exception as error:
			log.error(f"Failed to run Native Speech Generation dependency check: {error}", exc_info=True)

	def _registerSettingsPanel(self) -> None:
		from .interface.settings import NativeSpeechSettingsPanel

		self._settingsPanelClass = NativeSpeechSettingsPanel
		if NativeSpeechSettingsPanel not in gui.settingsDialogs.NVDASettingsDialog.categoryClasses:
			gui.settingsDialogs.NVDASettingsDialog.categoryClasses.append(NativeSpeechSettingsPanel)

	def _registerToolsMenuItem(self) -> None:
		toolsMenu = gui.mainFrame.sysTrayIcon.toolsMenu
		self.menuItem = toolsMenu.Append(
			wx.ID_ANY,
			# Translators: Name of the add-on in the NVDA Tools menu.
			_("&Native Speech Generation"),
			# Translators: Tooltip or description for the Native Speech Generation Tools menu item.
			_("Generate speech using Gemini TTS"),
		)
		gui.mainFrame.sysTrayIcon.Bind(wx.EVT_MENU, self.onShowDialog, self.menuItem)

	@script(
		# Translators: Input gesture description for opening the Native Speech Generation dialog.
		description=_("Open the Native Speech Generation dialog"),
		# Translators: Input gestures category name for Native Speech Generation.
		category=_("Native Speech Generation"),
		gesture="kb:NVDA+Control+Shift+G",
	)
	def script_openDialog(self, gesture: Any) -> None:
		self._openDialog()

	@script(
		# Translators: Input gesture description for speaking the selected text with Quick Speak.
		description=_("Speak selected text with Quick Speak, or stop Quick Speak"),
		# Translators: Input gestures category name for Native Speech Generation.
		category=_("Native Speech Generation"),
		gesture="kb:NVDA+Alt+E",
	)
	def script_quickSpeakSelection(self, gesture: Any) -> None:
		self._handleQuickSpeakGesture(gesture, getSelectedText)

	@script(
		# Translators: Input gesture description for speaking clipboard text with Quick Speak.
		description=_("Speak clipboard text with Quick Speak, or stop Quick Speak"),
		# Translators: Input gestures category name for Native Speech Generation.
		category=_("Native Speech Generation"),
		gesture="kb:NVDA+Alt+Shift+E",
	)
	def script_quickSpeakClipboard(self, gesture: Any) -> None:
		self._handleQuickSpeakGesture(gesture, getClipboardText)

	def _handleQuickSpeakGesture(self, gesture: Any, textProvider: Callable[[], str]) -> None:
		keyCode = getattr(gesture, "vkCode", None)
		if isinstance(keyCode, int):
			if keyCode in self._quickSpeakHeldKeys:
				return
			self._quickSpeakHeldKeys.add(keyCode)
			self._quickSpeakKeyTimers[keyCode] = wx.CallLater(
				10,
				self._releaseQuickSpeakKeyWhenUp,
				keyCode,
			)
		if not shouldWriteToDisk() or isSecureMode():
			# Translators: Error announced when Quick Speak is invoked in a restricted NVDA mode.
			ui.message(_("Quick Speak is unavailable in this NVDA mode."))
			return
		if self._quickSpeakController.stop():
			return
		try:
			text = textProvider()
			self._quickSpeakController.start(text)
		except QuickSpeakInputError as error:
			ui.message(str(error))

	def _releaseQuickSpeakKeyWhenUp(self, keyCode: int) -> None:
		if _isKeyDown(keyCode):
			self._quickSpeakKeyTimers[keyCode] = wx.CallLater(
				10,
				self._releaseQuickSpeakKeyWhenUp,
				keyCode,
			)
			return
		self._quickSpeakHeldKeys.discard(keyCode)
		self._quickSpeakKeyTimers.pop(keyCode, None)

	def onShowDialog(self, evt: wx.Event) -> None:
		wx.CallAfter(self._openDialog)

	def _openDialog(self) -> None:
		if not shouldWriteToDisk() or isSecureMode():
			return
		if not self._libsAvailable:
			self._showDependenciesPendingMessage()
			return
		if self.dialog and self.dialog.IsShown():
			wx.CallAfter(
				wx.MessageBox,
				_(
					# Translators: Warning shown when the user tries to open the add-on dialog twice.
					"The Native Speech Generation add-on is already open. Please close the dialog before opening it again.",
				),
				# Translators: Title of warning dialog when the user tries to open the add-on twice.
				_("Add-on Already Running"),
				wx.OK | wx.ICON_WARNING,
			)
			return
		try:
			from .interface.generation_dialog import NativeSpeechDialog

			self.dialog = NativeSpeechDialog(gui.mainFrame)
			self.dialog.Bind(wx.EVT_CLOSE, self.onDialogClose)
			self.dialog.Show()
		except Exception as error:
			log.error(f"Error showing NativeSpeechDialog: {error}", exc_info=True)
			wx.CallAfter(
				wx.MessageBox,
				# Translators: Error shown when the main add-on dialog cannot be opened.
				_("Failed to open Native Speech Generation dialog: {error}").format(error=str(error)),
				_("Error"),
				wx.OK | wx.ICON_ERROR,
			)

	def _showDependenciesPendingMessage(self) -> None:
		wx.CallAfter(
			wx.MessageBox,
			_(
				# Translators: Message shown when dependency installation is still pending.
				"Native Speech Generation is installing dependencies. "
				"Please restart NVDA for the changes to take effect.",
			),
			# Translators: Title of the information dialog recommending an NVDA restart.
			_("Restart Required"),
			wx.OK | wx.ICON_INFORMATION,
		)

	def onDialogClose(self, event: wx.Event) -> None:
		self.dialog = None
		event.Skip()

	def terminate(self) -> None:
		self._quickSpeakController.stop()
		for timer in self._quickSpeakKeyTimers.values():
			try:
				timer.Stop()
			except (AttributeError, RuntimeError):
				pass
		self._quickSpeakKeyTimers.clear()
		self._quickSpeakHeldKeys.clear()
		if self.dialog is not None:
			try:
				self.dialog.requestClose()
			except (AttributeError, RuntimeError) as error:
				log.debug(f"Failed to close Native Speech Generation dialog: {error}", exc_info=True)
			self.dialog = None
		if (
			self._settingsPanelClass is not None
			and self._settingsPanelClass in gui.settingsDialogs.NVDASettingsDialog.categoryClasses
		):
			gui.settingsDialogs.NVDASettingsDialog.categoryClasses.remove(self._settingsPanelClass)
		if self.menuItem is not None:
			try:
				gui.mainFrame.sysTrayIcon.toolsMenu.Remove(self.menuItem)
			except Exception as error:
				log.debug(f"Failed to remove Native Speech Generation menu item: {error}", exc_info=True)
		super().terminate()


def _isKeyDown(keyCode: int) -> bool:
	try:
		return bool(ctypes.windll.user32.GetAsyncKeyState(keyCode) & 0x8000)
	except (AttributeError, OSError):
		return False
