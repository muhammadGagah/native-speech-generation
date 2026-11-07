"""Keyboard-accessible voice catalog for the generation dialog only."""

from __future__ import annotations

import io
import os
import tempfile
import threading
import wave
import winsound

import addonHandler
import speech
import ui
import wx
from gui.guiHelper import BoxSizerHelper

from ..core.api_client import DirectApiError, generate_tts
from ..core.tts_requests import SpeechInputError
from ..core.voice_design import canRemix, createDesignedVoice, createRemixedVoice
from ..core.voice_library import (
	MAX_SAMPLE_BYTES,
	Voice,
	VoiceLibraryStore,
	builtInVoices,
	fetchVoices,
	fetchVoiceSample,
	filterVoices,
)
from ..core.voice_replication import RecordingError, createReplicatedVoice
from .new_voice_dialog import NewVoiceDialog
from .voice_design_dialog import VoiceDesignDialog
from .voice_remix_dialog import VoiceRemixDialog
from .voice_replication_dialog import VoiceReplicationDialog

addonHandler.initTranslation()


class VoiceLibraryDialog(wx.Dialog):
	# Class defaults keep partially constructed instances (and tests) consistent.
	_childDialog: wx.Dialog | None = None
	_closeRequested = False

	def __init__(self, parent: wx.Window, apiKey: str, model: str, store: VoiceLibraryStore, selectedId: str):
		# Translators: Title of the Gemini TTS voice browser.
		super().__init__(
			parent,
			title=_("Voice library"),
			style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
		)
		self.apiKey = apiKey
		self.model = model
		self.store = store
		self.selectedId = selectedId
		self.selectedVoice: Voice | None = None
		self._closed = False
		self._loadId = 0
		self._isLoading = False
		self._isCreating = False
		self._previewId = 0
		self._previewVoiceName = ""
		self._previewState = "idle"
		self._playbackTimer = None
		self._previewPath: str | None = None
		self._generatedSample: tuple[tuple[str, str, str], bytes] | None = None
		self._searchTimer = None
		self.voices, isFresh = store.readCatalog()
		if not self.voices and not isFresh:
			self.voices = builtInVoices()
		self.visibleVoices: list[Voice] = []
		self._types = ("", "prebuilt", "prompted", "replicated")
		self._languages: list[str | None] = [None, ""]
		self._attributeChoices: dict[str, wx.Choice] = {}
		self._attributeValues: dict[str, list[str | None]] = {}

		sizer = wx.BoxSizer(wx.VERTICAL)
		helper = BoxSizerHelper(self, sizer=sizer)
		# Translators: Keyboard shortcut and API usage notice for voice samples.
		guidance = wx.StaticText(
			self,
			label=_(
				"Select a voice and press Space or Enter to play its sample. "
				"Use Generate preview to create audio from the preview text using API quota.",
			),
		)
		guidance.Wrap(580)
		sizer.Add(guidance, flag=wx.ALL, border=6)
		# Translators: Search field in the voice library; searches names, language, accent, and descriptions.
		self.searchCtrl = helper.addLabeledControl(_("&Search voices:"), wx.TextCtrl)
		self.searchCtrl.Bind(wx.EVT_TEXT, self.onSearch)
		filtersSizer = wx.BoxSizer(wx.HORIZONTAL)
		typeSizer = wx.BoxSizer(wx.VERTICAL)
		typeHelper = BoxSizerHelper(self, sizer=typeSizer)
		# Translators: Filter for voice origin in the library.
		self.typeChoice = typeHelper.addLabeledControl(
			_("Voice &type:"),
			wx.Choice,
			choices=[
				# Translators: Voice library type filters, in order: all, built-in catalog, designed, replicated.
				_("All voices"),
				_("Prebuilt"),
				_("Designed"),
				_("Replicated"),
			],
		)
		self.typeChoice.SetSelection(0)
		self.typeChoice.Bind(wx.EVT_CHOICE, self.onFilter)
		languageSizer = wx.BoxSizer(wx.VERTICAL)
		languageHelper = BoxSizerHelper(self, sizer=languageSizer)
		# Translators: Filter by the language tag in the voice catalog, for example id-ID or en-US.
		self.languageChoice = languageHelper.addLabeledControl(_("&Language:"), wx.Choice)
		self.languageChoice.Bind(wx.EVT_CHOICE, self.onFilter)
		self._updateLanguages()
		filtersSizer.Add(typeSizer, proportion=1, flag=wx.EXPAND | wx.RIGHT, border=12)
		filtersSizer.Add(languageSizer, proportion=1, flag=wx.EXPAND)
		sizer.Add(filtersSizer, flag=wx.EXPAND | wx.TOP | wx.BOTTOM, border=6)
		# Translators: Catalog filters. Persona is the closest public API equivalent to AI Studio's Style.
		attributeLabels = (
			("gender", _("G&ender:")),
			("pitch", _("&Pitch:")),
			("persona", _("Perso&na:")),
			("context", _("Use c&ase:")),
		)
		for offset in (0, 2):
			row = wx.BoxSizer(wx.HORIZONTAL)
			for field, label in attributeLabels[offset : offset + 2]:
				column = wx.BoxSizer(wx.VERTICAL)
				choice = BoxSizerHelper(self, sizer=column).addLabeledControl(label, wx.Choice)
				choice.Bind(wx.EVT_CHOICE, self.onFilter)
				self._attributeChoices[field] = choice
				self._attributeValues[field] = [None, ""]
				row.Add(column, proportion=1, flag=wx.EXPAND | wx.RIGHT, border=12)
			sizer.Add(row, flag=wx.EXPAND | wx.TOP | wx.BOTTOM, border=6)
		self._updateAttributes()
		# Translators: Native list of voices matching the search and filter.
		self.results = helper.addLabeledControl(_("Available &voices:"), wx.ListBox, size=(580, 150))
		self.results.Bind(wx.EVT_LISTBOX, self.onSelection)
		# Translators: Read-only metadata for the currently selected voice.
		self.detailsCtrl = helper.addLabeledControl(
			_("Voice &details:"),
			wx.TextCtrl,
			style=wx.TE_MULTILINE | wx.TE_READONLY,
			size=(580, 100),
		)
		# Translators: Text synthesized only when the user activates Generate preview.
		self.previewTextCtrl = helper.addLabeledControl(_("Preview te&xt:"), wx.TextCtrl)
		self.previewTextCtrl.SetMaxLength(300)
		# Translators: Default short utterance for generated previews. Users can edit it in any language.
		self.previewTextCtrl.ChangeValue(_("Hello! This is a short preview of my voice."))
		self.previewTextCtrl.Bind(wx.EVT_TEXT, self.onPreviewTextChanged)
		# Translators: Read-only status of voice library loading, filtering, and preview.
		self.statusCtrl = helper.addLabeledControl(_("Status:"), wx.TextCtrl, style=wx.TE_READONLY)
		buttons = wx.BoxSizer(wx.HORIZONTAL)
		# Translators: Reload the complete catalog from Google.
		self.refreshBtn = wx.Button(self, label=_("&Refresh"))
		# Translators: Choose Voice Design or Voice Replication.
		self.newVoiceBtn = wx.Button(self, label=_("Ne&w voice"))
		# Translators: Explicitly generate a preview of the selected voice using API quota.
		self.previewBtn = wx.Button(self, label=_("&Generate preview"))
		# Translators: Creates a new voice by modifying the selected voice; the original is unchanged.
		self.remixBtn = wx.Button(self, label=_("Re&mix selected voice"))
		# Translators: Stop playing or waiting for a downloaded sample.
		self.stopBtn = wx.Button(self, label=_("St&op sample"))
		self.stopBtn.Disable()
		# Translators: Apply the selected voice to the speaker whose library was opened.
		self.useBtn = wx.Button(self, label=_("&Use selected voice"))
		self.cancelBtn = wx.Button(self, wx.ID_CANCEL)
		for button in (
			self.refreshBtn,
			self.newVoiceBtn,
			self.remixBtn,
			self.previewBtn,
			self.stopBtn,
			self.useBtn,
			self.cancelBtn,
		):
			buttons.Add(button, flag=wx.ALL, border=4)
		sizer.Add(buttons, flag=wx.ALL, border=6)
		self.refreshBtn.Bind(wx.EVT_BUTTON, self.onRefresh)
		self.newVoiceBtn.Bind(wx.EVT_BUTTON, self.onNewVoice)
		self.remixBtn.Bind(wx.EVT_BUTTON, self.onRemixVoice)
		self.previewBtn.Bind(wx.EVT_BUTTON, self.onGeneratePreview)
		self.stopBtn.Bind(wx.EVT_BUTTON, self.onStop)
		self.useBtn.Bind(wx.EVT_BUTTON, self.onUse)
		self.cancelBtn.Bind(wx.EVT_BUTTON, self.onCancel)
		self.Bind(wx.EVT_CLOSE, self.onCancel)
		self.Bind(wx.EVT_CHAR_HOOK, self.onCharHook)
		self.SetSizerAndFit(sizer)
		self.SetMinSize(self.GetSize())
		self.CenterOnParent()
		self._applyFilter(announce=False)
		if not isFresh:
			wx.CallAfter(self.onRefresh, None)
		self.searchCtrl.SetFocus()

	def _setStatus(self, message: str, *, announce: bool = True) -> None:
		if not self._closed:
			self.statusCtrl.ChangeValue(message)
			if announce:
				ui.message(message)

	def _selected(self) -> Voice | None:
		index = self.results.GetSelection()
		return self.visibleVoices[index] if 0 <= index < len(self.visibleVoices) else None

	def onSearch(self, evt: wx.Event) -> None:
		self._stopPreview()
		if self._searchTimer is not None:
			self._searchTimer.Stop()
		self._searchTimer = wx.CallLater(300, self._applyFilter)

	def onFilter(self, evt: wx.Event) -> None:
		self._applyFilter()

	def onPreviewTextChanged(self, evt: wx.Event) -> None:
		wasPreviewing = self._previewState != "idle"
		self._stopPreview()
		if wasPreviewing:
			# Translators: Editing the preview text stops playback or discards a pending response.
			self._setStatus(_("Sample stopped."), announce=False)

	def _updateLanguages(self) -> None:
		index = self.languageChoice.GetSelection()
		selected = self._languages[index] if 0 <= index < len(self._languages) else None
		codes = {
			voice.language.strip().casefold(): voice.language.strip()
			for voice in self.voices
			if voice.language.strip()
		}
		# Keep a removed language selected so refreshing never silently broadens the filter.
		if selected:
			codes.setdefault(selected, selected)
		self._languages = [None, "", *sorted(codes)]
		self.languageChoice.Set(
			[
				# Translators: Show all catalog voices regardless of language metadata.
				_("All languages"),
				# Translators: Voices whose catalog entry has no language tag.
				_("Unspecified"),
				*(codes[code] for code in sorted(codes)),
			],
		)
		self.languageChoice.SetSelection(self._languages.index(selected))

	def _updateAttributes(self) -> None:
		for field, choice in self._attributeChoices.items():
			index = choice.GetSelection()
			previous = self._attributeValues[field]
			selected = previous[index] if 0 <= index < len(previous) else None
			values = {
				getattr(voice, field).strip().casefold(): getattr(voice, field).strip()
				for voice in self.voices
				if getattr(voice, field).strip()
			}
			# Preserve active filters even if a refreshed catalog no longer has that value.
			if selected:
				values.setdefault(selected, selected)
			self._attributeValues[field] = [None, "", *sorted(values)]
			# Translators: Catalog filter choices: no restriction, or missing metadata.
			choice.Set([_("All"), _("Unspecified"), *(values[value] for value in sorted(values))])
			choice.SetSelection(self._attributeValues[field].index(selected))

	def _applyFilter(self, *, announce: bool = True) -> None:
		if self._closed:
			return
		if self._searchTimer is not None:
			self._searchTimer.Stop()
			self._searchTimer = None
		self._stopPreview()
		self.visibleVoices = filterVoices(
			self.voices,
			self.searchCtrl.GetValue(),
			self._types[self.typeChoice.GetSelection()],
			self._languages[self.languageChoice.GetSelection()],
			**{
				field: self._attributeValues[field][choice.GetSelection()]
				for field, choice in self._attributeChoices.items()
			},
		)
		self.results.Set([voice.displayName for voice in self.visibleVoices])
		ids = [voice.id for voice in self.visibleVoices]
		self.results.SetSelection(ids.index(self.selectedId) if self.selectedId in ids else wx.NOT_FOUND)
		self._updateDetails()
		# Translators: Number of voices matching the current filters; selection is never changed automatically.
		message = _("{count} voices found.").format(count=len(self.visibleVoices))
		if self.selectedId and self.selectedId not in ids:
			# Translators: Existing selection is hidden by a filter or absent from a refreshed catalog.
			message += " " + _(
				"The previous voice is not in these results. Choose a voice or change the filters.",
			)
		self._setStatus(message, announce=announce)

	def _updateDetails(self) -> None:
		voice = self._selected()
		canPreview = voice is not None and self.store.directory is not None
		remixable = voice is not None and canRemix(voice)
		if (
			(voice is None and self.useBtn.HasFocus())
			or (not canPreview and self.previewBtn.HasFocus())
			or (not remixable and self.remixBtn.HasFocus())
		):
			(self.results if self.visibleVoices else self.searchCtrl).SetFocus()
		self.useBtn.Enable(voice is not None)
		self.remixBtn.Enable(remixable)
		self.previewBtn.Enable(canPreview)
		if voice is None:
			self.detailsCtrl.ChangeValue("")
			return
		# Translators: Readable voice metadata; the ID distinguishes voices with identical display names.
		typeLabels = {"prebuilt": _("Prebuilt"), "prompted": _("Designed"), "replicated": _("Replicated")}
		self.detailsCtrl.ChangeValue(
			_(
				"Name: {name}\nID: {id}\nType: {type}\nLanguage: {language}\nAccent: {accent}\n"
				"Gender: {gender}\nPitch: {pitch}\nPersona: {persona}\nUse case: {context}\nDescription: {description}",
			).format(
				name=voice.displayName,
				id=voice.id,
				type=typeLabels.get(voice.type, voice.type),
				language=voice.language,
				accent=voice.accent,
				gender=voice.gender,
				pitch=voice.pitch,
				persona=voice.persona,
				context=voice.context,
				description=voice.description,
			),
		)

	def onSelection(self, evt: wx.Event) -> None:
		wasPreviewing = self._previewState != "idle"
		self._stopPreview()
		voice = self._selected()
		self.selectedId = voice.id if voice else ""
		self._updateDetails()
		if wasPreviewing:
			# Translators: Selecting another voice cancels preview; native selection speech identifies the voice.
			self._setStatus(_("Sample stopped."), announce=False)

	def onRefresh(self, evt: wx.Event | None) -> None:
		if self._closed or self._isLoading:
			return
		if self._isCreating:
			# Translators: Avoid overlapping catalog refresh with creation of a persistent voice.
			self._setStatus(_("Voice creation is still in progress."))
			return
		self._stopPreview()
		self._isLoading = True
		self._loadId += 1
		loadId = self._loadId
		# Keep the focused button enabled; ignore repeated activation until this request completes.
		# Translators: Voice catalog request is in progress; existing results remain usable.
		self._setStatus(_("Loading voices. Current results remain available."))
		threading.Thread(target=self._loadWorker, args=(loadId,), daemon=True).start()

	def onNewVoice(self, evt: wx.Event) -> None:
		if self._closed:
			return
		if self._isCreating:
			self._setStatus(_("Voice creation is still in progress."))
			return
		self._stopPreview()
		dialog = NewVoiceDialog(self)
		self._childDialog = dialog
		try:
			result = dialog.ShowModal()
			voiceType = dialog.voiceType
		finally:
			self._childDialog = None
			dialog.Destroy()
			self._afterChildDialog()
		if self._closed or result != wx.ID_OK:
			return
		if voiceType == "prompted":
			self.onDesignVoice(evt)
		elif voiceType == "replicated":
			self.onReplicateVoice(evt)

	def onDesignVoice(self, evt: wx.Event) -> None:
		if self._closed:
			return
		if self._isCreating:
			self._setStatus(_("Voice creation is still in progress."))
			return
		self._stopPreview()
		dialog = VoiceDesignDialog(self)
		self._childDialog = dialog
		try:
			result = dialog.ShowModal()
			design = dialog.design
		finally:
			self._childDialog = None
			dialog.Destroy()
			self._afterChildDialog()
		if self._closed or result != wx.ID_OK or design is None:
			return
		self._isCreating = True
		# Discard any catalog response started before the new voice is created.
		self._loadId += 1
		self._isLoading = False
		# Translators: The explicit create request is being sent; closing cannot cancel the server operation.
		self._setStatus(_("Creating voice using API quota. It will be saved in your Google project."))
		threading.Thread(target=self._createWorker, args=(design,), daemon=True).start()

	def onReplicateVoice(self, evt: wx.Event) -> None:
		if self._closed:
			return
		if self._isCreating:
			self._setStatus(_("Voice creation is still in progress."))
			return
		self._stopPreview()
		dialog = VoiceReplicationDialog(self)
		self._childDialog = dialog
		try:
			result = dialog.ShowModal()
			replication = dialog.replication
		finally:
			self._childDialog = None
			dialog.Destroy()
			self._afterChildDialog()
		if self._closed or result != wx.ID_OK or replication is None:
			return
		self._isCreating = True
		self._loadId += 1
		self._isLoading = False
		# Translators: Explicitly requested recording validation, upload, and voice creation.
		self._setStatus(
			_("Checking recordings and creating voice using API quota. Google will verify consent."),
		)
		threading.Thread(target=self._replicateWorker, args=(replication,), daemon=True).start()

	def onRemixVoice(self, evt: wx.Event) -> None:
		if self._closed:
			return
		if self._isCreating:
			self._setStatus(_("Voice creation is still in progress."))
			return
		if self._searchTimer is not None:
			self._applyFilter()
		base = self._selected()
		if base is None or not canRemix(base):
			# Translators: Shown when no voice is selected or the selected voice cannot be remixed.
			self._setStatus(
				_("Select a prebuilt or designed voice to remix. Replicated voices cannot be remixed."),
			)
			return
		self._stopPreview()
		dialog = VoiceRemixDialog(self, base.displayName)
		self._childDialog = dialog
		try:
			result = dialog.ShowModal()
			remix = dialog.remix
		finally:
			self._childDialog = None
			dialog.Destroy()
			if self._closeRequested:
				self._finish(wx.ID_CANCEL)
			elif not self._closed:
				self.remixBtn.SetFocus()
		if self._closed or result != wx.ID_OK or remix is None:
			return
		self._isCreating = True
		self._loadId += 1
		self._isLoading = False
		# Translators: Status while a remixed voice is being created.
		self._setStatus(_("Remixing voice using API quota. It will be saved in your Google project."))
		threading.Thread(target=self._remixWorker, args=(base, *remix), daemon=True).start()

	def _remixWorker(self, base: Voice, name: str, instructions: str) -> None:
		try:
			voice = createRemixedVoice(self.apiKey, base, name, instructions)
		except (DirectApiError, ValueError):
			wx.CallAfter(self._createFailed)
		else:
			wx.CallAfter(self._voiceCreated, voice)

	def _replicateWorker(self, replication: tuple[str, str, str]) -> None:
		try:
			voice = createReplicatedVoice(self.apiKey, self.model, *replication)
		except RecordingError as error:
			wx.CallAfter(self._recordingFailed, error.field)
		except (DirectApiError, ValueError):
			wx.CallAfter(self._createFailed)
		else:
			wx.CallAfter(self._voiceCreated, voice)

	def _recordingFailed(self, field: str) -> None:
		self._isCreating = False
		if self._closed:
			return
		# Translators: Local validation failed before any upload. Limits are for this add-on version.
		message = (
			_("Reference recording must be a readable 24 kHz mono 16-bit PCM WAV file of 10–30 seconds.")
			if field == "source"
			else _("Consent recording must be a readable 24 kHz mono 16-bit PCM WAV file, up to 60 seconds.")
		)
		# Translators: No network request was made for invalid audio.
		self._setStatus(
			message
			+ " "
			+ _("Nothing was uploaded. Open New voice, then Voice Replication to choose the files again."),
		)

	def _createWorker(self, design: tuple[str, str, str, str]) -> None:
		try:
			voice = createDesignedVoice(self.apiKey, self.model, *design)
		except (DirectApiError, ValueError):
			wx.CallAfter(self._createFailed)
		else:
			wx.CallAfter(self._voiceCreated, voice)

	def _createFailed(self) -> None:
		self._isCreating = False
		if not self._closed:
			self._stopPreview()
			# Translators: A lost response can hide successful creation; avoid prompting duplicate billable requests.
			self._setStatus(
				_(
					"Could not confirm voice creation. Refresh the library before trying again; "
					"the voice may already have been saved. Check billing, API access, quota, and, for replication, "
					"the consent recording if it is missing.",
				),
			)

	def _voiceCreated(self, voice: Voice) -> None:
		self._isCreating = False
		if self._closed:
			# Preserve a successful server result even if the user closed the library while waiting.
			self.store.rememberCreatedVoice(voice)
			return
		self._stopPreview()
		self.voices = [voice, *(item for item in self.voices if item.id != voice.id)]
		saved = self.store.rememberCreatedVoice(voice)
		self.selectedId = voice.id
		self.searchCtrl.ChangeValue("")
		self.typeChoice.SetSelection(0)
		self.languageChoice.SetSelection(0)
		for choice in self._attributeChoices.values():
			choice.SetSelection(0)
		self._updateLanguages()
		self._updateAttributes()
		self._applyFilter(announce=False)
		# Translators: Creation succeeded; the voice is selected in the library but not yet applied to a speaker.
		message = _(
			"Voice {name} created and saved in Google. Filters cleared to show it. "
			"Press Space or Enter on the voice to hear its sample, or use Use selected voice.",
		).format(name=voice.displayName)
		if voice.type == "replicated":
			# Translators: Replicated voices do not have a downloadable sample; preview is explicit.
			message = _(
				"Voice {name} created and saved in Google. Filters cleared to show it. "
				"Use Generate preview to hear it using API quota, or Use selected voice.",
			).format(name=voice.displayName)
		if not saved:
			# Translators: The server operation succeeded but local metadata persistence failed.
			message += " " + _("The local cache could not be saved.")
		self._setStatus(message)

	def _loadWorker(self, loadId: int) -> None:
		try:
			voices = fetchVoices(self.apiKey)
		except DirectApiError:
			wx.CallAfter(self._loadFailed, loadId)
		else:
			wx.CallAfter(self._loaded, loadId, voices)

	def _loadFailed(self, loadId: int) -> None:
		if not self._closed and loadId == self._loadId:
			self._isLoading = False
			self._stopPreview()
			# Translators: Refresh failed; do not discard cached voices or change the user's choice.
			self._setStatus(
				_(
					"Could not refresh voices. Previous results kept. Check the API key or connection and retry.",
				),
			)

	def _loaded(self, loadId: int, voices: list[Voice]) -> None:
		if self._closed or loadId != self._loadId:
			return
		self._isLoading = False
		self.voices = voices
		self._updateLanguages()
		self._updateAttributes()
		saved = self.store.writeCatalog(voices)
		self._applyFilter()
		if not saved:
			# Translators: Voices loaded successfully but could not be persisted in this NVDA session.
			self._setStatus(_("Voices loaded for this session. The cache could not be saved."))

	def onCharHook(self, evt: wx.KeyEvent) -> None:
		if (
			self.results.HasFocus()
			and not evt.HasAnyModifiers()
			and evt.GetKeyCode() in (wx.WXK_SPACE, wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER)
		):
			self.onPreview(evt)
			return
		evt.Skip()

	def onGeneratePreview(self, evt: wx.Event) -> None:
		self.onPreview(evt, generate=True)

	def onPreview(self, evt: wx.Event, *, generate: bool = False) -> None:
		if self._closed:
			return
		if self._searchTimer is not None:
			self._applyFilter()
		voice = self._selected()
		if voice is None:
			# Translators: A sample shortcut was used without a selected result.
			self._setStatus(_("Select a voice first."))
			return
		if self.store.directory is None:
			# Translators: NVDA is not allowing temporary audio files in this session.
			self._setStatus(_("Samples are unavailable while file saving is disabled."))
			return
		if self._previewState in ("loading", "generating"):
			return
		self._stopPreview()
		previewId = self._previewId
		self._previewVoiceName = voice.displayName
		if generate:
			self._generatePreview(previewId, voice, self.previewTextCtrl.GetValue().strip())
			return
		self._setPreviewState("loading")
		# Translators: Fetching an existing sample, without synthesizing speech.
		self._setStatus(_("Loading sample..."))
		threading.Thread(target=self._previewWorker, args=(previewId, voice), daemon=True).start()

	def _previewWorker(self, previewId: int, voice: Voice) -> None:
		try:
			data = fetchVoiceSample(self.apiKey, voice)
		except DirectApiError:
			wx.CallAfter(self._previewFailed, previewId)
		else:
			if data is None:
				wx.CallAfter(self._sampleUnavailable, previewId)
			else:
				wx.CallAfter(self._playPreview, previewId, data)

	def _sampleUnavailable(self, previewId: int) -> None:
		if not self._closed and previewId == self._previewId:
			self._stopPreview()
			# Translators: No recording exists. Generation requires a separate, explicit action.
			self._setStatus(
				_("Sample not available for this voice. Use Generate preview to create one using API quota."),
			)

	def _generatePreview(self, previewId: int, voice: Voice, text: str) -> None:
		# Only the explicit Generate preview action reaches this method.
		if self._closed or previewId != self._previewId:
			return
		if not text or len(text) > 300:
			self._stopPreview()
			# Translators: Validation for the short text used to generate a missing voice sample.
			self._setStatus(_("Enter preview text, up to 300 characters."))
			self.previewTextCtrl.SetFocus()
			return
		cacheKey = (self.model, voice.id, text)
		if self._generatedSample is not None and self._generatedSample[0] == cacheKey:
			self._playPreview(previewId, self._generatedSample[1])
			return
		# Translators: Generating a preview consumes the user's API quota.
		self._setStatus(_("Generating preview using API quota..."))
		self._setPreviewState("generating")
		threading.Thread(target=self._generateWorker, args=(previewId, cacheKey), daemon=True).start()

	def _generateWorker(self, previewId: int, cacheKey: tuple[str, str, str]) -> None:
		model, voiceId, text = cacheKey
		try:
			data, mimeType = generate_tts(self.apiKey, model, text, [voiceId], timeout=90)
			if mimeType != "audio/wav" or len(data) > MAX_SAMPLE_BYTES:
				raise DirectApiError("Preview did not return WAV audio.")
		except (DirectApiError, SpeechInputError):
			wx.CallAfter(self._previewFailed, previewId)
		else:
			wx.CallAfter(self._generatedPreview, previewId, cacheKey, data)

	def _generatedPreview(self, previewId: int, cacheKey: tuple[str, str, str], data: bytes) -> None:
		if self._closed or previewId != self._previewId:
			return
		self._playPreview(previewId, data)
		if self._previewState == "playing":
			self._generatedSample = (cacheKey, data)

	def _previewFailed(self, previewId: int) -> None:
		if not self._closed and previewId == self._previewId:
			self._stopPreview()
			# Translators: Retrieving, generating, or playing the voice sample failed.
			self._setStatus(_("Could not play the sample. Please try again."))

	def _playPreview(self, previewId: int, data: bytes) -> None:
		if self._closed or previewId != self._previewId:
			return
		try:
			with wave.open(io.BytesIO(data), "rb") as audio:
				duration = audio.getnframes() / audio.getframerate()
			with tempfile.NamedTemporaryFile(
				prefix="nsg_voice_preview_",
				suffix=".wav",
				delete=False,
			) as temp:
				self._previewPath = temp.name
				temp.write(data)
			speech.cancelSpeech()
			winsound.PlaySound(self._previewPath, winsound.SND_FILENAME | winsound.SND_ASYNC)
			self._setPreviewState("playing")
			# Translators: Readable status during playback; not spoken over the generated audio.
			self._setStatus(
				_("Playing sample for {name}.").format(name=self._previewVoiceName),
				announce=False,
			)
			self._playbackTimer = wx.CallLater(max(1, int(duration * 1000)), self._previewFinished, previewId)
		except (OSError, RuntimeError, EOFError, wave.Error):
			self._previewFailed(previewId)

	def _previewFinished(self, previewId: int) -> None:
		if not self._closed and previewId == self._previewId:
			self._stopPreview()
			# Translators: The voice preview has finished playing.
			self._setStatus(_("Sample complete."), announce=False)

	def _setPreviewState(self, state: str) -> None:
		self._previewState = state
		if not self._closed and state == "idle" and self.stopBtn.HasFocus():
			(self.previewBtn if self.previewBtn.IsEnabled() else self.results).SetFocus()
		self.stopBtn.Enable(state != "idle")

	def _stopPreview(self) -> None:
		self._previewId += 1
		if self._playbackTimer is not None:
			self._playbackTimer.Stop()
			self._playbackTimer = None
		self._setPreviewState("idle")
		if self._previewPath:
			try:
				winsound.PlaySound(None, 0)
			except RuntimeError:
				pass
			try:
				os.remove(self._previewPath)
			except OSError:
				pass
			self._previewPath = None

	def onStop(self, evt: wx.Event) -> None:
		wasGenerating = self._previewState == "generating"
		self._stopPreview()
		# Translators: Playback or retrieval of the sample was stopped locally.
		message = _("Sample stopped.")
		if wasGenerating:
			# Translators: Local cancellation cannot undo a request already submitted to Google.
			message += " " + _("A submitted generation request may still use API quota.")
		self._setStatus(message)

	def onUse(self, evt: wx.Event) -> None:
		if self._searchTimer is not None:
			self._applyFilter()
		voice = self._selected()
		if voice is not None:
			self.selectedVoice = voice
			self._finish(wx.ID_OK)

	def onCancel(self, evt: wx.Event) -> None:
		self._finish(wx.ID_CANCEL)

	def requestClose(self) -> None:
		"""Close from the owner without ending this modal loop under a nested one."""
		if self._closed or self._closeRequested:
			return
		self._closeRequested = True
		child = self._childDialog
		if child is None:
			self._finish(wx.ID_CANCEL)
		else:
			# _afterChildDialog finishes this dialog once the child's loop returns.
			child.requestClose()

	def _afterChildDialog(self) -> None:
		if self._closeRequested:
			self._finish(wx.ID_CANCEL)
		elif not self._closed:
			self.newVoiceBtn.SetFocus()

	def _finish(self, result: int) -> None:
		if self._closed:
			return
		self._closed = True
		if self._searchTimer is not None:
			self._searchTimer.Stop()
		self._stopPreview()
		self._generatedSample = None
		self.EndModal(result)
