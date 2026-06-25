"""Plain data structures shared across the package."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional


def _fmt_timestamp(seconds: float, *, comma: bool = False) -> str:
    """Format ``seconds`` as ``HH:MM:SS,mmm`` (SRT) or ``HH:MM:SS.mmm`` (VTT)."""
    if seconds < 0:
        seconds = 0.0
    millis = int(round(seconds * 1000))
    hours, millis = divmod(millis, 3_600_000)
    minutes, millis = divmod(millis, 60_000)
    secs, millis = divmod(millis, 1000)
    sep = "," if comma else "."
    return f"{hours:02d}:{minutes:02d}:{secs:02d}{sep}{millis:03d}"


def _fmt_clock(seconds: float) -> str:
    """Format ``seconds`` as ``HH:MM:SS`` (no milliseconds) for readable lists."""
    if seconds < 0:
        seconds = 0.0
    total = int(seconds)
    hours, total = divmod(total, 3600)
    minutes, secs = divmod(total, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


@dataclass
class MediaItem:
    """A single video/audio recording that may be transcribed."""

    path: Path
    filename: str
    source: str  # "photos" or "folder"
    uuid: Optional[str] = None
    created: Optional[datetime] = None
    duration: Optional[float] = None  # seconds, if known
    has_audio: Optional[bool] = None
    has_speech: Optional[bool] = None
    speech_seconds: Optional[float] = None

    def __post_init__(self) -> None:
        self.path = Path(self.path)
        if not self.filename:
            self.filename = self.path.name


@dataclass
class TranscriptSegment:
    """A contiguous chunk of recognised speech with timing."""

    start: float
    end: float
    text: str

    @property
    def clean_text(self) -> str:
        return self.text.strip()


@dataclass
class Transcript:
    """The verbatim transcript of one media item."""

    media: MediaItem
    language: str
    segments: List[TranscriptSegment] = field(default_factory=list)
    duration: Optional[float] = None
    model: Optional[str] = None

    @property
    def full_text(self) -> str:
        """The whole transcript as one verbatim block of text."""
        parts = [seg.clean_text for seg in self.segments if seg.clean_text]
        return "\n".join(parts)

    def to_dict(self) -> dict:
        return {
            "filename": self.media.filename,
            "path": str(self.media.path),
            "uuid": self.media.uuid,
            "source": self.media.source,
            "created": self.media.created.isoformat() if self.media.created else None,
            "language": self.language,
            "model": self.model,
            "duration": self.duration,
            "full_text": self.full_text,
            "segments": [
                {"start": s.start, "end": s.end, "text": s.clean_text}
                for s in self.segments
                if s.clean_text
            ],
        }
