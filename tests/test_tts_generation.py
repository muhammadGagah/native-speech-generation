from __future__ import annotations

import base64
import builtins
import importlib
import io
import sys
import types
import unittest
import wave
from pathlib import Path
from typing import Any
from unittest import mock

ADDON_PACKAGE = Path(__file__).resolve().parents[1] / "addon/globalPlugins/NativeSpeechGeneration"
PACKAGE_NAME = "nsg_tts_stage_one"


def translate(text: str) -> str:
	return text


def loadCore() -> tuple[Any, Any]:
	package = types.ModuleType(PACKAGE_NAME)
	package.__path__ = [str(ADDON_PACKAGE / "core")]
	sys.modules[PACKAGE_NAME] = package
	return (
		importlib.import_module(f"{PACKAGE_NAME}.tts_requests"),
		importlib.import_module(f"{PACKAGE_NAME}.api_client"),
	)


def wavAudio() -> bytes:
	output = io.BytesIO()
	with wave.open(output, "wb") as wavFile:
		wavFile.setparams((1, 2, 24000, 0, "NONE", "not compressed"))
		wavFile.writeframes(b"\x00\x00\x01\x00")
	return output.getvalue()


def _response(audio: bytes | None = None) -> dict[str, Any]:
	return {
		"steps": [
			{
				"type": "model_output",
				"content": [
					{
						"type": "audio",
						"mime_type": "audio/wav",
						"data": base64.b64encode(wavAudio() if audio is None else audio).decode(),
					},
				],
			},
		],
	}


def loadDialog() -> Any:
	"""Load only the generation dialog; no NVDA runtime, audio device, or network."""
	packageName = "nsg_generation_ui_under_test"
	stubs: dict[str, Any] = {}
	for name, path in (
		(packageName, ADDON_PACKAGE),
		(f"{packageName}.core", ADDON_PACKAGE / "core"),
		(f"{packageName}.interface", ADDON_PACKAGE / "interface"),
	):
		module = types.ModuleType(name)
		module.__path__ = [str(path)]
		stubs[name] = module
	for name in (
		"addonHandler",
		"gui",
		"ui",
		"wx",
		"logHandler",
		"winsound",
		f"{packageName}.talkWithAI",
		f"{packageName}.core.config_store",
	):
		stubs[name] = types.ModuleType(name)
	stubs["addonHandler"].initTranslation = lambda: None
	stubs["logHandler"].log = mock.Mock()
	stubs["ui"].message = mock.Mock()
	stubs["gui"].messageBox = mock.Mock()
	stubs[f"{packageName}.core.config_store"].ApiKeyResolution = object
	for name in (
		"Dialog",
		"BoxSizer",
		"TextCtrl",
		"Choice",
		"RadioButton",
		"StaticText",
		"CheckBox",
		"Panel",
		"Slider",
		"Button",
		"Window",
		"Event",
	):
		setattr(stubs["wx"], name, type(name, (), {}))
	stubs["wx"].OK = 1
	stubs["wx"].ICON_ERROR = 2
	stubs["wx"].NOT_FOUND = -1
	stubs["wx"].CallLater = mock.Mock()
	with (
		mock.patch.dict(sys.modules, stubs),
		mock.patch.object(builtins, "_", translate, create=True),
	):
		module = importlib.import_module(f"{packageName}.interface.generation_dialog")
		module._ = translate
		return module


class StructuredTtsTests(unittest.TestCase):
	requests: Any = None
	client: Any = None

	def setUp(self) -> None:
		self.requests, self.client = loadCore()

	def testSingleSpeakerKeepsTranscriptSeparateFromStyleForBothModels(self) -> None:
		text = "\nSelamat pagi: semuanya! <laugh>\nApa kabar?\n"
		for model in self.requests.STRUCTURED_TTS_MODELS:
			with (
				self.subTest(model=model),
				mock.patch.object(
					self.client,
					"_json_request",
					return_value=_response(),
				) as request,
			):
				data, mimeType = self.client.generate_tts(
					"key",
					model,
					text,
					["Kore"],
					style_instructions="  Speak warmly  ",
				)
				payload = request.call_args.args[2]
				part = payload["input"][0]["content"][0]
				self.assertEqual(part["text"], text)
				self.assertEqual(part["annotations"], [{"type": "speech_metadata", "style": "Speak warmly"}])
				self.assertEqual(payload["generation_config"]["speech_config"], [{"voice": "Kore"}])
				self.assertEqual(data, wavAudio())
				self.assertEqual(mimeType, "audio/wav")

	def testMultiSpeakerTurnsKeepNamesPunctuationAndVocalTags(self) -> None:
		payload = self.requests.buildTtsPayload(
			self.requests.FLASH_38_TTS_MODEL,
			"\nÉva: <sigh> Pukul 10:30.\r\n\r\nBudi: Ya!\nÉva: Terima kasih.",
			["Kore", "Puck"],
			speakerNames=["Éva", "Budi"],
			styleInstructions="Calm",
		)
		parts = payload["input"][0]["content"]
		self.assertEqual([part["text"] for part in parts], ["<sigh> Pukul 10:30.", "Ya!", "Terima kasih."])
		self.assertEqual([part["annotations"][0]["speaker"] for part in parts], ["Éva", "Budi", "Éva"])
		self.assertTrue(all(part["annotations"][0]["style"] == "Calm" for part in parts))
		self.assertEqual(
			payload["generation_config"]["speech_config"],
			{
				"mode": "conversational",
				"speakers": [{"speaker": "Éva", "voice": "Kore"}, {"speaker": "Budi", "voice": "Puck"}],
			},
		)

	def testEmptyStyleDoesNotBecomeSpokenText(self) -> None:
		payload = self.requests.buildTtsPayload(self.requests.FLASH_38_TTS_MODEL, "Hello", ["Kore"])
		self.assertEqual(payload["input"][0]["content"], [{"type": "text", "text": "Hello"}])

	def testInvalidScriptReportsOriginalLineBeforeAnyRequest(self) -> None:
		cases = (
			("\n\nAlice: Hello\nUnknown: Hi", "invalidSpeakerLabel", 4),
			("Alice: Hello\ncontinuation", "invalidSpeakerLabel", 2),
			("alice: Hello", "invalidSpeakerLabel", 1),
			("Bob:", "emptyTurn", 1),
			("\n  ", "emptyText", None),
		)
		for text, reason, line in cases:
			with self.subTest(text=text), mock.patch.object(self.client, "_json_request") as request:
				with self.assertRaises(self.requests.SpeechInputError) as raised:
					self.client.generate_tts(
						"key",
						self.requests.FLASH_38_TTS_MODEL,
						text,
						["Kore", "Puck"],
						speaker_names=["Alice", "Bob"],
					)
				self.assertEqual((raised.exception.reason, raised.exception.lineNumber), (reason, line))
				request.assert_not_called()

	def testInvalidSpeakerNamesAreNotSilentlyReplaced(self) -> None:
		for names, reason, index in (
			(["", "Bob"], "invalidSpeakerName", 0),
			(["Alice", "alice"], "duplicateSpeakerName", 1),
			(["Alice", "B:ob"], "invalidSpeakerName", 1),
			(["Alice", "B\nob"], "invalidSpeakerName", 1),
		):
			with self.subTest(names=names), self.assertRaises(self.requests.SpeechInputError) as raised:
				self.requests.parseSpeechTurns("Alice: Hello", names)
			self.assertEqual((raised.exception.reason, raised.exception.speakerIndex), (reason, index))

	def testVoiceSpeakerCountMismatchIsRejected(self) -> None:
		for voices, speakers in (([], []), (["Kore", "Puck"], []), (["Kore"], ["Alice"]), ([""], [])):
			with (
				self.subTest(voices=voices, speakers=speakers),
				self.assertRaises(self.requests.SpeechInputError),
			):
				self.requests.buildTtsPayload(
					self.requests.FLASH_38_TTS_MODEL,
					"Hello",
					voices,
					speakerNames=speakers,
				)

	def testApiErrorsNeverRetryWithLegacyPrompt(self) -> None:
		for code in (400, 401, 403, 404, 429, 500):
			with (
				self.subTest(code=code),
				mock.patch.object(
					self.client,
					"_json_request",
					side_effect=self.client.DirectApiError(f"HTTP {code}", code=code),
				) as request,
			):
				with self.assertRaises(self.client.DirectApiError):
					self.client.generate_tts("key", self.requests.FLASH_38_TTS_MODEL, "Hello", ["Kore"])
				self.assertEqual(request.call_count, 1)

	def testOnlyLastModelAudioIsUsed(self) -> None:
		response = _response()
		response["input"] = {"data": base64.b64encode(b"unrelated").decode()}
		response["steps"].insert(0, _response(b"not the final audio")["steps"][0])
		with mock.patch.object(self.client, "_json_request", return_value=response):
			data, mimeType = self.client.generate_tts(
				"key",
				self.requests.FLASH_38_TTS_MODEL,
				"Hello",
				["Kore"],
			)
		self.assertEqual((data, mimeType), (wavAudio(), "audio/wav"))

	def testMissingOrCorruptAudioDoesNotRetryOrSaveGarbage(self) -> None:
		invalidBase64 = _response()
		invalidBase64["steps"][0]["content"][0]["data"] = "%%%"
		for response in (
			{},
			_response(b""),
			_response(b"raw PCM"),
			invalidBase64,
			{"error": {"message": "Denied"}},
		):
			with (
				self.subTest(response=response),
				mock.patch.object(
					self.client,
					"_json_request",
					return_value=response,
				) as request,
			):
				with self.assertRaises(self.client.DirectApiError):
					self.client.generate_tts("key", self.requests.FLASH_38_TTS_MODEL, "Hello", ["Kore"])
				self.assertEqual(request.call_count, 1)

	def testLegacyTtsRequestAndFallbackStayUnchanged(self) -> None:
		pcm = {"inlineData": {"data": base64.b64encode(b"pcm").decode(), "mimeType": "audio/L16;rate=24000"}}
		with mock.patch.object(
			self.client,
			"_json_request",
			side_effect=[
				self.client.DirectApiError("HTTP 400", code=400),
				pcm,
			],
		) as request:
			result = self.client.generate_tts(
				"key",
				"gemini-3.1-flash-tts-preview",
				"Hello",
				["Kore"],
				style_instructions="Calm",
			)
		self.assertEqual(result, (b"pcm", "audio/L16;rate=24000"))
		self.assertEqual(request.call_args_list[0].args[2]["input"], "Calm\nHello")
		self.assertEqual(request.call_args_list[1].args[2]["contents"][0]["parts"], [{"text": "Calm\nHello"}])


class GenerationDialogTests(unittest.TestCase):
	module: Any = None
	dialog: Any = None

	def setUp(self) -> None:
		self.module = loadDialog()
		self.dialog = object.__new__(self.module.NativeSpeechDialog)
		self.dialog.isClosed = False
		self.dialog.isGenerating = False
		self.dialog.modeMulti = True
		self.dialog.model = self.module.FLASH_LITE_38_TTS_MODEL
		for name in ("textCtrl", "spk1NameCtrl", "spk2NameCtrl", "generateBtn", "modelChoice"):
			setattr(self.dialog, name, mock.Mock())
		self.dialog.spk1NameCtrl.GetValue.return_value = "Alice"
		self.dialog.spk2NameCtrl.GetValue.return_value = "Bob"
		self.dialog._resolveApiKeyForUse = mock.Mock(return_value="key")
		self.dialog._showMessage = mock.Mock()
		self.dialog._syncLibraryStore = mock.Mock()
		self.dialog._librarySelections = {}

	def testInvalidInputKeepsGenerateEnabledAndReturnsFocusAfterMessage(self) -> None:
		for text, name, control in (
			("\n\nUnknown: Hello", "Bob", self.dialog.textCtrl),
			("Alice: Hello", "Alice", self.dialog.spk2NameCtrl),
			("Alice: Hello", "", self.dialog.spk2NameCtrl),
		):
			with (
				self.subTest(text=text, name=name),
				mock.patch.object(self.module.threading, "Thread") as worker,
			):
				self.dialog.textCtrl.GetValue.return_value = text
				self.dialog.spk2NameCtrl.GetValue.return_value = name
				events: list[str] = []

				def showMessage(*args: Any, **kwargs: Any) -> None:
					events.append("message")

				self.dialog._showMessage.side_effect = showMessage
				control.SetFocus.side_effect = lambda: events.append("focus")
				self.dialog.onGenerate(mock.Mock())
				self.assertEqual(events, ["message", "focus"])
				self.assertFalse(self.dialog.isGenerating)
				self.dialog.generateBtn.Disable.assert_not_called()
				worker.assert_not_called()
				self.dialog.textCtrl.SetValue.assert_not_called()

	def testStructuredValidationDoesNotApplyToLegacyModel(self) -> None:
		self.dialog.model = self.module.DEFAULT_MODEL
		self.dialog.textCtrl.GetValue.return_value = "Old free-form dialogue"
		self.dialog._validateStructuredScript = mock.Mock(
			side_effect=AssertionError("legacy validation changed"),
		)
		self.dialog._buildGenerationRequest = mock.Mock(return_value=object())
		for name in ("closeBtn", "playBtn", "saveBtn", "talkBtn"):
			setattr(self.dialog, name, mock.Mock())
		with mock.patch.object(self.module.threading, "Thread") as worker:
			self.dialog.onGenerate(mock.Mock())
			worker.return_value.start.assert_called_once()

	def testDelayedModelDescriptionDoesNotInterruptAnotherControl(self) -> None:
		self.dialog._modelDescriptionAnnouncementId = 0
		self.dialog.modelChoice.HasFocus.return_value = False
		self.dialog._announceModelDescription("New model")
		self.module.wx.CallLater.call_args.args[1]()
		self.module.ui.message.assert_not_called()

	def testHelpIncludesCurrentNamesAndRestoresLauncherFocus(self) -> None:
		launcher = mock.Mock()
		event = mock.Mock()
		event.GetEventObject.return_value = launcher
		self.dialog.onScriptHelp(event)
		message = self.dialog._showMessage.call_args.args[0]
		self.assertIn("Alice: Hello!", message)
		self.assertIn("Bob: Good morning!", message)
		launcher.SetFocus.assert_called_once()

	def testWavIsNotWrappedTwiceAndLegacyPcmStillGetsHeader(self) -> None:
		wavData = wavAudio()
		self.assertEqual(self.module.convertToWav(wavData, "audio/wav"), wavData)
		pcm = b"\x00\x00\x01\x00"
		converted = self.module.convertToWav(pcm, "audio/L16;rate=24000")
		with wave.open(io.BytesIO(converted), "rb") as wavFile:
			self.assertEqual(wavFile.readframes(wavFile.getnframes()), pcm)
			self.assertEqual(wavFile.getframerate(), 24000)

	def testValidationMessageUsesModernNvdaApiWhenAvailable(self) -> None:
		messageModule = types.ModuleType("gui.message")
		messageModule.DialogType = types.SimpleNamespace(ERROR="error", STANDARD="standard")
		messageModule.MessageDialog = mock.Mock()
		with mock.patch.dict(sys.modules, {"gui.message": messageModule}):
			self.module.NativeSpeechDialog._showMessage(self.dialog, "Fix input", "Error", isError=True)
		messageModule.MessageDialog.assert_called_once_with(
			self.dialog,
			"Fix input",
			"Error",
			dialogType="error",
		)
		messageModule.MessageDialog.return_value.ShowModal.assert_called_once()
		self.module.gui.messageBox.assert_not_called()

	def testValidationMessageSupportsOlderNvda(self) -> None:
		with mock.patch.dict(sys.modules, {"gui.message": None}):
			self.module.NativeSpeechDialog._showMessage(self.dialog, "Fix input", "Error", isError=True)
		self.module.gui.messageBox.assert_called_once_with("Fix input", "Error", 3, parent=self.dialog)

	def testRequestBuildingErrorIsTranslatedAndFocusesVoice(self) -> None:
		self.dialog.voiceChoiceMulti1 = mock.Mock()
		error = self.module.SpeechInputError("voiceCount")
		self.dialog._reportSpeechInputError(error)
		message = self.dialog._showMessage.call_args.args[0]
		self.assertNotIn("voiceCount", message)
		self.assertIn("voice", message)
		self.dialog.voiceChoiceMulti1.SetFocus.assert_called_once()

	def testCloseWaitsForOpenLibraryBeforeDestroying(self) -> None:
		library = mock.Mock()
		self.dialog._libraryDialog = library
		self.dialog._finalizeClose = mock.Mock()
		self.dialog.onClose(mock.Mock())
		self.assertTrue(self.dialog.isClosed)
		library.requestClose.assert_called_once()
		self.dialog._finalizeClose.assert_not_called()


if __name__ == "__main__":
	unittest.main()
