from __future__ import annotations

import builtins
import importlib.util
import sys
import tempfile
import types
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
VENDOR_LOADER_PATH = REPO_ROOT / "addon" / "globalPlugins" / "NativeSpeechGeneration" / "core" / "vendor_loader.py"


class _Log:
	def debug(self, *_args: object, **_kwargs: object) -> None:
		pass

	def info(self, *_args: object, **_kwargs: object) -> None:
		pass

	def warning(self, *_args: object, **_kwargs: object) -> None:
		pass


def _loadVendorLoader() -> types.ModuleType:
	def translate(message: str) -> str:
		return message

	builtins._ = translate
	logHandler = types.ModuleType("logHandler")
	logHandler.log = _Log()
	sys.modules["logHandler"] = logHandler
	moduleName = "nsg_vendor_loader_under_test"
	sys.modules.pop(moduleName, None)
	spec = importlib.util.spec_from_file_location(moduleName, VENDOR_LOADER_PATH)
	assert spec is not None and spec.loader is not None
	module = importlib.util.module_from_spec(spec)
	sys.modules[moduleName] = module
	spec.loader.exec_module(module)
	return module


class VendorLoaderTests(unittest.TestCase):
	def testMissingLibraryDirectoryDoesNotImportHostPackages(self) -> None:
		vendorLoader = _loadVendorLoader()
		with tempfile.TemporaryDirectory() as tempDir:
			runtime = vendorLoader.load_runtime(str(Path(tempDir) / "missing"))

		self.assertFalse(runtime.pyaudioAvailable)
		self.assertIn("does not exist", runtime.pyaudioError or "")

	def testLazyModulesAreCapturedWhenScopedOperationFails(self) -> None:
		vendorLoader = _loadVendorLoader()
		with tempfile.TemporaryDirectory() as tempDir:
			fakePyAudio = types.ModuleType("pyaudio")
			runtime = vendorLoader.VendorRuntime(
				libDir=tempDir,
				pyaudio=None,
				modules={"pyaudio": fakePyAudio},
				versions={},
				pyaudioError=None,
			)
			with self.assertRaisesRegex(RuntimeError, "scoped failure"):
				with vendorLoader.runtime_scope(runtime):
					sys.modules["pyaudio.lazy"] = types.ModuleType("pyaudio.lazy")
					raise RuntimeError("scoped failure")

		self.assertIn("pyaudio.lazy", runtime.modules)
		self.assertIs(sys.modules.get("pyaudio.lazy"), None)


if __name__ == "__main__":
	unittest.main()
