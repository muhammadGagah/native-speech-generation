from __future__ import annotations

import importlib
import io
import json
import tempfile
import unittest
import urllib.error
import urllib.request
from typing import Any
from unittest import mock

import test_voice_library as voiceLibraryTests
from test_tts_generation import PACKAGE_NAME, loadCore, translate


class VoiceDesignApiTests(unittest.TestCase):
	module: Any = None

	def setUp(self) -> None:
		loadCore()
		self.module = importlib.import_module(f"{PACKAGE_NAME}.voice_design")

	def testCreateUsesOneExplicitStoredPostWithMetadata(self) -> None:
		response = {"id": "voice_123", "type": "prompted", "display_name": "Narrator", "sample_audio": {}}
		with mock.patch.object(
			urllib.request,
			"urlopen",
			return_value=io.BytesIO(json.dumps(response).encode()),
		) as post:
			voice = self.module.createDesignedVoice(
				"secret",
				"gemini-3.8-flash-tts",
				" Narrator ",
				" Warm and calm. ",
				"id-ID",
				"male",
			)
		post.assert_called_once()
		request = post.call_args.args[0]
		self.assertEqual(request.method, "POST")
		self.assertEqual(request.get_header("X-goog-api-key"), "secret")
		self.assertNotIn("secret", request.full_url)
		self.assertEqual(
			json.loads(request.data),
			{
				"store": True,
				"voice": {
					"type": "prompted",
					"model": "gemini-3.8-flash-tts",
					"display_name": "Narrator",
					"prompted": {"input": "Warm and calm."},
					"language_code": "id-ID",
					"gender": "male",
				},
			},
		)
		self.assertEqual((voice.id, voice.type, voice.language), ("voice_123", "prompted", "id-ID"))

	def testInvalidInputDoesNotSubmit(self) -> None:
		for name, description, language in (
			("", "warm", ""),
			("Name", "", ""),
			("Name", "x" * 2001, ""),
			("Name", "warm", "bad tag"),
		):
			with mock.patch.object(urllib.request, "urlopen") as post:
				with self.assertRaises(ValueError):
					self.module.createDesignedVoice(
						"key",
						"gemini-3.8-flash-tts",
						name,
						description,
						language,
					)
				post.assert_not_called()

	def testTimeoutAndHttpFailureNeverRetryOrExposeRequest(self) -> None:
		for error in (TimeoutError("secret"), urllib.error.HTTPError("secret", 429, "secret", {}, None)):
			with mock.patch.object(urllib.request, "urlopen", side_effect=error) as post:
				with self.assertRaises(self.module.DirectApiError) as caught:
					self.module.createDesignedVoice(
						"secret",
						"gemini-3.8-flash-tts",
						"Name",
						"private description",
					)
				post.assert_called_once()
				self.assertNotIn("secret", str(caught.exception))
				self.assertNotIn("private description", str(caught.exception))

	def testInvalidResponseNeverInventsVoiceId(self) -> None:
		for body in (b"{}", b'{"id":"Kore"}', b"not json", b'{"id":"voice_123","type":"prebuilt"}'):
			with (
				mock.patch.object(urllib.request, "urlopen", return_value=io.BytesIO(body)),
				self.assertRaises(self.module.DirectApiError),
			):
				self.module.createDesignedVoice("key", "gemini-3.8-flash-tts", "Name", "warm")

	def testOptionalMetadataOmittedAndLiteModelPreserved(self) -> None:
		with mock.patch.object(
			urllib.request,
			"urlopen",
			return_value=io.BytesIO(b'{"id":"voice_one"}'),
		) as post:
			self.module.createDesignedVoice("key", "gemini-3.8-flash-lite-tts", "Name", "Warm")
		payload = json.loads(post.call_args.args[0].data)
		self.assertNotIn("gender", payload["voice"])
		self.assertNotIn("language_code", payload["voice"])
		self.assertEqual(payload["voice"]["model"], "gemini-3.8-flash-lite-tts")

	def testCreatedVoiceDoesNotMakePartialCacheFresh(self) -> None:
		library = importlib.import_module(f"{PACKAGE_NAME}.voice_library")
		with tempfile.TemporaryDirectory() as directory:
			store = library.VoiceLibraryStore("key", directory)
			voice = library.Voice("voice_123", "Name", "prompted")
			self.assertTrue(store.rememberCreatedVoice(voice))
			self.assertEqual(store.readCatalog(), ([voice], False))
			store.writeCatalog([voice, library.Voice("Kore", "Kore")])
			store.rememberCreatedVoice(voice)
			self.assertEqual(len(store.readCatalog()[0]), 2)
			self.assertTrue(store.readCatalog()[1])

	def testCreatedVoiceDoesNotExtendFreshCatalogLifetime(self) -> None:
		library = importlib.import_module(f"{PACKAGE_NAME}.voice_library")
		with tempfile.TemporaryDirectory() as directory:
			store = library.VoiceLibraryStore("key", directory)
			fetchedAt = library.time.time() - library.CACHE_TTL + 60
			with mock.patch.object(library.time, "time", return_value=fetchedAt):
				store.writeCatalog([library.Voice("Kore", "Kore")])
			self.assertTrue(store.rememberCreatedVoice(library.Voice("voice_123", "Name", "prompted")))
			self.assertEqual(store._read("voices")["fetchedAt"], fetchedAt)
			with mock.patch.object(library.time, "time", return_value=fetchedAt + library.CACHE_TTL + 1):
				self.assertFalse(store.readCatalog()[1])


class VoiceRemixApiTests(unittest.TestCase):
	module: Any = None
	library: Any = None

	def setUp(self) -> None:
		loadCore()
		self.module = importlib.import_module(f"{PACKAGE_NAME}.voice_design")
		self.library = importlib.import_module(f"{PACKAGE_NAME}.voice_library")

	def testRemixPostsBaseVoiceAndInstructionsOnce(self) -> None:
		base = self.library.Voice("Puck", "Puck", language="en-US", accent="American")
		response = {"id": "voice_mix", "type": "prompted", "accent": "British", "sample_audio": {}}
		with mock.patch.object(
			urllib.request,
			"urlopen",
			return_value=io.BytesIO(json.dumps(response).encode()),
		) as post:
			voice = self.module.createRemixedVoice("secret", base, " Older Puck ", " Older, British accent ")
		post.assert_called_once()
		request = post.call_args.args[0]
		self.assertEqual(request.method, "POST")
		self.assertTrue(request.full_url.endswith("/voices"))
		self.assertEqual(request.get_header("X-goog-api-key"), "secret")
		self.assertEqual(request.get_header("User-agent"), "NativeSpeechGeneration-NVDA-Addon")
		payload = json.loads(request.data)
		self.assertEqual(
			payload,
			{
				"store": True,
				"voice": {
					"type": "prompted",
					"model": "gemini-3.8-flash-tts",
					"prompted": {"base_voice": "Puck", "input": "Older, British accent"},
					"display_name": "Older Puck",
				},
			},
		)
		self.assertEqual(
			(voice.id, voice.type, voice.displayName, voice.language, voice.accent),
			("voice_mix", "prompted", "Older Puck", "en-US", "British"),
		)

	def testBlankNameIsOmittedAndIdIsShown(self) -> None:
		base = self.library.Voice("voice_designed", "Narrator", "prompted")
		with mock.patch.object(
			urllib.request,
			"urlopen",
			return_value=io.BytesIO(b'{"id":"voice_mix2"}'),
		) as post:
			voice = self.module.createRemixedVoice("key", base, "  ", "Slower pacing")
		payload = json.loads(post.call_args.args[0].data)
		self.assertNotIn("display_name", payload["voice"])
		self.assertEqual(payload["voice"]["prompted"]["base_voice"], "voice_designed")
		self.assertEqual(voice.displayName, "voice_mix2")

	def testInvalidRemixNeverSubmits(self) -> None:
		replicated = self.library.Voice("voice_clone", "Clone", "replicated")
		prebuilt = self.library.Voice("Kore", "Kore")
		for base, name, instructions in (
			(replicated, "", "Older"),
			(prebuilt, "", "   "),
			(prebuilt, "x" * 101, "Older"),
			(prebuilt, "", "x" * 2001),
		):
			with mock.patch.object(urllib.request, "urlopen") as post:
				with self.assertRaises(ValueError):
					self.module.createRemixedVoice("key", base, name, instructions)
				post.assert_not_called()

	def testRemixResponseMustBeNewPromptedVoice(self) -> None:
		base = self.library.Voice("Kore", "Kore")
		for body in (b"{}", b'{"id":"Kore"}', b'{"id":"voice_x","type":"replicated"}', b"bad"):
			with (
				mock.patch.object(urllib.request, "urlopen", return_value=io.BytesIO(body)),
				self.assertRaises(self.module.DirectApiError),
			):
				self.module.createRemixedVoice("key", base, "", "Older")


class VoiceRemixFlowTests(unittest.TestCase):
	module: Any = None
	dialog: Any = None

	def setUp(self) -> None:
		fixture = voiceLibraryTests.BrowserStateTests()
		fixture.setUp()
		self.module = fixture.module
		self.dialog = fixture.dialog

	def testCancelDoesNotSubmitAndReturnsFocus(self) -> None:
		with (
			mock.patch.object(self.module, "VoiceRemixDialog") as form,
			mock.patch.object(self.module.threading, "Thread") as worker,
		):
			form.return_value.ShowModal.return_value = self.module.wx.ID_CANCEL
			self.dialog.onRemixVoice(None)
			form.assert_called_once_with(self.dialog, "One")
			worker.assert_not_called()
			form.return_value.Destroy.assert_called_once()
		self.dialog.remixBtn.SetFocus.assert_called_once()

	def testSubmissionUsesSelectedBaseAndBlocksDuplicates(self) -> None:
		with (
			mock.patch.object(self.module, "VoiceRemixDialog") as form,
			mock.patch.object(self.module.threading, "Thread") as worker,
		):
			form.return_value.ShowModal.return_value = self.module.wx.ID_OK
			form.return_value.remix = ("", "Older")
			self.dialog.onRemixVoice(None)
			self.dialog.onRemixVoice(None)
			worker.assert_called_once()
			self.assertEqual(worker.call_args.kwargs["args"], (self.dialog.voices[0], "", "Older"))
		self.assertTrue(self.dialog._isCreating)

	def testReplicatedVoiceCannotBeRemixed(self) -> None:
		self.dialog.voices = [self.module.Voice("voice_clone", "Clone", "replicated")]
		self.dialog.visibleVoices = list(self.dialog.voices)
		with mock.patch.object(self.module, "VoiceRemixDialog") as form:
			self.dialog.onRemixVoice(None)
			form.assert_not_called()
		self.dialog._updateDetails()
		self.dialog.remixBtn.Enable.assert_called_with(False)

	def testWorkerDispatchesSuccessAndFailure(self) -> None:
		base = self.module.Voice("Kore", "Kore")
		created = self.module.Voice("voice_mix", "Mix", "prompted")
		with mock.patch.object(self.module, "createRemixedVoice", return_value=created):
			self.dialog._remixWorker(base, "", "Older")
		self.module.wx.CallAfter.assert_called_with(self.dialog._voiceCreated, created)
		with mock.patch.object(
			self.module,
			"createRemixedVoice",
			side_effect=self.module.DirectApiError("x"),
		):
			self.dialog._remixWorker(base, "", "Older")
		self.module.wx.CallAfter.assert_called_with(self.dialog._createFailed)


class VoiceDesignFlowTests(unittest.TestCase):
	module: Any = None
	dialog: Any = None

	def setUp(self) -> None:
		fixture = voiceLibraryTests.BrowserStateTests()
		fixture.setUp()
		self.module = fixture.module
		self.dialog = fixture.dialog

	def testNewVoiceCancelDoesNotCreateAndReturnsFocus(self) -> None:
		with (
			mock.patch.object(self.module, "VoiceDesignDialog") as form,
			mock.patch.object(self.module.threading, "Thread") as worker,
		):
			form.return_value.ShowModal.return_value = self.module.wx.ID_CANCEL
			self.dialog.onDesignVoice(mock.Mock())
			worker.assert_not_called()
			form.return_value.Destroy.assert_called_once()
		self.dialog.newVoiceBtn.SetFocus.assert_called_once()

	def testChooserRoutesBothMethodsWithoutSubmitting(self) -> None:
		for voiceType, handler in (("prompted", "onDesignVoice"), ("replicated", "onReplicateVoice")):
			with (
				mock.patch.object(self.module, "NewVoiceDialog") as chooser,
				mock.patch.object(self.dialog, "onDesignVoice") as design,
				mock.patch.object(self.dialog, "onReplicateVoice") as replication,
				mock.patch.object(self.module.threading, "Thread") as worker,
			):
				chooser.return_value.ShowModal.return_value = self.module.wx.ID_OK
				chooser.return_value.voiceType = voiceType
				self.dialog.onNewVoice(None)
				getattr(self.dialog, handler).assert_called_once_with(None)
				(design if voiceType == "replicated" else replication).assert_not_called()
				worker.assert_not_called()
				chooser.return_value.Destroy.assert_called_once()

	def testChooserCancelReturnsFocusWithoutOpeningForms(self) -> None:
		with (
			mock.patch.object(self.module, "NewVoiceDialog") as chooser,
			mock.patch.object(self.module, "VoiceDesignDialog") as design,
			mock.patch.object(self.module, "VoiceReplicationDialog") as replication,
		):
			chooser.return_value.ShowModal.return_value = self.module.wx.ID_CANCEL
			self.dialog.onNewVoice(None)
			design.assert_not_called()
			replication.assert_not_called()
		self.dialog.newVoiceBtn.SetFocus.assert_called_once()

	def testChooserDoesNotOpenDuringCreationOrAfterClose(self) -> None:
		with mock.patch.object(self.module, "NewVoiceDialog") as chooser:
			self.dialog._isCreating = True
			self.dialog.onNewVoice(None)
			self.dialog._isCreating = False
			self.dialog._closed = True
			self.dialog.onNewVoice(None)
			chooser.assert_not_called()

	def testNewVoiceStartsOnceAndInvalidatesOldCatalog(self) -> None:
		design = ("Name", "Calm voice", "id-ID", "")
		with (
			mock.patch.object(self.module, "VoiceDesignDialog") as form,
			mock.patch.object(self.module.threading, "Thread") as worker,
		):
			form.return_value.ShowModal.return_value = self.module.wx.ID_OK
			form.return_value.design = design
			self.dialog.onDesignVoice(mock.Mock())
			self.dialog.onDesignVoice(mock.Mock())
			self.dialog.onRefresh(None)
			worker.assert_called_once_with(target=self.dialog._createWorker, args=(design,), daemon=True)
		self.assertTrue(self.dialog._isCreating)
		self.assertEqual(self.dialog._loadId, 2)

	def testCreatedVoiceBecomesVisibleWithoutApplyingOrPlaying(self) -> None:
		voice = self.module.Voice("voice_new", "New", "prompted", "id-ID")
		self.dialog._voiceCreated(voice)
		self.assertEqual(self.dialog._selected().id, "voice_new")
		self.assertIsNone(self.dialog.selectedVoice)
		self.dialog.EndModal.assert_not_called()
		self.dialog.store.rememberCreatedVoice.assert_called_once_with(voice)
		self.module.winsound.PlaySound.assert_not_called()

	def testLateCreationIsSavedWithoutTouchingClosedControls(self) -> None:
		self.dialog._closed = True
		voice = self.module.Voice("voice_new", "New", "prompted")
		self.dialog._voiceCreated(voice)
		self.dialog.store.rememberCreatedVoice.assert_called_once_with(voice)
		self.dialog.results.Set.assert_not_called()
		self.dialog.statusCtrl.ChangeValue.assert_not_called()

	def testFailureRecommendsRefreshWithoutRetry(self) -> None:
		self.dialog._isCreating = True
		with mock.patch.object(self.module.threading, "Thread") as worker:
			self.dialog._createFailed()
			worker.assert_not_called()
		self.assertFalse(self.dialog._isCreating)
		self.assertIn("Refresh", self.dialog.statusCtrl.ChangeValue.call_args.args[0])

	def testCreationWorkerQueuesSuccessOnGuiThread(self) -> None:
		design = ("Name", "Warm", "id-ID", "female")
		voice = self.module.Voice("voice_new", "Name", "prompted")
		self.module.wx.CallAfter.reset_mock()
		with mock.patch.object(self.module, "createDesignedVoice", return_value=voice) as create:
			self.dialog._createWorker(design)
			create.assert_called_once_with("key", self.dialog.model, *design)
		self.module.wx.CallAfter.assert_called_once_with(self.dialog._voiceCreated, voice)

	def testFormAcceptsValidatedDesignWithoutNetwork(self) -> None:
		self.module.VoiceDesignDialog.onCreate.__globals__["_"] = translate
		form = object.__new__(self.module.VoiceDesignDialog)
		for attr, value in (("nameCtrl", " Name "), ("descriptionCtrl", " Warm "), ("languageCtrl", "id-ID")):
			control = mock.Mock()
			control.GetValue.return_value = value
			setattr(form, attr, control)
		form.genderChoice = mock.Mock()
		form.genderChoice.GetSelection.return_value = 1
		form.EndModal = mock.Mock()
		form.onCreate(mock.Mock())
		self.assertEqual(form.design, ("Name", "Warm", "id-ID", "female"))
		form.EndModal.assert_called_once_with(self.module.wx.ID_OK)

	def testFormValidationFocusesRequiredField(self) -> None:
		self.module.VoiceDesignDialog.onCreate.__globals__["_"] = translate
		form = object.__new__(self.module.VoiceDesignDialog)
		form.nameCtrl = mock.Mock()
		form.nameCtrl.GetValue.return_value = ""
		form.descriptionCtrl = mock.Mock()
		form.descriptionCtrl.GetValue.return_value = "Warm"
		form.languageCtrl = mock.Mock()
		form.languageCtrl.GetValue.return_value = ""
		form.EndModal = mock.Mock()
		form.onCreate(mock.Mock())
		form.nameCtrl.SetFocus.assert_called_once()
		form.EndModal.assert_not_called()
