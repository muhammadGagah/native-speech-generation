# Tasks to perform during installation of the Native Speech Generation NVDA add-on
# Copyright (C) 2026 Muhammad.
# This add-on is free software, licensed under the terms of the GNU General Public License (version 2).
# For more details see: https://www.gnu.org/licenses/gpl-2.0.html

import os
import shutil

import addonHandler
from logHandler import log

addonHandler.initTranslation()


def onInstall() -> None:
	"""
	Called when the add-on is installed.
	Attempts to copy the 'lib' folder from an existing installation to preserve downloaded libraries.
	"""
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
			log.info(
				"NativeSpeechGeneration installTasks: Found existing libraries from previous version. Copying to new installation...",
			)
			shutil.copytree(existingLib, newLib)
			log.info(
				"NativeSpeechGeneration installTasks: Libraries copied successfully. No re-download needed.",
			)
		else:
			log.info(
				"NativeSpeechGeneration installTasks: No existing libraries found or new lib already present. Skipping copy.",
			)

	except Exception as e:
		log.warning(
			f"NativeSpeechGeneration installTasks: Failed to copy existing libraries during update: {e}",
		)

	log.info("NativeSpeechGeneration add-on onInstall phase completed.")


def onUninstall() -> None:
	"""
	Called when the add-on is uninstalled.
	The configuration is intentionally preserved so add-on updates do not wipe user settings.
	"""
	log.info("NativeSpeechGeneration uninstall: preserving configuration to avoid data loss across updates.")
