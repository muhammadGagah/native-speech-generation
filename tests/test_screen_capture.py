from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SCREEN_CAPTURE_PATH = (
	REPO_ROOT / "addon" / "globalPlugins" / "NativeSpeechGeneration" / "core" / "screen_capture.py"
)


def _loadScreenCapture() -> tuple[Any, types.SimpleNamespace]:
	state = types.SimpleNamespace(callAfter=[], timers=[])
	wx = types.ModuleType("wx")

	def callAfter(callback: Any, *args: object) -> None:
		state.callAfter.append(callback)
		callback(*args)

	class Timer:
		def __init__(self, delay: int, callback: Any) -> None:
			super().__init__()
			self.delay = delay
			self.callback = callback
			self.stopped = False

		def Stop(self) -> None:
			self.stopped = True

	def callLater(delay: int, callback: Any) -> Timer:
		timer = Timer(delay, callback)
		state.timers.append(timer)
		return timer

	wx.CallAfter = callAfter
	wx.CallLater = callLater
	sys.modules["wx"] = wx

	moduleName = "nsg_screen_capture_under_test"
	sys.modules.pop(moduleName, None)
	spec = importlib.util.spec_from_file_location(moduleName, SCREEN_CAPTURE_PATH)
	assert spec is not None and spec.loader is not None
	module = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(module)
	return module, state


class ScreenCaptureTests(unittest.TestCase):
	def testCaptureIsScheduledThroughWxThread(self) -> None:
		screenCapture, state = _loadScreenCapture()
		frames: list[str] = []
		screenCapture.is_screen_curtain_active = lambda: False
		screenCapture.capture_fullscreen = lambda: "jpeg"
		worker = screenCapture.ScreenCaptureWorker(frames.append, interval=2.0)

		worker.start()

		self.assertEqual(frames, ["jpeg"])
		self.assertEqual(len(state.callAfter), 1)
		self.assertEqual(state.timers[0].delay, 2000)
		worker.stop()
		self.assertTrue(state.timers[0].stopped)

	def testRepeatedCaptureFailureStopsSharing(self) -> None:
		screenCapture, state = _loadScreenCapture()
		failures: list[bool] = []
		screenCapture.is_screen_curtain_active = lambda: False
		screenCapture.capture_fullscreen = lambda: None

		def ignoreFrame(_frame: str) -> None:
			pass

		worker = screenCapture.ScreenCaptureWorker(ignoreFrame, on_failed=lambda: failures.append(True))

		worker.start()
		state.timers[-1].callback()
		state.timers[-1].callback()

		self.assertEqual(failures, [True])


if __name__ == "__main__":
	unittest.main()
