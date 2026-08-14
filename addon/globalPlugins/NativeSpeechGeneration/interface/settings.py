import webbrowser
from typing import TYPE_CHECKING

import addonHandler
import gui
import wx
from logHandler import log

from .. import lib_updater
from ..core import config_store

if TYPE_CHECKING:

	def _(msg: str) -> str:
		return msg


addonHandler.initTranslation()


class NativeSpeechSettingsPanel(gui.settingsDialogs.SettingsPanel):
	"""Settings panel for API key storage and dependency maintenance."""

	# Translators: Title of the settings panel in NVDA preferences.
	title = _("Native Speech Generation")

	def __init__(self, *args, **kwargs) -> None:
		super().__init__(*args, **kwargs)
		self._validatedApiKeyValue = ""
		self._validatedEncryptedApiKey = ""

	def makeSettings(self, settingsSizer: wx.Sizer) -> None:
		sHelper = gui.guiHelper.BoxSizerHelper(self, sizer=settingsSizer)
		apiResolution = config_store.resolveApiKey()

		apiSizer = wx.BoxSizer(wx.HORIZONTAL)

		# Translators: Label for the input field where user enters their Gemini API Key.
		apiLabel = wx.StaticText(self, label=_("&Gemini API Key:"))
		apiSizer.Add(apiLabel, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)

		apiValue = config_store.getStoredApiKey()

		self.apiKeyCtrlHidden = wx.TextCtrl(self, value=apiValue, style=wx.TE_PASSWORD)
		self.apiKeyCtrlVisible = wx.TextCtrl(self, value=apiValue)
		self.apiKeyCtrlVisible.Hide()

		apiSizer.Add(self.apiKeyCtrlHidden, 1, wx.EXPAND | wx.RIGHT, 5)
		apiSizer.Add(self.apiKeyCtrlVisible, 1, wx.EXPAND | wx.RIGHT, 5)

		# Translators: Checkbox to toggle visibility of the API key (show/hide characters).
		self.showApiCheck = wx.CheckBox(self, label=_("Show API Key"))
		self.showApiCheck.Bind(wx.EVT_CHECKBOX, self.onToggleApiVisibility)
		apiSizer.Add(self.showApiCheck, 0, wx.ALIGN_CENTER_VERTICAL)

		settingsSizer.Add(apiSizer, 0, wx.EXPAND | wx.ALL, 5)
		self.onToggleApiVisibility(None)  # Set initial state

		apiInfoMessage = self._getApiKeyInfoMessage(apiResolution)
		self.apiKeyInfoLabel = sHelper.addItem(wx.StaticText(self, label=apiInfoMessage))
		if apiInfoMessage:
			self.apiKeyInfoLabel.Wrap(560)
		else:
			self.apiKeyInfoLabel.Hide()

		# Translators: Button starting a process to help user get an API key (opens a website).
		self.getKeyBtn = wx.Button(self, label=_("&How to get API Key..."))
		sHelper.addItem(self.getKeyBtn)
		self.getKeyBtn.Bind(wx.EVT_BUTTON, self.onGetKey)

		# Translators: Button to force a reinstallation of external dependencies (Python libraries).
		self.reinstallBtn = wx.Button(self, label=_("&Reinstall Libraries"))
		sHelper.addItem(self.reinstallBtn)
		self.reinstallBtn.Bind(wx.EVT_BUTTON, self.onReinstall)

	def _getApiKeyInfoMessage(self, resolution: config_store.ApiKeyResolution) -> str:
		if resolution.status == "undecryptable" and resolution.source == "environment":
			# Translators: Information shown in settings when a stored key cannot be decrypted
			# and the add-on is using GEMINI_API_KEY from the environment instead.
			return _(
				"The stored API key could not be decrypted on this Windows user or machine. "
				"Using {envVarName} from the environment instead. Enter a new key here to replace it.",
			).format(envVarName=config_store.API_KEY_ENV_VAR)
		if resolution.status == "undecryptable":
			# Translators: Information shown in settings when a stored key cannot be decrypted.
			return _(
				"The stored API key could not be decrypted on this Windows user or machine. "
				"Enter a new key here, or set {envVarName} in the environment.",
			).format(envVarName=config_store.API_KEY_ENV_VAR)
		if resolution.source == "environment":
			# Translators: Information shown in settings when the add-on is using GEMINI_API_KEY
			# from the environment because no stored key is available.
			return _(
				"Using {envVarName} from the environment. Saving a key here will override it.",
			).format(envVarName=config_store.API_KEY_ENV_VAR)
		return ""

	def onToggleApiVisibility(self, event: wx.Event | None) -> None:
		sourceCtrl = self.apiKeyCtrlVisible if self.apiKeyCtrlVisible.IsShown() else self.apiKeyCtrlHidden
		targetCtrl = self.apiKeyCtrlVisible if self.showApiCheck.IsChecked() else self.apiKeyCtrlHidden
		value = sourceCtrl.GetValue()
		selectionStart, selectionEnd = sourceCtrl.GetSelection()
		insertionPoint = sourceCtrl.GetInsertionPoint()
		restoreFocus = sourceCtrl.HasFocus()

		targetCtrl.SetValue(value)
		if targetCtrl is self.apiKeyCtrlVisible:
			self.apiKeyCtrlHidden.Hide()
			self.apiKeyCtrlVisible.Show()
		else:
			self.apiKeyCtrlVisible.Hide()
			self.apiKeyCtrlHidden.Show()
		self.Layout()

		maxPos = len(value)
		selectionStart = min(selectionStart, maxPos)
		selectionEnd = min(selectionEnd, maxPos)
		insertionPoint = min(insertionPoint, maxPos)
		targetCtrl.SetSelection(selectionStart, selectionEnd)
		targetCtrl.SetInsertionPoint(insertionPoint)
		if restoreFocus:
			targetCtrl.SetFocus()

	def onGetKey(self, evt: wx.Event) -> None:
		"""Open Google AI Studio in the user's default browser."""
		webbrowser.open("https://aistudio.google.com/apikey")

	def _getCurrentApiKeyFieldValue(self) -> str:
		return (
			self.apiKeyCtrlVisible.GetValue()
			if self.showApiCheck.IsChecked()
			else self.apiKeyCtrlHidden.GetValue()
		)

	def _showStorageError(self, error: config_store.ApiKeyStorageError) -> None:
		log.error(f"Failed to store the Gemini API key securely: {error}", exc_info=True)
		wx.MessageBox(
			# Translators: Error shown if Windows DPAPI storage fails while saving the API key.
			_("Failed to save the Gemini API key securely: {error}").format(error=str(error)),
			_("Error"),
			wx.OK | wx.ICON_ERROR,
		)

	def isValid(self) -> bool:
		try:
			self._validatedApiKeyValue, self._validatedEncryptedApiKey = config_store.prepareApiKeyForStorage(
				self._getCurrentApiKeyFieldValue(),
			)
		except config_store.ApiKeyStorageError as error:
			self._validatedApiKeyValue = ""
			self._validatedEncryptedApiKey = ""
			self._showStorageError(error)
			return False
		return True

	def onReinstall(self, evt: wx.Event) -> None:
		"""Start the verified dependency update flow."""
		lib_updater.reinstallDependencies()

	def onSave(self) -> None:
		if not self.isValid():
			return
		try:
			config_store.writePreparedApiKey(
				self._validatedApiKeyValue,
				self._validatedEncryptedApiKey,
			)
		except config_store.ApiKeyStorageError as error:
			self._showStorageError(error)
