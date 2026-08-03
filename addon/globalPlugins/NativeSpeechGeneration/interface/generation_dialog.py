import mimetypes
import os
import tempfile
import threading
import urllib.request
import uuid
import webbrowser
import winsound
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import addonHandler
import gui
import ui
import wx
from logHandler import log

from .. import talkWithAI
from ..core import config_store
from ..core.audio_utils import convertToWav, mergeWavFiles, safeStartFile, saveBinaryFile
from ..core.constants import (
	DEFAULT_MODEL,
	FALLBACK_VOICES,
	FLASH_25_MODEL,
	PRO_25_MODEL,
	VOICE_SAMPLE_BASE,
)
from ..core.gemini_imports import GENAI_AVAILABLE, GENAI_IMPORT_ERROR, genai, getRuntimeScope, types

if TYPE_CHECKING:

	def _(msg: str) -> str:
		return msg


addonHandler.initTranslation()

GENERATED_AUDIO_DIR = os.path.join(tempfile.gettempdir(), "NativeSpeechGeneration")


@dataclass(frozen=True)
class GenerationRequest:
	"""Snapshot of user-selected generation options safe to pass to a worker thread."""

	apiKey: str
	text: str
	model: str
	temperature: float
	styleInstructions: str
	modeMulti: bool
	voiceName: str
	voiceName2: str
	speaker1Name: str
	speaker2Name: str


class NativeSpeechDialog(wx.Dialog):
	"""Main dialog for generating Gemini TTS audio from user-provided text."""

	def __init__(self, parent: wx.Window) -> None:
		# Translators: The title of the main dialog window for generating speech.
		super().__init__(parent, title=_("Native Speech Generation (Gemini TTS)"))

		self.lastAudioPath: str | None = None
		self.modelOptions = self._getModelOptions()
		self.model = self.modelOptions[0][0]
		self.modeMulti = False
		self.voices: list[dict[str, Any]] = []
		self.selectedVoiceIdx = 0
		self.selectedVoiceIdx2 = 0
		self.isGenerating = False
		self.client = None
		self.currentStream = None
		self.isClosed = False
		self._modelDescriptionAnnouncementId = 0

		self._buildUi()
		threading.Thread(target=self.loadVoices, daemon=True).start()
		self.textCtrl.SetFocus()

	def _getModelOptions(self) -> list[tuple[str, str, str]]:
		return [
			(
				DEFAULT_MODEL,
				# Translators: Model option for the newest Gemini Flash text-to-speech preview.
				_("Flash 3.1 Preview"),
				# Translators: Description for the Gemini Flash 3.1 Preview model.
				_("Powerful, low-latency speech generation, very good for short audio."),
			),
			(
				FLASH_25_MODEL,
				# Translators: Model option for the older Gemini Flash text-to-speech preview.
				_("Flash 2.5"),
				# Translators: Description for the Gemini Flash 2.5 model.
				_("Standard quality, responsive speech generation."),
			),
			(
				PRO_25_MODEL,
				# Translators: Model option for the Gemini Pro text-to-speech preview.
				_("Pro 2.5 (High Quality)"),
				# Translators: Description for the Gemini Pro 2.5 model.
				_("Premium speech generation with more realistic voices."),
			),
		]

	def _buildUi(self) -> None:
		mainSizer = wx.BoxSizer(wx.VERTICAL)

		# Translators: Label for the text area where user inputs text to be converted to speech.
		textLabel = wx.StaticText(self, label=_("&Type text to convert here:"))
		self.textCtrl = wx.TextCtrl(self, style=wx.TE_MULTILINE, size=(520, 160))
		mainSizer.Add(textLabel, flag=wx.ALL, border=6)
		mainSizer.Add(self.textCtrl, flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=6)

		# Translators: Label for optional instructions on how the speech should be spoken (e.g. "Happy", "Sad").
		styleLabel = wx.StaticText(self, label=_("&Style instructions (optional):"))
		self.styleCtrl = wx.TextCtrl(self, style=wx.TE_MULTILINE, size=(520, 60))
		mainSizer.Add(styleLabel, flag=wx.ALL, border=6)
		mainSizer.Add(self.styleCtrl, flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=6)

		modelOuterSizer = wx.BoxSizer(wx.VERTICAL)
		modelSizer = wx.BoxSizer(wx.HORIZONTAL)
		# Translators: Label for selecting the AI model to use for generation.
		modelLabel = wx.StaticText(self, label=_("Select &Model:"))
		self.modelChoice = wx.Choice(
			self,
			choices=[label for _model, label, _description in self.modelOptions],
		)
		self.modelChoice.SetSelection(0)
		self.modelChoice.Bind(wx.EVT_CHOICE, self.onModelChange)
		self.modelChoice.Bind(wx.EVT_SET_FOCUS, self.onModelFocus)
		modelSizer.Add(modelLabel, flag=wx.ALIGN_CENTER_VERTICAL | wx.ALL, border=6)
		modelSizer.Add(self.modelChoice, flag=wx.ALL, border=6)

		# Translators: Radio button to select single speaker mode.
		self.modeSingleRb = wx.RadioButton(self, label=_("Single-speaker"), style=wx.RB_GROUP)
		# Translators: Radio button to select multi-speaker mode.
		self.modeMultiRb = wx.RadioButton(self, label=_("Multi-speaker (2)"))
		self.modeSingleRb.SetValue(True)
		self.modeSingleRb.Bind(wx.EVT_RADIOBUTTON, self.onModeChange)
		self.modeMultiRb.Bind(wx.EVT_RADIOBUTTON, self.onModeChange)
		modelSizer.Add(self.modeSingleRb, flag=wx.ALL, border=6)
		modelSizer.Add(self.modeMultiRb, flag=wx.ALL, border=6)
		modelOuterSizer.Add(modelSizer, flag=wx.EXPAND)
		self.modelDescriptionLabel = wx.StaticText(self, label=self.modelOptions[0][2])
		self.modelDescriptionLabel.Wrap(520)
		modelOuterSizer.Add(self.modelDescriptionLabel, flag=wx.LEFT | wx.RIGHT | wx.BOTTOM, border=6)
		mainSizer.Add(modelOuterSizer, flag=wx.EXPAND)

		# Translators: Checkbox to show advanced settings like Temperature.
		self.settingsCheckbox = wx.CheckBox(self, label=_("Advanced Settings (&Temperature)"))
		self.settingsCheckbox.SetValue(False)
		mainSizer.Add(self.settingsCheckbox, flag=wx.LEFT | wx.RIGHT | wx.TOP, border=6)

		self.settingsPanel = wx.Panel(self)
		mainSizer.Add(self.settingsPanel, proportion=0, flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=6)

		paneSizer = wx.BoxSizer(wx.VERTICAL)
		tempSizer = wx.BoxSizer(wx.HORIZONTAL)
		# Translators: Label for the temperature slider which controls creativity of the AI.
		tempLabel = wx.StaticText(self.settingsPanel, label=_("Temperature:"))
		self.tempSlider = wx.Slider(
			self.settingsPanel,
			value=10,
			minValue=0,
			maxValue=20,
			style=wx.SL_HORIZONTAL,
		)
		self.tempValueLabel = wx.StaticText(self.settingsPanel, label=self._tempToLabel(10))
		self.tempSlider.Bind(wx.EVT_SLIDER, self.onTempChange)
		tempSizer.Add(tempLabel, flag=wx.ALIGN_CENTER_VERTICAL | wx.ALL, border=5)
		tempSizer.Add(self.tempSlider, proportion=1, flag=wx.EXPAND | wx.ALL, border=5)
		tempSizer.Add(self.tempValueLabel, flag=wx.ALIGN_CENTER_VERTICAL | wx.ALL, border=5)
		paneSizer.Add(tempSizer, flag=wx.EXPAND | wx.ALL, border=5)
		self.settingsPanel.SetSizer(paneSizer)
		self.settingsPanel.Hide()
		self.Bind(wx.EVT_CHECKBOX, self.onToggleSettings, self.settingsCheckbox)

		self.voicePanelSingle = self._buildVoicePanelSingle()
		self.voicePanelMulti = self._buildVoicePanelMulti()
		mainSizer.Add(self.voicePanelSingle, flag=wx.EXPAND | wx.ALL, border=5)
		mainSizer.Add(self.voicePanelMulti, flag=wx.EXPAND | wx.ALL, border=5)
		self.voicePanelMulti.Hide()

		btnSizer = wx.StdDialogButtonSizer()
		# Translators: Button to start generating the speech audio.
		self.generateBtn = wx.Button(self, label=_("&Generate Speech"))
		self.generateBtn.Bind(wx.EVT_BUTTON, self.onGenerate)
		btnSizer.AddButton(self.generateBtn)

		# Translators: Button to play the generated audio.
		self.playBtn = wx.Button(self, label=_("&Play"))
		self.playBtn.Bind(wx.EVT_BUTTON, self.onPlay)
		self.playBtn.Enable(False)
		btnSizer.AddButton(self.playBtn)

		# Translators: Button to save the generated audio to a file.
		self.saveBtn = wx.Button(self, label=_("Save &Audio"))
		self.saveBtn.Bind(wx.EVT_BUTTON, self.onSave)
		self.saveBtn.Enable(False)
		btnSizer.AddButton(self.saveBtn)
		btnSizer.Realize()
		mainSizer.Add(btnSizer, flag=wx.EXPAND | wx.ALL, border=10)

		# Translators: Button to open the real-time conversation dialog.
		self.talkBtn = wx.Button(self, label=_("Talk With &AI"))
		self.talkBtn.Bind(wx.EVT_BUTTON, self.onTalkWithAi)
		mainSizer.Add(self.talkBtn, flag=wx.ALIGN_CENTER | wx.ALL, border=5)

		footerSizer = wx.BoxSizer(wx.HORIZONTAL)
		# Translators: Button to open settings specifically for configuring the API key.
		self.getKeyBtn = wx.Button(self, label=_("API Key Settings"))
		self.getKeyBtn.Bind(wx.EVT_BUTTON, self.onSettings)
		# Translators: Button that opens a web browser to view available voices in Google AI Studio.
		self.viewVoicesBtn = wx.Button(self, label=_("View voices in AI Studio"))
		self.viewVoicesBtn.Bind(wx.EVT_BUTTON, self.onOpenAiStudio)
		footerSizer.Add(self.getKeyBtn, flag=wx.ALL, border=6)
		footerSizer.Add(self.viewVoicesBtn, flag=wx.ALL, border=6)
		mainSizer.Add(footerSizer, flag=wx.ALIGN_CENTER | wx.ALL, border=5)

		# Translators: Button to close the Native Speech Generation dialog.
		self.closeBtn = wx.Button(self, wx.ID_CANCEL, _("&Close"))
		mainSizer.Add(self.closeBtn, flag=wx.ALIGN_CENTER | wx.ALL, border=5)

		self.SetSizerAndFit(mainSizer)
		self.CenterOnParent()
		self.Bind(wx.EVT_CLOSE, self.onClose)
		self.Bind(wx.EVT_CHAR_HOOK, self.onCharHook)

	def onCharHook(self, evt: wx.Event) -> None:
		if evt.GetKeyCode() == wx.WXK_ESCAPE:
			self.Close()
		else:
			evt.Skip()

	def _buildVoicePanelSingle(self) -> wx.Panel:
		panel = wx.Panel(self)
		sizer = wx.BoxSizer(wx.HORIZONTAL)
		# Translators: Label for selecting a voice in single speaker mode.
		label = wx.StaticText(panel, label=_("Select &Voice:"))
		# Translators: Temporary item shown while the add-on prepares the voice list.
		self.voiceChoiceSingle = wx.Choice(panel, choices=[_("Loading voices...")])
		self.voiceChoiceSingle.SetSelection(0)
		self.voiceChoiceSingle.Bind(wx.EVT_CHOICE, self.onVoiceChange)
		self.voiceChoiceSingle.Bind(wx.EVT_CHAR_HOOK, self.onVoiceKeypressGeneric)
		self.voiceChoiceSingle.Bind(wx.EVT_KEY_DOWN, self.onVoiceKeypressGeneric)
		sizer.Add(label, flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=5)
		sizer.Add(self.voiceChoiceSingle, proportion=1, flag=wx.EXPAND | wx.ALL, border=5)
		panel.SetSizer(sizer)
		return panel

	def _buildVoicePanelMulti(self) -> wx.Panel:
		panel = wx.Panel(self)
		sizer = wx.BoxSizer(wx.VERTICAL)

		spk1Sizer = wx.BoxSizer(wx.HORIZONTAL)
		# Translators: Label for entering the first speaker name in multi-speaker mode.
		spk1Label = wx.StaticText(panel, label=_("Speaker 1 Name:"))
		# Translators: Default name for the first speaker in multi-speaker mode.
		self.spk1NameCtrl = wx.TextCtrl(panel, value=_("Speaker1"), size=(100, -1))
		# Translators: Label for choosing the first speaker voice in multi-speaker mode.
		voice1Label = wx.StaticText(panel, label=_("Voice:"))
		# Translators: Temporary item shown while the add-on prepares the voice list.
		self.voiceChoiceMulti1 = wx.Choice(panel, choices=[_("Loading voices...")])
		self.voiceChoiceMulti1.SetSelection(0)
		self.voiceChoiceMulti1.Bind(wx.EVT_CHOICE, self.onVoiceChange)
		self.voiceChoiceMulti1.Bind(wx.EVT_CHAR_HOOK, self.onVoiceKeypressGeneric)
		self.voiceChoiceMulti1.Bind(wx.EVT_KEY_DOWN, self.onVoiceKeypressGeneric)
		spk1Sizer.Add(spk1Label, flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=5)
		spk1Sizer.Add(self.spk1NameCtrl, flag=wx.RIGHT, border=10)
		spk1Sizer.Add(voice1Label, flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=5)
		spk1Sizer.Add(self.voiceChoiceMulti1, proportion=1, flag=wx.EXPAND)
		sizer.Add(spk1Sizer, flag=wx.EXPAND | wx.ALL, border=6)

		spk2Sizer = wx.BoxSizer(wx.HORIZONTAL)
		# Translators: Label for entering the second speaker name in multi-speaker mode.
		spk2Label = wx.StaticText(panel, label=_("Speaker 2 Name:"))
		# Translators: Default name for the second speaker in multi-speaker mode.
		self.spk2NameCtrl = wx.TextCtrl(panel, value=_("Speaker2"), size=(100, -1))
		# Translators: Label for choosing the second speaker voice in multi-speaker mode.
		voice2Label = wx.StaticText(panel, label=_("Voice:"))
		# Translators: Temporary item shown while the add-on prepares the voice list.
		self.voiceChoiceMulti2 = wx.Choice(panel, choices=[_("Loading voices...")])
		self.voiceChoiceMulti2.SetSelection(0)
		self.voiceChoiceMulti2.Bind(wx.EVT_CHOICE, self.onVoiceChange2)
		self.voiceChoiceMulti2.Bind(wx.EVT_CHAR_HOOK, self.onVoiceKeypressGeneric)
		self.voiceChoiceMulti2.Bind(wx.EVT_KEY_DOWN, self.onVoiceKeypressGeneric)
		spk2Sizer.Add(spk2Label, flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=5)
		spk2Sizer.Add(self.spk2NameCtrl, flag=wx.RIGHT, border=10)
		spk2Sizer.Add(voice2Label, flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=5)
		spk2Sizer.Add(self.voiceChoiceMulti2, proportion=1, flag=wx.EXPAND)
		sizer.Add(spk2Sizer, flag=wx.EXPAND | wx.ALL, border=6)

		panel.SetSizer(sizer)
		return panel

	def onClose(self, evt: wx.Event) -> None:
		self.isClosed = True
		currentStream = self.currentStream
		client = self.client
		self.currentStream = None
		self.client = None
		if currentStream or client:
			threading.Thread(
				target=self._closeGenerationResources,
				args=(currentStream, client),
				daemon=True,
			).start()
		self.Destroy()

	def _closeGenerationResources(self, currentStream: Any, client: Any) -> None:
		if currentStream:
			self._closeRuntimeResource("generation stream", currentStream.close)
		if client:
			self._closeRuntimeResource("generation client", client.close)

	def _closeRuntimeResource(self, label: str, closer: Any) -> None:
		try:
			with getRuntimeScope():
				closer()
		except Exception as error:
			log.debug(f"Failed to close {label}: {error}", exc_info=True)

	def _tempToLabel(self, valInt: int) -> str:
		return f"{valInt / 10.0:.1f}"

	def onTempChange(self, evt: wx.Event) -> None:
		newValueInt = evt.GetEventObject().GetValue()
		newLabelStr = self._tempToLabel(newValueInt)
		self.tempValueLabel.SetLabel(newLabelStr)

	def onToggleSettings(self, evt: wx.Event) -> None:
		isShown = self.settingsCheckbox.IsChecked()
		self.settingsPanel.Show(isShown)
		self.GetSizer().Layout()
		self.Fit()

	def onModelChange(self, evt: wx.Event) -> None:
		self._updateModelDescription(announce=True)

	def onModelFocus(self, evt: wx.Event) -> None:
		self._announceModelDescription(self._getSelectedModelDescription())
		evt.Skip()

	def _updateModelDescription(self, *, announce: bool) -> None:
		sel = self.modelChoice.GetSelection()
		if sel == wx.NOT_FOUND:
			sel = 0
		self.model = self.modelOptions[sel][0]
		description = self.modelOptions[sel][2]
		self.modelDescriptionLabel.SetLabel(description)
		self.modelDescriptionLabel.Wrap(520)
		self.GetSizer().Layout()
		self.Fit()
		if announce:
			self._announceModelDescription(description)

	def _getSelectedModelDescription(self) -> str:
		sel = self.modelChoice.GetSelection()
		if sel == wx.NOT_FOUND:
			sel = 0
		return self.modelOptions[sel][2]

	def _announceModelDescription(self, description: str) -> None:
		description = description.strip()
		if not description:
			return
		self._modelDescriptionAnnouncementId += 1
		announcementId = self._modelDescriptionAnnouncementId

		def announce() -> None:
			if self.isClosed or announcementId != self._modelDescriptionAnnouncementId:
				return
			ui.message(description)

		wx.CallLater(120, announce)

	def onModeChange(self, evt: wx.Event) -> None:
		self.modeMulti = self.modeMultiRb.GetValue()
		self.voicePanelSingle.Show(not self.modeMulti)
		self.voicePanelMulti.Show(self.modeMulti)
		self.GetSizer().Layout()
		self.Fit()

	def onVoiceChange(self, evt: wx.Event) -> None:
		self.selectedVoiceIdx = evt.GetEventObject().GetSelection()

	def onVoiceChange2(self, evt: wx.Event) -> None:
		self.selectedVoiceIdx2 = self.voiceChoiceMulti2.GetSelection()

	def onVoiceKeypressGeneric(self, evt: wx.Event) -> None:
		key = evt.GetKeyCode()
		match key:
			case wx.WXK_SPACE:
				ctrl = evt.GetEventObject()
				idx = ctrl.GetSelection()
				voiceName = self._getSelectedVoiceName(ctrl, idx)
				self._playSampleForVoice(voiceName)
			case _:
				evt.Skip()

	def _getSelectedVoiceName(self, choiceCtrl: wx.Choice, idx: int | None) -> str:
		try:
			if idx is None or idx == wx.NOT_FOUND or not self.voices:
				return self.voices[0]["name"] if self.voices else "Zephyr"
			voiceData = self.voices[idx]
			if isinstance(voiceData, dict) and "name" in voiceData:
				return voiceData["name"]
			return str(voiceData)
		except IndexError:
			return self.voices[0]["name"] if self.voices else "Zephyr"
		except Exception as e:
			log.error(f"Failed to get selected voice name: {e}", exc_info=True)
			return "Zephyr"

	def _resolveApiKeyForUse(self) -> str | None:
		resolution = config_store.resolveApiKey()
		if resolution.value:
			return resolution.value
		self._showApiKeyUnavailableMessage(resolution)
		return None

	def _showApiKeyUnavailableMessage(self, resolution: config_store.ApiKeyResolution) -> None:
		if resolution.status == "undecryptable":
			# Translators: Error shown when a stored encrypted API key cannot be decrypted.
			message = _(
				"The stored Gemini API key could not be decrypted on this Windows user or machine. "
				"Please enter it again in NVDA settings, or define {envVarName} in the environment.",
			).format(envVarName=config_store.API_KEY_ENV_VAR)
		else:
			# Translators: Error shown when no API key is available from config or environment.
			message = _(
				"No Gemini API key is configured. Set it in NVDA settings, or define {envVarName} "
				"in the environment.",
			).format(envVarName=config_store.API_KEY_ENV_VAR)
		# Translators: Title of an API key configuration error dialog.
		wx.CallAfter(wx.MessageBox, message, _("Error"), wx.OK | wx.ICON_ERROR)

	def onSettings(self, evt: wx.Event) -> None:
		from .settings import NativeSpeechSettingsPanel

		wx.CallAfter(
			gui.mainFrame.popupSettingsDialog,
			gui.settingsDialogs.NVDASettingsDialog,
			NativeSpeechSettingsPanel,
		)

	def onOpenAiStudio(self, evt: wx.Event) -> None:
		webbrowser.open("https://aistudio.google.com/generate-speech")

	def onTalkWithAi(self, evt: wx.Event) -> None:
		if not talkWithAI:
			wx.CallAfter(
				wx.MessageBox,
				# Translators: Error shown if the optional Talk With AI dialog module cannot be loaded.
				_("Talk With AI module is missing."),
				_("Error"),
				wx.OK | wx.ICON_ERROR,
			)
			return

		if self.modeMulti:
			wx.CallAfter(
				wx.MessageBox,
				_(
					# Translators: Warning shown when Talk With AI is opened while multi-speaker mode is selected.
					"Talk With AI currently does not support multi-speaker mode. Please select Single-speaker.",
				),
				_("Feature Limitation"),
				wx.OK | wx.ICON_WARNING,
			)
			return

		apiKey = self._resolveApiKeyForUse()
		if not apiKey:
			return

		voiceName = self._getSelectedVoiceName(self.voiceChoiceSingle, self.selectedVoiceIdx)
		styleInstructions = self.styleCtrl.GetValue().strip()

		try:
			# Keep this dialog alive so the user's draft remains available if the
			# Talk With AI dialog fails to initialize or after it closes.
			dlg = talkWithAI.TalkWithAIDialog(self, apiKey, voiceName, styleInstructions)
			dlg.ShowModal()
		except Exception as e:
			log.error(f"Failed to open TalkWithAI dialog: {e}", exc_info=True)
			wx.CallAfter(
				wx.MessageBox,
				_("Failed to open Talk With AI: {error}").format(error=str(e)),
				_("Error"),
				wx.OK | wx.ICON_ERROR,
			)

	def _buildGenerationRequest(self, text: str, apiKey: str) -> GenerationRequest:
		primaryVoiceCtrl = self.voiceChoiceMulti1 if self.modeMulti else self.voiceChoiceSingle
		primaryVoiceIdx = primaryVoiceCtrl.GetSelection()
		secondaryVoiceIdx = self.voiceChoiceMulti2.GetSelection()
		return GenerationRequest(
			apiKey=apiKey,
			text=text,
			model=self.model,
			temperature=self.tempSlider.GetValue() / 10.0,
			styleInstructions=self.styleCtrl.GetValue().strip(),
			modeMulti=self.modeMulti,
			voiceName=self._getSelectedVoiceName(primaryVoiceCtrl, primaryVoiceIdx),
			voiceName2=self._getSelectedVoiceName(self.voiceChoiceMulti2, secondaryVoiceIdx),
			# Translators: Fallback speaker name used when the first speaker field is blank.
			speaker1Name=self.spk1NameCtrl.GetValue().strip() or _("Speaker1"),
			# Translators: Fallback speaker name used when the second speaker field is blank.
			speaker2Name=self.spk2NameCtrl.GetValue().strip() or _("Speaker2"),
		)

	def onGenerate(self, evt: wx.Event) -> None:
		if self.isGenerating:
			return
		if not GENAI_AVAILABLE:
			message = _(
				# Translators: Error shown when the bundled google-genai dependency cannot be imported.
				"google-genai is not available. Please restart NVDA after updating the add-on libraries.",
			)
			if GENAI_IMPORT_ERROR:
				# Translators: Error details appended to a dependency import failure.
				message = _("{baseMessage}\n\nImport detail: {errorDetail}").format(
					baseMessage=message,
					errorDetail=GENAI_IMPORT_ERROR,
				)
			wx.CallAfter(
				wx.MessageBox,
				message,
				_("Error"),
				wx.OK | wx.ICON_ERROR,
			)
			return
		apiKey = self._resolveApiKeyForUse()
		if not apiKey:
			return
		text = self.textCtrl.GetValue().strip()
		if not text:
			wx.CallAfter(
				wx.MessageBox,
				# Translators: Error shown when the user tries to generate speech without entering text.
				_("Please enter text to generate."),
				_("Error"),
				wx.OK | wx.ICON_ERROR,
			)
			return

		generationRequest = self._buildGenerationRequest(text, apiKey)
		self.isGenerating = True
		# Translators: Temporary Generate button label while speech generation is running.
		self.generateBtn.SetLabel(_("Generating..."))
		self.playBtn.Enable(False)
		self.saveBtn.Enable(False)
		self.talkBtn.Enable(False)
		threading.Thread(target=self._generateThread, args=(generationRequest,), daemon=True).start()

	def _generateThread(self, generationRequest: GenerationRequest) -> None:
		# Translators: Status announcement made when speech generation starts.
		ui.message(_("Generating speech, please wait..."))
		try:
			with getRuntimeScope():
				self.client = genai.Client(api_key=generationRequest.apiKey)
		except Exception as e:
			log.error(f"Failed init genai client: {e}", exc_info=True)
			if not self.isClosed:
				wx.CallAfter(
					wx.MessageBox,
					_("Failed to initialize Google GenAI client: {error}").format(error=str(e)),
					_("Error"),
					wx.OK | wx.ICON_ERROR,
				)
				wx.CallAfter(self._restoreGenerateButton)
			return

		def handleSuccess(savedPath: str | None) -> None:
			if self.isClosed:
				return
			if not savedPath:
				# Translators: Status announcement made when speech generation fails.
				ui.message(_("Failed to generate audio."))
				return
			# Translators: Status announcement made when speech generation succeeds.
			ui.message(_("Generation complete."))
			self.lastAudioPath = savedPath
			safeStartFile(self.lastAudioPath)
			wx.CallAfter(self.playBtn.Enable, True)
			wx.CallAfter(self.saveBtn.Enable, True)

		try:
			with getRuntimeScope():
				if generationRequest.styleInstructions:
					finalText = f"{generationRequest.styleInstructions}\n{generationRequest.text}"
				else:
					finalText = f"Please read the following text aloud:\n{generationRequest.text}"

				contents = [types.Content(role="user", parts=[types.Part.from_text(text=finalText)])]

				if not generationRequest.modeMulti:
					speechConfig = types.SpeechConfig(
						voice_config=types.VoiceConfig(
							prebuilt_voice_config=types.PrebuiltVoiceConfig(
								voice_name=generationRequest.voiceName,
							),
						),
					)
				else:
					speechConfig = types.SpeechConfig(
						multi_speaker_voice_config=types.MultiSpeakerVoiceConfig(
							speaker_voice_configs=[
								types.SpeakerVoiceConfig(
									speaker=generationRequest.speaker1Name,
									voice_config=types.VoiceConfig(
										prebuilt_voice_config=types.PrebuiltVoiceConfig(
											voice_name=generationRequest.voiceName,
										),
									),
								),
								types.SpeakerVoiceConfig(
									speaker=generationRequest.speaker2Name,
									voice_config=types.VoiceConfig(
										prebuilt_voice_config=types.PrebuiltVoiceConfig(
											voice_name=generationRequest.voiceName2,
										),
									),
								),
							],
						),
					)

				generateConfig = types.GenerateContentConfig(
					temperature=generationRequest.temperature,
					response_modalities=["audio"],
					speech_config=speechConfig,
				)
			outPathBase = self._buildOutputPathBase()

			if self.isClosed:
				return

			savedPath = self._streamAndSaveAudio(
				self.client,
				generationRequest.model,
				contents,
				generateConfig,
				outPathBase,
			)

			if self.isClosed:
				return

			wx.CallAfter(handleSuccess, savedPath)

		except Exception as e:
			if self.isClosed:
				return
			# Translators: Status announcement made when speech generation raises an unexpected error.
			ui.message(_("An error occurred during generation."))
			log.error(f"Unexpected error in generateThread: {e}", exc_info=True)
			wx.CallAfter(
				wx.MessageBox,
				_("An unexpected error occurred: {error}").format(error=str(e)),
				_("Error"),
				wx.OK | wx.ICON_ERROR,
			)
		finally:
			if not self.isClosed:
				wx.CallAfter(self._restoreGenerateButton)

	def _restoreGenerateButton(self) -> None:
		# Translators: Button label restored after speech generation finishes.
		self.generateBtn.SetLabel(_("&Generate Speech"))
		self.talkBtn.Enable(True)
		self.isGenerating = False

	def _buildOutputPathBase(self) -> str:
		os.makedirs(GENERATED_AUDIO_DIR, exist_ok=True)
		return os.path.join(GENERATED_AUDIO_DIR, f"last_audio_generated_{uuid.uuid4().hex}")

	def _iterResponseParts(self, chunk: Any) -> list[Any]:
		parts = getattr(chunk, "parts", None)
		if parts:
			return list(parts)
		collectedParts = []
		for candidate in getattr(chunk, "candidates", []) or []:
			content = getattr(candidate, "content", None)
			candidateParts = getattr(content, "parts", None) if content else None
			if candidateParts:
				collectedParts.extend(candidateParts)
		return collectedParts

	def _streamAndSaveAudio(
		self,
		client: Any,
		model: str,
		contents: list[Any],
		configObj: Any,
		outPathBase: str,
	) -> str | None:
		fileIndex = 0
		savedPaths = []
		self.currentStream = None
		try:
			if self.isClosed:
				return None
			with getRuntimeScope():
				self.currentStream = client.models.generate_content_stream(
					model=model,
					contents=contents,
					config=configObj,
				)

			with getRuntimeScope():
				for chunk in self.currentStream:
					if self.isClosed:
						try:
							self.currentStream.close()
						except Exception as error:
							log.debug(
								f"Failed to close generation stream during shutdown: {error}",
								exc_info=True,
							)
						return None

					for part in self._iterResponseParts(chunk):
						if not getattr(part, "inline_data", None) or not getattr(
							part.inline_data,
							"data",
							None,
						):
							continue
						inline = part.inline_data
						ext = mimetypes.guess_extension(inline.mime_type or "") or ""

						if not ext or ext.lower() not in (".wav", ".mp3", ".ogg", ".flac"):
							wavBytes = convertToWav(inline.data, inline.mime_type)
							filename = f"{outPathBase}_{fileIndex}.wav"
							saveBinaryFile(filename, wavBytes)
						else:
							filename = f"{outPathBase}_{fileIndex}{ext}"
							saveBinaryFile(filename, inline.data)

						savedPaths.append(filename)
						fileIndex += 1

			if not savedPaths:
				wx.CallAfter(
					wx.MessageBox,
					_("No inline audio data returned by model."),
					_("Error"),
					wx.OK | wx.ICON_ERROR,
				)
				return None

			if len(savedPaths) > 1 and self._shouldMergeAudioChunks(model, savedPaths):
				outAll = f"{outPathBase}_combined.wav"
				try:
					mergeWavFiles(savedPaths, outAll)
					return outAll
				except Exception as e:
					log.error(f"Failed to merge WAV parts: {e}", exc_info=True)
					return self._selectBestGeneratedAudioPath(savedPaths)
			if len(savedPaths) > 1:
				return self._selectBestGeneratedAudioPath(savedPaths)
			return savedPaths[0]

		except Exception as e:
			if self.isClosed:
				return None
			log.error(f"Error streaming/generating audio: {e}", exc_info=True)
			wx.CallAfter(
				wx.MessageBox,
				_("Failed to generate speech: {error}").format(error=str(e)),
				_("Error"),
				wx.OK | wx.ICON_ERROR,
			)
			return None
		finally:
			self.currentStream = None

	def _shouldMergeAudioChunks(self, model: str, savedPaths: list[str]) -> bool:
		"""Return whether streamed audio parts should be concatenated."""
		return model == DEFAULT_MODEL and all(path.lower().endswith(".wav") for path in savedPaths)

	def _selectBestGeneratedAudioPath(self, savedPaths: list[str]) -> str:
		"""Choose the most complete single audio file when stream chunks overlap."""
		return max(savedPaths, key=os.path.getsize)

	def onPlay(self, evt: wx.Event) -> None:
		if not self.lastAudioPath or not os.path.exists(self.lastAudioPath):
			return
		safeStartFile(self.lastAudioPath)

	def onSave(self, evt: wx.Event) -> None:
		if not self.lastAudioPath or not os.path.exists(self.lastAudioPath):
			return
		with wx.FileDialog(
			self,
			_("Save Audio File"),
			wildcard=_("WAV files (*.wav)|*.wav|MP3 files (*.mp3)|*.mp3"),
			style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
		) as dlg:
			if dlg.ShowModal() == wx.ID_CANCEL:
				return
			dest = dlg.GetPath()
			try:
				os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
				with open(self.lastAudioPath, "rb") as src, open(dest, "wb") as dst:
					dst.write(src.read())
				wx.CallAfter(
					wx.MessageBox,
					_("Audio saved to {path}").format(path=dest),
					_("Success"),
					wx.OK | wx.ICON_INFORMATION,
				)
			except Exception as e:
				wx.CallAfter(
					wx.MessageBox,
					_("Failed to save audio: {error}").format(error=str(e)),
					_("Error"),
					wx.OK | wx.ICON_ERROR,
				)

	def _playSampleForVoice(self, voiceName: str) -> None:
		if not voiceName:
			return
		url = f"{VOICE_SAMPLE_BASE}/{voiceName}.wav"
		threading.Thread(target=self._downloadAndPlaySample, args=(url,), daemon=True).start()

	def _downloadAndPlaySample(self, url: str) -> None:
		try:
			request = urllib.request.Request(url, headers={"User-Agent": "NativeSpeechGeneration-NVDA-Addon"})
			with urllib.request.urlopen(request, timeout=10) as response:
				statusCode = getattr(response, "status", response.getcode())
				content = response.read()
			if statusCode != 200 or not content:
				ui.message(_("Sample not available"))
				return
			with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
				tmp.write(content)
				tempPath = tmp.name
			ui.message(_("Playing voice sample"))
			winsound.PlaySound(tempPath, winsound.SND_FILENAME | winsound.SND_ASYNC)
			threading.Timer(10.0, lambda: os.remove(tempPath) if os.path.exists(tempPath) else None).start()
		except Exception as e:
			log.error(f"Failed to play sample: {e}", exc_info=True)
			ui.message(_("Failed to play sample"))

	def loadVoices(self) -> None:
		try:
			log.info("Skipping API call for voices. Using fallback voices.")
			voices = [{"name": v, "label": v, "meta": {}} for v in FALLBACK_VOICES]

			def updateUi() -> None:
				try:
					self.voices = voices
					voiceLabels = [v["label"] for v in voices]
					for choiceCtrl in (
						self.voiceChoiceSingle,
						self.voiceChoiceMulti1,
						self.voiceChoiceMulti2,
					):
						choiceCtrl.Clear()
						choiceCtrl.AppendItems(voiceLabels)
					if voices:
						self.voiceChoiceSingle.SetSelection(0)
						self.voiceChoiceMulti1.SetSelection(0)
					if len(voices) > 1:
						self.voiceChoiceMulti2.SetSelection(1)
				except Exception as e:
					log.error(f"Failed to update voice UI: {e}", exc_info=True)

			wx.CallAfter(updateUi)
		except Exception as e:
			log.error(f"Unexpected error loading voices: {e}", exc_info=True)
