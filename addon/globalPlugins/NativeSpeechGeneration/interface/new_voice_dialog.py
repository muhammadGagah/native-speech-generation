"""Native, keyboard-accessible entry point for custom voice creation."""

from __future__ import annotations

import addonHandler
import wx

addonHandler.initTranslation()


class NewVoiceDialog(wx.Dialog):
	def __init__(self, parent: wx.Window):
		# Translators: Choose how to create a custom voice.
		super().__init__(parent, title=_("Create voice"), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
		self.voiceType: str | None = None
		sizer = wx.BoxSizer(wx.VERTICAL)
		# Translators: Both creation methods require a paid Gemini project.
		notice = wx.StaticText(
			self,
			label=_(
				"Choose how to create your voice. Both options require a Gemini API key "
				"from a project with billing enabled (paid tier).",
			),
		)
		notice.Wrap(540)
		sizer.Add(notice, flag=wx.ALL, border=10)
		# Translators: Button and description read together by screen readers. Keep the line breaks.
		self.designBtn = wx.Button(
			self,
			label=_(
				"Voice &Design\nCreate a voice from a text description of its age,\ntone, accent, and delivery.",
			),
		)
		# Translators: Button and description. Replication currently supports existing files only.
		self.replicationBtn = wx.Button(
			self,
			label=_(
				"Voice &Replication\nCreate a voice from a reference recording,\nwith the speaker's recorded consent verified by Google.",
			),
		)
		for button in (self.designBtn, self.replicationBtn):
			sizer.Add(button, flag=wx.EXPAND | wx.ALL, border=8)
		cancelBtn = wx.Button(self, wx.ID_CANCEL)
		sizer.Add(cancelBtn, flag=wx.ALIGN_RIGHT | wx.ALL, border=8)
		self.designBtn.Bind(wx.EVT_BUTTON, self.onDesign)
		self.replicationBtn.Bind(wx.EVT_BUTTON, self.onReplication)
		cancelBtn.Bind(wx.EVT_BUTTON, self.onCancel)
		self.Bind(wx.EVT_CLOSE, self.onCancel)
		self.SetSizerAndFit(sizer)
		self.SetMinSize(self.GetSize())
		self.CenterOnParent()
		self.designBtn.SetFocus()

	def onDesign(self, evt: wx.Event) -> None:
		self.voiceType = "prompted"
		self.EndModal(wx.ID_OK)

	def onReplication(self, evt: wx.Event) -> None:
		self.voiceType = "replicated"
		self.EndModal(wx.ID_OK)

	def onCancel(self, evt: wx.Event) -> None:
		self.EndModal(wx.ID_CANCEL)

	def requestClose(self) -> None:
		if self.IsModal():
			self.EndModal(wx.ID_CANCEL)
