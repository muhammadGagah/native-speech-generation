# -*- coding: utf-8 -*-
import wx
import webbrowser
import os
import shutil
import time
from typing import TYPE_CHECKING
import gui
import addonHandler
import config
from logHandler import log

# Import from core
from ..core.constants import CONFIG_DOMAIN
from .. import lib_updater

if TYPE_CHECKING:

	def _(msg: str) -> str:
		return msg

# Initialize translation
addonHandler.initTranslation()

class NativeSpeechSettingsPanel(gui.settingsDialogs.SettingsPanel):
	# Translators: Title of the settings panel in NVDA preferences.
	title = _("Native Speech Generation")

	def makeSettings(self, settingsSizer: wx.Sizer) -> None:
		sHelper = gui.guiHelper.BoxSizerHelper(self, sizer=settingsSizer)

		# API Key Configuration Group
		apiSizer = wx.BoxSizer(wx.HORIZONTAL)

		# Translators: Label for the input field where user enters their Gemini API Key.
		apiLabel = wx.StaticText(self, label=_("&Gemini API Key:"))
		apiSizer.Add(apiLabel, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)

		apiValue = config.conf.get(CONFIG_DOMAIN, {}).get("apiKey", "")

		self.apiKeyCtrlHidden = wx.TextCtrl(self, value=apiValue, style=wx.TE_PASSWORD)
		self.apiKeyCtrlVisible = wx.TextCtrl(self, value=apiValue)
		self.apiKeyCtrlVisible.Hide()

		# Add inputs with EXPAND to fill available space
		apiSizer.Add(self.apiKeyCtrlHidden, 1, wx.EXPAND | wx.RIGHT, 5)
		apiSizer.Add(self.apiKeyCtrlVisible, 1, wx.EXPAND | wx.RIGHT, 5)

		# Translators: Checkbox to toggle visibility of the API key (show/hide characters).
		self.showApiCheck = wx.CheckBox(self, label=_("Show API Key"))
		self.showApiCheck.Bind(wx.EVT_CHECKBOX, self.onToggleApiVisibility)
		apiSizer.Add(self.showApiCheck, 0, wx.ALIGN_CENTER_VERTICAL)

		# Add the row to the main settings sizer
		self.onToggleApiVisibility(None)  # Set initial state

		# Translators: Button starting a process to help user get an API key (opens a website).
		self.getKeyBtn = wx.Button(self, label=_("&How to get API Key..."))
		sHelper.addItem(self.getKeyBtn)
		self.getKeyBtn.Bind(wx.EVT_BUTTON, self.onGetKey)

		# Reinstall libraries button
		# Translators: Button to force a reinstallation of external dependencies (Python libraries).
		self.reinstallBtn = wx.Button(self, label=_("&Reinstall Libraries"))
		sHelper.addItem(self.reinstallBtn)
		self.reinstallBtn.Bind(wx.EVT_BUTTON, self.onReinstall)

	def onToggleApiVisibility(self, event: wx.Event) -> None:
		if self.showApiCheck.IsChecked():
			self.apiKeyCtrlVisible.SetValue(self.apiKeyCtrlHidden.GetValue())
			self.apiKeyCtrlHidden.Hide()
			self.apiKeyCtrlVisible.Show()
		else:
			self.apiKeyCtrlHidden.SetValue(self.apiKeyCtrlVisible.GetValue())
			self.apiKeyCtrlVisible.Hide()
			self.apiKeyCtrlHidden.Show()
		self.Layout()

	def onGetKey(self, evt: wx.Event) -> None:
		webbrowser.open("https://aistudio.google.com/apikey")

	def onReinstall(self, evt: wx.Event) -> None:
		"""Handles the reinstall libraries action."""
		res = wx.MessageBox(
			_("This will delete the existing library and restart NVDA to redownload it.\nAre you sure?"),
			_("Confirm Reinstall"),
			wx.OK | wx.CANCEL | wx.ICON_WARNING,
		)
		if res != wx.OK:
			return

		try:
			# Try to get LIB_DIR from lib_updater, fallback if needed
			try:
				targetLib = lib_updater.LIB_DIR
			except AttributeError:
				# Fallback calculation matching __init__.py logic if lib_updater fails
				# This path calculation assumes we are in gui/settings.py
				# And we want .../globalPlugins/NativeSpeechGeneration/lib
				guiDir = os.path.dirname(os.path.abspath(__file__))
				pkgDir = os.path.dirname(guiDir)
				targetLib = os.path.join(pkgDir, "lib")

			if os.path.exists(targetLib):
				# Rename first to avoid lock issues, let cleanupTrash handle deletion on next run
				tempTrash = targetLib + "_trash_" + str(time.time())
				os.rename(targetLib, tempTrash)
				# Try to delete immediately, but ignore errors if locked
				shutil.rmtree(tempTrash, ignore_errors=True)

			wx.MessageBox(
				_("Library removed successfully. NVDA will now restart to download the latest version."),
				_("Restart Required"),
				wx.OK | wx.ICON_INFORMATION,
			)
			import core

			core.restart()

		except Exception as e:
			log.error(f"Failed to delete lib folder: {e}", exc_info=True)
			wx.MessageBox(
				f"Failed to remove library: {e}\nPlease check log.",
				_("Error"),
				wx.OK | wx.ICON_ERROR,
			)

	def onSave(self) -> None:
		if CONFIG_DOMAIN not in config.conf:
			config.conf[CONFIG_DOMAIN] = {}
		value = (
			self.apiKeyCtrlVisible.GetValue()
			if self.showApiCheck.IsChecked()
			else self.apiKeyCtrlHidden.GetValue()
		)
		config.conf[CONFIG_DOMAIN]["apiKey"] = value
