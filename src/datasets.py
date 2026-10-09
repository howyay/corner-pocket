"""Every dataset the workbench can open, in one registry.

Two recordings are built in and never change: ``vod30`` (scan folder ``out/scan30``,
media ``data/vod_30min_260815.mp4``) and ``highlight`` (``out/scan_highlight``,
``data/vod_highlight.mp4``).  Imported Twitch VODs of a saved channel are listed in
``out/vods/index.json``; each keeps its operator data under ``out/vods/<id>/`` and
its media at ``data/vods/<id>.mp4`` (``annotator/vod_import.py`` writes both).

This module only reads.  A lookup never creates a folder and never rewrites the
index, so every GET that resolves a dataset stays a read.  The built-in ids never
read the index at all, so a damaged index cannot change how they behave.
``annotator/live_processing.py`` keeps its own list of the two built-in files: the
live source replays those, and an imported VOD is browsed, not replayed.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path

#: The built-in recordings: id -> (scan folder under out/, media file under data/).
STATIC = {"vod30": ("scan30", "vod_30min_260815.mp4"),
          "highlight": ("scan_highlight", "vod_highlight.mp4")}
#: id -> scan folder: the mapping src/store.py has always exported as DATASETS.
STATIC_OUT = {key: value[0] for key, value in STATIC.items()}

#: An imported VOD's id: ``tw-`` + the numeric Twitch VOD id, then ``-<start>-<end>``
#: (whole seconds into the broadcast) when only a range was imported.  Matched with
#: ``fullmatch``: a ``^...$`` pattern would also accept a trailing newline.
IMPORTED_ID = re.compile(r"tw-([0-9]{1,12})(?:-([0-9]+)-([0-9]+))?")
_ID_MAX = 64
#: The imported-VOD index, relative to the workspace root.
INDEX = Path("out") / "vods" / "index.json"


@dataclass(frozen=True)
class Dataset:
    """Where one dataset lives under a root.  Paths are joined, not resolved."""
    id: str
    kind: str          # 'recording' (built in) or 'vod' (an imported broadcast)
    out_dir: Path      # scan outputs and operator data (corrections)
    media_dir: Path    # the folder the media file must stay inside
    media_name: str    # a bare file name inside media_dir
    #: Decodable frames recorded at import (an imported VOD's container also counts the
    #: pre-roll its edit list hides, so the container's count is too high); None = trust it.
    frames: int | None = None

    def media_file(self):
        """The media path when it is a regular file inside ``media_dir``, else None."""
        return _inside(self.media_dir, self.media_name, file=True)


def _seconds(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) \
            or not math.isfinite(value) or value < 0 or int(value) != value:
        raise ValueError(f"{name} must be a whole number of seconds, 0 or more")
    return int(value)


def imported_id(vod_id, start_s=None, end_s=None):
    """The dataset id of Twitch VOD ``vod_id``: whole, or its ``start_s..end_s`` range.

    Built from numbers only, so an id can never carry a path, a URL or a token.
    """
    text = str(vod_id) if isinstance(vod_id, (int, str)) and not isinstance(vod_id, bool) else ""
    if not (text.isascii() and text.isdigit()) or int(text) <= 0 or len(str(int(text))) > 12:
        raise ValueError("vod_id must be a numeric Twitch VOD id of at most 12 digits")
    vod = str(int(text))
    if start_s is None and end_s is None:
        return f"tw-{vod}"
    if start_s is None or end_s is None:
        raise ValueError("a range needs both start_s and end_s")
    start, end = _seconds(start_s, "start_s"), _seconds(end_s, "end_s")
    if end <= start:
        raise ValueError("end_s must be after start_s")
    return f"tw-{vod}-{start}-{end}"


def parse_imported_id(dataset_id):
    """``(vod_id, start_s, end_s)`` of a canonical imported id, else None.

    A whole VOD has no range: ``('123', None, None)``.  Canonical means the id is
    exactly what :func:`imported_id` builds, so ``tw-0123`` and ``tw-1-9-5`` are
    refused and two spellings can never name the same folder.
    """
    if not isinstance(dataset_id, str) or len(dataset_id) > _ID_MAX:
        return None
    match = IMPORTED_ID.fullmatch(dataset_id)
    if match is None:
        return None
    vod, start, end = match.groups()
    start = None if start is None else int(start)
    end = None if end is None else int(end)
    try:
        if imported_id(vod, start, end) != dataset_id:
            return None
    except ValueError:
        return None
    return vod, start, end


def _inside(base, name, *, file=False):
    """``base / name`` when ``name`` is a bare name resolving inside ``base``, else None.

    The rule of ``annotator.unified_server.safe_file``; ``file=True`` also requires
    an existing regular file and returns the resolved path, as safe_file does.
    """
    if not isinstance(name, str) or not name or Path(name).name != name or name in (".", ".."):
        return None
    path = (base / name).resolve()
    if not path.is_relative_to(base.resolve()):
        return None
    if file:
        return path if path.is_file() else None
    return base / name


def read_index(root):
    """``({id: entry}, error)`` from ``root``'s imported-VOD index.  Pure.

    A missing index is ``({}, None)``.  An unreadable one is ``({}, sentence)`` so a
    caller can say why nothing is listed; entries that are not objects, or whose key
    is not the canonical id of their own ``vod_id``, are left out and counted.
    """
    path = Path(root) / INDEX
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}, None
    except (OSError, UnicodeDecodeError) as exc:
        return {}, f"out/vods/index.json cannot be read ({type(exc).__name__}); imported VODs are not listed"
    try:
        document = json.loads(text)
    except ValueError:
        return {}, "out/vods/index.json is not valid JSON; imported VODs are not listed"
    vods = document.get("vods") if isinstance(document, dict) else None
    if not isinstance(vods, dict):
        return {}, "out/vods/index.json has no 'vods' object; imported VODs are not listed"
    entries = {}
    for key, entry in vods.items():
        parsed = parse_imported_id(key)
        if parsed is not None and isinstance(entry, dict) and str(entry.get("vod_id")) == parsed[0]:
            entries[key] = entry
    skipped = len(vods) - len(entries)
    error = None
    if skipped:
        error = f"{skipped} entr{'y' if skipped == 1 else 'ies'} in out/vods/index.json {'is' if skipped == 1 else 'are'} not valid and not listed"
    return entries, error


def lookup(root, dataset_id):
    """The :class:`Dataset` named ``dataset_id`` under ``root``, or None.

    A built-in id resolves without reading the index.  An imported id resolves only
    while the index lists it, so a deleted VOD is unknown again (its corrections stay
    under ``out/vods/<id>/``).  An unhashable id raises TypeError, as ``in`` on the
    old dictionaries did.
    """
    root = Path(root)
    if dataset_id in STATIC:
        scan, media = STATIC[dataset_id]
        return Dataset(dataset_id, "recording", root / "out" / scan, root / "data", media)
    if parse_imported_id(dataset_id) is None:
        return None
    entry = read_index(root)[0].get(dataset_id)
    out_dir = _inside(root / "out" / "vods", dataset_id)
    if entry is None or out_dir is None:
        return None
    frames = _count(entry.get("frames"))
    return Dataset(dataset_id, "vod", out_dir, root / "data" / "vods", dataset_id + ".mp4", frames or None)


def media_path(root, dataset_id):
    """The media file of ``dataset_id`` under ``root``, or None for an unknown id.

    The answer comes from the registry, so the path names the file also when the
    file is absent.  The path is not resolved and not checked: the caller decides
    what to do with a missing recording.  None means that no dataset has this id.
    """
    found = lookup(root, dataset_id)
    return None if found is None else found.media_dir / found.media_name


def media_relpath(root, dataset_id):
    """``media_path(root, dataset_id)`` relative to ``root``, or None.

    A command line uses this form.  The other defaults of those parsers are
    relative to the workspace root.
    """
    path = media_path(root, dataset_id)
    return None if path is None else str(path.relative_to(Path(root)))


def _text(value):
    return value if isinstance(value, str) and value else None


def _count(value):
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def _rate(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        return None
    return float(value)


def clock(seconds):
    """``3600`` -> ``'1:00:00'``: a position in the broadcast."""
    seconds = int(seconds)
    return f"{seconds // 3600}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"


def describe(root, dataset_id, entry):
    """The /api/datasets row of one imported VOD (EN label; the client localises)."""
    vod, start, end = parse_imported_id(dataset_id)
    length = _count(entry.get("length_s"))
    whole = start is None
    start_s, end_s = (0, length) if whole else (start, end)
    channel, created = _text(entry.get("channel")), _text(entry.get("created_at"))
    span = "whole broadcast" if whole else f"{clock(start_s)}–{clock(end_s)}"
    label = " · ".join(part for part in (channel, created[:10] if created else None, span) if part)
    media = lookup(root, dataset_id)
    return {"id": dataset_id, "label": label, "kind": "vod", "vod_id": vod,
            "channel": channel, "title": _text(entry.get("title")), "created_at": created,
            "range": {"start_s": start_s, "end_s": end_s, "whole": whole},
            "length_s": length, "fps": _rate(entry.get("fps")), "frames": _count(entry.get("frames")),
            "width": _count(entry.get("width")), "height": _count(entry.get("height")),
            "bytes": _count(entry.get("bytes")), "imported_at": _text(entry.get("imported_at")),
            "media": bool(media and media.media_file())}


def listing(root):
    """``(rows, error)`` for /api/datasets.

    The built-in recordings come first, exactly as the endpoint has always listed
    them (``{'id', 'label'}``); each imported VOD follows, newest VOD first, with its
    metadata.  ``error`` is the index's problem sentence, or None.
    """
    rows = [{"id": key, "label": key} for key in STATIC]
    entries, error = read_index(root)
    order = sorted(entries, key=lambda key: (-int(parse_imported_id(key)[0]), parse_imported_id(key)[1] or 0))
    rows.extend(describe(root, key, entries[key]) for key in order)
    return rows, error
