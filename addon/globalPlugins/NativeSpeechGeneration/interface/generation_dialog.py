# -*- coding: utf-8 -*-
import wx
import threading
import os
import mimetypes
import requests
import webbrowser
import tempfile
import winsound
import gui
import ui
import config
from logHandler import log
from typing import Any, TYPE_CHECKING

from ..core.constants import (
	CONFIG_DOMAIN,
	DEFAULT_MODEL,
	SECOND_MODEL,
	VOICE_SAMPLE_BASE,
	FALLBACK_VOICES,
)
from ..core.audio_utils import convertToWav, mergeWavFiles, saveBinaryFile, safeStartFile
from ..core.gemini_imports import genai, types, GENAI_AVAILABLE

from .. import talkWithAI

if TYPE_CHECKING:

	def _(msg: str) -> str:
		return msg


# Need to know addon_dir for saving "last_audio_generated"
_guiDir = os.path.dirname(os.path.abspath(__file__))
_pkgDir = os.path.dirname(_guiDir)
_globalPluginsDir = os.path.dirname(_pkgDir)
ADDON_DIR_VAL = os.path.dirname(_globalPluginsDir)


class NativeSpeechDialog(wx.Dialog):
	def __init__(self, parent: wx.Window) -> None:
		super().__init__(parent, title=_("Native Speech Generation (Gemini TTS)"))
		try:
			self.apiKey = config.conf[CONFIG_DOMAIN]["apiKey"]
		except Exception:
			self.apiKey = ""

		self.lastAudioPath: str | None = None
		self.model = DEFAULT_MODEL
		self.modeMulti = False
		self.voices: list[dict[str, Any]] = []
		self.selectedVoiceIdx = 0
		self.selectedVoiceIdx2 = 0
		self.isGenerating = False
		self.client = None
		self.isClosed = False

		self._buildUi()
		threading.Thread(target=self.loadVoices, daemon=True).start()
		self.textCtrl.SetFocus()

	def _buildUi(self) -> None:
		mainSizer = wx.BoxSizer(wx.VERTICAL)

		# Text Input
		textLabel = wx.StaticText(self, label=_("&Type text to convert here:"))
		self.textCtrl = wx.TextCtrl(self, style=wx.TE_MULTILINE, size=(520, 160))
		mainSizer.Add(textLabel, flag=wx.ALL, border=6)
		mainSizer.Add(self.textCtrl, flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=6)

		# Style Input
		styleLabel = wx.StaticText(self, label=_("&Style instructions (optional):"))
		self.styleCtrl = wx.TextCtrl(self, style=wx.TE_MULTILINE, size=(520, 60))
		mainSizer.Add(styleLabel, flag=wx.ALL, border=6)
		mainSizer.Add(self.styleCtrl, flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=6)

		# Model & Mode Selection
		modelSizer = wx.BoxSizer(wx.HORIZONTAL)
		modelLabel = wx.StaticText(self, label=_("Select &Model:"))
		self.modelChoice = wx.Choice(self, choices=[_("Flash (Standard Quality)"), _("Pro (High Quality)")])
		self.modelChoice.SetSelection(0)
		self.modelChoice.Bind(wx.EVT_CHOICE, self.onModelChange)
		modelSizer.Add(modelLabel, flag=wx.ALIGN_CENTER_VERTICAL | wx.ALL, border=6)
		modelSizer.Add(self.modelChoice, flag=wx.ALL, border=6)

		self.modeSingleRb = wx.RadioButton(self, label=_("Single-speaker"), style=wx.RB_GROUP)
		self.modeMultiRb = wx.RadioButton(self, label=_("Multi-speaker (2)"))
		self.modeSingleRb.SetValue(True)
		self.modeSingleRb.Bind(wx.EVT_RADIOBUTTON, self.onModeChange)
		self.modeMultiRb.Bind(wx.EVT_RADIOBUTTON, self.onModeChange)
		modelSizer.Add(self.modeSingleRb, flag=wx.ALL, border=6)
		modelSizer.Add(self.modeMultiRb, flag=wx.ALL, border=6)
		mainSizer.Add(modelSizer, flag=wx.EXPAND)

		# Settings Toggle
		self.settingsCheckbox = wx.CheckBox(self, label=_("Advanced Settings (&Temperature)"))
		self.settingsCheckbox.SetValue(False)
		mainSizer.Add(self.settingsCheckbox, flag=wx.LEFT | wx.RIGHT | wx.TOP, border=6)

		# Settings Panel (Hidden)
		self.settingsPanel = wx.Panel(self)
		mainSizer.Add(self.settingsPanel, proportion=0, flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=6)

		paneSizer = wx.BoxSizer(wx.VERTICAL)
		tempSizer = wx.BoxSizer(wx.HORIZONTAL)
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

		# Voice Panels
		self.voicePanelSingle = self._buildVoicePanelSingle()
		self.voicePanelMulti = self._buildVoicePanelMulti()
		mainSizer.Add(self.voicePanelSingle, flag=wx.EXPAND | wx.ALL, border=5)
		mainSizer.Add(self.voicePanelMulti, flag=wx.EXPAND | wx.ALL, border=5)
		self.voicePanelMulti.Hide()

		# Action Buttons
		btnSizer = wx.StdDialogButtonSizer()
		self.generateBtn = wx.Button(self, label=_("&Generate Speech"))
		self.generateBtn.Bind(wx.EVT_BUTTON, self.onGenerate)
		btnSizer.AddButton(self.generateBtn)

		self.playBtn = wx.Button(self, label=_("&Play"))
		self.playBtn.Bind(wx.EVT_BUTTON, self.onPlay)
		self.playBtn.Enable(False)
		btnSizer.AddButton(self.playBtn)

		self.saveBtn = wx.Button(self, label=_("Save &Audio"))
		self.saveBtn.Bind(wx.EVT_BUTTON, self.onSave)
		self.saveBtn.Enable(False)
		btnSizer.AddButton(self.saveBtn)
		btnSizer.Realize()
		mainSizer.Add(btnSizer, flag=wx.EXPAND | wx.ALL, border=10)

		# Talk With AI Button
		self.talkBtn = wx.Button(self, label=_("Talk With &AI"))
		self.talkBtn.Bind(wx.EVT_BUTTON, self.onTalkWithAi)
		mainSizer.Add(self.talkBtn, flag=wx.ALIGN_CENTER | wx.ALL, border=5)

		# Footer
		footerSizer = wx.BoxSizer(wx.HORIZONTAL)
		self.getKeyBtn = wx.Button(self, label=_("API Key Settings"))
		self.getKeyBtn.Bind(wx.EVT_BUTTON, self.onSettings)
		self.viewVoicesBtn = wx.Button(self, label=_("View voices in AI Studio"))
		self.viewVoicesBtn.Bind(wx.EVT_BUTTON, self.onOpenAiStudio)
		footerSizer.Add(self.getKeyBtn, flag=wx.ALL, border=6)
		footerSizer.Add(self.viewVoicesBtn, flag=wx.ALL, border=6)
		mainSizer.Add(footerSizer, flag=wx.ALIGN_CENTER | wx.ALL, border=5)

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
		label = wx.StaticText(panel, label=_("Select &Voice:"))
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

		# Speaker 1
		spk1Sizer = wx.BoxSizer(wx.HORIZONTAL)
		spk1Label = wx.StaticText(panel, label=_("Speaker 1 Name:"))
		self.spk1NameCtrl = wx.TextCtrl(panel, value="Speaker1", size=(100, -1))
		voice1Label = wx.StaticText(panel, label=_("Voice:"))
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

		# Speaker 2
		spk2Sizer = wx.BoxSizer(wx.HORIZONTAL)
		spk2Label = wx.StaticText(panel, label=_("Speaker 2 Name:"))
		self.spk2NameCtrl = wx.TextCtrl(panel, value="Speaker2", size=(100, -1))
		voice2Label = wx.StaticText(panel, label=_("Voice:"))
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
		# Force close the stream if it's active
		if hasattr(self, "currentStream") and self.currentStream:
			try:
				self.currentStream.close()
			except Exception:
				pass

		# Close the client
		if self.client:
			try:
				self.client.close()
			except Exception:
				pass
		self.Destroy()

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
		sel = self.modelChoice.GetSelection()
		self.model = DEFAULT_MODEL if sel == 0 else SECOND_MODEL

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
		# Usage of match statement (Python 3.10+)
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
			# Fallback
			return str(voiceData)
		except IndexError:
			return self.voices[0]["name"] if self.voices else "Zephyr"
		except Exception as e:
			log.error(f"Failed to get selected voice name: {e}", exc_info=True)
			return "Zephyr"

	def onSettings(self, evt: wx.Event) -> None:
		# Import panel locally to avoid circular dep if needed, or pass class
		from .settings import NativeSpeechSettingsPanel

		self.Destroy()
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
				_("Talk With AI module is missing."),
				_("Error"),
				wx.OK | wx.ICON_ERROR,
			)
			return

		if self.modeMulti:
			wx.CallAfter(
				wx.MessageBox,
				_(
					"Talk With AI currently does not support multi-speaker mode. Please select Single-speaker.",
				),
				_("Feature Limitation"),
				wx.OK | wx.ICON_WARNING,
			)
			return

		if not self.apiKey:
			wx.CallAfter(wx.MessageBox, _("No GEMINI_API_KEY configured."), _("Error"), wx.OK | wx.ICON_ERROR)
			return

		# Get current settings
		voiceName = self._getSelectedVoiceName(self.voiceChoiceSingle, self.selectedVoiceIdx)
		styleInstructions = self.styleCtrl.GetValue().strip()

		try:
			# Close the main dialog first
			self.Close()

			# Show TalkWithAI dialog
			# We use gui.mainFrame as parent since self is being destroyed
			dlg = talkWithAI.TalkWithAIDialog(gui.mainFrame, self.apiKey, voiceName, styleInstructions)
			dlg.ShowModal()
		except Exception as e:
			log.error(f"Failed to open TalkWithAI dialog: {e}", exc_info=True)
			wx.CallAfter(
				wx.MessageBox,
				_("Failed to open Talk With AI: {error}").format(error=str(e)),
				_("Error"),
				wx.OK | wx.ICON_ERROR,
			)

	def onGenerate(self, evt: wx.Event) -> None:
		if self.isGenerating:
			return
		if not GENAI_AVAILABLE:
			wx.CallAfter(
				wx.MessageBox,
				_("google-genai library not installed. Please restart NVDA."),
				_("Error"),
				wx.OK | wx.ICON_ERROR,
			)
			return
		if not self.apiKey:
			wx.CallAfter(
				wx.MessageBox,
				_("No GEMINI_API_KEY configured. Set it in NVDA settings."),
				_("Error"),
				wx.OK | wx.ICON_ERROR,
			)
			return
		text = self.textCtrl.GetValue().strip()
		if not text:
			wx.CallAfter(
				wx.MessageBox,
				_("Please enter text to generate."),
				_("Error"),
				wx.OK | wx.ICON_ERROR,
			)
			return

		self.isGenerating = True
		self.generateBtn.SetLabel(_("Generating..."))
		self.playBtn.Enable(False)
		self.saveBtn.Enable(False)
		self.talkBtn.Enable(False)
		threading.Thread(target=self._generateThread, args=(text,), daemon=True).start()

	def _generateThread(self, text: str) -> None:
		ui.message(_("Generating speech, please wait..."))
		try:
			self.client = genai.Client(api_key=self.apiKey)
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
				ui.message(_("Failed to generate audio."))
				return
			ui.message(_("Generation complete."))
			self.lastAudioPath = savedPath
			safeStartFile(self.lastAudioPath)
			wx.CallAfter(self.playBtn.Enable, True)
			wx.CallAfter(self.saveBtn.Enable, True)

		try:
			temp = self.tempSlider.GetValue() / 10.0
			styleInstructions = self.styleCtrl.GetValue().strip()
			finalText = f"{styleInstructions}\n{text}" if styleInstructions else text

			contents = [types.Content(role="user", parts=[types.Part.from_text(text=finalText)])]

			if not self.modeMulti:
				voiceName = self._getSelectedVoiceName(self.voiceChoiceSingle, self.selectedVoiceIdx)
				speechConfig = types.SpeechConfig(
					voice_config=types.VoiceConfig(
						prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voiceName),
					),
				)
			else:
				speaker1Name = self.spk1NameCtrl.GetValue().strip() or "Speaker1"
				speaker2Name = self.spk2NameCtrl.GetValue().strip() or "Speaker2"
				voice1 = self._getSelectedVoiceName(self.voiceChoiceMulti1, self.selectedVoiceIdx)
				voice2 = self._getSelectedVoiceName(self.voiceChoiceMulti2, self.selectedVoiceIdx2)
				speechConfig = types.SpeechConfig(
					multi_speaker_voice_config=types.MultiSpeakerVoiceConfig(
						speaker_voice_configs=[
							types.SpeakerVoiceConfig(
								speaker=speaker1Name,
								voice_config=types.VoiceConfig(
									prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice1),
								),
							),
							types.SpeakerVoiceConfig(
								speaker=speaker2Name,
								voice_config=types.VoiceConfig(
									prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice2),
								),
							),
						],
					),
				)

			generateConfig = types.GenerateContentConfig(
				temperature=temp,
				response_modalities=["audio"],
				speech_config=speechConfig,
			)
			outPathBase = os.path.join(ADDON_DIR_VAL, "last_audio_generated")

			if self.isClosed:
				return

			savedPath = self._streamAndSaveAudio(
				self.client,
				self.model,
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
		self.generateBtn.SetLabel(_("&Generate Speech"))
		self.talkBtn.Enable(True)
		self.isGenerating = False

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
		# Keep reference to current stream so we can close it from main thread if needed
		self.currentStream = None
		try:
			if self.isClosed:
				return None
			# Store the stream object
			self.currentStream = client.models.generate_content_stream(
				model=model,
				contents=contents,
				config=configObj,
			)

			for chunk in self.currentStream:
				if self.isClosed:
					# Explicitly close the stream iterator to kill connection
					try:
						self.currentStream.close()
					except Exception:
						pass
					return None

				if not getattr(chunk, "candidates", None):
					continue
				candidate = chunk.candidates[0]
				if not candidate.content or not candidate.content.parts:
					continue
				part = candidate.content.parts[0]

				if part.inline_data and getattr(part.inline_data, "data", None):
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

			if len(savedPaths) > 1 and all(p.lower().endswith(".wav") for p in savedPaths):
				outAll = f"{outPathBase}_combined.wav"
				try:
					mergeWavFiles(savedPaths, outAll)
					return outAll
				except Exception as e:
					log.error(f"Failed to merge WAV parts: {e}", exc_info=True)
					return savedPaths[0]
			return savedPaths[0]

		except Exception as e:
			# If exception is due to closure, ignore
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
			# Cleanup stream reference
			self.currentStream = None

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
			wildcard="WAV files (*.wav)|*.wav|MP3 files (*.mp3)|*.mp3",
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
			resp = requests.get(url, timeout=10)
			if resp.status_code != 200 or not resp.content:
				ui.message(_("Sample not available"))
				return
			with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
				tmp.write(resp.content)
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
