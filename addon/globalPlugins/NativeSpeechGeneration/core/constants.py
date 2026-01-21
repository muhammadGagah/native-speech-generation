# -*- coding: utf-8 -*-
import os

CONFIG_DOMAIN = "NativeSpeechGeneration"
DEFAULT_MODEL = "gemini-2.5-flash-preview-tts"
SECOND_MODEL = "gemini-2.5-pro-preview-tts"

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
