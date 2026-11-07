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
- High-Quality Voices: Choose Gemini Flash-Lite 3.8 TTS for everyday narration or Gemini Flash 3.8 TTS for expressive dialogue. Previous Gemini 3.1 and 2.5 TTS models remain available.
- Single and Multi-Speaker Modes: Easily generate audio for a single speaker or create dynamic dialogues with two distinct speakers. Simply format your text with "SpeakerName:" to assign voices.
- Advanced Voice Control: Fine-tune the output by adjusting the temperature for more creative or stable results, and provide custom style instructions.
- Quick Speak: Speak selected text or clipboard text immediately with separate model, voice, and style settings while keeping focus in the current application.
- Seamless Workflow: The add-on provides instant audio playback upon generation and allows you to save the resulting .wav file for later use.

To get started, obtain a Gemini API key from Google AI Studio and enter it in the add-on's settings panel, found under NVDA's Tools menu."""),
	addon_version="1.8.3",
	# Translators: Short release notes shown for this add-on version.
	addon_changelog=_("""- Tested with NVDA 2026.3.
- Fixed Voice Library caching, voice creation, and dialog closing issues, and updated the Indonesian translation.
- Added Voice Remix to create a new voice by describing changes to an existing voice in Voice Library.
- Grouped Voice Design and Voice Replication under New voice with descriptions.
- Added Voice Replication with reference and consent WAV uploads, consent verification, and a paid-tier notice.
- Clarified that Voice Design requires an API key from a project with billing enabled.
- Added Voice Design to create custom voices from descriptions in Voice Library.
- Added Gender, Pitch, Persona, and Use case filters to Voice Library.
- Fixed existing samples for extended voice IDs such as en-us-fola and en-us-rami.
- Native Speech Generation stage 2: Added a searchable Voice Library with type and language filters, 70 verified voice samples and explicitly generated previews with editable text, cached catalogs, and saved narrator/speaker voices for Gemini 3.8 TTS.
- Native Speech Generation stage 1: Added Gemini 3.8 Flash-Lite and Flash TTS, structured style and speaker metadata, script validation, and Script Help.
- Added Gemini 3.8 Live for Quick Speak and Talk with AI, and Gemini 3.8 Live Extended Thinking for Talk with AI.
- Applied model-specific thinking settings while preserving existing model preferences.
- Fixed interrupted WebSocket reads, permanent API error handling, reconnect status, and keyboard focus preservation.
- See changelog.md for full details.
"""),
	addon_author="Muhammad <muha.aku@gmail.com>",
	addon_url="https://github.com/muhammadGagah/native-speech-generation/",
	addon_sourceURL="https://github.com/muhammadGagah/native-speech-generation/",
	addon_docFileName="readme.html",
	addon_minimumNVDAVersion="2024.1",
	addon_lastTestedNVDAVersion="2026.3",
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
