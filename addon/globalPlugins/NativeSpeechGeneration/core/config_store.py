import base64
import ctypes
import os
from dataclasses import dataclass
from typing import Any, Final, Literal

import config
from logHandler import log

from .constants import CONFIG_DOMAIN

API_KEY_ENV_VAR: Final[str] = "GEMINI_API_KEY"
_DPAPI_DESCRIPTION: Final[str] = "Native Speech Generation API Key"
_CRYPTPROTECT_UI_FORBIDDEN: Final[int] = 0x1
_CONFIG_SPEC: Final[dict[str, str]] = {
	"apiKey": "string(default='')",
	"apiKeyEncrypted": "string(default='')",
}

ApiKeySource = Literal["stored", "environment", "missing"]
ApiKeyStatus = Literal["stored", "environment", "missing", "undecryptable", "legacyMigrated"]


@dataclass(frozen=True)
class ApiKeyResolution:
	value: str
	source: ApiKeySource
	status: ApiKeyStatus


class ApiKeyStorageError(RuntimeError):
	pass


class _DATA_BLOB(ctypes.Structure):
	_fields_ = [
		("cbData", ctypes.c_uint32),
		("pbData", ctypes.POINTER(ctypes.c_ubyte)),
	]


def registerConfigSpec() -> None:
	config.conf.spec[CONFIG_DOMAIN] = _CONFIG_SPEC.copy()
	_getConfigSection()


def prepareConfigForStartup(*, persist: bool) -> bool:
	registerConfigSpec()
	removedLegacyPlaintext = _removeLegacyPlaintextIfEncryptedExists()
	migratedLegacyPlaintext = _migratePlaintextApiKey()
	if persist and (removedLegacyPlaintext or migratedLegacyPlaintext):
		config.save()
	return removedLegacyPlaintext or migratedLegacyPlaintext


def getStoredApiKey() -> str:
	prepareConfigForStartup(persist=False)
	encryptedValue = _getTextSetting("apiKeyEncrypted").strip()
	if not encryptedValue:
		return ""
	try:
		return _decryptApiKey(encryptedValue)
	except ApiKeyStorageError as error:
		log.warning(f"Stored encrypted Gemini API key could not be decrypted: {error}")
		return ""


def prepareApiKeyForStorage(value: str) -> tuple[str, str]:
	cleanValue = value.strip()
	if not cleanValue:
		return "", ""
	return cleanValue, _encryptApiKey(cleanValue)


def writePreparedApiKey(cleanValue: str, encryptedValue: str) -> None:
	registerConfigSpec()
	if not cleanValue:
		_setTextSetting("apiKeyEncrypted", "")
		_setTextSetting("apiKey", "")
		return
	_setTextSetting("apiKeyEncrypted", encryptedValue)
	_setTextSetting("apiKey", "")


def setStoredApiKey(value: str) -> None:
	cleanValue, encryptedValue = prepareApiKeyForStorage(value)
	writePreparedApiKey(cleanValue, encryptedValue)


def resolveApiKey() -> ApiKeyResolution:
	migratedLegacyPlaintext = prepareConfigForStartup(persist=False)
	encryptedValue = _getTextSetting("apiKeyEncrypted").strip()
	if encryptedValue:
		try:
			return ApiKeyResolution(
				value=_decryptApiKey(encryptedValue),
				source="stored",
				status="legacyMigrated" if migratedLegacyPlaintext else "stored",
			)
		except ApiKeyStorageError as error:
			log.warning(f"Stored encrypted Gemini API key could not be decrypted: {error}")
			environmentValue = _getEnvironmentApiKey()
			if environmentValue:
				return ApiKeyResolution(
					value=environmentValue,
					source="environment",
					status="undecryptable",
				)
			return ApiKeyResolution(value="", source="missing", status="undecryptable")

	environmentValue = _getEnvironmentApiKey()
	if environmentValue:
		return ApiKeyResolution(value=environmentValue, source="environment", status="environment")
	return ApiKeyResolution(value="", source="missing", status="missing")


def _getEnvironmentApiKey() -> str:
	return os.environ.get(API_KEY_ENV_VAR, "").strip()


def _getConfigSection() -> Any:
	return config.conf[CONFIG_DOMAIN]


def _getTextSetting(name: str) -> str:
	value = _getConfigSection().get(name, "")
	return value if isinstance(value, str) else str(value or "")


def _setTextSetting(name: str, value: str) -> None:
	_getConfigSection()[name] = value


def _removeLegacyPlaintextIfEncryptedExists() -> bool:
	legacyValue = _getTextSetting("apiKey").strip()
	encryptedValue = _getTextSetting("apiKeyEncrypted").strip()
	if not (legacyValue and encryptedValue):
		return False
	_setTextSetting("apiKey", "")
	log.info("Removed legacy plaintext Gemini API key from configuration.")
	return True


def _migratePlaintextApiKey() -> bool:
	legacyValue = _getTextSetting("apiKey").strip()
	encryptedValue = _getTextSetting("apiKeyEncrypted").strip()
	if not legacyValue or encryptedValue:
		return False
	try:
		_setTextSetting("apiKeyEncrypted", _encryptApiKey(legacyValue))
	except ApiKeyStorageError:
		log.error(
			"Failed to migrate the legacy plaintext Gemini API key to encrypted storage.",
			exc_info=True,
		)
		return False
	_setTextSetting("apiKey", "")
	log.info("Migrated legacy plaintext Gemini API key to DPAPI-protected storage.")
	return True


def _encryptApiKey(value: str) -> str:
	if not value:
		return ""
	try:
		protectedValue = _protectBytesWithDpapi(value.encode("utf-8"))
	except Exception as error:
		raise ApiKeyStorageError("Failed to encrypt the API key with Windows DPAPI.") from error
	return base64.b64encode(protectedValue).decode("ascii")


def _decryptApiKey(value: str) -> str:
	if not value:
		return ""
	try:
		protectedValue = base64.b64decode(value.encode("ascii"), validate=True)
	except Exception as error:
		raise ApiKeyStorageError("Stored API key data is not valid base64.") from error
	try:
		plainValue = _unprotectBytesWithDpapi(protectedValue)
	except Exception as error:
		raise ApiKeyStorageError(
			"Stored API key data could not be decrypted for this Windows user or machine.",
		) from error
	try:
		return plainValue.decode("utf-8")
	except UnicodeDecodeError as error:
		raise ApiKeyStorageError("Stored API key data is not valid UTF-8 text.") from error


def _protectBytesWithDpapi(value: bytes) -> bytes:
	try:
		import win32crypt
	except ImportError:
		return _protectBytesWithCtypes(value)
	return win32crypt.CryptProtectData(
		value,
		_DPAPI_DESCRIPTION,
		None,
		None,
		None,
		_CRYPTPROTECT_UI_FORBIDDEN,
	)


def _unprotectBytesWithDpapi(value: bytes) -> bytes:
	try:
		import win32crypt
	except ImportError:
		return _unprotectBytesWithCtypes(value)
	_description, plainValue = win32crypt.CryptUnprotectData(
		value,
		None,
		None,
		None,
		_CRYPTPROTECT_UI_FORBIDDEN,
	)
	return plainValue


def _protectBytesWithCtypes(value: bytes) -> bytes:
	dataIn, inputBuffer = _createDataBlob(value)
	dataOut = _DATA_BLOB()
	crypt32, _kernel32 = _loadDpapiLibraries()
	if not crypt32.CryptProtectData(
		ctypes.byref(dataIn),
		_DPAPI_DESCRIPTION,
		None,
		None,
		None,
		_CRYPTPROTECT_UI_FORBIDDEN,
		ctypes.byref(dataOut),
	):
		raise ctypes.WinError(ctypes.get_last_error())
	# Keep inputBuffer alive until CryptProtectData returns; dataIn points into it.
	del inputBuffer
	return _copyAndFreeDataBlob(dataOut)


def _unprotectBytesWithCtypes(value: bytes) -> bytes:
	dataIn, inputBuffer = _createDataBlob(value)
	dataOut = _DATA_BLOB()
	crypt32, _kernel32 = _loadDpapiLibraries()
	if not crypt32.CryptUnprotectData(
		ctypes.byref(dataIn),
		None,
		None,
		None,
		None,
		_CRYPTPROTECT_UI_FORBIDDEN,
		ctypes.byref(dataOut),
	):
		raise ctypes.WinError(ctypes.get_last_error())
	# Keep inputBuffer alive until CryptUnprotectData returns; dataIn points into it.
	del inputBuffer
	return _copyAndFreeDataBlob(dataOut)


def _createDataBlob(value: bytes) -> tuple[_DATA_BLOB, ctypes.Array[ctypes.c_char] | None]:
	if not value:
		return _DATA_BLOB(0, ctypes.POINTER(ctypes.c_ubyte)()), None
	buffer = ctypes.create_string_buffer(value, len(value))
	return _DATA_BLOB(
		len(value),
		ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)),
	), buffer


def _copyAndFreeDataBlob(blob: _DATA_BLOB) -> bytes:
	_crypt32, kernel32 = _loadDpapiLibraries()
	try:
		if not blob.cbData or not blob.pbData:
			return b""
		return ctypes.string_at(blob.pbData, blob.cbData)
	finally:
		if blob.pbData:
			kernel32.LocalFree(ctypes.cast(blob.pbData, ctypes.c_void_p))


def _loadDpapiLibraries() -> tuple[ctypes.WinDLL, ctypes.WinDLL]:
	crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
	kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
	crypt32.CryptProtectData.argtypes = (
		ctypes.POINTER(_DATA_BLOB),
		ctypes.c_wchar_p,
		ctypes.POINTER(_DATA_BLOB),
		ctypes.c_void_p,
		ctypes.c_void_p,
		ctypes.c_uint32,
		ctypes.POINTER(_DATA_BLOB),
	)
	crypt32.CryptProtectData.restype = ctypes.c_int
	crypt32.CryptUnprotectData.argtypes = (
		ctypes.POINTER(_DATA_BLOB),
		ctypes.POINTER(ctypes.c_wchar_p),
		ctypes.POINTER(_DATA_BLOB),
		ctypes.c_void_p,
		ctypes.c_void_p,
		ctypes.c_uint32,
		ctypes.POINTER(_DATA_BLOB),
	)
	crypt32.CryptUnprotectData.restype = ctypes.c_int
	kernel32.LocalFree.argtypes = (ctypes.c_void_p,)
	kernel32.LocalFree.restype = ctypes.c_void_p
	return crypt32, kernel32
