import contextlib
import importlib
import os
import re
import struct
import sys
import threading
from dataclasses import dataclass
from types import ModuleType
from typing import Any

from logHandler import log

_MISSING = object()
_RUNTIME_LOCK = threading.RLock()
_CONFLICT_PREFIXES = (
	"google",
	"pydantic",
	"pydantic_core",
	"annotated_types",
	"typing_extensions",
	"websockets",
	"httpx",
	"httpcore",
	"anyio",
	"sniffio",
	"certifi",
	"charset_normalizer",
	"idna",
	"cryptography",
	"cffi",
	"pycparser",
	"h11",
	"distro",
	"tenacity",
	"pyasn1",
	"pyasn1_modules",
	"typing_inspection",
)
_BINARY_TAG_PATTERN = re.compile(r"\.(cp\d+)-(win32|win_amd64|win_arm64)\.pyd$", re.IGNORECASE)


def _has_prefix(moduleName: str) -> bool:
	return any(moduleName == prefix or moduleName.startswith(f"{prefix}.") for prefix in _CONFLICT_PREFIXES)


def _collect_conflicting_modules() -> dict[str, ModuleType]:
	return {name: module for name, module in sys.modules.items() if _has_prefix(name)}


def _load_versions(modules: dict[str, ModuleType], names: tuple[str, ...]) -> dict[str, str]:
	versions: dict[str, str] = {}
	for name in names:
		module = modules.get(name)
		if module is None:
			continue
		version = getattr(module, "__version__", None)
		if isinstance(version, str):
			versions[name] = version
	return versions


def _get_current_binary_tags() -> tuple[str, str]:
	pythonTag = f"cp{sys.version_info.major}{sys.version_info.minor}"
	archBits = struct.calcsize("P") * 8
	if archBits == 64:
		platformTag = "win_amd64"
	elif archBits == 32:
		platformTag = "win32"
	else:
		platformTag = f"{archBits}-bit"
	return pythonTag, platformTag


def _scan_binary_compatibility_hints(libDir: str) -> dict[str, str]:
	currentPythonTag, currentPlatformTag = _get_current_binary_tags()
	hints: dict[str, str] = {}
	for root, _dirs, files in os.walk(libDir):
		for fileName in files:
			match = _BINARY_TAG_PATTERN.search(fileName)
			if match is None:
				continue
			targetPythonTag = match.group(1).lower()
			targetPlatformTag = match.group(2).lower()
			if targetPythonTag == currentPythonTag and targetPlatformTag == currentPlatformTag:
				continue
			fullPath = os.path.join(root, fileName)
			relPath = os.path.relpath(fullPath, libDir)
			packageName = relPath.split(os.sep, 1)[0]
			if packageName in hints:
				continue
			hints[packageName] = (
				f"Binary compatibility mismatch for '{relPath}': built for "
				f"{targetPythonTag}-{targetPlatformTag}, current runtime is "
				f"{currentPythonTag}-{currentPlatformTag}. Reinstall the add-on "
				"libraries using NVDA's embedded Python."
			)
	return hints


def _combine_error_details(error: BaseException, *hints: str | None) -> str:
	parts = [repr(error)]
	for hint in hints:
		if hint:
			parts.append(hint)
	return " | ".join(parts)


@dataclass
class VendorRuntime:
	libDir: str
	genai: Any | None
	types: Any | None
	pyaudio: ModuleType | None
	modules: dict[str, ModuleType]
	versions: dict[str, str]
	genaiError: str | None
	pyaudioError: str | None

	@property
	def genaiAvailable(self) -> bool:
		return self.genai is not None and self.types is not None

	@property
	def pyaudioAvailable(self) -> bool:
		return self.pyaudio is not None


def _create_runtime(libDir: str) -> VendorRuntime:
	absLibDir = os.path.abspath(libDir)
	genai = None
	types = None
	pyaudio = None
	runtimeModules: dict[str, ModuleType] = {}
	versions: dict[str, str] = {}
	genaiError: str | None = None
	pyaudioError: str | None = None
	binaryCompatibilityHints = _scan_binary_compatibility_hints(absLibDir)

	with _RUNTIME_LOCK:
		originalPath = list(sys.path)
		originalModules = _collect_conflicting_modules()
		try:
			sys.path = [absLibDir] + [p for p in sys.path if p != absLibDir]
			for moduleName in list(sys.modules.keys()):
				if _has_prefix(moduleName):
					sys.modules.pop(moduleName, None)

			try:
				pyaudio = importlib.import_module("pyaudio")
			except Exception as error:
				pyaudio = None
				pyaudioError = _combine_error_details(error, binaryCompatibilityHints.get("pyaudio"))

			try:
				from google import genai as loadedGenai
				from google.genai import types as loadedTypes

				genai = loadedGenai
				types = loadedTypes
			except Exception as error:
				genai = None
				types = None
				genaiError = _combine_error_details(
					error,
					binaryCompatibilityHints.get("pydantic_core"),
				)

			runtimeModules = _collect_conflicting_modules()
			if pyaudio is not None:
				runtimeModules["pyaudio"] = pyaudio
			versions = _load_versions(
				runtimeModules,
				(
					"google.genai",
					"pydantic",
					"pydantic_core",
					"websockets",
					"httpx",
					"typing_extensions",
					"pyaudio",
				),
			)
		finally:
			sys.path = originalPath
			for moduleName in list(sys.modules.keys()):
				if _has_prefix(moduleName):
					sys.modules.pop(moduleName, None)
			sys.modules.update(originalModules)

	if genai is not None and hasattr(genai, "__file__"):
		log.info(f"vendor_loader: google.genai loaded from {genai.__file__}")
	if pyaudio is not None and hasattr(pyaudio, "__file__"):
		log.info(f"vendor_loader: pyaudio loaded from {pyaudio.__file__}")
	if versions:
		log.info(f"vendor_loader: resolved versions {versions}")
	if genaiError:
		log.warning(f"vendor_loader: failed to import google.genai: {genaiError}")
	if pyaudioError:
		log.warning(f"vendor_loader: failed to import pyaudio: {pyaudioError}")

	return VendorRuntime(
		libDir=absLibDir,
		genai=genai,
		types=types,
		pyaudio=pyaudio,
		modules=runtimeModules,
		versions=versions,
		genaiError=genaiError,
		pyaudioError=pyaudioError,
	)


@contextlib.contextmanager
def runtime_scope(runtime: VendorRuntime):
	with _RUNTIME_LOCK:
		originalPath = list(sys.path)
		moduleSnapshot = {name: sys.modules.get(name, _MISSING) for name in runtime.modules}
		prefixBefore = _collect_conflicting_modules()
		try:
			sys.path = [runtime.libDir] + [p for p in sys.path if p != runtime.libDir]
			sys.modules.update(runtime.modules)
			yield
			for name, module in list(sys.modules.items()):
				if _has_prefix(name):
					runtime.modules[name] = module
			if runtime.pyaudio is not None:
				runtime.modules["pyaudio"] = runtime.pyaudio
		finally:
			for name in list(sys.modules.keys()):
				if _has_prefix(name):
					sys.modules.pop(name, None)
			sys.modules.update(prefixBefore)
			for name, originalValue in moduleSnapshot.items():
				if originalValue is _MISSING:
					sys.modules.pop(name, None)
				else:
					sys.modules[name] = originalValue
			sys.path = originalPath


def load_runtime(libDir: str) -> VendorRuntime:
	return _create_runtime(libDir)
