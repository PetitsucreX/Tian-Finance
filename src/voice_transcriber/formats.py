"""Render a :class:`Transcript` into the various output formats."""

from __future__ import annotations

import json

from .models import Transcript, _fmt_clock, _fmt_timestamp

FORMATS = ("txt", "md", "srt", "vtt", "json")


def to_txt(transcript: Transcript) -> str:
    """Pure verbatim text — the 逐字稿 itself, no timestamps."""
    return transcript.full_text + ("\n" if transcript.full_text else "")


def to_md(transcript: Transcript) -> str:
    """A readable transcript with a header and timestamped lines."""
    m = transcript.media
    lines = [
        f"# 逐字稿 · {m.filename}",
        "",
        f"- 来源: {m.source}" + (f" ({m.uuid})" if m.uuid else ""),
        f"- 语言: {transcript.language}",
        f"- 模型: {transcript.model or 'n/a'}",
    ]
    if m.created:
        lines.append(f"- 拍摄时间: {m.created.isoformat()}")
    if transcript.duration:
        lines.append(f"- 时长: {_fmt_timestamp(transcript.duration)}")
    lines += ["", "## 全文", "", transcript.full_text, "", "## 带时间轴", ""]
    for seg in transcript.segments:
        if not seg.clean_text:
            continue
        stamp = _fmt_clock(seg.start)
        lines.append(f"`[{stamp}]` {seg.clean_text}")
    return "\n".join(lines) + "\n"


def to_srt(transcript: Transcript) -> str:
    blocks = []
    index = 1
    for seg in transcript.segments:
        if not seg.clean_text:
            continue
        start = _fmt_timestamp(seg.start, comma=True)
        end = _fmt_timestamp(seg.end, comma=True)
        blocks.append(f"{index}\n{start} --> {end}\n{seg.clean_text}\n")
        index += 1
    return "\n".join(blocks)


def to_vtt(transcript: Transcript) -> str:
    blocks = ["WEBVTT", ""]
    for seg in transcript.segments:
        if not seg.clean_text:
            continue
        start = _fmt_timestamp(seg.start)
        end = _fmt_timestamp(seg.end)
        blocks.append(f"{start} --> {end}\n{seg.clean_text}\n")
    return "\n".join(blocks)


def to_json(transcript: Transcript) -> str:
    return json.dumps(transcript.to_dict(), ensure_ascii=False, indent=2)


_RENDERERS = {
    "txt": to_txt,
    "md": to_md,
    "srt": to_srt,
    "vtt": to_vtt,
    "json": to_json,
}


def render(transcript: Transcript, fmt: str) -> str:
    try:
        return _RENDERERS[fmt](transcript)
    except KeyError:
        raise ValueError(f"unknown format: {fmt!r} (choose from {', '.join(FORMATS)})")
