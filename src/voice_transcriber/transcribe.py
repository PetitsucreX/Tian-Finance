"""Verbatim speech-to-text with faster-whisper."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .audio import extract_audio
from .models import MediaItem, Transcript, TranscriptSegment

DEFAULT_MODEL = "large-v3"


class Transcriber:
    """Lazily loads a faster-whisper model and transcribes media word-for-word.

    The model is loaded once and reused across calls, so transcribing a batch of
    recordings only pays the load cost a single time.
    """

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        *,
        device: str = "auto",
        compute_type: str = "auto",
        beam_size: int = 5,
    ) -> None:
        self.model_name = model
        self.device = device
        self.compute_type = compute_type
        self.beam_size = beam_size
        self._model = None

    def _load(self):
        if self._model is None:
            try:
                from faster_whisper import WhisperModel  # type: ignore
            except ImportError as exc:  # pragma: no cover - environment dependent
                raise RuntimeError(
                    "Transcription needs 'faster-whisper'. Install it with "
                    "`pip install faster-whisper`."
                ) from exc
            self._model = WhisperModel(
                self.model_name, device=self.device, compute_type=self.compute_type
            )
        return self._model

    def transcribe(
        self,
        media: MediaItem,
        *,
        language: Optional[str] = None,
        vad_filter: bool = True,
        initial_prompt: Optional[str] = None,
    ) -> Transcript:
        """Transcribe ``media`` verbatim.

        ``language=None`` lets Whisper auto-detect (fr / zh / en / …). Passing an
        explicit code is faster and more reliable when you know the language.
        """
        model = self._load()

        # Extract a clean 16 kHz mono WAV; Whisper is happiest with that.
        wav = extract_audio(media.path)
        try:
            segments_iter, info = model.transcribe(
                str(wav),
                language=language,
                beam_size=self.beam_size,
                vad_filter=vad_filter,
                word_timestamps=True,
                # Keep it verbatim: don't let the model "tidy up" or drop content.
                condition_on_previous_text=True,
                initial_prompt=initial_prompt,
            )
            segments = [
                TranscriptSegment(start=s.start, end=s.end, text=s.text)
                for s in segments_iter
            ]
        finally:
            wav.unlink(missing_ok=True)

        return Transcript(
            media=media,
            language=getattr(info, "language", language or "unknown"),
            segments=segments,
            duration=getattr(info, "duration", None),
            model=self.model_name,
        )
