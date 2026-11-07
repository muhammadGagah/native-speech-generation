"""Accessible form collecting a voice design before a single explicit POST."""

from __future__ import annotations

import addonHandler
import ui
import wx
from gui.guiHelper import BoxSizerHelper

from ..core.voice_design import validateDesign

addonHandler.initTranslation()


class VoiceDesignDialog(wx.Dialog):
	def __init__(self, parent: wx.Window):
		# Translators: Title of the form for creating a custom voice from a description.
		super().__init__(parent, title=_("Voice Design"), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
		self.design: tuple[str, str, str, str] | None = None
		sizer = wx.BoxSizer(wx.VERTICAL)
		helper = BoxSizerHelper(self, sizer=sizer)
		# Translators: Billing requirement and the effect of creating a voice before submission.
		notice = wx.StaticText(
			self,
			label=_(
				"Voice Design requires a Gemini API key from a project with billing enabled (paid tier). "
				"Free-tier API keys cannot create voices. "
				"Describe the voice's age, tone, accent, and delivery. Create voice uses API quota "
				"and saves the voice in your Google project immediately. Closing the library "
				"does not cancel creation or delete the voice.",
			),
		)
		notice.Wrap(540)
		sizer.Add(notice, flag=wx.ALL, border=8)
		# Translators: Required display name of the new designed voice.
		self.nameCtrl = helper.addLabeledControl(_("Voice &name:"), wx.TextCtrl)
		self.nameCtrl.SetMaxLength(100)
		# Translators: Natural language description of the vocal identity, not a script to read.
		self.descriptionCtrl = helper.addLabeledControl(
			_("Voice &description:"),
			wx.TextCtrl,
			style=wx.TE_MULTILINE,
			size=(540, 130),
		)
		self.descriptionCtrl.SetMaxLength(2000)
		# Translators: Optional BCP-47 language tag for catalog metadata.
		self.languageCtrl = helper.addLabeledControl(_("&Language tag (optional, e.g. id-ID):"), wx.TextCtrl)
		# Translators: Optional gender presentation metadata for the designed voice.
		self.genderChoice = helper.addLabeledControl(
			_("&Gender:"),
			wx.Choice,
			choices=[_("Unspecified"), _("Female"), _("Male"), _("Neutral")],
		)
		self.genderChoice.SetSelection(0)
		# Translators: Explicitly create and store a voice using the API.
		self.createBtn = wx.Button(self, label=_("&Create voice"))
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
		self.nameCtrl.SetFocus()

	def onCreate(self, evt: wx.Event) -> None:
		name = self.nameCtrl.GetValue().strip()
		description = self.descriptionCtrl.GetValue().strip()
		language = self.languageCtrl.GetValue().strip()
		error = validateDesign(name, description, language)
		if error:
			# Translators: Validation messages for the Voice Design form.
			messages = {
				"name": (self.nameCtrl, _("Enter a voice name, up to 100 characters.")),
				"description": (self.descriptionCtrl, _("Enter a voice description, up to 2000 characters.")),
				"language": (self.languageCtrl, _("Enter a language tag such as id-ID, or leave it blank.")),
			}
			control, message = messages[error]
			control.SetFocus()
			ui.message(message)
			return
		gender = ("", "female", "male", "neutral")[self.genderChoice.GetSelection()]
		self.design = (name, description, language, gender)
		self.EndModal(wx.ID_OK)

	def onCancel(self, evt: wx.Event) -> None:
		self.EndModal(wx.ID_CANCEL)

	def requestClose(self) -> None:
		if self.IsModal():
			self.EndModal(wx.ID_CANCEL)
