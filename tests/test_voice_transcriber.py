"""Tests for the voice_transcriber package.

These exercise the pure-Python logic (discovery, filtering, formatting, CLI
wiring) without requiring ffmpeg, osxphotos or faster-whisper to be installed —
the heavy pieces are monkeypatched.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from voice_transcriber import audio, photos, voicememos
from voice_transcriber.cli import build_parser, cmd_transcribe
from voice_transcriber.formats import render
from voice_transcriber.models import MediaItem, Transcript, TranscriptSegment
from voice_transcriber.models import _fmt_timestamp


# --------------------------------------------------------------------------- #
# Discovery
# --------------------------------------------------------------------------- #
def _touch(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x00")
    return path


def test_find_in_folder_filters_by_extension(tmp_path):
    _touch(tmp_path / "a.mov")
    _touch(tmp_path / "b.mp4")
    _touch(tmp_path / "memo.m4a")
    _touch(tmp_path / "photo.jpg")
    _touch(tmp_path / "notes.txt")

    items = photos.find_in_folder(tmp_path)
    names = sorted(i.filename for i in items)
    assert names == ["a.mov", "b.mp4", "memo.m4a"]
    assert all(i.source == "folder" for i in items)


def test_find_in_folder_videos_only(tmp_path):
    _touch(tmp_path / "a.mov")
    _touch(tmp_path / "memo.m4a")
    items = photos.find_in_folder(tmp_path, videos_only=True)
    assert [i.filename for i in items] == ["a.mov"]


def test_find_in_folder_recursive_toggle(tmp_path):
    _touch(tmp_path / "top.mov")
    _touch(tmp_path / "sub" / "deep.mov")
    assert len(photos.find_in_folder(tmp_path, recursive=True)) == 2
    assert len(photos.find_in_folder(tmp_path, recursive=False)) == 1


def test_find_in_folder_date_window(tmp_path):
    old = _touch(tmp_path / "old.mov")
    import os
    import time

    old_ts = time.mktime(datetime(2020, 1, 1).timetuple())
    os.utime(old, (old_ts, old_ts))
    _touch(tmp_path / "new.mov")  # mtime = now

    items = photos.find_in_folder(tmp_path, since=datetime(2023, 1, 1))
    assert [i.filename for i in items] == ["new.mov"]


def test_find_in_folder_rejects_non_directory(tmp_path):
    f = _touch(tmp_path / "x.mov")
    with pytest.raises(NotADirectoryError):
        photos.find_in_folder(f)


def test_filter_available(tmp_path):
    real = _touch(tmp_path / "real.mov")
    items = [
        MediaItem(path=real, filename="real.mov", source="folder"),
        MediaItem(path=tmp_path / "ghost.mov", filename="ghost.mov", source="folder"),
    ]
    assert [i.filename for i in photos.filter_available(items)] == ["real.mov"]


# --------------------------------------------------------------------------- #
# Voice Memos
# --------------------------------------------------------------------------- #
def test_apple_time_conversion():
    # 2001-01-01 + 0s is the Apple epoch itself.
    assert voicememos._apple_time(0) == datetime(2001, 1, 1)
    assert voicememos._apple_time(None) is None
    # 757432800s after 2001-01-01 = 2025-01-01.
    assert voicememos._apple_time(757432800).year == 2025


def test_find_voice_memos_scans_folder(tmp_path):
    _touch(tmp_path / "memo1.m4a")
    _touch(tmp_path / "memo2.caf")
    _touch(tmp_path / "cover.jpg")  # ignored
    items = voicememos.find_voice_memos(recordings_dir=tmp_path)
    names = sorted(i.path.name for i in items)
    assert names == ["memo1.m4a", "memo2.caf"]
    assert all(i.source == "voicememos" for i in items)


def test_find_voice_memos_missing_dir_raises():
    with pytest.raises((RuntimeError, NotADirectoryError)):
        voicememos.find_voice_memos(recordings_dir=Path("/no/such/dir"))


def test_find_voice_memos_enriches_titles_from_db(tmp_path):
    import sqlite3

    _touch(tmp_path / "ABC.m4a")
    db = tmp_path / "CloudRecordings.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE ZCLOUDRECORDING "
        "(ZPATH TEXT, ZCUSTOMLABEL TEXT, ZDATE REAL, ZDURATION REAL)"
    )
    conn.execute(
        "INSERT INTO ZCLOUDRECORDING VALUES (?, ?, ?, ?)",
        ("ABC.m4a", "重要会议", 757432800.0, 42.0),
    )
    conn.commit()
    conn.close()

    items = voicememos.find_voice_memos(recordings_dir=tmp_path)
    assert len(items) == 1
    assert items[0].filename == "重要会议.m4a"
    assert items[0].created.year == 2025
    assert items[0].duration == 42.0


def test_load_metadata_tolerates_missing_table(tmp_path):
    import sqlite3

    db = tmp_path / "CloudRecordings.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE SOMETHING_ELSE (x INTEGER)")
    conn.commit()
    conn.close()
    assert voicememos._load_metadata(db) == {}


# --------------------------------------------------------------------------- #
# Formatting
# --------------------------------------------------------------------------- #
def _sample_transcript() -> Transcript:
    media = MediaItem(
        path=Path("/tmp/clip.mov"),
        filename="clip.mov",
        source="photos",
        uuid="ABC-123",
        created=datetime(2026, 1, 2, 15, 4, 5),
    )
    segs = [
        TranscriptSegment(0.0, 2.5, " Bonjour tout le monde. "),
        TranscriptSegment(2.5, 5.0, "大家好，今天我们开始。"),
        TranscriptSegment(5.0, 6.0, "   "),  # blank → skipped
    ]
    return Transcript(media=media, language="fr", segments=segs,
                      duration=6.0, model="large-v3")


def test_fmt_timestamp():
    assert _fmt_timestamp(0) == "00:00:00.000"
    assert _fmt_timestamp(3661.5) == "01:01:01.500"
    assert _fmt_timestamp(3661.5, comma=True) == "01:01:01,500"
    assert _fmt_timestamp(-1) == "00:00:00.000"


def test_full_text_is_verbatim_and_skips_blanks():
    t = _sample_transcript()
    assert t.full_text == "Bonjour tout le monde.\n大家好，今天我们开始。"


def test_render_txt():
    out = render(_sample_transcript(), "txt")
    assert out == "Bonjour tout le monde.\n大家好，今天我们开始。\n"


def test_render_srt_numbers_and_timestamps():
    out = render(_sample_transcript(), "srt")
    assert "1\n00:00:00,000 --> 00:00:02,500\nBonjour tout le monde." in out
    assert "2\n00:00:02,500 --> 00:00:05,000\n大家好，今天我们开始。" in out
    assert "3" not in out.split("\n\n")[-1].split("\n")[0]  # blank seg dropped


def test_render_vtt_header():
    out = render(_sample_transcript(), "vtt")
    assert out.startswith("WEBVTT")


def test_render_json_roundtrip():
    import json

    out = render(_sample_transcript(), "json")
    data = json.loads(out)
    assert data["language"] == "fr"
    assert data["full_text"].startswith("Bonjour")
    assert len(data["segments"]) == 2  # blank dropped


def test_render_md_has_header_and_timeline():
    out = render(_sample_transcript(), "md")
    assert "# 逐字稿 · clip.mov" in out
    assert "`[00:00:02]` 大家好" in out


def test_render_unknown_format():
    with pytest.raises(ValueError):
        render(_sample_transcript(), "pdf")


# --------------------------------------------------------------------------- #
# Audio fallbacks (no ffmpeg in test env)
# --------------------------------------------------------------------------- #
def test_has_audio_stream_safe_when_ffprobe_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(audio.shutil, "which", lambda _: None)
    assert audio.has_audio_stream(tmp_path / "x.mov") is False


def test_detect_speech_falls_back_to_audio_stream(monkeypatch, tmp_path):
    # faster_whisper not installed → fall back to has_audio_stream
    monkeypatch.setattr(audio, "has_audio_stream", lambda _p: True)
    has_speech, secs = audio.detect_speech(tmp_path / "x.mov")
    assert has_speech is True and secs == 0.0


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def test_parser_find_defaults():
    args = build_parser().parse_args(["find"])
    assert args.command == "find"
    assert args.source == "photos"
    assert args.videos_only is True


def test_parser_include_audio_flag():
    args = build_parser().parse_args(["find", "--include-audio"])
    assert args.videos_only is False


def test_parser_transcribe_multiformat():
    args = build_parser().parse_args(
        ["transcribe", "a.mov", "--format", "txt", "srt", "--model", "small"]
    )
    assert args.inputs == ["a.mov"]
    assert args.format == ["txt", "srt"]
    assert args.model == "small"


def test_cmd_transcribe_end_to_end(monkeypatch, tmp_path, capsys):
    """Drive cmd_transcribe with a fake Transcriber and fake ffmpeg check."""
    clip = _touch(tmp_path / "clip.mov")
    out_dir = tmp_path / "out"

    from voice_transcriber import cli

    monkeypatch.setattr(cli.audio, "ffmpeg_available", lambda: True)

    class FakeTranscriber:
        def __init__(self, *a, **k):
            pass

        def transcribe(self, media, **kwargs):
            return Transcript(
                media=media,
                language="zh",
                segments=[TranscriptSegment(0.0, 1.0, "测试逐字稿")],
                duration=1.0,
                model="large-v3",
            )

    monkeypatch.setattr(cli, "Transcriber", FakeTranscriber)

    args = build_parser().parse_args(
        ["transcribe", str(clip), "--output-dir", str(out_dir), "--format", "txt", "json"]
    )
    rc = cmd_transcribe(args)
    assert rc == 0
    assert (out_dir / "clip.txt").read_text(encoding="utf-8") == "测试逐字稿\n"
    assert "完成" in capsys.readouterr().out


def test_parser_voicememos_source():
    args = build_parser().parse_args(
        ["transcribe", "--source", "voicememos", "--skip-existing"]
    )
    assert args.source == "voicememos"
    assert args.skip_existing is True


def test_cmd_transcribe_skip_existing(monkeypatch, tmp_path, capsys):
    clip = _touch(tmp_path / "clip.mov")
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    (out_dir / "clip.txt").write_text("already done", encoding="utf-8")

    from voice_transcriber import cli

    monkeypatch.setattr(cli.audio, "ffmpeg_available", lambda: True)
    # If it tried to transcribe, this would explode — proving it skipped.
    monkeypatch.setattr(
        cli, "Transcriber", lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not run"))
    )

    args = build_parser().parse_args(
        ["transcribe", str(clip), "--output-dir", str(out_dir),
         "--format", "txt", "--skip-existing"]
    )
    rc = cmd_transcribe(args)
    assert rc == 1  # nothing left to do
    assert "跳过 1" in capsys.readouterr().out


def test_main_handles_source_error_cleanly(capsys):
    from voice_transcriber.cli import main

    rc = main(["find", "--source", "voicememos", "--recordings-dir", "/no/such/dir"])
    assert rc == 2
    assert "错误" in capsys.readouterr().err


def test_cmd_transcribe_no_ffmpeg(monkeypatch, tmp_path):
    clip = _touch(tmp_path / "clip.mov")
    from voice_transcriber import cli

    monkeypatch.setattr(cli.audio, "ffmpeg_available", lambda: False)
    args = build_parser().parse_args(["transcribe", str(clip)])
    assert cmd_transcribe(args) == 2
