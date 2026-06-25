"""Find voice/video recordings and produce verbatim transcripts (逐字稿).

This package locates videos in the macOS Photos library (or a plain folder),
detects which ones contain spoken audio, extracts the audio track with ffmpeg
and transcribes it word-for-word with faster-whisper.

Heavy, platform-specific dependencies (``osxphotos``, ``faster_whisper``,
``ffmpeg``) are imported lazily inside the functions that need them, so the
package can be imported — and unit-tested — on any machine without them.
"""

from __future__ import annotations

from .models import MediaItem, Transcript, TranscriptSegment

__all__ = ["MediaItem", "Transcript", "TranscriptSegment"]
