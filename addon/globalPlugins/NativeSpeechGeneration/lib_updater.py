import ctypes
import glob
import hashlib
import json
import os
import shutil
import ssl
import struct
import sys
import tempfile
import threading
import time
import urllib.parse
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

if __package__:
	from .core.nvda_compat import shouldWriteToDisk
else:
	# Keep the updater unit-testable when loaded as a standalone module.
	def shouldWriteToDisk() -> bool:
		return True


addonHandler.initTranslation()

PYAUDIO_VERSION = "0.2.14"
PYAUDIO_RELEASE_API_URL = f"https://pypi.org/pypi/PyAudio/{PYAUDIO_VERSION}/json"
APPROVED_LIBRARY_SHA256 = {
	"PyAudio-0.2.14-cp311-cp311-win32.whl": "506b32a595f8693811682ab4b127602d404df7dfc453b499c91a80d0f7bad289",
	"PyAudio-0.2.14-cp311-cp311-win_amd64.whl": "bbeb01d36a2f472ae5ee5e1451cacc42112986abe622f735bb870a5db77cf903",
	"PyAudio-0.2.14-cp312-cp312-win32.whl": "5fce4bcdd2e0e8c063d835dbe2860dac46437506af509353c7f8114d4bacbd5b",
	"PyAudio-0.2.14-cp312-cp312-win_amd64.whl": "12f2f1ba04e06ff95d80700a78967897a489c05e093e3bffa05a84ed9c0a7fa3",
	"PyAudio-0.2.14-cp313-cp313-win32.whl": "95328285b4dab57ea8c52a4a996cb52be6d629353315be5bfda403d15932a497",
	"PyAudio-0.2.14-cp313-cp313-win_amd64.whl": "692d8c1446f52ed2662120bcd9ddcb5aa2b71f38bda31e58b19fb4672fffba69",
}
USER_AGENT = "NativeSpeechGeneration-NVDA-Addon"

PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
ADDON_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LIB_DIR = os.path.join(PACKAGE_DIR, "lib")

_CERT_CHAIN_REFRESH_LOCK = threading.Lock()
_CERT_CHAIN_REFRESHED_HOSTS: set[str] = set()
_CERT_CHAIN_REFRESH_TIMEOUT = 20
_CERT_CHAIN_REFRESH_TIMEOUT_MS = 15_000


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
	if not shouldWriteToDisk():
		return
	for pattern in ("lib_trash_*", ".lib_staging_*", ".lib_ready_*"):
		for trashDir in glob.glob(os.path.join(PACKAGE_DIR, pattern)):
			if not os.path.isdir(trashDir):
				continue
			try:
				shutil.rmtree(trashDir, ignore_errors=True)
				log.debug(f"lib_updater: Cleaned temporary directory: {trashDir}")
			except Exception as error:
				log.warning(f"lib_updater: Failed to clean temporary directory {trashDir}: {error}")


def initialize() -> None:
	"""Run startup cleanup for dependency update state."""
	cleanupTrash()


def _getRuntimeTags(
	pythonVersion: tuple[int, int] | None = None,
	archBits: int | None = None,
) -> tuple[str, str]:
	if pythonVersion is None:
		pythonVersion = (sys.version_info.major, sys.version_info.minor)
	if archBits is None:
		archBits = struct.calcsize("P") * 8
	pythonTag = f"cp{pythonVersion[0]}{pythonVersion[1]}"
	if archBits == 64:
		platformTag = "win_amd64"
	elif archBits == 32:
		platformTag = "win32"
	else:
		raise LibraryUpdateError(f"Unsupported Python architecture: {archBits}-bit")
	return pythonTag, platformTag


def getRuntimeAssetName(
	pythonVersion: tuple[int, int] | None = None,
	archBits: int | None = None,
) -> str:
	"""Return the pinned PyAudio wheel matching NVDA's embedded Python runtime."""
	pythonTag, platformTag = _getRuntimeTags(pythonVersion, archBits)
	return f"PyAudio-{PYAUDIO_VERSION}-{pythonTag}-{pythonTag}-{platformTag}.whl"


def getApprovedLibraryAsset(assetName: str | None = None) -> LibraryAsset:
	"""Return the pinned, checksum-verified PyAudio wheel for this runtime."""
	if assetName is None:
		assetName = getRuntimeAssetName()
	sha256 = APPROVED_LIBRARY_SHA256.get(assetName, "").strip()
	if not sha256:
		raise LibraryUpdateError(
			# Translators: Error shown when this add-on has no trusted checksum for a dependency archive.
			_("No approved checksum is bundled for {assetName}.").format(assetName=assetName),
		)
	asset = _findPypiWheel(_readJsonUrl(PYAUDIO_RELEASE_API_URL), assetName)
	metadataChecksum = str(asset.get("digests", {}).get("sha256") or "")
	if metadataChecksum.lower() != sha256.lower():
		raise LibraryUpdateError(
			_("PyAudio checksum metadata does not match the checksum approved by this add-on."),
		)
	return LibraryAsset(
		version=PYAUDIO_VERSION,
		name=assetName,
		url=str(asset["url"]),
		sha256=sha256,
		source="pypi",
	)


getVerifiedLibraryAsset = getApprovedLibraryAsset


def downloadAndExtract(
	_addonDir: str,
	progressCallback: Callable[[int, str], None],
	*,
	forceLatest: bool = False,
) -> bool:
	"""Download, verify, and install dependency libraries for this NVDA runtime."""
	try:
		if forceLatest:
			log.debug("lib_updater: User requested a clean reinstall of the pinned PyAudio wheel.")
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
	if not shouldWriteToDisk():
		log.warning("Skipped dependency installation because NVDA must not write to disk.")
		return
	if not forceReinstall and _isCurrentLibraryInstall():
		log.debug("Dependencies already installed, skipping check.")
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
				"This will reinstall the verified PyAudio wheel for NVDA's Python runtime and require an NVDA restart. Continue?",
			)
			# Translators: Title of the dialog confirming a dependency library reinstall.
			title = _("Confirm Library Update")
		else:
			msg = _(
				# Translators: Confirmation shown when required libraries are missing.
				"PyAudio is missing or incompatible. Click OK to download the verified wheel for NVDA's Python runtime.",
			)
			# Translators: Title of the dialog shown when dependency libraries are missing.
			title = _("Missing Dependencies")

		res = wx.MessageBox(msg, title, wx.OK | wx.CANCEL | wx.ICON_INFORMATION)
		if res == wx.OK:
			runInstallation()
		else:
			log.debug("User cancelled dependency installation.")

	wx.CallAfter(confirmAction)


def reinstallDependencies() -> None:
	"""Public wrapper to reinstall the latest verified dependency package."""
	checkAndInstallDependencies(forceReinstall=True)


def _resolveLibraryAsset(*, forceLatest: bool = False) -> LibraryAsset:
	return getApprovedLibraryAsset(getRuntimeAssetName())


def _isCurrentLibraryInstall() -> bool:
	pyaudioDir = os.path.join(LIB_DIR, "pyaudio")
	if not os.path.isdir(pyaudioDir) or not os.path.isfile(os.path.join(pyaudioDir, "__init__.py")):
		return False
	pythonTag, platformTag = _getRuntimeTags()
	expectedBinary = os.path.join(pyaudioDir, f"_portaudio.{pythonTag}-{platformTag}.pyd")
	if not os.path.isfile(expectedBinary):
		return False
	allowedEntries = {"pyaudio", f"pyaudio-{PYAUDIO_VERSION}.dist-info", "__pycache__"}
	return all(name.lower() in allowedEntries for name in os.listdir(LIB_DIR))


def _installLibraryAsset(
	asset: LibraryAsset,
	progressCallback: Callable[[int, str], None],
) -> None:
	if not shouldWriteToDisk():
		raise LibraryUpdateError("NVDA is not allowed to write dependency files in the current mode.")
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
		log.debug(
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


def _findCertificateVerificationError(error: BaseException) -> ssl.SSLCertVerificationError | None:
	"""Find a certificate verification error wrapped by urllib or another client."""
	pending: list[BaseException] = [error]
	seen: set[int] = set()
	while pending:
		current = pending.pop()
		if id(current) in seen:
			continue
		seen.add(id(current))
		if isinstance(current, ssl.SSLCertVerificationError):
			return current
		for related in (
			getattr(current, "reason", None),
			getattr(current, "__cause__", None),
			getattr(current, "__context__", None),
		):
			if isinstance(related, BaseException):
				pending.append(related)
	return None


def _isMissingIssuerError(error: BaseException) -> bool:
	certificateError = _findCertificateVerificationError(error)
	if certificateError is None:
		return False
	verifyCode = getattr(certificateError, "verify_code", None)
	if verifyCode in (20, 21):
		return True
	message = str(certificateError).lower()
	return (
		"unable to get local issuer certificate" in message
		or "unable to verify the first certificate" in message
	)


def _getPeerCertificate(url: str, timeout: int) -> bytes:
	"""Read only the peer certificate using a temporary unverified TLS probe."""
	context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
	context.check_hostname = False
	context.verify_mode = ssl.CERT_NONE
	request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
	with urllib.request.urlopen(request, context=context, timeout=timeout) as response:
		socket = getattr(getattr(getattr(response, "fp", None), "raw", None), "_sock", None)
		if socket is None or not hasattr(socket, "getpeercert"):
			# Translators: Error shown when the updater cannot inspect the HTTPS peer certificate.
			raise LibraryUpdateError(_("Unable to inspect the HTTPS peer certificate."))
		certificate = socket.getpeercert(binary_form=True)
		if not isinstance(certificate, bytes) or not certificate:
			# Translators: Error shown when the HTTPS peer does not provide a certificate.
			raise LibraryUpdateError(_("The HTTPS peer did not provide a certificate."))
		return certificate


def _refreshWindowsCertificateChain(certificate: bytes) -> bool:
	"""Ask Windows CryptoAPI to build a chain and refresh missing trust roots."""
	if os.name != "nt":
		return False
	winDll: Any = getattr(ctypes, "WinDLL", None)
	if winDll is None:
		return False

	class CertificateEnhancedKeyUsage(ctypes.Structure):
		_fields_ = [("count", ctypes.c_uint32), ("identifiers", ctypes.c_void_p)]

	class CertificateUsageMatch(ctypes.Structure):
		_fields_ = [("matchType", ctypes.c_uint32), ("usage", CertificateEnhancedKeyUsage)]

	class CertificateChainParameters(ctypes.Structure):
		_fields_ = [
			("size", ctypes.c_uint32),
			("requestedUsage", CertificateUsageMatch),
			("requestedIssuancePolicy", CertificateUsageMatch),
			("urlRetrievalTimeout", ctypes.c_uint32),
			("checkRevocationFreshnessTime", ctypes.c_int),
			("revocationFreshnessTime", ctypes.c_uint32),
			("cacheResyncTime", ctypes.c_void_p),
			("strongSignParameters", ctypes.c_void_p),
			("strongSignFlags", ctypes.c_uint32),
		]

	try:
		crypt32: Any = winDll("crypt32.dll", use_last_error=True)
		createContext: Any = crypt32.CertCreateCertificateContext
		createContext.argtypes = [
			ctypes.c_uint32,
			ctypes.POINTER(ctypes.c_ubyte),
			ctypes.c_uint32,
		]
		createContext.restype = ctypes.c_void_p
		getChain: Any = crypt32.CertGetCertificateChain
		getChain.argtypes = [
			ctypes.c_void_p,
			ctypes.c_void_p,
			ctypes.c_void_p,
			ctypes.c_void_p,
			ctypes.POINTER(CertificateChainParameters),
			ctypes.c_uint32,
			ctypes.c_void_p,
			ctypes.POINTER(ctypes.c_void_p),
		]
		getChain.restype = ctypes.c_int
		freeContext: Any = crypt32.CertFreeCertificateContext
		freeContext.argtypes = [ctypes.c_void_p]
		freeContext.restype = ctypes.c_int
		freeChain: Any = crypt32.CertFreeCertificateChain
		freeChain.argtypes = [ctypes.c_void_p]
		freeChain.restype = None

		encodedCertificate = (ctypes.c_ubyte * len(certificate)).from_buffer_copy(certificate)
		certificateContext = createContext(0x00010001, encodedCertificate, len(certificate))
		if not certificateContext:
			log.debug(f"lib_updater: CertCreateCertificateContext failed ({ctypes.get_last_error()}).")
			return False
		chainContext = ctypes.c_void_p()
		chainParameters = CertificateChainParameters()
		chainParameters.size = ctypes.sizeof(CertificateChainParameters)
		chainParameters.urlRetrievalTimeout = _CERT_CHAIN_REFRESH_TIMEOUT_MS
		try:
			result = bool(
				getChain(
					None,
					certificateContext,
					None,
					None,
					ctypes.byref(chainParameters),
					0,
					None,
					ctypes.byref(chainContext),
				),
			)
			if not result:
				log.debug(f"lib_updater: CertGetCertificateChain failed ({ctypes.get_last_error()}).")
			return result
		finally:
			if chainContext:
				freeChain(chainContext)
			freeContext(certificateContext)
	except Exception as error:
		log.debug(f"lib_updater: Windows certificate-chain refresh failed: {error}", exc_info=True)
		return False


def _refreshWindowsRootForUrl(url: str, timeout: int) -> bool:
	if os.name != "nt":
		return False
	parsedUrl = urllib.parse.urlsplit(url)
	host = parsedUrl.hostname
	if parsedUrl.scheme.lower() != "https" or not host:
		return False
	with _CERT_CHAIN_REFRESH_LOCK:
		if host in _CERT_CHAIN_REFRESHED_HOSTS:
			return True
		try:
			certificate = _getPeerCertificate(url, min(timeout, _CERT_CHAIN_REFRESH_TIMEOUT))
			refreshed = _refreshWindowsCertificateChain(certificate)
			if refreshed:
				_CERT_CHAIN_REFRESHED_HOSTS.add(host)
			return refreshed
		except Exception as error:
			log.debug(f"lib_updater: Could not probe certificate for {host}: {error}", exc_info=True)
			return False


def _openUrl(url: str, *, timeout: int):
	request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
	try:
		return urllib.request.urlopen(request, timeout=timeout)
	except Exception as error:
		if not _isMissingIssuerError(error) or not _refreshWindowsRootForUrl(url, timeout):
			raise
		log.debug(f"lib_updater: Retrying verified HTTPS request after Windows certificate refresh: {url}")
		return urllib.request.urlopen(request, timeout=timeout)


def _getResponseLength(response: Any) -> int:
	contentLength = response.headers.get("Content-Length", "")
	try:
		return int(contentLength)
	except (TypeError, ValueError):
		return 0


def _findPypiWheel(release: dict[str, Any], assetName: str) -> dict[str, Any]:
	for asset in release.get("urls", []):
		if asset.get("filename") == assetName and asset.get("url"):
			return asset
	raise LibraryUpdateError(
		_("PyAudio {version} does not provide a wheel for this NVDA Python runtime: {assetName}.").format(
			version=PYAUDIO_VERSION,
			assetName=assetName,
		),
	)
