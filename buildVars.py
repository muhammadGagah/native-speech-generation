from site_scons.site_tools.NVDATool.typings import (
	AddonInfo,
	BrailleTables,
	SpeechDictionaries,
	SymbolDictionaries,
)
from site_scons.site_tools.NVDATool.utils import _

addon_info = AddonInfo(
	addon_name="NativeSpeechGeneration",
	# Translators: Summary for this add-on shown in NVDA's Add-ons Store and Add-ons Manager.
	addon_summary=_("Native Speech Generation"),
	# Translators: Long description for this add-on shown in NVDA's Add-ons Store and Add-ons Manager.
	addon_description=_("""Harness the power of Google's state-of-the-art Gemini AI for high-quality speech generation directly within NVDA. This add-on provides a user-friendly dialog to convert text into natural-sounding audio.

Key Features:
- High-Quality Voices: Choose between Gemini Flash 3.1 Preview for powerful, low-latency short audio, Gemini Flash 2.5 for standard responsive generation, and Gemini Pro 2.5 for premium, life-like speech.
- Single and Multi-Speaker Modes: Easily generate audio for a single speaker or create dynamic dialogues with two distinct speakers. Simply format your text with "SpeakerName:" to assign voices.
- Advanced Voice Control: Fine-tune the output by adjusting the temperature for more creative or stable results, and provide custom style instructions.
- Quick Speak: Speak selected text or clipboard text immediately with separate model, voice, and style settings while keeping focus in the current application.
- Seamless Workflow: The add-on provides instant audio playback upon generation and allows you to save the resulting .wav file for later use.

To get started, obtain a Gemini API key from Google AI Studio and enter it in the add-on's settings panel, found under NVDA's Tools menu."""),
	addon_version="1.8.0",
	# Translators: Short release notes shown for this add-on version.
	addon_changelog=_("""- Added Quick Speak for selected text (NVDA+Alt+E) and clipboard text (NVDA+Alt+Shift+E), with configurable model, voice, style, volume, and internal playback.
- Migrated Gemini Live features to a direct WebSocket API and improved connection timeouts, retries, server errors, and cancellation.
- Improved Quick Speak with high thinking for Gemini 3.1 Flash Live Preview, silent routine states, protected-field blocking, focus preservation, key-repeat suppression, and stale playback protection.
- Improved Talk With AI with saved audio devices and volume, better default-device selection, safer playback interruption and shutdown, and more reliable screen sharing.
- Updated accessibility, error announcements, translations, and documentation. Tested through NVDA 2026.2 while retaining NVDA 2024.1 as the minimum supported version.
- See changelog.md for full details.
"""),
	addon_author="Muhammad <muha.aku@gmail.com>",
	addon_url="https://github.com/muhammadGagah/native-speech-generation/",
	addon_sourceURL="https://github.com/muhammadGagah/native-speech-generation/",
	addon_docFileName="readme.html",
	addon_minimumNVDAVersion="2024.1",
	addon_lastTestedNVDAVersion="2026.2",
	addon_updateChannel=None,
	addon_license="GPL-2.0",
	addon_licenseURL="https://www.gnu.org/licenses/gpl-2.0.html",
)

pythonSources: list[str] = [
	"addon/globalPlugins/NativeSpeechGeneration/*.py",
	"addon/globalPlugins/NativeSpeechGeneration/core/*.py",
	"addon/globalPlugins/NativeSpeechGeneration/interface/*.py",
	"addon/installTasks.py",
]

i18nSources: list[str] = pythonSources + ["buildVars.py"]

excludedFiles: list[str] = [
	"**/__pycache__/*",
	"**/*.pyc",
	"**/*.pyo",
	"**/*.whl",
	"**/.lib_staging_*/*",
	"**/.lib_ready_*/*",
	"**/lib_trash_*/*",
	"**/last_audio_generated*",
	"**/voices_cache.json",
]

baseLanguage: str = "en"

markdownExtensions: list[str] = []

brailleTables: BrailleTables = {}

symbolDictionaries: SymbolDictionaries = {}

speechDictionaries: SpeechDictionaries = {}
