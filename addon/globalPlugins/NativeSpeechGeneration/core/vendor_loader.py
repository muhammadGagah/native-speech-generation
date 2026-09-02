import contextlib
import importlib
import os
import re
import struct
import sys
import threading
from dataclasses import dataclass
from types import ModuleType

from logHandler import log

_MISSING = object()
_RUNTIME_LOCK = threading.RLock()
_CONFLICT_PREFIXES = ("pyaudio",)
_BINARY_TAG_PATTERN = re.compile(r"\.(cp\d+)-(win32|win_amd64|win_arm64)\.pyd$", re.IGNORECASE)


def _has_prefix(moduleName: str) -> bool:
	return any(moduleName == prefix or moduleName.startswith(f"{prefix}.") for prefix in _CONFLICT_PREFIXES)


def _collect_conflicting_modules() -> dict[str, ModuleType]:
	return {
		name: module
		for name, module in sys.modules.items()
		if _has_prefix(name) and isinstance(module, ModuleType)
	}


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
	pyaudio: ModuleType | None
	modules: dict[str, ModuleType]
	versions: dict[str, str]
	pyaudioError: str | None

	@property
	def pyaudioAvailable(self) -> bool:
		return self.pyaudio is not None


def _create_runtime(libDir: str) -> VendorRuntime:
	absLibDir = os.path.abspath(libDir)
	if not os.path.isdir(absLibDir):
		error = f"Vendor library directory does not exist: {absLibDir}"
		log.warning(f"vendor_loader: {error}")
		return VendorRuntime(
			libDir=absLibDir,
			pyaudio=None,
			modules={},
			versions={},
			pyaudioError=error,
		)
	pyaudio = None
	runtimeModules: dict[str, ModuleType] = {}
	versions: dict[str, str] = {}
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

			runtimeModules = _collect_conflicting_modules()
			if pyaudio is not None:
				runtimeModules["pyaudio"] = pyaudio
			versions = _load_versions(runtimeModules, ("pyaudio",))
		finally:
			sys.path = originalPath
			for moduleName in list(sys.modules.keys()):
				if _has_prefix(moduleName):
					sys.modules.pop(moduleName, None)
			sys.modules.update(originalModules)

	if pyaudio is not None and hasattr(pyaudio, "__file__"):
		log.debug(f"vendor_loader: pyaudio loaded from {pyaudio.__file__}")
	if versions:
		log.debug(f"vendor_loader: resolved versions {versions}")
	if pyaudioError:
		log.warning(f"vendor_loader: failed to import pyaudio: {pyaudioError}")

	return VendorRuntime(
		libDir=absLibDir,
		pyaudio=pyaudio,
		modules=runtimeModules,
		versions=versions,
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
			for name in list(sys.modules.keys()):
				if _has_prefix(name):
					sys.modules.pop(name, None)
			sys.modules.update(runtime.modules)
			yield
		finally:
			# Preserve modules imported lazily even when the scoped operation fails.
			for name, module in _collect_conflicting_modules().items():
				runtime.modules[name] = module
			if runtime.pyaudio is not None:
				runtime.modules["pyaudio"] = runtime.pyaudio
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
