# -*- coding: utf-8 -*-
import sys
import platform
from logHandler import log

GENAI_AVAILABLE = False
genai = None
types = None

__all__ = ["genai", "types", "GENAI_AVAILABLE"]

try:
	# Dependency Conflict Resolution (Scoped / Safe Mode)
	conflictingLibs = ["typing_extensions", "pydantic", "pydantic_core", "annotated_types"]
	originalModules = {}

	for lib in conflictingLibs:
		if lib in sys.modules:
			originalModules[lib] = sys.modules[lib]
			del sys.modules[lib]
	try:
		from google import genai
		from google.genai import types

		GENAI_AVAILABLE = True
		log.info("google-genai loaded successfully via core.gemini_imports")
	finally:
		# Restore original modules to avoid breaking other add-ons
		for lib, module in originalModules.items():
			sys.modules[lib] = module
except Exception as e:
	genai = None
	types = None
	GENAI_AVAILABLE = False

	errMsg = (
		f"Google GenAI Import Error:\n{e}\n\n"
		f"Python: {sys.version}\n"
		f"Arch: {platform.architecture()}\n"
		f"Path: {sys.path[:3]}..."
	)
	log.warning("google-genai not available", exc_info=True)
	log.error(errMsg)
