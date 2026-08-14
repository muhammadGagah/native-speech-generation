import glob
import hashlib
import json
import os
import re
import shutil
import tempfile
import threading
import time
import urllib.request
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import addonHandler
import core
import gui
import wx
from logHandler import log

addonHandler.initTranslation()

LIBRARY_RELEASE_API_URL = "https://api.github.com/repos/muhammadGagah/python-library-add-on-Native-Speech-Generation/releases/latest"
LIBRARY_RELEASE_DOWNLOAD_BASE = (
	"https://github.com/muhammadGagah/python-library-add-on-Native-Speech-Generation/releases/download"
)
APPROVED_LIBRARY_VERSION = "2.2.0"
APPROVED_LIBRARY_SHA256 = {
	"lib.zip": "96140636befa9880fbe48efc309f71f6057e80f48a7e58299d9657287df76d90",
	"lib64.zip": "f8082c18d503454728b8d7ab97dbc407cd74c8ee086f6e2a6fde27dff9945b37",
}
NVDA_2026_RUNTIME_VERSION = (2026, 1, 0)
USER_AGENT = "NativeSpeechGeneration-NVDA-Addon"
SHA256_RE = re.compile(r"\b([a-fA-F0-9]{64})\b")

PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
ADDON_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LIB_DIR = os.path.join(PACKAGE_DIR, "lib")


@dataclass(frozen=True)
class LibraryAsset:
	version: str
	name: str
	url: str
	sha256: str
	source: str


class LibraryUpdateError(RuntimeError):
	pass


def cleanupTrash() -> None:
	"""Remove dependency update leftovers from previous sessions."""
	for pattern in ("lib_trash_*", ".lib_staging_*", ".lib_ready_*"):
		for trashDir in glob.glob(os.path.join(PACKAGE_DIR, pattern)):
			if not os.path.isdir(trashDir):
				continue
			try:
				shutil.rmtree(trashDir, ignore_errors=True)
				log.info(f"lib_updater: Cleaned temporary directory: {trashDir}")
			except Exception as error:
				log.warning(f"lib_updater: Failed to clean temporary directory {trashDir}: {error}")


def initialize() -> None:
	"""Run startup cleanup for dependency update state."""
	cleanupTrash()


def parseNvdaVersion(versionText: str) -> tuple[int, int, int] | None:
	match = re.search(r"(\d{4})\.(\d+)(?:\.(\d+))?", versionText)
	if match is None:
		return None
	year = int(match.group(1))
	major = int(match.group(2))
	minor = int(match.group(3) or 0)
	return year, major, minor


def getCurrentNvdaVersionText() -> str:
	try:
		import buildVersion

		return str(buildVersion.version)
	except Exception as error:
		log.warning(f"lib_updater: Could not read NVDA version: {error}", exc_info=True)
		return ""


def getRuntimeAssetName(versionText: str | None = None) -> str:
	"""Return the dependency archive name for the running NVDA runtime."""
	if versionText is None:
		versionText = getCurrentNvdaVersionText()
	nvdaVersion = parseNvdaVersion(versionText)
	if nvdaVersion is None:
		log.warning(
			"lib_updater: Could not parse NVDA version for dependency selection; using lib.zip.",
		)
		return "lib.zip"
	if nvdaVersion >= NVDA_2026_RUNTIME_VERSION:
		return "lib64.zip"
	return "lib.zip"


def getApprovedLibraryAsset(assetName: str | None = None) -> LibraryAsset:
	"""Return the pinned dependency archive approved for stable add-on releases."""
	if assetName is None:
		assetName = getRuntimeAssetName()
	sha256 = APPROVED_LIBRARY_SHA256.get(assetName, "").strip()
	if not sha256:
		raise LibraryUpdateError(
			# Translators: Error shown when this add-on has no trusted checksum for a dependency archive.
			_("No approved checksum is bundled for {assetName}.").format(assetName=assetName),
		)
	return LibraryAsset(
		version=APPROVED_LIBRARY_VERSION,
		name=assetName,
		url=f"{LIBRARY_RELEASE_DOWNLOAD_BASE}/{APPROVED_LIBRARY_VERSION}/{assetName}",
		sha256=sha256,
		source="approved",
	)


def getLatestVerifiedLibraryAsset(assetName: str | None = None) -> LibraryAsset:
	"""Return a checksum-verified asset from the latest GitHub release."""
	if assetName is None:
		assetName = getRuntimeAssetName()
	release = _readJsonUrl(LIBRARY_RELEASE_API_URL)
	version = str(release.get("tag_name") or "")
	if not version:
		raise LibraryUpdateError(
			# Translators: Error shown when the GitHub release metadata cannot identify the release version.
			_("The latest library release does not include a version tag."),
		)
	asset = _findReleaseAsset(release, assetName)
	checksum = _findReleaseChecksum(release, assetName, asset)
	return LibraryAsset(
		version=version,
		name=assetName,
		url=str(asset["browser_download_url"]),
		sha256=checksum,
		source="github",
	)


getVerifiedLibraryAsset = getLatestVerifiedLibraryAsset


def downloadAndExtract(
	_addonDir: str,
	progressCallback: Callable[[int, str], None],
	*,
	forceLatest: bool = False,
) -> bool:
	"""Download, verify, and install dependency libraries for this NVDA runtime."""
	try:
		if forceLatest:
			log.info("lib_updater: User requested dependency reinstall from the latest verified release.")
		asset = _resolveLibraryAsset(forceLatest=forceLatest)
		_installLibraryAsset(asset, progressCallback)
		return True
	except Exception as error:
		log.error(f"Failed to download or install libraries: {error}", exc_info=True)
		wx.CallAfter(
			gui.messageBox,
			# Translators: Error shown when dependency download, verification, or extraction fails.
			_(
				"Failed to download or install required libraries. The add-on might not work correctly.\n\nError: {error}",
			).format(error=error),
			_("Error"),
			wx.OK | wx.ICON_ERROR,
		)
		return False


def checkAndInstallDependencies(forceReinstall: bool = False) -> None:
	"""Prompt the user and install dependency libraries when needed."""
	if not forceReinstall and os.path.exists(LIB_DIR):
		log.info("Dependencies already installed, skipping check.")
		return

	def runInstallation() -> None:
		progressDialog = wx.ProgressDialog(
			# Translators: Title of a progress dialog shown while installing add-on dependencies.
			_("Installing Dependencies"),
			# Translators: Initial progress message while dependency installation is being prepared.
			_("Checking for required libraries..."),
			maximum=100,
			parent=gui.mainFrame,
			style=wx.PD_APP_MODAL | wx.PD_AUTO_HIDE,
		)

		def updateProgress(progress: int, message: str) -> None:
			if progress == 100:
				# Translators: Progress message shown when dependency installation has completed.
				progressDialog.Update(100, _("Installation complete!"))
				wx.CallLater(500, progressDialog.Destroy)
			else:
				progressDialog.Update(progress, message)

		def doWork() -> None:
			success = downloadAndExtract(ADDON_DIR, updateProgress, forceLatest=forceReinstall)

			def finalMessage() -> None:
				if success:
					message = _(
						# Translators: Message shown after dependencies are installed and NVDA must restart.
						"The Native Speech Generation libraries have been successfully installed/updated.\n\nPlease restart NVDA for the changes to take effect.",
					)
					# Translators: Title of the dialog shown after dependency installation completes.
					title = _("Installation Complete")
					res = wx.MessageBox(message, title, wx.OK | wx.ICON_INFORMATION)
					if res == wx.OK:
						core.restart()
				else:
					# Translators: Error shown when dependency installation fails.
					message = _("Library installation failed. Please check the log.")
					# Translators: Title of a dependency installation error dialog.
					title = _("Error")
					wx.CallAfter(wx.MessageBox, message, title, wx.OK | wx.ICON_ERROR)

			wx.CallAfter(finalMessage)

		threading.Thread(target=doWork, daemon=True).start()

	def confirmAction() -> None:
		if forceReinstall:
			msg = _(
				# Translators: Confirmation before reinstalling or updating external Python dependencies from GitHub.
				"This will download the latest verified libraries for your NVDA version and require an NVDA restart. Continue?",
			)
			# Translators: Title of the dialog confirming a dependency library reinstall.
			title = _("Confirm Library Update")
		else:
			msg = _(
				# Translators: Confirmation shown when required libraries are missing.
				"Required libraries for Native Speech Generation are missing. Click OK to download the latest verified package for your NVDA version.",
			)
			# Translators: Title of the dialog shown when dependency libraries are missing.
			title = _("Missing Dependencies")

		res = wx.MessageBox(msg, title, wx.OK | wx.CANCEL | wx.ICON_INFORMATION)
		if res == wx.OK:
			runInstallation()
		else:
			log.info("User cancelled dependency installation.")

	wx.CallAfter(confirmAction)


def reinstallDependencies() -> None:
	"""Public wrapper to reinstall the latest verified dependency package."""
	checkAndInstallDependencies(forceReinstall=True)


def _resolveLibraryAsset(*, forceLatest: bool = False) -> LibraryAsset:
	assetName = getRuntimeAssetName()
	try:
		return getLatestVerifiedLibraryAsset(assetName)
	except Exception as error:
		if forceLatest:
			raise
		log.warning(
			f"lib_updater: Could not resolve latest verified {assetName}; falling back to approved release: {error}",
			exc_info=True,
		)
		return getApprovedLibraryAsset(assetName)


def _installLibraryAsset(
	asset: LibraryAsset,
	progressCallback: Callable[[int, str], None],
) -> None:
	zipPath = ""
	candidateDir = ""
	try:
		fd, zipPath = tempfile.mkstemp(prefix="nsg_lib_", suffix=f"_{asset.name}")
		os.close(fd)
		_downloadLibraryZip(asset, zipPath, progressCallback)
		_verifySha256(zipPath, asset.sha256)
		wx.CallAfter(
			progressCallback,
			80,
			# Translators: Progress message shown while verified libraries are being extracted.
			_("Extracting libraries..."),
		)
		candidateDir = _extractLibraryCandidate(zipPath)
		wx.CallAfter(
			progressCallback,
			92,
			# Translators: Progress message shown while replacing the dependency library folder.
			_("Installing libraries..."),
		)
		replaceLibraryDirectory(candidateDir)
		candidateDir = ""
		wx.CallAfter(
			progressCallback,
			100,
			# Translators: Progress message shown after library extraction and installation.
			_("Library installation complete."),
		)
		log.info(
			f"lib_updater: Installed {asset.name} from {asset.source} release {asset.version}.",
		)
	finally:
		if zipPath and os.path.exists(zipPath):
			os.remove(zipPath)
		if candidateDir and os.path.isdir(candidateDir):
			shutil.rmtree(candidateDir, ignore_errors=True)


def _downloadLibraryZip(
	asset: LibraryAsset,
	zipPath: str,
	progressCallback: Callable[[int, str], None],
) -> None:
	wx.CallAfter(
		progressCallback,
		10,
		# Translators: Progress message shown before dependency download begins.
		_("Downloading libraries..."),
	)
	with _openUrl(asset.url, timeout=30) as response, open(zipPath, "wb") as outFile:
		totalLength = _getResponseLength(response)
		downloaded = 0
		while True:
			data = response.read(8192)
			if not data:
				break
			downloaded += len(data)
			outFile.write(data)
			if totalLength:
				percent = 10 + int(downloaded / totalLength * 60)
				wx.CallAfter(
					progressCallback,
					min(percent, 70),
					# Translators: Progress message shown while dependency download is in progress.
					_("Downloading..."),
				)
	wx.CallAfter(
		progressCallback,
		72,
		# Translators: Progress message shown while checking the downloaded dependency package.
		_("Verifying libraries..."),
	)


def _extractLibraryCandidate(zipPath: str) -> str:
	stagingDir = tempfile.mkdtemp(prefix=".lib_staging_", dir=PACKAGE_DIR)
	try:
		with zipfile.ZipFile(zipPath, "r") as zipFile:
			_validateZipMembers(zipFile, stagingDir)
			zipFile.extractall(stagingDir)
		sourceDir = _getLibrarySourceDir(stagingDir)
		readyDir = os.path.join(PACKAGE_DIR, f".lib_ready_{int(time.time())}_{threading.get_ident()}")
		shutil.move(sourceDir, readyDir)
		if os.path.isdir(stagingDir):
			shutil.rmtree(stagingDir, ignore_errors=True)
		return readyDir
	except Exception:
		if os.path.isdir(stagingDir):
			shutil.rmtree(stagingDir, ignore_errors=True)
		raise


def replaceLibraryDirectory(candidateDir: str) -> None:
	trashDir = ""
	if os.path.exists(LIB_DIR):
		trashDir = os.path.join(PACKAGE_DIR, f"lib_trash_{int(time.time())}_{threading.get_ident()}")
		os.rename(LIB_DIR, trashDir)
	try:
		os.rename(candidateDir, LIB_DIR)
	except Exception:
		if trashDir and os.path.isdir(trashDir) and not os.path.exists(LIB_DIR):
			os.rename(trashDir, LIB_DIR)
		raise
	if trashDir and os.path.isdir(trashDir):
		shutil.rmtree(trashDir, ignore_errors=True)


def _validateZipMembers(zipFile: zipfile.ZipFile, stagingDir: str) -> None:
	stagingAbs = os.path.abspath(stagingDir)
	for member in zipFile.infolist():
		memberName = member.filename.replace("\\", "/")
		normalized = os.path.normpath(memberName)
		parts = normalized.split(os.sep)
		if (
			not memberName
			or os.path.isabs(memberName)
			or os.path.splitdrive(memberName)[0]
			or normalized.startswith("..")
			or ".." in parts
		):
			raise LibraryUpdateError(
				# Translators: Error shown when a downloaded dependency archive contains an unsafe path.
				_("The library archive contains an unsafe path: {path}").format(path=member.filename),
			)
		targetAbs = os.path.abspath(os.path.join(stagingDir, normalized))
		if os.path.commonpath([stagingAbs, targetAbs]) != stagingAbs:
			raise LibraryUpdateError(
				# Translators: Error shown when a downloaded dependency archive would extract outside the target folder.
				_("The library archive contains a path outside the installation directory: {path}").format(
					path=member.filename,
				),
			)


def _getLibrarySourceDir(stagingDir: str) -> str:
	topLevelLib = os.path.join(stagingDir, "lib")
	if os.path.isdir(topLevelLib):
		return topLevelLib
	return stagingDir


def _verifySha256(filePath: str, expectedSha256: str) -> None:
	actualSha256 = _calculateSha256(filePath)
	if actualSha256.lower() != expectedSha256.lower():
		raise LibraryUpdateError(
			# Translators: Error shown when a downloaded dependency package fails checksum verification.
			_("Library checksum mismatch. Expected {expected}, got {actual}.").format(
				expected=expectedSha256,
				actual=actualSha256,
			),
		)


def _calculateSha256(filePath: str) -> str:
	hashObj = hashlib.sha256()
	with open(filePath, "rb") as fileObj:
		for chunk in iter(lambda: fileObj.read(1024 * 1024), b""):
			hashObj.update(chunk)
	return hashObj.hexdigest()


def _readJsonUrl(url: str) -> dict[str, Any]:
	with _openUrl(url, timeout=20) as response:
		return json.loads(response.read().decode("utf-8"))


def _readTextUrl(url: str) -> str:
	with _openUrl(url, timeout=20) as response:
		return response.read().decode("utf-8", errors="replace")


def _openUrl(url: str, *, timeout: int):
	request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
	return urllib.request.urlopen(request, timeout=timeout)


def _getResponseLength(response: Any) -> int:
	contentLength = response.headers.get("Content-Length", "")
	try:
		return int(contentLength)
	except (TypeError, ValueError):
		return 0


def _findReleaseAsset(release: dict[str, Any], assetName: str) -> dict[str, Any]:
	for asset in release.get("assets", []):
		if asset.get("name") == assetName and asset.get("browser_download_url"):
			return asset
	raise LibraryUpdateError(
		# Translators: Error shown when a GitHub release lacks the dependency asset needed for this NVDA version.
		_("The latest library release does not contain {assetName}.").format(assetName=assetName),
	)


def _findReleaseChecksum(release: dict[str, Any], assetName: str, asset: dict[str, Any]) -> str:
	checksumAssetNames = (f"{assetName}.sha256", "checksums.txt")
	for checksumAssetName in checksumAssetNames:
		checksumAsset = _findOptionalReleaseAsset(release, checksumAssetName)
		if checksumAsset is None:
			continue
		checksumText = _readTextUrl(str(checksumAsset["browser_download_url"]))
		checksum = _parseChecksumText(
			checksumText,
			assetName,
			allowFallback=checksumAssetName != "checksums.txt",
		)
		if checksum:
			return checksum
	checksum = _parseReleaseAssetDigest(asset)
	if checksum:
		return checksum
	raise LibraryUpdateError(
		# Translators: Error shown when a dependency release lacks checksum metadata.
		_("The latest library release does not include a checksum for {assetName}.").format(
			assetName=assetName,
		),
	)


def _findOptionalReleaseAsset(release: dict[str, Any], assetName: str) -> dict[str, Any] | None:
	for asset in release.get("assets", []):
		if asset.get("name") == assetName and asset.get("browser_download_url"):
			return asset
	return None


def _parseReleaseAssetDigest(asset: dict[str, Any]) -> str:
	digest = str(asset.get("digest") or "")
	if not digest.lower().startswith("sha256:"):
		return ""
	checksum = digest.split(":", 1)[1].strip()
	if SHA256_RE.fullmatch(checksum) is None:
		return ""
	return checksum


def _parseChecksumText(checksumText: str, assetName: str, *, allowFallback: bool) -> str:
	fallback = ""
	for line in checksumText.splitlines():
		match = SHA256_RE.search(line)
		if match is None:
			continue
		if assetName in line:
			return match.group(1)
		if not fallback:
			fallback = match.group(1)
	return fallback if allowFallback else ""
