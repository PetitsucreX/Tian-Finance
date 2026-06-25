"""Discover recordings from the macOS / iOS Voice Memos app (语音备忘录).

Voice Memos sync over iCloud, so memos recorded on an iPhone show up on the Mac
inside a Group Container as ``.m4a`` files alongside a ``CloudRecordings.db``
SQLite database that holds the user-facing titles, dates and durations.

The folder scan is the reliable core (works regardless of macOS version); the
database is read on a best-effort basis to enrich filenames into real titles.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from .models import MediaItem

# Known on-disk locations across macOS versions (newest first).
KNOWN_DIRS = (
    "~/Library/Group Containers/group.com.apple.VoiceMemos.shared/Recordings",
    "~/Library/Application Support/com.apple.voicememos/Recordings",
    "~/Library/Application Support/com.apple.VoiceMemos/Recordings",
)

MEMO_EXTS = {".m4a", ".caf", ".wav", ".aiff"}

# Core Data stores timestamps as seconds since 2001-01-01 UTC.
_APPLE_EPOCH = datetime(2001, 1, 1)


def default_recordings_dir() -> Optional[Path]:
    """Return the first Voice Memos recordings directory that exists, if any."""
    for candidate in KNOWN_DIRS:
        path = Path(candidate).expanduser()
        if path.is_dir():
            return path
    return None


def _apple_time(value: Optional[float]) -> Optional[datetime]:
    if value is None:
        return None
    try:
        return _APPLE_EPOCH + timedelta(seconds=float(value))
    except (TypeError, ValueError, OverflowError):
        return None


def _find_db(recordings_dir: Path) -> Optional[Path]:
    for candidate in (
        recordings_dir / "CloudRecordings.db",
        recordings_dir.parent / "CloudRecordings.db",
        recordings_dir / "Recordings.db",
    ):
        if candidate.is_file():
            return candidate
    return None


def _load_metadata(db_path: Path) -> Dict[str, dict]:
    """Best-effort map of ``filename -> {title, created, duration}`` from the DB.

    Schemas differ between macOS releases, so columns are discovered at runtime
    and anything unexpected degrades to an empty map rather than raising.
    """
    meta: Dict[str, dict] = {}
    try:
        uri = f"file:{db_path}?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
    except sqlite3.Error:
        return meta
    try:
        cols = {
            row[1].upper()
            for row in conn.execute("PRAGMA table_info(ZCLOUDRECORDING)")
        }
        if "ZPATH" not in cols:
            return meta  # without a path column we cannot map rows to files
        title_col = next(
            (c for c in ("ZCUSTOMLABEL", "ZENCRYPTEDTITLE", "ZTITLE") if c in cols),
            None,
        )
        date_col = "ZDATE" if "ZDATE" in cols else None
        dur_col = "ZDURATION" if "ZDURATION" in cols else None

        select = ["ZPATH"]
        select += [c for c in (title_col, date_col, dur_col) if c]
        rows = conn.execute(f"SELECT {', '.join(select)} FROM ZCLOUDRECORDING")
        for row in rows:
            data = dict(zip(select, row))
            raw_path = data.get("ZPATH")
            if not raw_path:
                continue
            key = Path(str(raw_path)).name
            meta[key] = {
                "title": data.get(title_col) if title_col else None,
                "created": _apple_time(data.get(date_col)) if date_col else None,
                "duration": data.get(dur_col) if dur_col else None,
            }
    except sqlite3.Error:
        return {}
    finally:
        conn.close()
    return meta


def find_voice_memos(
    *,
    recordings_dir: Optional[Path] = None,
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
) -> List[MediaItem]:
    """Return Voice Memos recordings as :class:`MediaItem` objects."""
    directory = Path(recordings_dir).expanduser() if recordings_dir else default_recordings_dir()
    if directory is None:
        raise RuntimeError(
            "找不到语音备忘录目录。请确认 macOS 上的「语音备忘录」已开启 iCloud 同步，"
            "或用 --recordings-dir 指定路径。"
        )
    if not directory.is_dir():
        raise NotADirectoryError(f"not a directory: {directory}")

    db = _find_db(directory)
    metadata = _load_metadata(db) if db else {}

    items: List[MediaItem] = []
    for path in sorted(directory.glob("*")):
        if not path.is_file() or path.suffix.lower() not in MEMO_EXTS:
            continue
        info = metadata.get(path.name, {})
        created = info.get("created")
        if created is None:
            try:
                created = datetime.fromtimestamp(path.stat().st_mtime)
            except OSError:
                created = None
        if since is not None and created is not None and created < since:
            continue
        if until is not None and created is not None and created > until:
            continue

        title = info.get("title")
        filename = f"{title}.m4a" if title else path.name
        items.append(
            MediaItem(
                path=path,
                filename=filename,
                source="voicememos",
                created=created,
                duration=info.get("duration"),
            )
        )
    return items
