"""Audio probing, extraction and speech detection — thin wrappers over ffmpeg."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


def probe(path: Path) -> dict:
    """Return ffprobe metadata for a media file (streams + format)."""
    if shutil.which("ffprobe") is None:
        raise RuntimeError("ffprobe not found — install ffmpeg (e.g. `brew install ffmpeg`).")
    cmd = [
        "ffprobe", "-v", "error", "-print_format", "json",
        "-show_format", "-show_streams", str(path),
    ]
    result = _run(cmd)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed for {path}: {result.stderr.strip()}")
    return json.loads(result.stdout or "{}")


def has_audio_stream(path: Path) -> bool:
    """True if the file carries at least one audio stream."""
    try:
        info = probe(path)
    except RuntimeError:
        return False
    return any(s.get("codec_type") == "audio" for s in info.get("streams", []))


def duration_seconds(path: Path) -> Optional[float]:
    try:
        info = probe(path)
    except RuntimeError:
        return None
    fmt = info.get("format", {})
    if "duration" in fmt:
        try:
            return float(fmt["duration"])
        except (TypeError, ValueError):
            pass
    return None


def extract_audio(path: Path, dest: Optional[Path] = None) -> Path:
    """Extract a 16 kHz mono WAV suitable for Whisper. Returns the WAV path.

    If ``dest`` is omitted a temp file is created; the caller owns cleanup.
    """
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg not found — install ffmpeg (e.g. `brew install ffmpeg`).")
    if dest is None:
        fd, name = tempfile.mkstemp(suffix=".wav", prefix="voice_")
        dest = Path(name)
        import os

        os.close(fd)
    cmd = [
        "ffmpeg", "-y", "-i", str(path),
        "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le",
        str(dest),
    ]
    result = _run(cmd)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg audio extraction failed for {path}: {result.stderr.strip()}")
    return dest


def detect_speech(path: Path, *, min_speech_seconds: float = 0.5) -> tuple[bool, float]:
    """Return ``(has_speech, speech_seconds)`` using Silero VAD via faster-whisper.

    Falls back to "has an audio stream" if faster-whisper is unavailable.
    """
    try:
        from faster_whisper.audio import decode_audio  # type: ignore
        from faster_whisper.vad import VadOptions, get_speech_timestamps  # type: ignore
    except ImportError:
        return (has_audio_stream(path), 0.0)

    sampling_rate = 16000
    audio = decode_audio(str(path), sampling_rate=sampling_rate)
    timestamps = get_speech_timestamps(audio, vad_options=VadOptions())
    speech_seconds = sum(
        (ts["end"] - ts["start"]) / sampling_rate for ts in timestamps
    )
    return (speech_seconds >= min_speech_seconds, speech_seconds)
