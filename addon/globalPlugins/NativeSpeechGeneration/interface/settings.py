import webbrowser
from typing import TYPE_CHECKING

import addonHandler
import gui
import wx
from logHandler import log

from .. import lib_updater
from ..core import config_store
from ..core.constants import (
	DEFAULT_MODEL,
	FALLBACK_VOICES,
	FLASH_25_MODEL,
	LIVE_MODEL,
	NATIVE_AUDIO_25_MODEL,
	PRO_25_MODEL,
)

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
		apiValue = config_store.getStoredApiKey()

		self.apiHiddenLabel = wx.StaticText(self, label=_("&Gemini API Key:"))
		self.apiKeyCtrlHidden = wx.TextCtrl(self, value=apiValue, style=wx.TE_PASSWORD)
		self.apiVisibleLabel = wx.StaticText(self, label=_("&Gemini API Key:"))
		self.apiKeyCtrlVisible = wx.TextCtrl(self, value=apiValue)
		self.apiVisibleLabel.Hide()
		self.apiKeyCtrlVisible.Hide()

		apiSizer.Add(self.apiHiddenLabel, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
		apiSizer.Add(self.apiKeyCtrlHidden, 1, wx.EXPAND | wx.RIGHT, 5)
		apiSizer.Add(self.apiVisibleLabel, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
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

		quickSpeakSettings = config_store.getQuickSpeakSettings()
		# Translators: Group label for Quick Speak settings.
		quickSpeakBox = wx.StaticBoxSizer(wx.VERTICAL, self, _("Quick Speak"))
		settingsSizer.Add(quickSpeakBox, 0, wx.EXPAND | wx.ALL, 5)
		quickSpeakHelper = gui.guiHelper.BoxSizerHelper(self, sizer=quickSpeakBox)

		self.quickSpeakModels = [
			# Translators: Recommended low-latency model for Quick Speak.
			(_("Gemini 3.1 Flash Live Preview (recommended)"), LIVE_MODEL),
			# Translators: Low-latency native audio model for Quick Speak.
			(_("Gemini 2.5 Flash Native Audio"), NATIVE_AUDIO_25_MODEL),
			# Translators: Gemini text-to-speech model choice for Quick Speak.
			(_("Gemini 3.1 Flash TTS Preview"), DEFAULT_MODEL),
			# Translators: Gemini text-to-speech model choice for Quick Speak.
			(_("Gemini 2.5 Flash TTS Preview"), FLASH_25_MODEL),
			# Translators: Gemini text-to-speech model choice for Quick Speak.
			(_("Gemini 2.5 Pro TTS Preview (need paid API)"), PRO_25_MODEL),
		]
		# Translators: Label for choosing the model used by Quick Speak.
		self.quickSpeakModelChoice = quickSpeakHelper.addLabeledControl(
			_("Quick Speak &model:"),
			wx.Choice,
			choices=[label for label, _model in self.quickSpeakModels],
		)
		modelValues = [model for _label, model in self.quickSpeakModels]
		self.quickSpeakModelChoice.SetSelection(modelValues.index(quickSpeakSettings.model))

		voiceVolumeSizer = wx.BoxSizer(wx.HORIZONTAL)
		# Translators: Label for choosing the Gemini voice used by Quick Speak.
		voiceLabel = wx.StaticText(self, label=_("Quick Speak &voice:"))
		self.quickSpeakVoiceChoice = wx.Choice(self, choices=FALLBACK_VOICES)
		voiceVolumeSizer.Add(voiceLabel, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
		voiceVolumeSizer.Add(self.quickSpeakVoiceChoice, 1, wx.RIGHT, 12)
		self.quickSpeakVoiceChoice.SetSelection(FALLBACK_VOICES.index(quickSpeakSettings.voice))

		# Translators: Label for the Quick Speak playback volume slider.
		volumeLabel = wx.StaticText(self, label=_("Quick Speak &volume:"))
		self.quickSpeakVolumeSlider = wx.Slider(
			self,
			value=quickSpeakSettings.volume,
			minValue=0,
			maxValue=100,
			style=wx.SL_HORIZONTAL,
		)
		self.quickSpeakVolumeSlider.SetName(_("Quick Speak volume"))
		voiceVolumeSizer.Add(volumeLabel, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
		voiceVolumeSizer.Add(self.quickSpeakVolumeSlider, 1, wx.EXPAND)
		quickSpeakHelper.addItem(voiceVolumeSizer)

		# Translators: Label for optional pronunciation or speaking style instructions used by Quick Speak.
		self.quickSpeakStyleCtrl = quickSpeakHelper.addLabeledControl(
			_("Pronunciation and &style instructions:"),
			wx.TextCtrl,
			value=quickSpeakSettings.styleInstructions,
			style=wx.TE_MULTILINE,
			size=(-1, self.FromDIP(80)),
		)

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
			self.apiHiddenLabel.Hide()
			self.apiKeyCtrlHidden.Hide()
			self.apiVisibleLabel.Show()
			self.apiKeyCtrlVisible.Show()
		else:
			self.apiVisibleLabel.Hide()
			self.apiKeyCtrlVisible.Hide()
			self.apiHiddenLabel.Show()
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
		modelSelection = self.quickSpeakModelChoice.GetSelection()
		voiceSelection = self.quickSpeakVoiceChoice.GetSelection()
		if modelSelection == wx.NOT_FOUND or voiceSelection == wx.NOT_FOUND:
			invalidChoice = (
				self.quickSpeakModelChoice if modelSelection == wx.NOT_FOUND else self.quickSpeakVoiceChoice
			)
			wx.MessageBox(
				# Translators: Error shown when a Quick Speak model or voice has not been selected.
				_("Select both a Quick Speak model and voice."),
				_("Error"),
				wx.OK | wx.ICON_ERROR,
			)
			invalidChoice.SetFocus()
			return False
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
			modelSelection = self.quickSpeakModelChoice.GetSelection()
			voiceSelection = self.quickSpeakVoiceChoice.GetSelection()
			config_store.setQuickSpeakSettings(
				self.quickSpeakModels[modelSelection][1],
				FALLBACK_VOICES[voiceSelection],
				self.quickSpeakStyleCtrl.GetValue(),
				self.quickSpeakVolumeSlider.GetValue(),
			)
		except config_store.ApiKeyStorageError as error:
			self._showStorageError(error)
