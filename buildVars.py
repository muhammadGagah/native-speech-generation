from site_scons.site_tools.NVDATool.typings import AddonInfo, BrailleTables, SymbolDictionaries
from site_scons.site_tools.NVDATool.utils import _

addon_info = AddonInfo(
	addon_name="NativeSpeechGeneration",
	addon_summary=_("Native Speech Generation"),
	addon_description=_("""Harness the power of Google's state-of-the-art Gemini AI for high-quality speech generation directly within NVDA. This add-on provides a user-friendly dialog to convert text into natural-sounding audio.

Key Features:
- High-Quality Voices: Choose between Gemini Pro for premium, life-like speech and Gemini Flash for standard quality, responsive generation.
- Single and Multi-Speaker Modes: Easily generate audio for a single speaker or create dynamic dialogues with two distinct speakers. Simply format your text with "SpeakerName:" to assign voices.
- Advanced Voice Control: Fine-tune the output by adjusting the temperature for more creative or stable results, and provide custom style instructions.
- Accessible Interface: All controls are fully accessible, including a collapsible panel for advanced settings to keep the interface clean and easy to navigate.
- Seamless Workflow: The add-on provides instant audio playback upon generation and allows you to save the resulting .wav file for later use.

To get started, obtain a Gemini API key from Google AI Studio and enter it in the add-on's settings panel, found under NVDA's Tools menu."""),
	addon_version="1.5.3",
	addon_changelog=_("""- Code Refactoring: Complies with NVDA coding standards (Tabs, CamelCase).
- Optimized Update: Preserves library files to avoid redownloading data.
- Improved UX: Restored device selection in "Talk With AI", better button states, and fixed dialog closing behavior.
- Fix: Resolved namespace conflicts and ensured proper stream cancellation.
"""),
	addon_author="Muhammad <muha.aku@gmail.com>",
	addon_url="https://github.com/muhammadGagah/native-speech-generation/",
	addon_sourceURL="https://github.com/muhammadGagah/native-speech-generation/",
	addon_docFileName="readme.html",
	addon_minimumNVDAVersion="2024.1",
	addon_lastTestedNVDAVersion="2025.3.2",
	addon_updateChannel=None,
	addon_license="GPL-2.0",
	addon_licenseURL="https://www.gnu.org/licenses/gpl-2.0.html",
)

pythonSources: list[str] = ["addon/globalPlugins/NativeSpeechGeneration/*.py", "addon/installTasks.py"]

i18nSources: list[str] = pythonSources + ["buildVars.py"]

excludedFiles: list[str] = []

baseLanguage: str = "en"

markdownExtensions: list[str] = []

brailleTables: BrailleTables = {}

symbolDictionaries: SymbolDictionaries = {}
