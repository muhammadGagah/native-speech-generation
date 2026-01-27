# -*- coding: utf-8 -*-
import struct
import wave
import os
import contextlib
from logHandler import log
import wx


def parseAudioMimeType(mimeType: str) -> dict[str, int]:
	"""Parses the MIME type string to extract sample rate and bit depth."""
	bitsPerSample = 16
	rate = 24000
	if not mimeType:
		return {"bitsPerSample": bitsPerSample, "rate": rate}

	parts = [p.strip() for p in mimeType.split(";")]
	for p in parts:
		if p.lower().startswith("rate="):
			with contextlib.suppress(Exception):
				rate = int(p.split("=", 1)[1])
		if "L" in p and p.lower().startswith("audio/l"):
			with contextlib.suppress(Exception):
				bitsPerSample = int(p.split("L", 1)[1])
	return {"bitsPerSample": bitsPerSample, "rate": rate}


def convertToWav(audioData: bytes, mimeType: str) -> bytes:
	"""Wraps raw PCM audio data in a WAV header based on MIME type parameters."""
	if mimeType and "wav" in mimeType.lower():
		return audioData

	params = parseAudioMimeType(mimeType)
	bitsPerSample = params.get("bitsPerSample", 16) or 16
	sampleRate = params.get("rate", 24000) or 24000
	numChannels = 1
	dataSize = len(audioData)
	bytesPerSample = bitsPerSample // 8
	blockAlign = numChannels * bytesPerSample
	byteRate = sampleRate * blockAlign
	chunkSize = 36 + dataSize

	header = struct.pack(
		"<4sI4s4sIHHIIHH4sI",
		b"RIFF",
		chunkSize,
		b"WAVE",
		b"fmt ",
		16,
		1,
		numChannels,
		sampleRate,
		byteRate,
		blockAlign,
		bitsPerSample,
		b"data",
		dataSize,
	)
	return header + audioData


def mergeWavFiles(inputPaths: list[str], outputPath: str) -> None:
	"""Combines multiple WAV files into a single continuous audio file."""
	if not inputPaths:
		raise ValueError("No input WAV files to merge.")

	with wave.open(inputPaths[0], "rb") as w0:
		params = w0.getparams()
		frames = [w0.readframes(w0.getnframes())]

	for p in inputPaths[1:]:
		with wave.open(p, "rb") as wi:
			if wi.getparams() != params:
				raise ValueError("WAV files have different parameters; cannot merge safely.")
			frames.append(wi.readframes(wi.getnframes()))

	with wave.open(outputPath, "wb") as wo:
		wo.setparams(params)
		for fr in frames:
			wo.writeframes(fr)
	log.info(f"Merged {len(inputPaths)} WAV files -> {outputPath}")


def saveBinaryFile(fileName: str, data: bytes) -> None:
	"""Writes binary data to a file, creating parent directories if necessary."""
	os.makedirs(os.path.dirname(fileName) or ".", exist_ok=True)
	with open(fileName, "wb") as f:
		f.write(data)
	log.info(f"Saved audio file: {fileName}")


def safeStartFile(path: str) -> None:
	"""Opens a file with the default OS application, handling errors safely."""
	try:
		os.startfile(path)
	except Exception as e:
		log.error(f"Failed to open file: {e}", exc_info=True)
		wx.CallAfter(
			wx.MessageBox,
			f"Audio generated, but failed to play automatically: {e}",
			"Info",
			wx.OK | wx.ICON_INFORMATION,
		)
