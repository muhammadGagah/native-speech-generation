from __future__ import annotations

import base64
import importlib
import io
import json
import tempfile
import unittest
import urllib.error
import urllib.request
import wave
from pathlib import Path
from typing import Any
from unittest import mock

import test_voice_library as voiceLibraryTests
from test_tts_generation import PACKAGE_NAME, loadCore, translate


def recording(seconds: int = 10, rate: int = 24000, channels: int = 1) -> bytes:
	stream = io.BytesIO()
	with wave.open(stream, "wb") as audio:
		audio.setnchannels(channels)
		audio.setsampwidth(2)
		audio.setframerate(rate)
		audio.writeframes(b"\x00\x00" * seconds * rate * channels)
	return stream.getvalue()


class ReplicationApiTests(unittest.TestCase):
	module: Any = None
	directory: Any = None
	source: str = ""
	consent: str = ""

	def setUp(self) -> None:
		loadCore()
		self.module = importlib.import_module(f"{PACKAGE_NAME}.voice_replication")
		self.directory = tempfile.TemporaryDirectory()
		self.addCleanup(self.directory.cleanup)
		self.source = str(Path(self.directory.name) / "source.wav")
		self.consent = str(Path(self.directory.name) / "consent.wav")
		Path(self.source).write_bytes(recording())
		Path(self.consent).write_bytes(recording(5))

	def create(self, model: str = "gemini-3.8-flash-tts") -> Any:
		return self.module.createReplicatedVoice("secret", model, " Speaker ", self.source, self.consent)

	def testBothModelsSubmitTwoRecordingsAndStoreOnlyMetadata(self) -> None:
		for model in ("gemini-3.8-flash-tts", "gemini-3.8-flash-lite-tts"):
			body = b'{"id":"voice_new","type":"replicated","key":"private","sample_audio":{}}'
			with mock.patch.object(urllib.request, "urlopen", return_value=io.BytesIO(body)) as post:
				voice = self.create(model)
			post.assert_called_once()
			request = post.call_args.args[0]
			self.assertEqual(request.method, "POST")
			self.assertEqual(request.get_header("User-agent"), "NativeSpeechGeneration-NVDA-Addon")
			self.assertEqual(request.get_header("X-goog-api-key"), "secret")
			self.assertNotIn("secret", request.full_url)
			payload = json.loads(request.data)
			self.assertTrue(payload["store"])
			self.assertEqual(payload["voice"]["model"], model)
			self.assertEqual(payload["voice"]["type"], "replicated")
			self.assertEqual(payload["voice"]["display_name"], "Speaker")
			for field, path in (("source_audio", self.source), ("consent_audio", self.consent)):
				clip = payload["voice"]["replicated"][field]
				self.assertEqual(clip["mime_type"], "audio/wav")
				self.assertEqual(base64.b64decode(clip["data"]), Path(path).read_bytes())
			self.assertEqual((voice.id, voice.type), ("voice_new", "replicated"))
			self.assertNotIn("private", repr(voice))

	def testInvalidRecordingsNeverUpload(self) -> None:
		for invalid in (
			b"bad wav",
			recording(9),
			recording(31),
			recording(rate=22050),
			recording(channels=2),
			recording()[:-2],
		):
			Path(self.source).write_bytes(invalid)
			with mock.patch.object(urllib.request, "urlopen") as post:
				with self.assertRaises(self.module.RecordingError) as caught:
					self.create()
				self.assertEqual(caught.exception.field, "source")
				post.assert_not_called()

	def testConsentMustAlsoBeReadableAndWithinLocalLimit(self) -> None:
		for invalid in (b"", recording(61)):
			Path(self.consent).write_bytes(invalid)
			with mock.patch.object(urllib.request, "urlopen") as post:
				with self.assertRaises(self.module.RecordingError) as caught:
					self.create()
				self.assertEqual(caught.exception.field, "consent")
				post.assert_not_called()

	def testMissingOrOversizeFileIsRejected(self) -> None:
		Path(self.source).unlink()
		with self.assertRaises(self.module.RecordingError):
			self.create()
		Path(self.source).write_bytes(b"x" * (self.module.MAX_RECORDING_BYTES + 1))
		with self.assertRaises(self.module.RecordingError):
			self.create()

	def testNoRetryAndNoSensitiveErrorText(self) -> None:
		for error in (TimeoutError("secret"), urllib.error.HTTPError("secret", 403, "private", {}, None)):
			with mock.patch.object(urllib.request, "urlopen", side_effect=error) as post:
				with self.assertRaises(self.module.DirectApiError) as caught:
					self.create()
				post.assert_called_once()
				self.assertNotIn("secret", str(caught.exception))

	def testOversizeResponseIsRejected(self) -> None:
		library = importlib.import_module(f"{PACKAGE_NAME}.voice_library")
		body = b" " * (library.MAX_SAMPLE_BYTES + 1)
		with (
			mock.patch.object(urllib.request, "urlopen", return_value=io.BytesIO(body)),
			self.assertRaises(self.module.DirectApiError),
		):
			self.create()

	def testMalformedResponsesDoNotInventVoice(self) -> None:
		for body in (b"{}", b"[]", b"bad", b'{"id":"voice_"}', b'{"id":"voice_new","type":"prompted"}'):
			with (
				mock.patch.object(urllib.request, "urlopen", return_value=io.BytesIO(body)),
				self.assertRaises(self.module.DirectApiError),
			):
				self.create()


class ReplicationFlowTests(unittest.TestCase):
	module: Any = None
	dialog: Any = None

	def setUp(self) -> None:
		fixture = voiceLibraryTests.BrowserStateTests()
		fixture.setUp()
		self.module, self.dialog = fixture.module, fixture.dialog

	def testOwnerCloseUnwindsNestedFormBeforeEndingLibrary(self) -> None:
		child = mock.Mock()
		self.dialog._childDialog = child
		self.dialog.requestClose()
		child.requestClose.assert_called_once()
		self.dialog.EndModal.assert_not_called()
		self.dialog._childDialog = None
		self.dialog._afterChildDialog()
		self.dialog.EndModal.assert_called_once_with(self.module.wx.ID_CANCEL)
		self.dialog.newVoiceBtn.SetFocus.assert_not_called()

	def testOwnerCloseWithoutNestedFormEndsImmediately(self) -> None:
		self.dialog.requestClose()
		self.dialog.EndModal.assert_called_once_with(self.module.wx.ID_CANCEL)

	def testCancelDoesNotSubmitAndReturnsFocus(self) -> None:
		with (
			mock.patch.object(self.module, "VoiceReplicationDialog") as form,
			mock.patch.object(self.module.threading, "Thread") as worker,
		):
			form.return_value.ShowModal.return_value = self.module.wx.ID_CANCEL
			self.dialog.onReplicateVoice(None)
			worker.assert_not_called()
			form.return_value.Destroy.assert_called_once()
		self.dialog.newVoiceBtn.SetFocus.assert_called_once()

	def testSubmissionBlocksDuplicateAndDesignCreation(self) -> None:
		with (
			mock.patch.object(self.module, "VoiceReplicationDialog") as form,
			mock.patch.object(self.module.threading, "Thread") as worker,
		):
			form.return_value.ShowModal.return_value = self.module.wx.ID_OK
			form.return_value.replication = ("Speaker", "source.wav", "consent.wav")
			self.dialog.onReplicateVoice(None)
			self.dialog.onReplicateVoice(None)
			self.dialog.onNewVoice(None)
			self.dialog.onRefresh(None)
			worker.assert_called_once()
		self.assertTrue(self.dialog._isCreating)
		self.assertEqual(self.dialog._loadId, 2)

	def testWorkerDispatchesSuccessAndValidationFailure(self) -> None:
		voice = self.module.Voice("voice_new", "Speaker", "replicated")
		with mock.patch.object(self.module, "createReplicatedVoice", return_value=voice):
			self.dialog._replicateWorker(("Speaker", "source.wav", "consent.wav"))
		self.module.wx.CallAfter.assert_called_with(self.dialog._voiceCreated, voice)
		with mock.patch.object(
			self.module,
			"createReplicatedVoice",
			side_effect=self.module.RecordingError("consent"),
		):
			self.dialog._replicateWorker(("Speaker", "source.wav", "consent.wav"))
		self.module.wx.CallAfter.assert_called_with(self.dialog._recordingFailed, "consent")

	def testCreatedReplicationOffersManualPreview(self) -> None:
		self.dialog._voiceCreated(self.module.Voice("voice_new", "Speaker", "replicated"))
		self.assertIn("Generate preview", self.dialog.statusCtrl.ChangeValue.call_args.args[0])
		self.module.winsound.PlaySound.assert_not_called()
		self.assertIsNone(self.dialog.selectedVoice)

	def testLateValidationFailureDoesNotTouchClosedControls(self) -> None:
		self.dialog._closed = True
		self.dialog._recordingFailed("source")
		self.dialog.statusCtrl.ChangeValue.assert_not_called()
		self.assertFalse(self.dialog._isCreating)

	def testFormRequiresConsentBeforeAccepting(self) -> None:
		formClass = self.module.VoiceReplicationDialog
		formClass.onCreate.__globals__["_"] = translate
		form = object.__new__(formClass)
		for attr, value in (
			("nameCtrl", "Speaker"),
			("sourceCtrl", "source.wav"),
			("consentCtrl", "consent.wav"),
		):
			control = mock.Mock()
			control.GetValue.return_value = value
			setattr(form, attr, control)
		form.confirmCtrl = mock.Mock()
		form.confirmCtrl.GetValue.return_value = False
		form.EndModal = mock.Mock()
		with mock.patch("os.path.isfile", return_value=True):
			form.onCreate(None)
			form.EndModal.assert_not_called()
			form.confirmCtrl.SetFocus.assert_called_once()
			form.confirmCtrl.GetValue.return_value = True
			form.onCreate(None)
		self.assertEqual(form.replication, ("Speaker", "source.wav", "consent.wav"))
		form.EndModal.assert_called_once_with(self.module.wx.ID_OK)
