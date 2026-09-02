# Tasks to perform during installation of the Native Speech Generation NVDA add-on
# Copyright (C) 2026 Muhammad.
# This add-on is free software, licensed under the terms of the GNU General Public License (version 2).
# For more details see: https://www.gnu.org/licenses/gpl-2.0.html

import os
import shutil

import addonHandler
import gui
import wx
from logHandler import log

try:
	from gui.message import MessageDialog
except ImportError:  # NVDA 2024.x
	MessageDialog = None

addonHandler.initTranslation()


def _isUpdate() -> bool:
	currentAddon = addonHandler.getCodeAddon()
	currentPath = os.path.normcase(os.path.abspath(currentAddon.path))
	return any(
		addon.name == currentAddon.name
		and not addon.path.lower().endswith(".pendinginstall")
		and os.path.normcase(os.path.abspath(addon.path)) != currentPath
		for addon in addonHandler.getAvailableAddons()
	)


def _showUpdateWarning() -> None:
	gui.mainFrame.prePopup()
	try:
		# Translators: Warning shown after updating the add-on from an older connection architecture.
		message = _(
			"Native Speech Generation now uses a WebSocket connection. For the best performance and compatibility, "
			"restart NVDA, open NVDA Settings, select Native Speech Generation, and choose Reinstall Libraries.",
		)
		# Translators: Title of the warning shown after updating the add-on.
		title = _("Native Speech Generation updated")
		if MessageDialog is not None:
			MessageDialog.alert(message, title, parent=gui.mainFrame)
		else:
			gui.messageBox(message, title, wx.OK | wx.ICON_WARNING, parent=gui.mainFrame)
	finally:
		gui.mainFrame.postPopup()


def onInstall() -> None:
	"""
	Called when the add-on is installed.
	Attempts to copy the 'lib' folder from an existing installation to preserve downloaded libraries.
	"""
	isUpdate = _isUpdate()
	try:
		# Current running file is in .../addons/NativeSpeechGeneration.pendingInstall/installTasks.py
		# We want to find .../addons/NativeSpeechGeneration/globalPlugins/NativeSpeechGeneration/lib

		# Get the directory where THIS script is running (pending install dir)
		myDir = os.path.dirname(os.path.abspath(__file__))
		addonsDir = os.path.dirname(myDir)  # .../addons/

		# The standard existing installed folder name
		existingAddonDir = os.path.join(addonsDir, "NativeSpeechGeneration")

		# Define paths to the 'lib' folder
		# Note: Adjust path if structure changes. Currently: addon/globalPlugins/NativeSpeechGeneration/lib
		existingLib = os.path.join(existingAddonDir, "globalPlugins", "NativeSpeechGeneration", "lib")
		newLib = os.path.join(myDir, "globalPlugins", "NativeSpeechGeneration", "lib")

		# Check if we are updating (old lib exists) and new lib is missing (fresh install/update pkg)
		if os.path.exists(existingLib) and not os.path.exists(newLib):
			log.debug(
				"NativeSpeechGeneration installTasks: Found existing libraries from previous version. Copying to new installation...",
			)
			shutil.copytree(existingLib, newLib)
			log.debug(
				"NativeSpeechGeneration installTasks: Libraries copied successfully. No re-download needed.",
			)
		else:
			log.debug(
				"NativeSpeechGeneration installTasks: No existing libraries found or new lib already present. Skipping copy.",
			)

	except Exception as e:
		log.warning(
			f"NativeSpeechGeneration installTasks: Failed to copy existing libraries during update: {e}",
		)

	if isUpdate:
		wx.CallAfter(_showUpdateWarning)

	log.debug("NativeSpeechGeneration add-on onInstall phase completed.")


def onUninstall() -> None:
	"""
	Called when the add-on is uninstalled.
	The configuration is intentionally preserved so add-on updates do not wipe user settings.
	"""
	log.debug("NativeSpeechGeneration uninstall: preserving configuration to avoid data loss across updates.")
