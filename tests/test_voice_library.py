from __future__ import annotations

import base64
import importlib
import io
import json
import sys
import tempfile
import types
import unittest
import urllib.error
from pathlib import Path
from typing import Any
from unittest import mock

from test_tts_generation import (
	ADDON_PACKAGE,
	PACKAGE_NAME,
	loadCore,
	loadDialog,
	translate,
	wavAudio,
)


def _library() -> Any:
	loadCore()
	return importlib.import_module(f"{PACKAGE_NAME}.voice_library")


def _browser() -> Any:
	main = loadDialog()
	packageName = "nsg_voice_browser_test"
	stubs: dict[str, Any] = {"wx": main.wx, "ui": main.ui, "gui": main.gui}
	for name, path in (
		(packageName, ADDON_PACKAGE),
		(f"{packageName}.core", ADDON_PACKAGE / "core"),
		(f"{packageName}.interface", ADDON_PACKAGE / "interface"),
	):
		package = types.ModuleType(name)
		package.__path__ = [str(path)]
		stubs[name] = package
	addonHandler = types.ModuleType("addonHandler")
	addonHandler.initTranslation = lambda: None
	stubs["addonHandler"] = addonHandler
	helper = types.ModuleType("gui.guiHelper")
	helper.BoxSizerHelper = mock.Mock()
	stubs["gui.guiHelper"] = helper
	winsound = types.ModuleType("winsound")
	winsound.PlaySound = mock.Mock()
	winsound.SND_FILENAME = 1
	winsound.SND_ASYNC = 2
	stubs["winsound"] = winsound
	speech = types.ModuleType("speech")
	speech.cancelSpeech = mock.Mock()
	stubs["speech"] = speech
	main.wx.WXK_SPACE = 32
	main.wx.WXK_RETURN = 13
	main.wx.WXK_NUMPAD_ENTER = 370
	main.wx.ID_OK = 5100
	main.wx.ID_CANCEL = 5101
	main.wx.CallAfter = mock.Mock()
	with mock.patch.dict(sys.modules, stubs):
		module = importlib.import_module(f"{packageName}.interface.voice_library_dialog")
		module._ = translate
		return module


class VoiceCatalogTests(unittest.TestCase):
	library: Any = None

	def setUp(self) -> None:
		self.library = _library()

	def testPagesAreCombinedByStableId(self) -> None:
		with mock.patch.object(
			self.library,
			"_getCatalogPage",
			side_effect=[
				{
					"voices": [{"id": "one", "display_name": "Same", "type": "prompted"}],
					"next_page_token": "a +&",
				},
				{"voices": [{"id": "two", "display_name": "Same"}, {"id": "one", "display_name": "Renamed"}]},
			],
		) as page:
			voices = self.library.fetchVoices("secret")
		self.assertEqual([(v.id, v.displayName) for v in voices], [("one", "Renamed"), ("two", "Same")])
		self.assertEqual(page.call_args_list[1].args, ("secret", "a +&"))

	def testGetUsesHeaderForKeyAndEncodesPagination(self) -> None:
		with mock.patch.object(
			self.library.urllib.request,
			"urlopen",
			return_value=io.BytesIO(b'{"voices": []}'),
		) as request:
			self.library._getCatalogPage("secret-key", "a +&")
		req = request.call_args.args[0]
		self.assertEqual(req.method, "GET")
		self.assertNotIn("secret-key", req.full_url)
		self.assertEqual(req.get_header("X-goog-api-key"), "secret-key")
		self.assertIn("page_token=a+%2B%26", req.full_url)

	def testRepeatedTokenAndInvalidResponsesAreRejected(self) -> None:
		for response in (
			{"voices": [], "next_page_token": "same"},
			{"voices": "invalid"},
			{"voices": [{"display_name": "Missing ID"}]},
		):
			with (
				self.subTest(response=response),
				mock.patch.object(self.library, "_getCatalogPage", return_value=response),
				self.assertRaises(self.library.DirectApiError),
			):
				self.library.fetchVoices("key")

	def testCatalogPageReadIsBounded(self) -> None:
		body = b" " * (self.library.MAX_SAMPLE_BYTES + 1)
		with (
			mock.patch.object(self.library.urllib.request, "urlopen", return_value=io.BytesIO(body)),
			self.assertRaises(self.library.DirectApiError),
		):
			self.library._getCatalogPage("secret-key", "")

	def testFailedLaterPageDoesNotReturnPartialCatalog(self) -> None:
		with (
			mock.patch.object(
				self.library,
				"_getCatalogPage",
				side_effect=[
					{"voices": [{"id": "one"}], "next_page_token": "two"},
					self.library.DirectApiError("offline"),
				],
			),
			self.assertRaises(self.library.DirectApiError),
		):
			self.library.fetchVoices("key")

	def testSearchMatchesMetadataAndType(self) -> None:
		voices = [
			self.library.Voice("one", "Warm narrator", "prompted", "id-ID", "Jakarta"),
			self.library.Voice("two", "Warm narrator", "prebuilt", "en-US"),
		]
		self.assertEqual(self.library.filterVoices(voices, "ID-id warm", "prompted"), voices[:1])
		self.assertEqual(self.library.filterVoices(voices, "Jakarta", "prebuilt"), [])

	def testLanguageFilterCombinesWithSearchAndType(self) -> None:
		voices = [
			self.library.Voice("one", "Warm", "prompted", "id-ID"),
			self.library.Voice("two", "Warm", "prebuilt", "id-ID"),
			self.library.Voice("three", "Warm", "prompted", "id"),
			self.library.Voice("four", "Warm", "prompted", ""),
		]
		self.assertEqual(self.library.filterVoices(voices, "warm", "prompted", "ID-id"), voices[:1])
		self.assertEqual(self.library.filterVoices(voices, languageCode=""), voices[3:])
		self.assertEqual(self.library.filterVoices(voices, languageCode=None), voices)
		self.assertEqual(self.library.filterVoices(voices, languageCode="en-US"), [])

	def testCacheScopesKeysAndPreservesMetadataAndSelections(self) -> None:
		with tempfile.TemporaryDirectory() as directory:
			first = self.library.VoiceLibraryStore("secret-one", directory)
			second = self.library.VoiceLibraryStore("secret-two", directory)
			voice = self.library.Voice("voice_1", "Suara Indonesia", "prompted", "id-ID")
			self.assertTrue(first.writeCatalog([voice]))
			self.assertTrue(first.writeSelections({"speaker2": voice}))
			self.assertEqual(first.readCatalog(), ([voice], True))
			self.assertEqual(first.readSelections(), {"speaker2": voice})
			self.assertEqual(second.readCatalog(), ([], False))
			self.assertEqual(second.readSelections(), {})
			for path in Path(directory).rglob("*.json"):
				self.assertNotIn("secret-one", path.read_text(encoding="utf-8"))
				self.assertNotIn("secret-one", path.name)

	def testExtendedMetadataLoadedAndFiltersCombine(self) -> None:
		with mock.patch.object(
			self.library,
			"_getCatalogPage",
			return_value={
				"voices": [
					{
						"id": "de-de-advisor-1",
						"display_name": "Advisor",
						"language_code": "de-DE",
						"gender": "female",
						"pitch": "low",
						"persona": "Warm, Friendly",
						"context": "News",
					},
				],
			},
		):
			voices = self.library.fetchVoices("key")
		self.assertEqual(voices[0].pitch, "low")
		self.assertEqual(voices[0].persona, "Warm, Friendly")
		self.assertEqual(voices[0].context, "News")
		self.assertEqual(
			self.library.filterVoices(
				voices,
				"news",
				"prebuilt",
				"de-DE",
				gender=" FEMALE ",
				pitch="LOW",
				persona="warm, friendly",
				context="news",
			),
			voices,
		)
		self.assertEqual(self.library.filterVoices(voices, gender="male"), [])
		self.assertEqual(self.library.filterVoices(voices, persona="warm"), [])
		self.assertEqual(self.library.filterVoices(voices, pitch=""), [])
		missing = self.library.Voice("missing", "Missing")
		self.assertEqual(self.library.filterVoices([missing], pitch="", persona="", context=""), [missing])

	def testOldCacheLoadsButRequiresMetadataRefreshAndPreservesSelections(self) -> None:
		with tempfile.TemporaryDirectory() as directory:
			store = self.library.VoiceLibraryStore("key", directory)
			old = {"id": "one", "displayName": "One"}
			store._write("voices", {"fetchedAt": self.library.time.time(), "voices": [old]})
			store._write("selections", {"single": old})
			voices, fresh = store.readCatalog()
			self.assertFalse(fresh)
			self.assertEqual(voices[0].pitch, "")
			self.assertEqual(store.readSelections()["single"].id, "one")
			updated = self.library.Voice("one", "One", pitch="high", persona="Bright", context="News")
			store.writeCatalog([updated])
			self.assertEqual(store.readCatalog(), ([updated], True))

	def testExpiredCorruptAndDisabledCache(self) -> None:
		with tempfile.TemporaryDirectory() as directory:
			store = self.library.VoiceLibraryStore("key", directory)
			voice = self.library.Voice("one", "One")
			with mock.patch.object(self.library.time, "time", return_value=1):
				store.writeCatalog([voice])
			self.assertEqual(store.readCatalog(), ([voice], False))
			file = next(Path(directory).rglob("voices-*.json"))
			file.write_text("invalid json", encoding="utf-8")
			self.assertEqual(store.readCatalog(), ([], False))
			disabled = self.library.VoiceLibraryStore("key", None)
			self.assertFalse(disabled.writeCatalog([voice]))
			self.assertFalse(disabled.writeSelections({"single": voice}))
			self.assertEqual(disabled.readSelections(), {})

	def testCacheWriteFailureLeavesPreviousCatalog(self) -> None:
		with tempfile.TemporaryDirectory() as directory:
			store = self.library.VoiceLibraryStore("key", directory)
			voice = self.library.Voice("one", "One")
			store.writeCatalog([voice])
			with mock.patch.object(self.library.os, "replace", side_effect=OSError("read only")):
				self.assertFalse(store.writeCatalog([]))
			self.assertEqual(store.readCatalog()[0], [voice])
			self.assertEqual(len(list((Path(directory) / "NativeSpeechGeneration").iterdir())), 1)


class VoiceSampleTests(unittest.TestCase):
	library: Any = None

	def setUp(self) -> None:
		self.library = _library()

	def testBuiltInSampleUsesKnownPublicUrlWithoutKey(self) -> None:
		with mock.patch.object(
			self.library.urllib.request,
			"urlopen",
			return_value=io.BytesIO(wavAudio()),
		) as get:
			self.assertEqual(
				self.library.fetchVoiceSample("secret", self.library.Voice("kore", "Kore")),
				wavAudio(),
			)
		request = get.call_args.args[0]
		self.assertEqual(request.method, "GET")
		self.assertTrue(request.full_url.endswith("/Kore.wav"))
		self.assertIsNone(request.get_header("X-goog-api-key"))

	def testDesignedSampleUsesAuthenticatedGetAndDecodesExistingAudio(self) -> None:
		voice = self.library.Voice("voice_a/b", "Designed", "prompted")
		response = json.dumps(
			{
				"id": voice.id,
				"sample_audio": {
					"mime_type": "audio/wav",
					"data": base64.b64encode(wavAudio()).decode("ascii"),
				},
			},
		).encode()
		with mock.patch.object(
			self.library.urllib.request,
			"urlopen",
			return_value=io.BytesIO(response),
		) as get:
			self.assertEqual(self.library.fetchVoiceSample("secret", voice), wavAudio())
		request = get.call_args.args[0]
		self.assertEqual(request.method, "GET")
		self.assertTrue(request.full_url.endswith("/voices/voice_a%2Fb"))
		self.assertEqual(request.get_header("X-goog-api-key"), "secret")

	def testExtendedSamplesUseVerifiedNamesWithoutKey(self) -> None:
		self.assertEqual(len(set(self.library.EXTENDED_SAMPLE_NAMES)), 40)
		for name in self.library.EXTENDED_SAMPLE_NAMES:
			with (
				self.subTest(name=name),
				mock.patch.object(
					self.library.urllib.request,
					"urlopen",
					return_value=io.BytesIO(wavAudio()),
				) as get,
			):
				self.library.fetchVoiceSample("secret", self.library.Voice(name, name))
				request = get.call_args.args[0]
				self.assertTrue(request.full_url.endswith(f"/daikon/en-us-{name.lower()}.wav"))
				self.assertIsNone(request.get_header("X-goog-api-key"))

	def testUnsupportedVoicesNeverIssueRequests(self) -> None:
		with mock.patch.object(self.library.urllib.request, "urlopen") as get:
			for voice in (
				self.library.Voice("unknown", "Kore"),
				self.library.Voice("Kore", "Clone", "replicated"),
				self.library.Voice("ar-eg-commercial-9", "Commercial Voiceover 9", language="ar-EG"),
				self.library.Voice("ar-eg-fola", "Fola", language="ar-EG"),
				self.library.Voice("voice_custom", "Fola", "replicated"),
			):
				self.assertIsNone(self.library.fetchVoiceSample("secret", voice))
			get.assert_not_called()

	def testExtendedCatalogIdsResolveWithoutDuplicatingLanguagePrefix(self) -> None:
		for name in self.library.EXTENDED_SAMPLE_NAMES:
			voiceId = f"en-us-{name.lower()}"
			with (
				self.subTest(voiceId=voiceId),
				mock.patch.object(
					self.library.urllib.request,
					"urlopen",
					return_value=io.BytesIO(wavAudio()),
				) as get,
			):
				voice = self.library.Voice(voiceId, name, language="en-US")
				self.assertEqual(self.library.fetchVoiceSample("secret", voice), wavAudio())
				request = get.call_args.args[0]
				self.assertEqual(request.full_url, f"{self.library.VOICE_SAMPLE_BASE}/daikon/{voiceId}.wav")
				self.assertIsNone(request.get_header("X-goog-api-key"))

	def testMissingSampleAnd404AreUnavailable(self) -> None:
		voice = self.library.Voice("voice_one", "One", "prompted")
		with mock.patch.object(
			self.library.urllib.request,
			"urlopen",
			return_value=io.BytesIO(b'{"id":"voice_one"}'),
		):
			self.assertIsNone(self.library.fetchVoiceSample("secret", voice))
		with mock.patch.object(
			self.library.urllib.request,
			"urlopen",
			side_effect=urllib.error.HTTPError("url", 404, "missing", {}, None),
		):
			self.assertIsNone(self.library.fetchVoiceSample("secret", voice))

	def testInvalidAudioAndAuthenticationFailuresAreErrors(self) -> None:
		voice = self.library.Voice("Kore", "Kore")
		with (
			mock.patch.object(self.library.urllib.request, "urlopen", return_value=io.BytesIO(b"not audio")),
			self.assertRaises(self.library.DirectApiError),
		):
			self.library.fetchVoiceSample("secret", voice)
		with (
			mock.patch.object(
				self.library.urllib.request,
				"urlopen",
				side_effect=urllib.error.HTTPError("url", 403, "denied", {}, None),
			),
			self.assertRaises(self.library.DirectApiError),
		):
			self.library.fetchVoiceSample("secret", voice)


class BrowserStateTests(unittest.TestCase):
	module: Any = None
	dialog: Any = None
	# A fresh list is assigned in setUp; None avoids a shared mutable class default.
	selection: Any = None

	def setUp(self) -> None:
		self.module = _browser()
		self.dialog = object.__new__(self.module.VoiceLibraryDialog)
		self.dialog._closed = False
		self.dialog._loadId = 1
		self.dialog._isLoading = False
		self.dialog._isCreating = False
		self.dialog._previewId = 0
		self.dialog._previewPath = None
		self.dialog._generatedSample = None
		self.dialog.model = "gemini-3.8-flash-lite-tts"
		self.dialog.apiKey = "key"
		self.dialog._playbackTimer = None
		self.dialog._previewVoiceName = "Voice One"
		self.dialog._previewState = "idle"
		self.dialog._searchTimer = None
		self.dialog._types = ("", "prebuilt", "prompted", "replicated")
		self.dialog._languages = [None, ""]
		self.dialog._attributeChoices = {}
		self.dialog._attributeValues = {}
		self.dialog.selectedId = "one"
		self.dialog.selectedVoice = None
		self.dialog.voices = [self.module.Voice("one", "One"), self.module.Voice("two", "Two")]
		self.dialog.visibleVoices = list(self.dialog.voices)
		self.dialog.store = mock.Mock()
		self.dialog.store.directory = Path("unused")
		for name in (
			"results",
			"searchCtrl",
			"typeChoice",
			"languageChoice",
			"detailsCtrl",
			"previewTextCtrl",
			"statusCtrl",
			"useBtn",
			"previewBtn",
			"stopBtn",
			"newVoiceBtn",
			"remixBtn",
		):
			control = mock.Mock()
			control.HasFocus.return_value = False
			setattr(self.dialog, name, control)
		self.selection = [0]
		self.dialog.results.GetSelection.side_effect = lambda: self.selection[0]

		def select(index: int) -> None:
			self.selection[0] = index

		self.dialog.results.SetSelection.side_effect = select
		self.dialog.searchCtrl.GetValue.return_value = ""
		self.dialog.previewTextCtrl.GetValue.return_value = "Hello."
		self.dialog.typeChoice.GetSelection.return_value = 0
		self.dialog.languageChoice.GetSelection.return_value = 0
		self.dialog.EndModal = mock.Mock()

	def testLanguageOptionsComeFromCatalogAndPreserveRemovedSelection(self) -> None:
		self.dialog.voices = [
			self.module.Voice("one", "One", language="en-US"),
			self.module.Voice("two", "Two", language="EN-us"),
		]
		self.dialog._languages = [None, "", "id-id"]
		self.dialog.languageChoice.GetSelection.return_value = 2
		self.dialog._updateLanguages()
		self.assertEqual(self.dialog._languages, [None, "", "en-us", "id-id"])
		self.dialog.languageChoice.SetSelection.assert_called_with(3)
		self.dialog.languageChoice.SetFocus.assert_not_called()

	def testLanguageChangeFiltersResultsAndInvalidatesSample(self) -> None:
		self.dialog._languages = [None, "", "id-id"]
		self.dialog.languageChoice.GetSelection.return_value = 2
		self.dialog.voices = [
			self.module.Voice("one", "One", language="id-ID"),
			self.module.Voice("two", "Two", language="en-US"),
		]
		self.dialog._previewState = "loading"
		self.dialog.onFilter(mock.Mock())
		self.assertEqual([voice.id for voice in self.dialog.visibleVoices], ["one"])
		self.assertEqual(self.dialog._previewState, "idle")
		self.assertGreater(self.dialog._previewId, 0)
		self.dialog.languageChoice.SetFocus.assert_not_called()

	def testRefreshReorderPreservesIdAndSearchFocus(self) -> None:
		self.dialog.searchCtrl.HasFocus.return_value = True
		self.dialog._loaded(1, list(reversed(self.dialog.voices)))
		self.assertEqual(self.selection[0], 1)
		self.assertEqual(self.dialog._selected().id, "one")
		self.dialog.results.SetFocus.assert_not_called()
		self.dialog.searchCtrl.SetFocus.assert_not_called()

	def testAttributeFiltersPreserveSelectionAndCancelPendingAudio(self) -> None:
		choice = mock.Mock()
		choice.GetSelection.return_value = 2
		self.dialog._attributeChoices = {"persona": choice}
		self.dialog._attributeValues = {"persona": [None, "", "warm"]}
		self.dialog.voices = [
			self.module.Voice("one", "One", persona="Warm"),
			self.module.Voice("two", "Two", persona="Bright"),
		]
		self.dialog._previewState = "generating"
		self.dialog.onFilter(mock.Mock())
		self.assertEqual([v.id for v in self.dialog.visibleVoices], ["one"])
		self.assertEqual(self.dialog._previewState, "idle")
		self.assertGreater(self.dialog._previewId, 0)
		self.dialog.voices = [self.dialog.voices[1]]
		self.dialog._updateAttributes()
		self.assertEqual(self.dialog._attributeValues["persona"], [None, "", "bright", "warm"])
		choice.SetSelection.assert_called_with(3)
		choice.SetFocus.assert_not_called()

	def testMissingSelectionMovesOnlyDisabledActionFocus(self) -> None:
		self.dialog.useBtn.HasFocus.return_value = True
		self.dialog._loaded(1, [self.dialog.voices[1]])
		self.dialog.results.SetFocus.assert_called_once()
		self.dialog.useBtn.Enable.assert_called_with(False)
		self.assertIsNone(self.dialog._selected())

	def testSearchImmediatelyFollowedByUseCannotApplyOldResult(self) -> None:
		self.dialog._searchTimer = mock.Mock()
		self.dialog.searchCtrl.GetValue.return_value = "no matches"
		self.dialog.onUse(mock.Mock())
		self.assertIsNone(self.dialog.selectedVoice)
		self.dialog.EndModal.assert_not_called()
		self.assertIsNone(self.dialog._searchTimer)

	def testSearchImmediatelyFollowedBySampleCannotFetchOldVoice(self) -> None:
		self.dialog._searchTimer = mock.Mock()
		self.dialog.searchCtrl.GetValue.return_value = "no matches"
		with mock.patch.object(self.module.threading, "Thread") as worker:
			self.dialog.onPreview(mock.Mock())
			worker.assert_not_called()

	def testClosedAndOutdatedCatalogResponsesAreIgnored(self) -> None:
		oldVoices = list(self.dialog.voices)
		self.dialog._loaded(0, [])
		self.dialog._closed = True
		self.dialog._loaded(1, [])
		self.assertEqual(self.dialog.voices, oldVoices)
		self.dialog.store.writeCatalog.assert_not_called()

	def testRefreshFailureKeepsCatalogAndSelection(self) -> None:
		oldVoices = list(self.dialog.voices)
		self.dialog._loadFailed(1)
		self.assertEqual(self.dialog.voices, oldVoices)
		self.assertEqual(self.dialog.selectedId, "one")
		self.dialog.store.writeCatalog.assert_not_called()

	def testStopAndCloseSuppressLatePlayback(self) -> None:
		self.dialog._stopPreview()
		self.dialog._playPreview(0, wavAudio())
		self.dialog._closed = True
		self.dialog._playPreview(self.dialog._previewId, wavAudio())
		self.module.winsound.PlaySound.assert_not_called()

	def testPlaybackHasAccurateStatusAndCleansTemporaryFile(self) -> None:
		self.dialog._playPreview(0, wavAudio())
		path = Path(self.dialog._previewPath)
		self.assertTrue(path.exists())
		self.assertEqual(self.dialog._previewState, "playing")
		self.assertIn("Voice One", self.dialog.statusCtrl.ChangeValue.call_args.args[0])
		self.dialog._previewFinished(0)
		self.assertFalse(path.exists())
		self.assertEqual(self.dialog._previewState, "idle")

	def testCancelDoesNotApplySelection(self) -> None:
		self.dialog.onCancel(mock.Mock())
		self.assertIsNone(self.dialog.selectedVoice)
		self.dialog.EndModal.assert_called_once_with(self.module.wx.ID_CANCEL)

	def testSelectingVoiceClearsObsoletePreviewStatus(self) -> None:
		self.dialog._previewState = "loading"
		self.dialog.onSelection(mock.Mock())
		self.assertEqual(self.dialog._previewState, "idle")
		self.dialog.statusCtrl.ChangeValue.assert_called_with("Sample stopped.")

	def testSpaceAndEnterOnlyFetchWhenVoiceListHasFocus(self) -> None:
		for key in (32, 13, 370):
			for focused, modified in ((True, False), (False, False), (True, True)):
				with self.subTest(key=key, focused=focused, modified=modified):
					event = mock.Mock()
					event.GetKeyCode.return_value = key
					event.HasAnyModifiers.return_value = modified
					self.dialog.results.HasFocus.return_value = focused
					with mock.patch.object(self.dialog, "onPreview") as preview:
						self.dialog.onCharHook(event)
						if focused and not modified:
							preview.assert_called_once_with(event)
							event.Skip.assert_not_called()
						else:
							preview.assert_not_called()
							event.Skip.assert_called_once()
		self.dialog.EndModal.assert_not_called()

	def testOtherKeysKeepNativeBehavior(self) -> None:
		self.dialog.results.HasFocus.return_value = True
		for key in (9, 27, 315, 316):
			event = mock.Mock()
			event.GetKeyCode.return_value = key
			event.HasAnyModifiers.return_value = False
			self.dialog.onCharHook(event)
			event.Skip.assert_called_once()

	def testRepeatedActivationWhileLoadingDoesNotStartAnotherFetch(self) -> None:
		for state in ("loading", "generating"):
			self.dialog._previewState = state
			with mock.patch.object(self.module.threading, "Thread") as worker:
				self.dialog.onPreview(mock.Mock())
				worker.assert_not_called()

	def testStopDuringGenerationExplainsQuotaAndIgnoresResult(self) -> None:
		self.dialog._previewState = "generating"
		self.dialog.onStop(mock.Mock())
		self.assertIn("may still use API quota", self.dialog.statusCtrl.ChangeValue.call_args.args[0])
		with mock.patch.object(self.dialog, "_playPreview") as play:
			self.dialog._generatedPreview(0, (self.dialog.model, "one", "Hello."), wavAudio())
			play.assert_not_called()

	def testInvalidGeneratedAudioIsNotCached(self) -> None:
		self.dialog._generatedPreview(0, (self.dialog.model, "one", "Hello."), b"not WAV")
		self.assertIsNone(self.dialog._generatedSample)
		self.assertEqual(self.dialog._previewState, "idle")

	def testCancelledLookupCannotStartBillableGeneration(self) -> None:
		self.dialog._stopPreview()
		with mock.patch.object(self.module.threading, "Thread") as worker:
			self.dialog._generatePreview(0, self.dialog.voices[0], "Hello.")
			self.dialog._closed = True
			self.dialog._generatePreview(self.dialog._previewId, self.dialog.voices[0], "Hello.")
			worker.assert_not_called()

	def testMissingSampleOnlyAnnouncesUnavailableWithoutGeneration(self) -> None:
		voice = self.dialog.voices[0]
		self.module.wx.CallAfter.reset_mock()
		with mock.patch.object(self.module, "fetchVoiceSample", return_value=None):
			self.dialog._previewWorker(0, voice)
		self.module.wx.CallAfter.assert_called_once_with(self.dialog._sampleUnavailable, 0)
		with mock.patch.object(self.module.threading, "Thread") as worker:
			self.dialog._sampleUnavailable(0)
			worker.assert_not_called()
		self.assertIn("Sample not available", self.dialog.statusCtrl.ChangeValue.call_args.args[0])
		self.assertEqual(self.dialog._previewState, "idle")

	def testGenerateButtonExplicitlyStartsPreviewWithoutSampleLookup(self) -> None:
		with (
			mock.patch.object(self.dialog, "_generatePreview") as generate,
			mock.patch.object(self.module.threading, "Thread") as worker,
		):
			self.dialog.onGeneratePreview(mock.Mock())
			generate.assert_called_once_with(self.dialog._previewId, self.dialog.voices[0], "Hello.")
			worker.assert_not_called()

	def testUnavailableCallbackIgnoredAfterCancellation(self) -> None:
		self.dialog._stopPreview()
		self.dialog._sampleUnavailable(0)
		self.dialog.statusCtrl.ChangeValue.assert_not_called()

	def testDownloadErrorDoesNotStartBillableFallback(self) -> None:
		self.module.wx.CallAfter.reset_mock()
		with mock.patch.object(
			self.module,
			"fetchVoiceSample",
			side_effect=self.module.DirectApiError("offline"),
		):
			self.dialog._previewWorker(0, self.dialog.voices[0])
		self.module.wx.CallAfter.assert_called_once_with(self.dialog._previewFailed, 0)

	def testGeneratedPreviewUsesSelectedModelIdAndEditableText(self) -> None:
		key = (self.dialog.model, "ar-eg-commercial-9", "أهلا بيك، دي تجربة قصيرة لصوتي.")
		self.module.wx.CallAfter.reset_mock()
		with mock.patch.object(
			self.module,
			"generate_tts",
			return_value=(wavAudio(), "audio/wav"),
		) as generate:
			self.dialog._generateWorker(0, key)
			generate.assert_called_once_with("key", key[0], key[2], [key[1]], timeout=90)
		self.module.wx.CallAfter.assert_called_once_with(self.dialog._generatedPreview, 0, key, wavAudio())

	def testGeneratedPreviewReplayUsesMemoryCacheAndTextChangeMisses(self) -> None:
		key = (self.dialog.model, "one", "Hello.")
		self.dialog._generatedPreview(0, key, wavAudio())
		self.dialog._stopPreview()
		with mock.patch.object(self.module.threading, "Thread") as worker:
			self.dialog._generatePreview(self.dialog._previewId, self.dialog.voices[0], "Hello.")
			worker.assert_not_called()
			self.dialog._stopPreview()
			self.dialog._generatePreview(self.dialog._previewId, self.dialog.voices[0], "Different.")
			worker.assert_called_once()
		self.dialog._stopPreview()

	def testLateGeneratedResponseDoesNotPlayOrCache(self) -> None:
		self.dialog._stopPreview()
		with mock.patch.object(self.dialog, "_playPreview") as play:
			self.dialog._generatedPreview(0, (self.dialog.model, "one", "Hello."), wavAudio())
			play.assert_not_called()
		self.assertIsNone(self.dialog._generatedSample)

	def testEmptyAndOverlongTextNeverGenerate(self) -> None:
		for text in ("", "x" * 301):
			with mock.patch.object(self.module.threading, "Thread") as worker:
				self.dialog._generatePreview(self.dialog._previewId, self.dialog.voices[0], text)
				worker.assert_not_called()
		self.dialog.previewTextCtrl.SetFocus.assert_called()

	def testEditingPreviewTextInvalidatesPendingResponse(self) -> None:
		self.dialog._previewState = "loading"
		self.dialog.onPreviewTextChanged(mock.Mock())
		self.assertGreater(self.dialog._previewId, 0)
		self.assertEqual(self.dialog._previewState, "idle")

	def testGenerationFailureIsReportedWithoutRetry(self) -> None:
		self.module.wx.CallAfter.reset_mock()
		with mock.patch.object(
			self.module,
			"generate_tts",
			side_effect=self.module.DirectApiError("quota"),
		) as generate:
			self.dialog._generateWorker(0, (self.dialog.model, "one", "Hello."))
			generate.assert_called_once()
		self.module.wx.CallAfter.assert_called_once_with(self.dialog._previewFailed, 0)

	def testCatalogFailureStopsSampleBeforeAnnouncing(self) -> None:
		order = mock.Mock()
		with (
			mock.patch.object(self.dialog, "_stopPreview", order.stop),
			mock.patch.object(self.dialog, "_setStatus", order.status),
		):
			self.dialog._loadFailed(1)
		self.assertEqual(order.mock_calls[0], mock.call.stop())
		self.assertEqual(order.mock_calls[1][0], "status")

	def testWorkerFetchesExistingSampleAndQueuesPlayback(self) -> None:
		self.dialog.apiKey = "key"
		voice = self.dialog.voices[0]
		self.module.wx.CallAfter.reset_mock()
		with mock.patch.object(self.module, "fetchVoiceSample", return_value=wavAudio()) as fetch:
			self.dialog._previewWorker(0, voice)
			fetch.assert_called_once_with("key", voice)
		self.module.wx.CallAfter.assert_called_once_with(self.dialog._playPreview, 0, wavAudio())


class GenerationLibraryIsolationTests(unittest.TestCase):
	def testLibraryChoiceAffectsOnlyTargetTtsVoice(self) -> None:
		module = loadDialog()
		dialog = object.__new__(module.NativeSpeechDialog)
		first, second = mock.Mock(), mock.Mock()
		dialog._libraryControls = {"single": (first, mock.Mock()), "speaker2": (second, mock.Mock())}
		dialog._librarySelections = {"single": module.Voice("voice_custom", "Custom")}
		dialog.voices = [{"name": "Kore"}, {"name": "Puck"}]
		self.assertEqual(dialog._getGenerationVoiceName(first, 0), "voice_custom")
		self.assertEqual(dialog._getGenerationVoiceName(second, 1), "Puck")
		# Talk With AI still calls the original built-in voice accessor.
		self.assertEqual(dialog._getSelectedVoiceName(first, 0), "Kore")

	def testUncheckingOverrideReturnsToBuiltInAndPersistsRemoval(self) -> None:
		module = loadDialog()
		dialog = object.__new__(module.NativeSpeechDialog)
		choice, checkbox = mock.Mock(), mock.Mock()
		checkbox.GetValue.return_value = False
		dialog._libraryControls = {"speaker2": (choice, checkbox)}
		dialog._librarySelections = {"speaker2": module.Voice("voice_custom", "Custom")}
		dialog._libraryStore = mock.Mock()
		event = mock.Mock()
		event.GetEventObject.return_value = checkbox
		dialog.onLibrarySelectionToggle(event, "speaker2")
		self.assertEqual(dialog._librarySelections, {})
		choice.SetFocus.assert_called_once()
		checkbox.Disable.assert_called_once()
		self.assertIn("Speaker 2", checkbox.SetLabel.call_args.args[0])
		dialog._libraryStore.writeSelections.assert_called_once_with({})


if __name__ == "__main__":
	unittest.main()
