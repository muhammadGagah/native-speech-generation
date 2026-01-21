# -*- coding: utf-8 -*-
import os
import wx
import gui
import addonHandler
import core
import urllib.request
import zipfile
import threading
import shutil
import glob
from logHandler import log
from collections.abc import Callable

addonHandler.initTranslation()

LIB_URL = "https://github.com/muhammadGagah/python-library-add-on-Native-Speech-Generation/releases/latest/download/lib.zip"

# Centralized Path Definitions
ADDON_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")


def cleanupTrash() -> None:
	"""
	Garbage Collection: Delete any 'lib_trash_*' folders left over from previous updates.
	Run this at startup when files are likely unlocked.
	"""
	try:
		gpBase = os.path.dirname(os.path.abspath(__file__))
		trashPattern = os.path.join(gpBase, "lib_trash_*")
		for trashDir in glob.glob(trashPattern):
			if os.path.isdir(trashDir):
				try:
					shutil.rmtree(trashDir, ignore_errors=True)
					log.info(f"lib_updater: Cleaned up trash directory: {trashDir}")
				except Exception as e:
					log.warning(f"lib_updater: Failed to clean trash {trashDir}: {e}")
	except Exception as e:
		log.warning(f"lib_updater: Error during trash cleanup: {e}")


def initialize() -> None:
	"""
	Entry point for initialization. Performs cleanup.
	"""
	cleanupTrash()


def downloadAndExtract(addonDir: str, progressCallback: Callable[[int, str], None]) -> bool:
	"""
	Downloads and extracts the lib folder.
	"""
	zipPath = os.path.join(addonDir, "lib.zip")

	try:
		wx.CallAfter(progressCallback, 10, _("Downloading libraries..."))

		# Download the file (Standard HTTP, no custom SSL context as requested)
		with urllib.request.urlopen(LIB_URL, timeout=30) as response, open(zipPath, "wb") as outFile:
			totalLength = response.length
			if totalLength:
				dl = 0
				while True:
					data = response.read(8192)
					if not data:
						break
					dl += len(data)
					outFile.write(data)
					percent = 10 + int(dl / totalLength * 70)
					wx.CallAfter(progressCallback, percent, _("Downloading..."))
			else:  # No content length
				outFile.write(response.read())

		log.info("Download complete. Extracting...")
		wx.CallAfter(progressCallback, 80, _("Extracting libraries..."))

		# Extract the zip file
		with zipfile.ZipFile(zipPath, "r") as zipRef:
			# Extract into the package directory (NativeSpeechGeneration)
			zipRef.extractall(os.path.dirname(os.path.abspath(__file__)))

		log.info("Extraction complete.")
		wx.CallAfter(progressCallback, 100, _("Extraction complete."))

		if os.path.exists(zipPath):
			os.remove(zipPath)
		return True

	except Exception as e:
		log.error(f"Failed to download or extract libraries: {e}", exc_info=True)
		wx.CallAfter(
			gui.messageBox,
			_(
				"Failed to download or extract required libraries. The add-on might not work correctly.\n\nError: {error}",
			).format(error=e),
			_("Error"),
			wx.OK | wx.ICON_ERROR,
		)
		if os.path.exists(zipPath):
			os.remove(zipPath)
		return False


def checkAndInstallDependencies(forceReinstall: bool = False) -> None:
	# Verifies if the 'lib' folder exists, and if not (or if forced), instigates the download process
	addonDir = ADDON_DIR
	libDir = LIB_DIR

	if not forceReinstall and os.path.exists(libDir):
		log.info("Dependencies already installed, skipping check.")
		return

	def runInstallation() -> None:
		# Sets up the progress UI and runs the download/extract thread
		progressDialog = wx.ProgressDialog(
			_("Installing Dependencies"),
			_("Checking for required libraries..."),
			maximum=100,
			parent=gui.mainFrame,
			style=wx.PD_APP_MODAL | wx.PD_AUTO_HIDE,
		)

		def updateProgress(progress: int, message: str) -> None:
			# CallAfter target to update the progress dialog from the background thread
			if progress == 100:
				progressDialog.Update(100, _("Installation complete!"))
				wx.CallLater(500, progressDialog.Destroy)
			else:
				progressDialog.Update(progress, message)

		def doWork() -> None:
			# The background worker that performs cleanup, download, and extraction
			if forceReinstall and os.path.exists(libDir):
				try:
					shutil.rmtree(libDir)
				except Exception as e:
					log.warning(f"Failed to remove existing lib dir during reinstall: {e}")

			success = downloadAndExtract(addonDir, updateProgress)

			def finalMessage() -> None:
				if success:
					message = _(
						"The Native Speech Generation libraries have been successfully installed/updated.\n\nPlease restart NVDA for the changes to take effect.",
					)
					title = _("Installation Complete")
					res = wx.MessageBox(message, title, wx.OK | wx.ICON_INFORMATION)
					if res == wx.OK:
						core.restart()
				else:
					message = _("Library installation failed. Please check the log.")
					title = _("Error")
					wx.CallAfter(wx.MessageBox, message, title, wx.OK | wx.ICON_ERROR)

			wx.CallAfter(finalMessage)

		threading.Thread(target=doWork).start()

	def confirmAction() -> None:
		# Prompts the user for confirmation before starting the installation
		if forceReinstall:
			msg = _(
				"Are you sure you want to reinstall the libraries? This will redownload the dependencies and require an NVDA restart.",
			)
			title = _("Confirm Reinstall")
		else:
			msg = _("Required libraries for Native Speech Generation are missing. Click OK to download them.")
			title = _("Missing Dependencies")

		res = wx.MessageBox(msg, title, wx.OK | wx.CANCEL | wx.ICON_INFORMATION)

		if res == wx.OK:
			runInstallation()
		else:
			log.info("User cancelled dependency installation.")

	wx.CallAfter(confirmAction)


def reinstallDependencies() -> None:
	"""Public wrapper to force reinstallation."""
	checkAndInstallDependencies(forceReinstall=True)
