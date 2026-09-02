"""Opt-in, bounded screen capture for Talk With AI."""

from __future__ import annotations

import base64
import ctypes
import io
import threading
from collections.abc import Callable

import wx


def is_screen_curtain_active() -> bool:
	"""Return whether NVDA's Screen Curtain currently blanks the display."""
	try:
		return bool(ctypes.windll.nvdaHelperLocal.isScreenFullyBlack())
	except (AttributeError, OSError):
		return False


def capture_fullscreen() -> str | None:
	"""Capture the primary display as JPEG base64; intended for a worker thread."""
	try:
		width, height = wx.GetDisplaySize()
		bitmap = wx.Bitmap(width, height)
		screen = wx.ScreenDC()
		memory = wx.MemoryDC(bitmap)
		try:
			memory.Blit(0, 0, width, height, screen, 0, 0)
		finally:
			memory.SelectObject(wx.NullBitmap)
		image = bitmap.ConvertToImage()
		stream = io.BytesIO()
		image.SetOption("quality", 85)
		if not image.SaveFile(stream, wx.BITMAP_TYPE_JPEG):
			return None
		return base64.b64encode(stream.getvalue()).decode("ascii")
	except Exception:
		return None


class ScreenCaptureWorker:
	"""Capture on the wx thread and submit at most one frame per interval."""

	def __init__(
		self,
		on_frame: Callable[[str], None],
		interval: float = 2.0,
		on_blocked: Callable[[], None] | None = None,
		on_failed: Callable[[], None] | None = None,
	) -> None:
		super().__init__()
		self._on_frame = on_frame
		self._interval = interval
		self._on_blocked = on_blocked
		self._on_failed = on_failed
		self._stop = threading.Event()
		self._timer = None
		self._failureCount = 0

	def start(self) -> None:
		self._stop.clear()
		wx.CallAfter(self._capture)

	def _capture(self) -> None:
		if self._stop.is_set():
			return
		if is_screen_curtain_active():
			if self._on_blocked:
				self._on_blocked()
			return
		frame = capture_fullscreen()
		if frame and not self._stop.is_set():
			self._failureCount = 0
			self._on_frame(frame)
		elif not frame:
			self._failureCount += 1
			if self._failureCount >= 3:
				if self._on_failed:
					self._on_failed()
				return
		if not self._stop.is_set():
			self._timer = wx.CallLater(max(1, int(self._interval * 1000)), self._capture)

	def stop(self) -> None:
		self._stop.set()
		wx.CallAfter(self._stopTimer)

	def _stopTimer(self) -> None:
		timer = self._timer
		self._timer = None
		if timer is not None:
			try:
				timer.Stop()
			except (AttributeError, RuntimeError):
				pass


__all__ = ["ScreenCaptureWorker", "capture_fullscreen", "is_screen_curtain_active"]
