import os

CONFIG_DOMAIN = "NativeSpeechGeneration"
DEFAULT_MODEL = "gemini-3.1-flash-tts-preview"
FLASH_25_MODEL = "gemini-2.5-flash-preview-tts"
PRO_25_MODEL = "gemini-2.5-pro-preview-tts"
LIVE_MODEL = "gemini-3.1-flash-live-preview"
LIVE_38_MODEL = "gemini-3.8-live"
LIVE_38_EXTENDED_MODEL = "gemini-3.8-live-extended-thinking"
TALK_WITH_AI_MODELS = (LIVE_38_MODEL, LIVE_38_EXTENDED_MODEL, LIVE_MODEL)
TALK_WITH_AI_THINKING_LEVELS = ("minimal", "low", "medium", "high")
NATIVE_AUDIO_25_MODEL = "gemini-2.5-flash-native-audio-preview-12-2025"

QUICK_SPEAK_DEFAULT_MODEL = LIVE_38_MODEL
QUICK_SPEAK_DEFAULT_VOICE = "Kore"
QUICK_SPEAK_DEFAULT_VOLUME = 80
TALK_WITH_AI_DEFAULT_VOLUME = 80

# Compute directories relative to this file
_coreDir = os.path.dirname(os.path.abspath(__file__))
_pkgDir = os.path.dirname(_coreDir)  # NativeSpeechGeneration
_globalPluginsDir = os.path.dirname(_pkgDir)  # globalPlugins
_addonDir = os.path.dirname(_globalPluginsDir)  # addon

VOICE_SAMPLE_BASE = "https://www.gstatic.com/aistudio/voices/samples"

FALLBACK_VOICES = [
	"Zephyr",
	"Puck",
	"Charon",
	"Kore",
	"Fenrir",
	"Leda",
	"Orus",
	"Aoede",
	"Callirrhoe",
	"Autonoe",
	"Enceladus",
	"Iapetus",
	"Umbriel",
	"Algieba",
	"Despina",
	"Erinome",
	"Algenib",
	"Rasalgethi",
	"Laomedeia",
	"Achernar",
	"Alnilam",
	"Schedar",
	"Gacrux",
	"Pulcherrima",
	"Achird",
	"Zubenelgenubi",
	"Vindemiatrix",
	"Sadachbia",
	"Sadaltager",
	"Sulafat",
]

CACHE_FILE = os.path.join(_addonDir, "voices_cache.json")
CACHE_TTL = 24 * 60 * 60  # 24 hours
