"""The only module in this repository that decides which file a request may serve.

A request names a file with a string. That string never comes from this program, so it
can name a file above the root the route is allowed to read. Two servers in this
repository answer a file request: `annotator/unified_server.py` (the review API) and
`annotator/server.py` (the legacy single-page annotator). Both call the functions below,
so one rule answers for both and the two copies cannot drift apart.

The rule:
  * `bare_name(name)` is True for one path component: not empty, no separator, and not
    "." or "..". A media request and a crop request use this shape.
  * `file_under(base, name)` is the resolved file `name` inside `base`, or None. It
    needs a bare name, it must stay inside `base` after the resolution, and it must be
    an existing file.
  * `relative_under(base, rel)` does the same for a string that may carry
    subdirectories, and is what a static file route uses. It must stay inside `base`
    too, and an absolute `rel` cannot leave it.

What these functions do not do:
  * They do not decode a URL. The caller decodes the path first.
  * They do not open or read the file. They only say which path is allowed.
  * They do not follow a link out of `base`. The resolution happens first, so a link
    inside `base` that points outside `base` gives None.

The refusal stays at the caller, because each server has its own body and status for it.
"""
from __future__ import annotations

from pathlib import Path

__all__ = ["bare_name", "file_under", "relative_under"]


def bare_name(name) -> bool:
    """True when `name` is one path component and cannot walk to a parent directory."""
    return bool(name) and Path(name).name == name and name not in (".", "..")


def file_under(base, name):
    """The resolved file `name` inside `base`, or None.

    `name` must be a bare name, the resolved path must stay inside `base`, and the
    path must be an existing file. A missing file, a directory, a name with a
    separator and a name that leaves `base` all give None.
    """
    if not bare_name(name):
        return None
    path = (Path(base) / name).resolve()
    return path if path.is_relative_to(Path(base).resolve()) and path.is_file() else None


def relative_under(base, rel):
    """The resolved file `rel` inside `base`, or None.

    This is the static file shape: `rel` may carry subdirectories, as in
    "media/vod30/frame.jpg". The resolved path must stay inside `base`, and the path
    must be an existing file. An empty string, an absolute path and a path that leaves
    `base` all give None.
    """
    if not rel:
        return None
    path = (Path(base) / rel).resolve()
    return path if path.is_relative_to(Path(base).resolve()) and path.is_file() else None
