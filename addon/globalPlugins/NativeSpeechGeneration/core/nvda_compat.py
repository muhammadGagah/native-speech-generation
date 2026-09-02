from typing import Any


def isSecureMode() -> bool:
	"""Return whether NVDA is running on a secure desktop."""
	try:
		import globalVars

		return bool(getattr(globalVars.appArgs, "secure", False))
	except (AttributeError, ImportError):
		return False


def shouldWriteToDisk() -> bool:
	"""Use NVDA's current disk-write policy with a fallback for older releases."""
	try:
		import NVDAState

		checker: Any = getattr(NVDAState, "shouldWriteToDisk", None)
		if checker is not None:
			return bool(checker())
	except ImportError:
		pass

	try:
		import globalVars

		appArgs = globalVars.appArgs
		return not (bool(getattr(appArgs, "secure", False)) or bool(getattr(appArgs, "launcher", False)))
	except (AttributeError, ImportError):
		return True
