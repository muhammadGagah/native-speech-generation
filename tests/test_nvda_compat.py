from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
COMPAT_PATH = REPO_ROOT / "addon" / "globalPlugins" / "NativeSpeechGeneration" / "core" / "nvda_compat.py"


def _loadCompat() -> Any:
	moduleName = "nsg_nvda_compat_under_test"
	sys.modules.pop(moduleName, None)
	spec = importlib.util.spec_from_file_location(moduleName, COMPAT_PATH)
	assert spec is not None
	assert spec.loader is not None
	module = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(module)
	return module


class NvdaCompatTests(unittest.TestCase):
	def tearDown(self) -> None:
		sys.modules.pop("NVDAState", None)
		sys.modules.pop("globalVars", None)

	def testUsesCurrentNvdaDiskPolicyWhenAvailable(self) -> None:
		nvdaState = types.ModuleType("NVDAState")
		nvdaState.shouldWriteToDisk = lambda: False
		sys.modules["NVDAState"] = nvdaState

		self.assertFalse(_loadCompat().shouldWriteToDisk())

	def testFallbackBlocksSecureAndLauncherModes(self) -> None:
		globalVars = types.ModuleType("globalVars")
		globalVars.appArgs = types.SimpleNamespace(secure=True, launcher=False)
		sys.modules["globalVars"] = globalVars
		self.assertFalse(_loadCompat().shouldWriteToDisk())

		globalVars.appArgs = types.SimpleNamespace(secure=False, launcher=True)
		self.assertFalse(_loadCompat().shouldWriteToDisk())

	def testFallbackAllowsNormalOlderNvdaMode(self) -> None:
		globalVars = types.ModuleType("globalVars")
		globalVars.appArgs = types.SimpleNamespace(secure=False, launcher=False)
		sys.modules["globalVars"] = globalVars

		compat = _loadCompat()
		self.assertTrue(compat.shouldWriteToDisk())
		self.assertFalse(compat.isSecureMode())


if __name__ == "__main__":
	unittest.main()
