"""Locate candidate recordings, either in the macOS Photos library or a folder."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Optional

from .models import MediaItem

# Extensions we treat as "a recording that may contain speech".
VIDEO_EXTS = {".mov", ".mp4", ".m4v", ".avi", ".mkv", ".webm", ".3gp"}
AUDIO_EXTS = {".m4a", ".mp3", ".wav", ".aac", ".caf", ".aiff", ".flac", ".ogg"}
MEDIA_EXTS = VIDEO_EXTS | AUDIO_EXTS


def _matches_date(when: Optional[datetime], since: Optional[datetime],
                  until: Optional[datetime]) -> bool:
    if when is None:
        # Unknown date: keep it rather than silently dropping the recording.
        return True
    if since is not None and when < since:
        return False
    if until is not None and when > until:
        return False
    return True


def find_in_folder(
    folder: Path,
    *,
    recursive: bool = True,
    videos_only: bool = False,
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
) -> List[MediaItem]:
    """Scan a directory for media files. Works on any OS — no Photos needed."""
    folder = Path(folder).expanduser()
    if not folder.is_dir():
        raise NotADirectoryError(f"not a directory: {folder}")

    exts = VIDEO_EXTS if videos_only else MEDIA_EXTS
    paths = folder.rglob("*") if recursive else folder.glob("*")

    items: List[MediaItem] = []
    for path in sorted(paths):
        if not path.is_file() or path.suffix.lower() not in exts:
            continue
        try:
            mtime = datetime.fromtimestamp(path.stat().st_mtime)
        except OSError:
            mtime = None
        if not _matches_date(mtime, since, until):
            continue
        items.append(
            MediaItem(
                path=path,
                filename=path.name,
                source="folder",
                created=mtime,
            )
        )
    return items


def find_in_photos(
    *,
    videos_only: bool = True,
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
    library_path: Optional[Path] = None,
) -> List[MediaItem]:
    """Read the macOS Photos library and return its videos as :class:`MediaItem`.

    Requires the ``osxphotos`` package (``pip install osxphotos``) and only
    works on macOS where a Photos library exists.
    """
    try:
        import osxphotos  # type: ignore
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise RuntimeError(
            "Reading the Photos library needs 'osxphotos'. Install it with "
            "`pip install osxphotos`, or use --source folder instead."
        ) from exc

    db = osxphotos.PhotosDB(dbfile=str(library_path)) if library_path else osxphotos.PhotosDB()

    items: List[MediaItem] = []
    for photo in db.photos(movies=True, images=not videos_only):
        if videos_only and not getattr(photo, "ismovie", False):
            continue
        created = getattr(photo, "date", None)
        if not _matches_date(created, since, until):
            continue
        # ``path`` is the original file on disk; may be None if not downloaded
        # from iCloud yet.
        path = getattr(photo, "path", None)
        items.append(
            MediaItem(
                path=Path(path) if path else Path(photo.filename),
                filename=getattr(photo, "original_filename", None) or photo.filename,
                source="photos",
                uuid=getattr(photo, "uuid", None),
                created=created,
            )
        )
    return items


def filter_available(items: Iterable[MediaItem]) -> List[MediaItem]:
    """Drop items whose file is not actually on disk (e.g. not yet downloaded)."""
    return [it for it in items if it.path.exists()]
