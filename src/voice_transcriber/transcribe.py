"""Verbatim speech-to-text.

Two backends are supported:

* ``mlx``           — Apple's MLX framework, runs on the Apple-Silicon GPU.
                      Far faster and cooler than CPU inference; the default on
                      arm64 macOS when ``mlx-whisper`` is installed.
* ``faster-whisper`` — CTranslate2, CPU-only on macOS. The portable fallback.

Audio is decoded with PyAV (bundled via faster-whisper), so a system ``ffmpeg``
binary is **not** required.
"""

from __future__ import annotations

import platform
from typing import Optional

from .audio import decode_audio_array
from .models import MediaItem, Transcript, TranscriptSegment

DEFAULT_MODEL = "large-v3"

# Friendly model name -> MLX Hugging Face repo.
_MLX_MODEL_MAP = {
    "large-v3": "mlx-community/whisper-large-v3-mlx",
    "large-v3-turbo": "mlx-community/whisper-large-v3-turbo",
    "turbo": "mlx-community/whisper-large-v3-turbo",
    "distil-large-v3": "mlx-community/distil-whisper-large-v3",
    "medium": "mlx-community/whisper-medium-mlx",
    "small": "mlx-community/whisper-small-mlx",
}


def resolve_engine(engine: str) -> str:
    """Resolve ``"auto"`` to a concrete backend for this machine."""
    if engine != "auto":
        return engine
    if platform.system() == "Darwin" and platform.machine() == "arm64":
        try:
            import mlx_whisper  # type: ignore  # noqa: F401

            return "mlx"
        except ImportError:
            return "faster-whisper"
    return "faster-whisper"


def mlx_repo(model: str) -> str:
    """Map a model name to an MLX repo (pass-through if it already looks like one)."""
    if "/" in model:
        return model
    return _MLX_MODEL_MAP.get(model, "mlx-community/whisper-large-v3-mlx")


class Transcriber:
    """Transcribe media word-for-word using the MLX or faster-whisper backend.

    The model is loaded once and reused across calls, so transcribing a batch of
    recordings only pays the load cost a single time.
    """

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        *,
        engine: str = "auto",
        device: str = "auto",
        compute_type: str = "auto",
        beam_size: int = 5,
    ) -> None:
        self.model_name = model
        self.engine = resolve_engine(engine)
        self.device = device
        self.compute_type = compute_type
        self.beam_size = beam_size
        self._model = None  # faster-whisper model handle (MLX caches its own)

    # -- faster-whisper -------------------------------------------------- #
    def _load_faster_whisper(self):
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

    def _transcribe_faster_whisper(
        self, media, language, vad_filter, initial_prompt
    ) -> Transcript:
        model = self._load_faster_whisper()
        # faster-whisper decodes the file via PyAV itself — no system ffmpeg.
        segments_iter, info = model.transcribe(
            str(media.path),
            language=language,
            beam_size=self.beam_size,
            vad_filter=vad_filter,
            word_timestamps=True,
            condition_on_previous_text=True,  # keep it verbatim, no tidying
            initial_prompt=initial_prompt,
        )
        segments = [
            TranscriptSegment(start=s.start, end=s.end, text=s.text)
            for s in segments_iter
        ]
        return Transcript(
            media=media,
            language=getattr(info, "language", language or "unknown"),
            segments=segments,
            duration=getattr(info, "duration", None),
            model=self.model_name,
        )

    # -- MLX (Apple Silicon GPU) ----------------------------------------- #
    def _transcribe_mlx(self, media, language, initial_prompt) -> Transcript:
        try:
            import mlx_whisper  # type: ignore
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise RuntimeError(
                "MLX backend needs 'mlx-whisper'. Install it with "
                "`pip install mlx-whisper`, or use --engine faster-whisper."
            ) from exc

        # Decode to a 16 kHz float32 array with PyAV so MLX never shells out to
        # a missing system ffmpeg.
        audio = decode_audio_array(media.path)
        repo = mlx_repo(self.model_name)
        result = mlx_whisper.transcribe(
            audio,
            path_or_hf_repo=repo,
            language=language,
            word_timestamps=True,
            condition_on_previous_text=True,
            initial_prompt=initial_prompt,
        )
        segments = [
            TranscriptSegment(
                start=float(s.get("start", 0.0)),
                end=float(s.get("end", 0.0)),
                text=s.get("text", ""),
            )
            for s in result.get("segments", [])
        ]
        duration = segments[-1].end if segments else None
        return Transcript(
            media=media,
            language=result.get("language", language or "unknown"),
            segments=segments,
            duration=duration,
            model=repo,
        )

    # -- public ---------------------------------------------------------- #
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
        if self.engine == "mlx":
            return self._transcribe_mlx(media, language, initial_prompt)
        return self._transcribe_faster_whisper(
            media, language, vad_filter, initial_prompt
        )
