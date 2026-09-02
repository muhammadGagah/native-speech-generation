import asyncio
import base64
import os
import queue
import random
import struct
import threading
import time
import traceback
import winsound
from typing import Any, cast

import addonHandler
import ui
import wx
from logHandler import log

from .core import config_store
from .core.api_client import DirectLiveSession
from .core.audio_runtime import PYAUDIO_AVAILABLE, PYAUDIO_IMPORT_ERROR, getRuntimeScope, pyaudio
from .core.screen_capture import ScreenCaptureWorker, is_screen_curtain_active

addonHandler.initTranslation()


MODEL_NAME = "gemini-3.1-flash-live-preview"
MEDIA_DIR = os.path.join(os.path.dirname(__file__), "media")
STREAM_START_SOUND_PATH = os.path.join(MEDIA_DIR, "stream-start.wav")
STREAM_END_SOUND_PATH = os.path.join(MEDIA_DIR, "stream-end.wav")

FORMAT = pyaudio.paInt16 if pyaudio else 8
CHANNELS = 1
INPUT_RATE = 16000
OUTPUT_RATE = 24000
CHUNK = 1024
BUFFER_THRESHOLD = 5
MIN_BUFFER_THRESHOLD = 2
MAX_BUFFER_THRESHOLD = 10
BACKOFF_BASE_SECONDS = 1.0
BACKOFF_MAX_SECONDS = 20.0
BACKOFF_JITTER_SECONDS = 0.4
HISTORY_MAX_TURNS = 12
HISTORY_MAX_CHARS = 1800


class TalkWithAIDialog(wx.Dialog):
	"""Dialog and runtime controller for Gemini Live voice conversation."""

	statusLabel: wx.StaticText
	connectBtn: wx.Button
	disconnectBtn: wx.Button
	micBtn: wx.ToggleButton
	deviceSizer: wx.BoxSizer
	inputChoice: wx.Choice
	outputChoice: wx.Choice
	googleSearchCb: wx.CheckBox
	shareScreenCb: wx.CheckBox
	thinkingLabel: wx.StaticText
	thinkingChoice: wx.Choice
	volSlider: wx.Slider

	def __init__(self, parent: wx.Window, apiKey: str, voiceName: str, systemInstruction: str) -> None:
		# Translators: Title of the dialog for the "Talk With AI" feature (REAL-TIME conversation).
		super().__init__(parent, title=_("Talk With AI"), size=(420, 320))
		self.statusLabel = cast(wx.StaticText, None)
		self.connectBtn = cast(wx.Button, None)
		self.disconnectBtn = cast(wx.Button, None)
		self.micBtn = cast(wx.ToggleButton, None)
		self.deviceSizer = cast(wx.BoxSizer, None)
		self.inputChoice = cast(wx.Choice, None)
		self.outputChoice = cast(wx.Choice, None)
		self.googleSearchCb = cast(wx.CheckBox, None)
		self.shareScreenCb = cast(wx.CheckBox, None)
		self.thinkingLabel = cast(wx.StaticText, None)
		self.thinkingChoice = cast(wx.Choice, None)
		self.volSlider = cast(wx.Slider, None)
		self.apiKey = apiKey
		self.voiceName = voiceName
		self.systemInstruction = systemInstruction

		self.session = None
		self.sessionActive = False
		self.loop = None
		self.loopThread = None
		self._sessionTask = None
		self._sessionId = 0
		self._sessionHadError = False
		self._restoreConnectFocus = False
		self.audioInterface = None
		self.inputStream = None
		self.outputStream = None
		self._audioPlayerThread: threading.Thread | None = None
		self.micOn = True
		self.useGoogleSearch = False
		self.selectedThinkingLevel = "minimal"
		self._screenCaptureWorker: ScreenCaptureWorker | None = None
		self._screenFramePending = False
		self.shareScreen = False

		self.audioQueue = queue.Queue()
		self.outputLock = threading.Lock()
		self._micReadFinished = threading.Event()
		self._micReadFinished.set()
		self._playbackGeneration = 0
		self.isPlaying = False
		persistedSettings = config_store.getTalkWithAISettings()
		self.volume = persistedSettings.volume
		self._persistedInputDevice = persistedSettings.inputDevice
		self._persistedOutputDevice = persistedSettings.outputDevice
		self._inputDeviceSelectionDirty = False
		self._outputDeviceSelectionDirty = False
		self._restoringDevices = False
		self.bufferThreshold = BUFFER_THRESHOLD
		self.lastBufferAdjustAt = 0.0
		self.lastStatusAt = 0.0
		self.lastAnnouncedStatus = ""
		self._isClosing = False
		self.sessionHistory = []
		self.historyLock = threading.Lock()

		self.inputDevices: list[dict[str, Any]] = []
		self.outputDevices: list[dict[str, Any]] = []
		self._devicesLoaded = False
		self.selectedInputIdx = None
		self.selectedOutputIdx = None
		self.thinkingChoices = [
			# Translators: Choice label for the lowest reasoning setting in Talk With AI.
			(_("No Thinking"), "minimal"),
			# Translators: Choice label for low reasoning depth in Talk With AI.
			(_("Low"), "low"),
			# Translators: Choice label for medium reasoning depth in Talk With AI.
			(_("Medium"), "medium"),
			# Translators: Choice label for high reasoning depth in Talk With AI.
			(_("High"), "high"),
		]

		self._buildUi()
		self.connectBtn.Disable()
		self.compatibilityError = self._getRuntimeCompatibilityError()

		if not PYAUDIO_AVAILABLE:
			wx.CallAfter(
				self.reportError,
				self._buildMissingDependencyMessage(
					_("PyAudio is not available. This feature requires a working PyAudio installation."),
					PYAUDIO_IMPORT_ERROR,
				),
			)
			self.connectBtn.Disable()
		if self.compatibilityError:
			wx.CallAfter(self.reportError, self.compatibilityError)
			self.connectBtn.Disable()
		if PYAUDIO_AVAILABLE:
			threading.Thread(target=self._loadDevicesWorker, daemon=True).start()
		wx.CallAfter(self._setInitialFocus)

		self.Bind(wx.EVT_CLOSE, self.onClose)
		self.Bind(wx.EVT_CHAR_HOOK, self.onCharHook)

	def _setInitialFocus(self) -> None:
		if self._isClosing:
			return
		if self.connectBtn.IsEnabled():
			self.connectBtn.SetFocus()
		else:
			self.micBtn.SetFocus()

	def _loadDevicesWorker(self) -> None:
		inputDevices = self._getDeviceList(input=True)
		outputDevices = self._getDeviceList(input=False)
		wx.CallAfter(self._applyDeviceLists, inputDevices, outputDevices)

	def _applyDeviceLists(
		self,
		inputDevices: list[dict[str, Any]],
		outputDevices: list[dict[str, Any]],
	) -> None:
		if self._isClosing:
			return
		self._restoringDevices = True
		try:
			self.inputDevices = inputDevices
			self.outputDevices = outputDevices
			self.inputChoice.Clear()
			self.inputChoice.AppendItems([device["name"] for device in inputDevices])
			self.outputChoice.Clear()
			self.outputChoice.AppendItems([device["name"] for device in outputDevices])
			self.inputChoice.Enable(bool(inputDevices))
			self.outputChoice.Enable(bool(outputDevices))
			inputSelection = self._findDeviceSelection(inputDevices, self._persistedInputDevice)
			outputSelection = self._findDeviceSelection(outputDevices, self._persistedOutputDevice)
			if inputSelection != wx.NOT_FOUND:
				self.inputChoice.SetSelection(inputSelection)
			if outputSelection != wx.NOT_FOUND:
				self.outputChoice.SetSelection(outputSelection)
		finally:
			self._restoringDevices = False
		self._devicesLoaded = True
		runtimeUsable = not getattr(self, "compatibilityError", None) and PYAUDIO_AVAILABLE
		if not runtimeUsable:
			return
		self.connectBtn.Enable()
		if self.micBtn.HasFocus():
			self.connectBtn.SetFocus()
		if inputDevices or outputDevices:
			# Translators: Status shown after Talk With AI finishes enumerating audio devices.
			self.updateStatus(_("Audio devices loaded"), announce=True)
		else:
			# Translators: Status shown when Talk With AI will use the operating system's default audio devices.
			self.updateStatus(
				_("No explicit audio devices found. System defaults will be used."),
				announce=True,
			)

	@staticmethod
	def _findDeviceSelection(devices: list[dict[str, Any]], persistedName: str) -> int:
		if not devices:
			return wx.NOT_FOUND
		for index, device in enumerate(devices):
			if str(device.get("name") or "") == persistedName:
				return index
		return 0

	def _savePersistentSettings(self) -> None:
		inputDevice = self._persistedInputDevice
		outputDevice = self._persistedOutputDevice
		inputSelection = self.inputChoice.GetSelection()
		if (
			inputSelection != wx.NOT_FOUND
			and inputSelection < len(self.inputDevices)
			and (self._inputDeviceSelectionDirty or not inputDevice)
		):
			inputDevice = str(self.inputDevices[inputSelection].get("name") or "")
		outputSelection = self.outputChoice.GetSelection()
		if (
			outputSelection != wx.NOT_FOUND
			and outputSelection < len(self.outputDevices)
			and (self._outputDeviceSelectionDirty or not outputDevice)
		):
			outputDevice = str(self.outputDevices[outputSelection].get("name") or "")
		config_store.setTalkWithAISettings(inputDevice, outputDevice, self.volSlider.GetValue())

	def _onInputDeviceChange(self, evt: wx.Event) -> None:
		if not self._restoringDevices:
			self._inputDeviceSelectionDirty = True
		evt.Skip()

	def _onOutputDeviceChange(self, evt: wx.Event) -> None:
		if not self._restoringDevices:
			self._outputDeviceSelectionDirty = True
		evt.Skip()

	def _logCleanupFailure(self, action: str, error: BaseException) -> None:
		log.debug(f"Talk With AI cleanup issue during {action}: {error}", exc_info=True)

	def _getDeviceList(self, input: bool = True) -> list[dict[str, Any]]:
		"""Returns a list of dicts: {'index': int, 'name': str}"""
		devices: list[dict[str, Any]] = []
		if not PYAUDIO_AVAILABLE:
			return devices
		p = None
		try:
			with getRuntimeScope():
				p = pyaudio.PyAudio()
			defaultIndex = None
			defaultGetter = getattr(
				p,
				"get_default_input_device_info" if input else "get_default_output_device_info",
				None,
			)
			if defaultGetter is not None:
				try:
					defaultIndex = int(defaultGetter().get("index"))
				except (AttributeError, KeyError, TypeError, ValueError, OSError):
					pass
			numDevices = p.get_device_count()
			for i in range(numDevices):
				dev = p.get_device_info_by_index(i)
				deviceIndex = int(dev.get("index", i))
				deviceName = str(dev.get("name") or f"Device {deviceIndex}")
				if input:
					if int(dev.get("maxInputChannels", 0)) > 0:
						devices.append({"index": deviceIndex, "name": deviceName})
				else:
					if int(dev.get("maxOutputChannels", 0)) > 0:
						devices.append({"index": deviceIndex, "name": deviceName})
			if defaultIndex is not None:
				devices.sort(key=lambda device: device["index"] != defaultIndex)
		except Exception as error:
			log.error(f"Error listing devices: {error}")
		finally:
			if p is not None:
				p.terminate()
		return devices

	def _buildUi(self) -> None:
		"""Build the accessible controls for starting and managing a Live API session."""
		mainSizer = wx.BoxSizer(wx.VERTICAL)
		panel = wx.Panel(self)
		panelSizer = wx.BoxSizer(wx.VERTICAL)

		# Translators: Group label for connection status in the Talk With AI dialog.
		statusBox = wx.StaticBox(panel, label=_("Status"))
		statusSizer = wx.StaticBoxSizer(statusBox, wx.VERTICAL)
		# Translators: Initial status shown while Talk With AI enumerates audio devices.
		initialStatus = _("Loading audio devices...")
		self.statusLabel = wx.StaticText(
			panel,
			# Translators: Status label. {status} is replaced with the current Talk With AI status.
			label=_("Status: {status}").format(status=initialStatus),
		)
		statusSizer.Add(self.statusLabel, 0, wx.ALL | wx.EXPAND, 5)
		panelSizer.Add(statusSizer, 0, wx.ALL | wx.EXPAND, 5)

		# Translators: Group label for Talk With AI controls.
		controlsBox = wx.StaticBox(panel, label=_("Controls"))
		controlsSizer = wx.StaticBoxSizer(controlsBox, wx.VERTICAL)

		btnSizer = wx.BoxSizer(wx.HORIZONTAL)
		# Translators: Button to start the voice conversation.
		self.connectBtn = wx.Button(panel, label=_("Start Conversation"))
		self.connectBtn.Bind(wx.EVT_BUTTON, self.onConnect)
		# Translators: Button to stop the voice conversation.
		self.disconnectBtn = wx.Button(panel, label=_("Stop Conversation"))
		self.disconnectBtn.Bind(wx.EVT_BUTTON, self.onDisconnect)
		self.disconnectBtn.Disable()

		btnSizer.Add(self.connectBtn, 1, wx.RIGHT, 5)
		btnSizer.Add(self.disconnectBtn, 1, wx.LEFT, 5)
		controlsSizer.Add(btnSizer, 0, wx.EXPAND | wx.ALL, 5)

		# Translators: Toggle button label indicating microphone is ON.
		self.micBtn = wx.ToggleButton(panel, label=_("Microphone: ON"))
		self.micBtn.SetValue(True)
		self.micBtn.Bind(wx.EVT_TOGGLEBUTTON, self.onMicToggle)
		controlsSizer.Add(self.micBtn, 0, wx.ALL | wx.EXPAND, 5)

		self.deviceSizer = wx.BoxSizer(wx.VERTICAL)

		inputSizer = wx.BoxSizer(wx.HORIZONTAL)
		# Translators: Label for selecting the microphone input device.
		inputLabel = wx.StaticText(panel, label=_("Microphone input device:"))
		inputChoices = [device["name"] for device in self.inputDevices]
		self.inputChoice = wx.Choice(panel, choices=inputChoices)
		self.inputChoice.Disable()
		self.inputChoice.Bind(wx.EVT_CHOICE, self._onInputDeviceChange)
		if inputChoices:
			self.inputChoice.SetSelection(0)
		inputSizer.Add(inputLabel, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
		inputSizer.Add(self.inputChoice, 1, wx.EXPAND)
		self.deviceSizer.Add(inputSizer, 0, wx.ALL | wx.EXPAND, 5)

		outputSizer = wx.BoxSizer(wx.HORIZONTAL)
		# Translators: Label for selecting the audio output device.
		outputLabel = wx.StaticText(panel, label=_("&Speaker output device:"))
		outputChoices = [device["name"] for device in self.outputDevices]
		self.outputChoice = wx.Choice(panel, choices=outputChoices)
		self.outputChoice.Disable()
		self.outputChoice.Bind(wx.EVT_CHOICE, self._onOutputDeviceChange)
		if outputChoices:
			self.outputChoice.SetSelection(0)
		outputSizer.Add(outputLabel, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
		outputSizer.Add(self.outputChoice, 1, wx.EXPAND)
		self.deviceSizer.Add(outputSizer, 0, wx.ALL | wx.EXPAND, 5)

		controlsSizer.Add(self.deviceSizer, 0, wx.EXPAND)

		# Translators: Checkbox to enable grounding with Google Search in Talk With AI.
		self.googleSearchCb = wx.CheckBox(panel, label=_("Grounding with Google Search"))
		self.googleSearchCb.SetValue(False)
		controlsSizer.Add(self.googleSearchCb, 0, wx.ALL | wx.EXPAND, 5)

		# Translators: Opt-in toggle for sending periodic screen frames to the assistant.
		self.shareScreenCb = wx.CheckBox(panel, label=_("Share screen with AI"))
		self.shareScreenCb.SetValue(False)
		self.shareScreenCb.Bind(wx.EVT_CHECKBOX, self.onShareScreenToggle)
		controlsSizer.Add(self.shareScreenCb, 0, wx.ALL | wx.EXPAND, 5)

		thinkingSizer = wx.BoxSizer(wx.HORIZONTAL)
		# Translators: Label for choosing the reasoning depth in Talk With AI.
		self.thinkingLabel = wx.StaticText(panel, label=_("Thinking level:"))
		self.thinkingChoice = wx.Choice(panel, choices=[label for label, _value in self.thinkingChoices])
		self.thinkingChoice.SetSelection(0)
		thinkingSizer.Add(self.thinkingLabel, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
		thinkingSizer.Add(self.thinkingChoice, 1, wx.EXPAND)
		controlsSizer.Add(thinkingSizer, 0, wx.ALL | wx.EXPAND, 5)

		volSizer = wx.BoxSizer(wx.HORIZONTAL)
		# Translators: Label for the Talk With AI playback volume slider.
		volLabel = wx.StaticText(panel, label=_("Volume:"))
		self.volSlider = wx.Slider(panel, value=self.volume, minValue=0, maxValue=100, style=wx.SL_HORIZONTAL)
		self.volSlider.Bind(wx.EVT_SLIDER, self.onVolumeChange)
		volSizer.Add(volLabel, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
		volSizer.Add(self.volSlider, 1, wx.EXPAND)
		controlsSizer.Add(volSizer, 0, wx.ALL | wx.EXPAND, 5)

		panelSizer.Add(controlsSizer, 0, wx.ALL | wx.EXPAND, 5)

		infoLabel = wx.StaticText(
			panel,
			# Translators: Informational label. {voiceName} is replaced with the selected Gemini voice.
			label=_("Assistant voice: {voiceName}").format(voiceName=str(self.voiceName)),
		)
		panelSizer.Add(infoLabel, 0, wx.ALL | wx.ALIGN_CENTER_HORIZONTAL, 10)

		panel.SetSizer(panelSizer)
		mainSizer.Add(panel, 1, wx.EXPAND)
		self.SetSizer(mainSizer)
		self.CenterOnParent()

	def _announceStatus(self, text: str, force: bool = False) -> None:
		message = str(text or "").strip()
		if not message:
			return
		if not force and message == self.lastAnnouncedStatus:
			return
		self.lastAnnouncedStatus = message
		try:
			ui.message(message)
		except Exception as error:
			self._logCleanupFailure("status announcement", error)

	def updateStatus(self, text: str, announce: bool = False, forceAnnouncement: bool = False) -> None:
		try:
			if self:
				# Translators: Status label. {status} is replaced with the current Talk With AI status.
				self.statusLabel.SetLabel(_("Status: {status}").format(status=text))
		except RuntimeError:
			return
		if announce:
			self._announceStatus(text, force=forceAnnouncement)

	def reportError(self, msg: object) -> None:
		if self._isClosing:
			return
		try:
			if self:
				# Translators: Title of an error dialog in Talk With AI.
				wx.MessageBox(str(msg), _("Error"), wx.OK | wx.ICON_ERROR)
				# Translators: Status shown when Talk With AI enters an error state.
				self.updateStatus(_("Error"), announce=True, forceAnnouncement=True)
		except RuntimeError:
			return

	def _reportConnected(self, sessionId: int) -> None:
		if not self._isSessionCurrent(sessionId):
			return
		# Translators: Status shown when Talk With AI connects successfully.
		self.updateStatus(_("Connected"), announce=True)
		self._playSoundEffect(STREAM_START_SOUND_PATH)

	def _reportSessionError(self, sessionId: int, message: str, persistent: bool = False) -> None:
		if sessionId != self._sessionId or self._isClosing:
			return
		self._sessionHadError = True
		if persistent:
			self.compatibilityError = message
		self.reportError(message)

	def onMicToggle(self, evt: wx.Event) -> None:
		self.micOn = self.micBtn.GetValue()
		# Translators: Toggle button label indicating microphone state.
		label = _("Microphone: ON") if self.micOn else _("Microphone: OFF")
		self.micBtn.SetLabel(label)

	def onShareScreenToggle(self, evt: wx.Event) -> None:
		self.shareScreen = self.shareScreenCb.GetValue()
		if self.shareScreen and is_screen_curtain_active():
			self.shareScreen = False
			self.shareScreenCb.SetValue(False)
			self._stopScreenCapture()
			# Translators: Status announced when screen sharing is blocked by NVDA's Screen Curtain.
			self._announceStatus(
				_("Screen sharing is unavailable while Screen Curtain is enabled"),
				force=True,
			)
			return
		if self.shareScreen and self.sessionActive:
			self._startScreenCapture(self._sessionId)
		else:
			self._stopScreenCapture()
		self._announceStatus(
			_("Screen sharing enabled") if self.shareScreen else _("Screen sharing disabled"),
			force=True,
		)

	def _startScreenCapture(self, sessionId: int) -> None:
		self._stopScreenCapture()

		def onBlocked() -> None:
			wx.CallAfter(self._handleScreenCaptureBlocked, sessionId)

		def onFailed() -> None:
			wx.CallAfter(self._handleScreenCaptureFailed, sessionId)

		self._screenCaptureWorker = ScreenCaptureWorker(
			lambda frame: self._sendScreenFrame(sessionId, frame),
			on_blocked=onBlocked,
			on_failed=onFailed,
		)
		self._screenCaptureWorker.start()

	def _handleScreenCaptureBlocked(self, sessionId: int) -> None:
		if sessionId != self._sessionId or not self.shareScreen:
			return
		self.shareScreen = False
		self.shareScreenCb.SetValue(False)
		self._stopScreenCapture()
		# Translators: Status announced when Screen Curtain stops an active screen-sharing stream.
		self._announceStatus(_("Screen sharing stopped because Screen Curtain is enabled"), force=True)

	def _handleScreenCaptureFailed(self, sessionId: int) -> None:
		if sessionId != self._sessionId or not self.shareScreen:
			return
		self.shareScreen = False
		self.shareScreenCb.SetValue(False)
		self._stopScreenCapture()
		# Translators: Status announced after repeated screen capture failures stop screen sharing.
		self._announceStatus(_("Screen sharing stopped because screen capture failed"), force=True)

	def _stopScreenCapture(self) -> None:
		worker = self._screenCaptureWorker
		self._screenCaptureWorker = None
		if worker:
			worker.stop()
		self._screenFramePending = False

	def _sendScreenFrame(self, sessionId: int, frame: str) -> None:
		if not self._isSessionCurrent(sessionId) or not self.shareScreen:
			return
		loop = self.loop
		session = self.session
		if loop and session and loop.is_running() and not self._screenFramePending:
			try:
				self._screenFramePending = True
				future = asyncio.run_coroutine_threadsafe(session.send_realtime_input(video=frame), loop)
				future.add_done_callback(self._handleScreenSendResult)
			except RuntimeError:
				self._screenFramePending = False
				return

	def _handleScreenSendResult(self, future: Any) -> None:
		self._screenFramePending = False
		try:
			future.result()
		except Exception as error:
			if not self._isClosing:
				log.debug(f"TalkWithAI screen frame send failed: {error}", exc_info=True)

	def onVolumeChange(self, evt: wx.Event) -> None:
		self.volume = self.volSlider.GetValue()

	def _getSelectedThinkingLevel(self) -> str:
		selection = self.thinkingChoice.GetSelection()
		if selection == wx.NOT_FOUND:
			return "minimal"
		return self.thinkingChoices[selection][1]

	def _clearSessionHistory(self) -> None:
		with self.historyLock:
			self.sessionHistory = []

	def _buildMissingDependencyMessage(self, baseMessage: str, errorDetail: str | None) -> str:
		if not errorDetail:
			return baseMessage
		# Translators: Dependency error detail. {baseMessage} is the main error and {errorDetail} is the import exception.
		return _("{baseMessage}\n\nImport detail: {errorDetail}").format(
			baseMessage=baseMessage,
			errorDetail=errorDetail,
		)

	def _mergeHistoryText(self, existing: str, incoming: str) -> str:
		if not existing:
			return incoming
		if incoming == existing or existing.endswith(incoming):
			return existing
		if incoming.startswith(existing):
			return incoming
		if existing.startswith(incoming):
			return existing
		return f"{existing} {incoming}"

	def _rememberConversationTurn(self, role: str, text: str) -> None:
		cleaned = str(text or "").strip()
		if not cleaned:
			return
		with self.historyLock:
			if self.sessionHistory and self.sessionHistory[-1]["role"] == role:
				self.sessionHistory[-1]["text"] = self._mergeHistoryText(
					self.sessionHistory[-1]["text"],
					cleaned,
				)
			else:
				self.sessionHistory.append({"role": role, "text": cleaned})
			self._trimSessionHistory()

	def _trimSessionHistory(self) -> None:
		if len(self.sessionHistory) > HISTORY_MAX_TURNS:
			self.sessionHistory = self.sessionHistory[-HISTORY_MAX_TURNS:]
		totalChars = sum(len(turn["text"]) for turn in self.sessionHistory)
		while self.sessionHistory and totalChars > HISTORY_MAX_CHARS:
			totalChars -= len(self.sessionHistory.pop(0)["text"])

	def _buildReconnectHistoryTurns(self) -> list[Any]:
		with self.historyLock:
			return [
				{"role": turn["role"], "parts": [{"text": turn["text"]}]}
				for turn in self.sessionHistory
				if turn["text"].strip()
			]

	def _buildSystemInstruction(self) -> str:
		baseRules = (
			"You are a voice assistant for blind and low-vision users. "
			"Never fabricate facts. If uncertain, explicitly say you are not sure. "
			"When screen frames are provided, describe only what is clearly visible and say when text or details are unclear."
		)
		userInstruction = self.systemInstruction.strip() if self.systemInstruction else ""
		parts = [baseRules]
		if userInstruction:
			parts.append(f"User preference:\n{userInstruction}")
		return "\n\n".join(parts)

	def _buildReconnectDelay(self, attempt: int) -> float:
		baseDelay = min(BACKOFF_MAX_SECONDS, BACKOFF_BASE_SECONDS * (2 ** max(0, attempt - 1)))
		return baseDelay + random.uniform(0.0, BACKOFF_JITTER_SECONDS)

	def _getRuntimeCompatibilityError(self) -> str | None:
		return None

	def onConnect(self, evt: wx.Event) -> None:
		if self.compatibilityError:
			self.reportError(self.compatibilityError)
			return
		if self.loopThread is not None and self.loopThread.is_alive():
			return

		self.disconnectBtn.Enable()
		self.disconnectBtn.SetFocus()
		self.connectBtn.Disable()

		self.useGoogleSearch = self.googleSearchCb.GetValue()
		self.selectedThinkingLevel = self._getSelectedThinkingLevel()

		self.googleSearchCb.Hide()
		self.thinkingLabel.Hide()
		self.thinkingChoice.Hide()

		inSel = self.inputChoice.GetSelection()
		if inSel != wx.NOT_FOUND and self.inputDevices:
			self.selectedInputIdx = self.inputDevices[inSel]["index"]

		outSel = self.outputChoice.GetSelection()
		if outSel != wx.NOT_FOUND and self.outputDevices:
			self.selectedOutputIdx = self.outputDevices[outSel]["index"]

		for child in self.deviceSizer.GetChildren():
			window = child.GetWindow()
			if window:
				window.Hide()
			sizer = child.GetSizer()
			if sizer:
				for nestedChild in sizer.GetChildren():
					nestedWindow = nestedChild.GetWindow()
					if nestedWindow:
						nestedWindow.Hide()

		self.Layout()
		# Translators: Status shown while Talk With AI is connecting.
		self.updateStatus(_("Connecting..."), announce=True)

		self._sessionId += 1
		sessionId = self._sessionId
		self._sessionHadError = False
		self._restoreConnectFocus = False
		self.sessionActive = True
		self.loopThread = threading.Thread(target=self._startAsyncLoop, args=(sessionId,), daemon=True)
		self.loopThread.start()

	def onDisconnect(self, evt: wx.Event) -> None:
		self._stopScreenCapture()
		sessionId = self._sessionId
		self.sessionActive = False
		self._restoreConnectFocus = self.disconnectBtn.HasFocus()
		if self._restoreConnectFocus:
			self.micBtn.SetFocus()
		self.disconnectBtn.Disable()
		# Translators: Status shown while Talk With AI is disconnecting.
		self.updateStatus(_("Disconnecting..."), announce=True)
		loop = self.loop
		if loop and loop.is_running():
			try:
				asyncio.run_coroutine_threadsafe(self.cleanupAsync(sessionId), loop)
			except RuntimeError as error:
				self._logCleanupFailure("disconnect cleanup scheduling", error)
		elif self.loopThread is None or not self.loopThread.is_alive():
			wx.CallAfter(self._finishSessionUi, sessionId)

	def _playSoundEffect(self, path: str) -> None:
		def _bgPlay() -> None:
			try:
				if os.path.exists(path):
					winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)
			except Exception as error:
				self._logCleanupFailure("sound effect playback", error)

		threading.Thread(target=_bgPlay, daemon=True).start()

	def onCharHook(self, evt: wx.Event) -> None:
		if evt.GetKeyCode() == wx.WXK_ESCAPE:
			self.Close()
		else:
			evt.Skip()

	def onClose(self, evt: wx.Event) -> None:
		if self._isClosing:
			return
		self._isClosing = True
		self._stopScreenCapture()
		try:
			self._savePersistentSettings()
		except Exception as error:
			# Saving preferences must never prevent modal teardown.
			self._logCleanupFailure("Talk With AI settings save", error)
		self._sessionId += 1
		self.sessionActive = False
		self.isPlaying = False
		self._clearSessionHistory()
		self._flushAudioQueue()
		self.audioQueue.put(b"")

		if self.loop and self.loop.is_running():
			try:
				asyncio.run_coroutine_threadsafe(self._shutdownLoop(), self.loop)
			except Exception as error:
				self._logCleanupFailure("loop shutdown scheduling", error)
				if self.session is not None:
					try:
						self.session.abort()
					except Exception as abortError:
						self._logCleanupFailure("Live session abort", abortError)
				self._stopAudioPlayer()
				self._closeAudioResources()
		else:
			self._stopAudioPlayer()
			self._closeAudioResources()

		if self.IsModal():
			self.EndModal(wx.ID_CANCEL)
		self.Destroy()

	async def _shutdownLoop(self) -> None:
		await self.cleanupAsync()

	def _startAsyncLoop(self, sessionId: int) -> None:
		loop = asyncio.new_event_loop()
		sessionTask = None
		try:
			asyncio.set_event_loop(loop)
			if sessionId != self._sessionId or not self.sessionActive or self._isClosing:
				return
			self.loop = loop
			sessionTask = loop.create_task(self.runSession(sessionId))
			self._sessionTask = sessionTask
			loop.run_until_complete(sessionTask)
		except asyncio.CancelledError:
			pass
		except RuntimeError as error:
			self._logCleanupFailure("async loop shutdown", error)
		except Exception as error:
			log.error(f"Async Loop Error: {error}", exc_info=True)
		finally:
			try:
				pending = asyncio.all_tasks(loop)
				for task in pending:
					task.cancel()
				if pending and not loop.is_closed():
					loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
				if not loop.is_closed():
					loop.close()
			except Exception as error:
				self._logCleanupFailure("async loop finalization", error)
			if self._sessionTask is sessionTask:
				self._sessionTask = None
			if self.loop is loop:
				self.loop = None
			if self.loopThread is threading.current_thread():
				self.loopThread = None
			wx.CallAfter(self._finishSessionUi, sessionId)

	def _flushAudioQueue(self) -> None:
		self._playbackGeneration += 1
		while not self.audioQueue.empty():
			try:
				self.audioQueue.get_nowait()
			except queue.Empty:
				break

	def _interruptPlayback(self) -> None:
		self._flushAudioQueue()
		stream = self.outputStream
		if stream is None:
			return
		lock = getattr(self, "outputLock", None)
		try:
			if lock is not None:
				with lock:
					if stream.is_active():
						stream.stop_stream()
					stream.start_stream()
			elif stream.is_active():
				stream.stop_stream()
				stream.start_stream()
		except Exception as error:
			self._logCleanupFailure("audio interruption", error)

	async def cleanupAsync(self, sessionId: int | None = None) -> None:
		"""Stop the active Live API session and release audio resources."""
		if sessionId is not None and sessionId != self._sessionId:
			return
		self.sessionActive = False
		self._stopScreenCapture()
		self.isPlaying = False
		session = self.session
		self.session = None
		if session is not None:
			try:
				await session.close()
			except Exception as error:
				self._logCleanupFailure("Live session close", error)

		currentTask = asyncio.current_task()
		sessionTask = self._sessionTask
		if sessionTask is not None and sessionTask is not currentTask:
			sessionTask.cancel()
			await asyncio.gather(sessionTask, return_exceptions=True)

		self._flushAudioQueue()
		self._stopAudioPlayer()
		self._closeAudioResources()

	def _stopAudioPlayer(self) -> None:
		self.isPlaying = False
		playerThread = self._audioPlayerThread
		if playerThread is not None and playerThread is not threading.current_thread():
			playerThread.join(timeout=1.5)
		self._audioPlayerThread = None

	def _closeAudioResources(self) -> None:
		micReadFinished = getattr(self, "_micReadFinished", None)
		if micReadFinished is not None:
			micReadFinished.wait(timeout=1.0)
		for attributeName in ("inputStream", "outputStream"):
			stream = getattr(self, attributeName)
			if stream is None:
				continue
			try:
				if stream.is_active():
					stream.stop_stream()
				stream.close()
			except Exception as error:
				self._logCleanupFailure(f"{attributeName} close", error)
			setattr(self, attributeName, None)
		if self.audioInterface is not None:
			try:
				self.audioInterface.terminate()
			except Exception as error:
				self._logCleanupFailure("audio interface termination", error)
			self.audioInterface = None

	def _failSessionFromAudioWorker(self, sessionId: int, error: BaseException) -> None:
		if not self._isSessionCurrent(sessionId):
			return
		self._sessionHadError = True
		self.sessionActive = False
		# Translators: Error shown when Talk With AI cannot play received audio.
		message = _("Audio playback failed: {error}").format(error=error)
		wx.CallAfter(self._reportSessionError, sessionId, message)
		loop = self.loop
		if loop and loop.is_running():
			try:
				asyncio.run_coroutine_threadsafe(self.cleanupAsync(sessionId), loop)
			except RuntimeError as schedulingError:
				self._logCleanupFailure("audio failure cleanup scheduling", schedulingError)

	def _audioPlayerWorker(self, sessionId: int) -> None:
		buffer = []
		buffering = True
		playbackGeneration = self._playbackGeneration
		self.bufferThreshold = BUFFER_THRESHOLD

		try:
			while self._isSessionCurrent(sessionId) and self.isPlaying:
				try:
					if playbackGeneration != self._playbackGeneration:
						buffer.clear()
						buffering = True
						playbackGeneration = self._playbackGeneration
					data = self.audioQueue.get(timeout=0.1)
					if playbackGeneration != self._playbackGeneration:
						continue
					if self.volume != 100:
						count = len(data) // 2
						shorts = struct.unpack(f"{count}h", data)
						factor = self.volume / 100.0
						scaledShorts = []
						for sample in shorts:
							value = int(sample * factor)
							value = min(value, 32767)
							value = max(value, -32768)
							scaledShorts.append(value)
						data = struct.pack(f"{count}h", *scaledShorts)

					if buffering:
						buffer.append(data)
						if len(buffer) >= self.bufferThreshold:
							buffering = False
							for chunk in buffer:
								if playbackGeneration != self._playbackGeneration:
									break
								self._writeAudioChunk(chunk)
							buffer = []
					else:
						if playbackGeneration == self._playbackGeneration:
							self._writeAudioChunk(data)
						queueDepth = self.audioQueue.qsize()
						now = time.monotonic()
						if (
							queueDepth > self.bufferThreshold + 3
							and self.bufferThreshold > MIN_BUFFER_THRESHOLD
						):
							if now - self.lastBufferAdjustAt > 1.0:
								self.bufferThreshold -= 1
								self.lastBufferAdjustAt = now
						elif queueDepth <= 1 and self.bufferThreshold < MAX_BUFFER_THRESHOLD:
							if now - self.lastBufferAdjustAt > 1.0:
								self.bufferThreshold += 1
								self.lastBufferAdjustAt = now
				except queue.Empty:
					if not buffering and self._isSessionCurrent(sessionId):
						buffering = True
						now = time.monotonic()
						if (
							self.bufferThreshold < MAX_BUFFER_THRESHOLD
							and now - self.lastBufferAdjustAt > 0.8
						):
							self.bufferThreshold += 1
							self.lastBufferAdjustAt = now
					continue
		except Exception as error:
			log.error(f"Audio Player Error: {error}", exc_info=True)
			self._failSessionFromAudioWorker(sessionId, error)
		finally:
			if self._audioPlayerThread is threading.current_thread():
				self.isPlaying = False

	def _writeAudioChunk(self, data: bytes) -> None:
		lock = getattr(self, "outputLock", None)
		if lock is None:
			self._writeAudioChunkUnlocked(data)
			return
		with lock:
			self._writeAudioChunkUnlocked(data)

	def _writeAudioChunkUnlocked(self, data: bytes) -> None:
		stream = self.outputStream
		if stream is None or not stream.is_active():
			raise RuntimeError(_("Audio output device is no longer available."))
		stream.write(data)

	def _isPermanentSessionError(self, error: BaseException) -> bool:
		for attributeName in ("status_code", "status", "code"):
			status = getattr(error, attributeName, None)
			try:
				if int(status) in {400, 401, 403, 404}:
					return True
			except (TypeError, ValueError):
				continue
		message = str(error).lower()
		return any(
			marker in message
			for marker in (
				"invalid api key",
				"api key not valid",
				"unauthorized",
				"permission denied",
				"forbidden",
				"not found",
				"invalid argument",
				"unsupported model",
				"socks proxies are not supported",
			)
		)

	def _isSessionCurrent(self, sessionId: int) -> bool:
		return sessionId == self._sessionId and self.sessionActive and not self._isClosing

	async def sendAudioLoop(self, session: Any, sessionId: int) -> None:
		"""Read microphone audio and stream it to the active Live API session."""
		loop = asyncio.get_running_loop()
		while self._isSessionCurrent(sessionId):
			if self.micOn and self.inputStream and self.inputStream.is_active():
				try:
					self._micReadFinished.clear()
					try:
						data = await loop.run_in_executor(
							None,
							lambda: self.inputStream.read(CHUNK, exception_on_overflow=False),
						)
					finally:
						self._micReadFinished.set()
					await session.send_realtime_input(audio=data)
				except asyncio.CancelledError:
					raise
				except Exception as error:
					log.error(f"Mic/Send Error: {error}")
					raise
			else:
				await asyncio.sleep(0.1)

	def _queueAudioData(self, data: bytes) -> None:
		if data:
			self.audioQueue.put(data)

	def _handleServerContent(self, serverContent: Any) -> bool:
		if serverContent.get("interrupted"):
			self._interruptPlayback()
			return False
		for key, role in (("inputTranscription", "user"), ("outputTranscription", "model")):
			transcription = serverContent.get(key)
			if isinstance(transcription, dict) and transcription.get("text"):
				self._rememberConversationTurn(role, str(transcription["text"]))
		modelTurn = serverContent.get("modelTurn") or {}
		queuedAudio = False
		for part in modelTurn.get("parts", []) if isinstance(modelTurn, dict) else []:
			inline = part.get("inlineData") if isinstance(part, dict) else None
			if isinstance(inline, dict) and inline.get("data"):
				try:
					self._queueAudioData(base64.b64decode(inline["data"]))
					queuedAudio = True
				except (TypeError, ValueError):
					log.debug("TalkWithAI: Ignoring invalid base64 audio payload.")
			if isinstance(part, dict) and part.get("text"):
				self._rememberConversationTurn("model", str(part["text"]))
		return queuedAudio

	async def receiveLoop(self, session: Any, sessionId: int) -> None:
		"""Receive text/audio events from the Live API and queue audio playback."""
		try:
			async for response in session.receive():
				if not self._isSessionCurrent(sessionId):
					break
				serverContent = response.get("serverContent")
				if isinstance(serverContent, dict):
					self._handleServerContent(serverContent)
				if response.get("toolCall") is not None:
					log.debug("TalkWithAI: Ignoring tool_call event from Live API.")
		except asyncio.CancelledError:
			raise
		except OSError as error:
			# Closing the session from another thread can make a blocked recv see WSAENOTSOCK.
			if not self._isSessionCurrent(sessionId) and (
				getattr(error, "winerror", None) == 10038
				or getattr(error, "errno", None) in {9, 10038}
				or "not a socket" in str(error).lower()
			):
				log.debug("TalkWithAI: Receive loop ended after the Live socket was closed.")
				return
			log.error(f"TalkWithAI Receive Loop Error: {error}")
			raise
		except Exception as error:
			log.error(f"TalkWithAI Receive Loop Error: {error}")
			raise
		finally:
			log.debug("TalkWithAI: Receive loop ended")

	async def runSession(self, sessionId: int) -> None:
		"""Open audio devices and keep the Live API session connected with retry backoff."""
		try:
			if not self._isSessionCurrent(sessionId):
				return
			self.audioInterface = pyaudio.PyAudio()

			self.outputStream = self.audioInterface.open(
				format=FORMAT,
				channels=CHANNELS,
				rate=OUTPUT_RATE,
				output=True,
				frames_per_buffer=CHUNK,
				output_device_index=self.selectedOutputIdx,
			)

			self.inputStream = self.audioInterface.open(
				format=FORMAT,
				channels=CHANNELS,
				rate=INPUT_RATE,
				input=True,
				frames_per_buffer=CHUNK,
				input_device_index=self.selectedInputIdx,
			)

			firstConnect = True
			retryAttempt = 0

			while self._isSessionCurrent(sessionId):
				try:
					historyTurns = self._buildReconnectHistoryTurns()
					log.debug("TalkWithAI: Connecting to Gemini Live...")
					session = DirectLiveSession(
						self.apiKey,
						MODEL_NAME,
						self.voiceName,
						self._buildSystemInstruction(),
						thinking_level=self.selectedThinkingLevel,
						use_google_search=self.useGoogleSearch,
					)
					self.session = session
					sendTask = None
					receiveTask = None
					results: list[Any] = []
					try:
						await session.connect(historyTurns)
						if not self._isSessionCurrent(sessionId):
							return
						retryAttempt = 0
						if firstConnect:
							wx.CallAfter(self._reportConnected, sessionId)
							firstConnect = False
						if self.shareScreen:
							self._startScreenCapture(sessionId)
						sendTask = asyncio.create_task(self.sendAudioLoop(session, sessionId))
						receiveTask = asyncio.create_task(self.receiveLoop(session, sessionId))
						if not self.isPlaying:
							playWorker = threading.Thread(
								target=self._audioPlayerWorker,
								args=(sessionId,),
								daemon=True,
							)
							self.isPlaying = True
							self._audioPlayerThread = playWorker
							playWorker.start()
						await asyncio.wait([sendTask, receiveTask], return_when=asyncio.FIRST_COMPLETED)
					finally:
						self._stopScreenCapture()
						tasks = [task for task in (sendTask, receiveTask) if task is not None]
						for task in tasks:
							if not task.done():
								task.cancel()
						if tasks:
							results = await asyncio.gather(*tasks, return_exceptions=True)
						await session.close()
						if self.session is session:
							self.session = None
					for result in results:
						if isinstance(result, Exception):
							raise result
					if self._isSessionCurrent(sessionId):
						raise RuntimeError("Live session ended unexpectedly.")

				except asyncio.CancelledError:
					raise
				except Exception as error:
					if not self._isSessionCurrent(sessionId):
						break
					if self._isPermanentSessionError(error):
						log.error(f"TalkWithAI Permanent Session Error: {error}", exc_info=True)
						self._sessionHadError = True
						self.sessionActive = False
						wx.CallAfter(self._reportSessionError, sessionId, str(error))
						break
					log.error(f"TalkWithAI Session/Connection Error: {error}", exc_info=True)
					retryAttempt += 1
					delay = self._buildReconnectDelay(retryAttempt)
					now = time.monotonic()
					if now - self.lastStatusAt > 1.0:
						wx.CallAfter(
							self.updateStatus,
							(
								# Translators: Status shown when the first Talk With AI connection attempt failed.
								_("Connection failed. Retrying in {seconds:.1f}s")
								if firstConnect
								# Translators: Status shown while Talk With AI waits before reconnecting.
								else _("Connection lost. Retrying in {seconds:.1f}s")
							).format(seconds=delay),
							True,
						)
						self.lastStatusAt = now
					await asyncio.sleep(delay)

				if self._isSessionCurrent(sessionId):
					log.debug("TalkWithAI: Reconnecting...")

		except asyncio.CancelledError:
			pass
		except Exception as error:
			errorDetail = traceback.format_exc()
			log.error(f"TalkWithAI Fatal Error: {errorDetail}")
			self._sessionHadError = True
			# Translators: Error shown when Talk With AI cannot initialize its audio or session runtime.
			message = _("Talk With AI could not start: {error}").format(
				error=str(error) or _("Unknown error"),
			)
			wx.CallAfter(self._reportSessionError, sessionId, message)
			self.sessionActive = False
		finally:
			self._stopScreenCapture()
			self._stopAudioPlayer()
			self._playSoundEffect(STREAM_END_SOUND_PATH)
			self._closeAudioResources()
			self.session = None

	def _finishSessionUi(self, sessionId: int) -> None:
		if sessionId == self._sessionId and not self._isClosing:
			self.resetUi()

	def resetUi(self) -> None:
		"""Restore controls after a Live API session ends."""
		if self._isClosing:
			return
		if self:
			try:
				currentFocus = wx.Window.FindFocus()
				shouldRestoreFocus = self._restoreConnectFocus or currentFocus in (None, self.disconnectBtn)
				canConnect = self._devicesLoaded and not self.compatibilityError and PYAUDIO_AVAILABLE
				self.connectBtn.Enable(canConnect)
				self.disconnectBtn.Disable()
				self.googleSearchCb.Show()
				self.thinkingLabel.Show()
				self.thinkingChoice.Show()

				for child in self.deviceSizer.GetChildren():
					window = child.GetWindow()
					if window:
						window.Show()
					sizer = child.GetSizer()
					if sizer:
						for nestedChild in sizer.GetChildren():
							nestedWindow = nestedChild.GetWindow()
							if nestedWindow:
								nestedWindow.Show()

				self.Layout()
				if not self._sessionHadError:
					# Translators: Status shown when Talk With AI is ready for a new session.
					self.updateStatus(_("Ready"), announce=True)
				if self.connectBtn.IsEnabled() and shouldRestoreFocus:
					self.connectBtn.SetFocus()
				self._restoreConnectFocus = False
			except RuntimeError:
				pass
