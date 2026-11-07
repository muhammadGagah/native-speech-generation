"""Accessible form collecting voice remix instructions before a single explicit POST."""

from __future__ import annotations

import addonHandler
import ui
import wx
from gui.guiHelper import BoxSizerHelper

from ..core.voice_design import MAX_INSTRUCTION_LENGTH, validateRemix

addonHandler.initTranslation()


class VoiceRemixDialog(wx.Dialog):
	def __init__(self, parent: wx.Window, baseName: str):
		# Translators: Title of the dialog that creates a new voice by modifying an existing one.
		super().__init__(parent, title=_("Voice Remix"), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
		self.remix: tuple[str, str] | None = None
		sizer = wx.BoxSizer(wx.VERTICAL)
		helper = BoxSizerHelper(self, sizer=sizer)
		notice = wx.StaticText(
			self,
			# Translators: Explains Voice Remix requirements, cost, and that the base voice is unchanged.
			label=_(
				"Voice Remix creates a new voice based on {name}. The original voice is not changed. "
				"It requires a Gemini API key from a project with billing enabled (paid tier). "
				"Describe one or two changes, such as age, pitch, energy, pacing, tone, or accent. "
				"Create voice uses API quota and saves the new voice in your Google project immediately. "
				"Closing the library does not cancel creation or delete the voice.",
			).format(name=baseName),
		)
		notice.Wrap(540)
		sizer.Add(notice, flag=wx.ALL, border=8)
		self.baseCtrl = helper.addLabeledControl(
			# Translators: Read-only field showing the voice that will be remixed.
			_("&Base voice:"),
			wx.TextCtrl,
			value=baseName,
			style=wx.TE_READONLY,
		)
		# Translators: Optional name for the new remixed voice.
		self.nameCtrl = helper.addLabeledControl(_("New voice &name (optional):"), wx.TextCtrl)
		self.nameCtrl.SetMaxLength(100)
		self.instructionsCtrl = helper.addLabeledControl(
			# Translators: Field describing how the base voice should change.
			_("&Changes to make:"),
			wx.TextCtrl,
			style=wx.TE_MULTILINE,
			size=(540, 130),
		)
		self.instructionsCtrl.SetMaxLength(MAX_INSTRUCTION_LENGTH)
		# Translators: Button that submits a voice remix request.
		self.createBtn = wx.Button(self, label=_("Create &voice"))
		self.cancelBtn = wx.Button(self, wx.ID_CANCEL)
		buttons = wx.BoxSizer(wx.HORIZONTAL)
		for button in (self.createBtn, self.cancelBtn):
			buttons.Add(button, flag=wx.ALL, border=6)
		sizer.Add(buttons, flag=wx.ALL, border=6)
		self.createBtn.Bind(wx.EVT_BUTTON, self.onCreate)
		self.cancelBtn.Bind(wx.EVT_BUTTON, self.onCancel)
		self.Bind(wx.EVT_CLOSE, self.onCancel)
		self.SetSizerAndFit(sizer)
		self.SetMinSize(self.GetSize())
		self.CenterOnParent()
		self.instructionsCtrl.SetFocus()

	def onCreate(self, evt: wx.Event) -> None:
		name = self.nameCtrl.GetValue().strip()
		instructions = self.instructionsCtrl.GetValue().strip()
		error = validateRemix(name, instructions)
		if error == "name":
			self.nameCtrl.SetFocus()
			# Translators: Validation error for an overly long remixed voice name.
			ui.message(_("Enter a voice name of up to 100 characters, or leave it blank."))
			return
		if error:
			self.instructionsCtrl.SetFocus()
			# Translators: Validation error when remix instructions are missing or too long.
			ui.message(_("Describe the changes to make, up to 2000 characters."))
			return
		self.remix = (name, instructions)
		self.EndModal(wx.ID_OK)

	def onCancel(self, evt: wx.Event) -> None:
		self.EndModal(wx.ID_CANCEL)

	def requestClose(self) -> None:
		if self.IsModal():
			self.EndModal(wx.ID_CANCEL)
