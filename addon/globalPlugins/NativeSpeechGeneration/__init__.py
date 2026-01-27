# -*- coding: utf-8 -*-
import os
import sys
import wx
import addonHandler
import globalPluginHandler
import config
import gui
from logHandler import log
from scriptHandler import script
from typing import Any, TYPE_CHECKING
from .core.constants import CONFIG_DOMAIN

# Initialize translation
addonHandler.initTranslation()

if TYPE_CHECKING:

	def _(msg: str) -> str:
		return msg


# Initialization & Dependency Management
pkgDir = os.path.dirname(os.path.abspath(__file__))

# Ensure globalPlugins is in path
gpDir = os.path.dirname(pkgDir)
if gpDir not in sys.path:
	sys.path.insert(0, gpDir)

# Libs setup
try:
	from . import lib_updater

	# Run trash cleanup and init
	lib_updater.initialize()
	libDir = lib_updater.LIB_DIR
except Exception as e:
	log.error(f"Failed to initialize lib_updater: {e}", exc_info=True)
	libDir = os.path.join(pkgDir, "lib")

LIBS_AVAILABLE = False

if not os.path.isdir(libDir):

	def runCheck() -> None:
		try:
			from . import lib_updater

			lib_updater.checkAndInstallDependencies(forceReinstall=False)
		except Exception as e:
			log.error(f"Failed to run lib_updater check: {e}", exc_info=True)

	wx.CallAfter(runCheck)
else:
	if libDir not in sys.path:
		sys.path.insert(0, libDir)
	LIBS_AVAILABLE = True

if not LIBS_AVAILABLE:
	# Dummy Plugin
	class GlobalPlugin(globalPluginHandler.GlobalPlugin):
		"""
		A dummy plugin that informs the user that the addon is not ready
		and that a restart is required.
		"""

		@script(
			description=_("Open the Native Speech Generation dialog"),
			category=_("Native Speech Generation"),
			gesture="kb:NVDA+Control+Shift+G",
		)
		def script_openDialog(self, gesture: Any) -> None:
			wx.CallAfter(
				wx.MessageBox,
				_(
					"Native Speech Generation is installing dependencies. Please restart NVDA for the changes to take effect.",
				),
				_("Restart Required"),
				wx.OK | wx.ICON_INFORMATION,
			)

else:
	# Full Functionality
	# Import GUI components only when libs are available to avoid import errors
	try:
		# We use local imports inside the class or method where possible to avoid circular deps during init
		# But GlobalPlugin needs to register settings panel on init.
		from .interface.settings import NativeSpeechSettingsPanel
		from .interface.generation_dialog import NativeSpeechDialog
	except ImportError as e:
		log.error(f"Failed to import GUI components: {e}", exc_info=True)
		# Fallback to dummy plugin or raise?
		# If we can't load GUI, we can't run.
		raise e

	class GlobalPlugin(globalPluginHandler.GlobalPlugin):
		def __init__(self) -> None:
			super().__init__()
			self.dialog = None  # Track active dialog instance
			if CONFIG_DOMAIN not in config.conf:
				config.conf[CONFIG_DOMAIN] = {"apiKey": ""}
			config.conf.spec[CONFIG_DOMAIN] = {"apiKey": "string(default='')"}

			# Register settings panel
			# Note: We check if it is already registered
			if NativeSpeechSettingsPanel not in gui.settingsDialogs.NVDASettingsDialog.categoryClasses:
				gui.settingsDialogs.NVDASettingsDialog.categoryClasses.append(NativeSpeechSettingsPanel)

			toolsMenu = gui.mainFrame.sysTrayIcon.toolsMenu
			self.menuItem = toolsMenu.Append(
				wx.ID_ANY,
				_("&Native Speech Generation"),
				_("Generate speech using Gemini TTS"),
			)
			gui.mainFrame.sysTrayIcon.Bind(wx.EVT_MENU, self.onShowDialog, self.menuItem)

		@script(
			description=_("Open the Native Speech Generation dialog"),
			category=_("Native Speech Generation"),
			gesture="kb:NVDA+Control+Shift+G",
		)
		def script_openDialog(self, gesture: Any) -> None:
			self._openDialog()

		def onShowDialog(self, evt: wx.Event) -> None:
			wx.CallAfter(self._openDialog)

		def _openDialog(self) -> None:
			if self.dialog and self.dialog.IsShown():
				wx.CallAfter(
					wx.MessageBox,
					_(
						"The Native Speech Generation add-on is already open. Please close the dialog before opening it again.",
					),
					_("Add-on Already Running"),
					wx.OK | wx.ICON_WARNING,
				)
				return
			try:
				self.dialog = NativeSpeechDialog(gui.mainFrame)
				self.dialog.Bind(wx.EVT_CLOSE, self.onDialogClose)
				self.dialog.Show()
			except Exception as e:
				log.error(f"Error showing NativeSpeechDialog: {e}", exc_info=True)
				wx.CallAfter(
					wx.MessageBox,
					_("Failed to open Native Speech Generation dialog: {error}").format(error=str(e)),
					_("Error"),
					wx.OK | wx.ICON_ERROR,
				)

		def onDialogClose(self, event: wx.Event) -> None:
			self.dialog = None
			event.Skip()

		def terminate(self) -> None:
			if NativeSpeechSettingsPanel in gui.settingsDialogs.NVDASettingsDialog.categoryClasses:
				gui.settingsDialogs.NVDASettingsDialog.categoryClasses.remove(NativeSpeechSettingsPanel)
			try:
				gui.mainFrame.sysTrayIcon.toolsMenu.Remove(self.menuItem)
			except Exception:
				pass
			super().terminate()
