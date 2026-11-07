"""Accessible file-based voice replication form; submission occurs in the library worker."""

from __future__ import annotations

import os

import addonHandler
import ui
import wx
from gui.guiHelper import BoxSizerHelper

addonHandler.initTranslation()

# These are Google's verbatim consent statements, not translatable interface strings.
CONSENT_STATEMENTS = (
	"Saya pemilik suara ini dan saya menyetujui Google menggunakan suara ini untuk membuat model suara sintetis.",
	"I am the owner of this voice and I consent to Google using this voice to create a synthetic voice model.",
)


class VoiceReplicationDialog(wx.Dialog):
	_browsing = False
	_closeRequested = False

	def __init__(self, parent: wx.Window):
		# Translators: Form for creating a voice from recordings.
		super().__init__(
			parent,
			title=_("Voice Replication"),
			style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
		)
		self.replication: tuple[str, str, str] | None = None
		sizer = wx.BoxSizer(wx.VERTICAL)
		helper = BoxSizerHelper(self, sizer=sizer)
		# Translators: Billing, recording requirements, and upload/storage notice.
		notice = wx.StaticText(
			self,
			label=_(
				"Voice Replication requires a Gemini API key from a project with billing enabled (paid tier). "
				"Free-tier API keys cannot create voices. Use two real recordings from the same adult speaker. "
				"This version accepts 24 kHz mono 16-bit PCM WAV files: reference speech of 10–30 seconds "
				"and a consent recording of up to 60 seconds. Record the exact statement below. "
				"Create voice uploads both recordings to Google for verification, uses API quota, and saves "
				"the voice in your Google project. Closing the library does not cancel creation or delete the voice.",
			),
		)
		notice.Wrap(580)
		sizer.Add(notice, flag=wx.ALL, border=8)
		# Translators: Name of the new replicated voice.
		self.nameCtrl = helper.addLabeledControl(_("Voice &name:"), wx.TextCtrl)
		self.nameCtrl.SetMaxLength(100)
		# Translators: Language of the displayed consent statement only.
		self.languageChoice = helper.addLabeledControl(
			_("Consent statement &language:"),
			wx.Choice,
			choices=[_("Indonesian"), _("English")],
		)
		self.languageChoice.SetSelection(0)
		# Translators: Read-only text that the speaker must record verbatim.
		self.statementCtrl = helper.addLabeledControl(
			_("Statement to &record:"),
			wx.TextCtrl,
			value=CONSENT_STATEMENTS[0],
			style=wx.TE_MULTILINE | wx.TE_READONLY,
			size=(580, 70),
		)
		# Translators: Local reference audio file path.
		self.sourceCtrl = helper.addLabeledControl(_("Reference &audio file:"), wx.TextCtrl)
		# Translators: Choose the reference recording from disk.
		sourceBtn = wx.Button(self, label=_("&Browse reference…"))
		sizer.Add(sourceBtn, flag=wx.ALL, border=4)
		# Translators: Local consent audio file path.
		self.consentCtrl = helper.addLabeledControl(_("&Consent audio file:"), wx.TextCtrl)
		# Translators: Choose the consent recording from disk.
		consentBtn = wx.Button(self, label=_("Browse con&sent…"))
		sizer.Add(consentBtn, flag=wx.ALL, border=4)
		# Translators: Explicit confirmation before sending recordings for Google's verification.
		self.confirmCtrl = wx.CheckBox(
			self,
			label=_(
				"I con&firm these are recordings of the same adult speaker who gave the recorded consent.",
			),
		)
		sizer.Add(self.confirmCtrl, flag=wx.ALL, border=8)
		# Translators: Explicit paid upload and creation action.
		self.createBtn = wx.Button(self, label=_("Cr&eate voice"))
		cancelBtn = wx.Button(self, wx.ID_CANCEL)
		buttons = wx.BoxSizer(wx.HORIZONTAL)
		for button in (self.createBtn, cancelBtn):
			buttons.Add(button, flag=wx.ALL, border=6)
		sizer.Add(buttons, flag=wx.ALL, border=6)
		self.languageChoice.Bind(wx.EVT_CHOICE, self.onLanguage)
		sourceBtn.Bind(wx.EVT_BUTTON, self.onBrowseSource)
		consentBtn.Bind(wx.EVT_BUTTON, self.onBrowseConsent)
		self.createBtn.Bind(wx.EVT_BUTTON, self.onCreate)
		cancelBtn.Bind(wx.EVT_BUTTON, self.onCancel)
		self.Bind(wx.EVT_CLOSE, self.onCancel)
		self.SetSizerAndFit(sizer)
		self.SetMinSize(self.GetSize())
		self.CenterOnParent()
		self.nameCtrl.SetFocus()

	def onLanguage(self, evt: wx.Event) -> None:
		self.statementCtrl.ChangeValue(CONSENT_STATEMENTS[self.languageChoice.GetSelection()])

	def onBrowseSource(self, evt: wx.Event) -> None:
		self.browse(self.sourceCtrl)

	def onBrowseConsent(self, evt: wx.Event) -> None:
		self.browse(self.consentCtrl)

	def browse(self, control: wx.TextCtrl) -> None:
		# Translators: Audio file selection dialog title.
		dialog = wx.FileDialog(
			self,
			message=_("Choose WAV recording"),
			wildcard="WAV (*.wav)|*.wav",
			style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST,
		)
		self._browsing = True
		try:
			if dialog.ShowModal() == wx.ID_OK and not self._closeRequested:
				control.ChangeValue(dialog.GetPath())
		finally:
			self._browsing = False
			dialog.Destroy()
			if self._closeRequested:
				self.EndModal(wx.ID_CANCEL)
			else:
				control.SetFocus()

	def onCreate(self, evt: wx.Event) -> None:
		name = self.nameCtrl.GetValue().strip()
		if not name or len(name) > 100:
			self.nameCtrl.SetFocus()
			# Translators: Required voice name validation.
			ui.message(_("Enter a voice name, up to 100 characters."))
			return
		for control in (self.sourceCtrl, self.consentCtrl):
			if not os.path.isfile(control.GetValue().strip()):
				control.SetFocus()
				# Translators: Missing local audio file; nothing has been uploaded.
				ui.message(_("Choose an existing WAV recording."))
				return
		if not self.confirmCtrl.GetValue():
			self.confirmCtrl.SetFocus()
			# Translators: Required consent confirmation; Google also verifies the recording.
			ui.message(_("Confirm the speaker's recorded consent before creating the voice."))
			return
		self.replication = (name, self.sourceCtrl.GetValue().strip(), self.consentCtrl.GetValue().strip())
		self.EndModal(wx.ID_OK)

	def onCancel(self, evt: wx.Event) -> None:
		self.EndModal(wx.ID_CANCEL)

	def requestClose(self) -> None:
		"""Cancel now, or as soon as an open native file dialog returns."""
		self._closeRequested = True
		if not self._browsing and self.IsModal():
			self.EndModal(wx.ID_CANCEL)
