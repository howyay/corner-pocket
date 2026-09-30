"""Which ffmpeg and ffprobe the app runs, in one place.

The service's ``PATH`` has neither binary, so the choice is explicit:

1. ``POOL_FFMPEG`` / ``POOL_FFPROBE`` - what the systemd drop-in
   ``~/.config/systemd/user/pool-workbench.service.d/30-ffmpeg.conf`` sets, pointing
   at the garbage-collection-rooted build ``~/.local/state/pool/ffmpeg-bin``.
   When one of them is set and the file is not there we refuse to guess: the caller
   turns :class:`MediaBinaryMissing` into a 503 that names the variable.  A silent
   fallback would hide a broken deployment - the exact failure this pin fixes.
2. the sibling of the resolved ffmpeg (same build, so the same version).
3. ``PATH``.
4. the newest ``/nix/store/*-ffmpeg-headless-*-bin`` build.

Step 4 is the fallback for dev checkouts only.  Those store paths are **not**
rooted: ``nix-collect-garbage`` deletes them, and event clips and VOD imports then
break.  Production pins the variables, so it never reaches step 4.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

FFMPEG_VAR = "POOL_FFMPEG"
FFPROBE_VAR = "POOL_FFPROBE"
#: Where the last-resort glob looks; a module attribute so tests can redirect it.
STORE = Path("/nix/store")


class MediaBinaryMissing(Exception):
    """A media binary is pinned but not where it was said to be, or absent entirely."""


def _pinned(variable, environ):
    """The pinned path when the variable is set and real; ``None`` when it is unset."""
    value = (environ.get(variable) or "").strip()
    if not value:
        return None
    if Path(value).is_file():
        return value
    raise MediaBinaryMissing(
        f"{variable} is set to {value}, which is not a file on this host: "
        f"fix the value or unset {variable}")


def _newest_in_store(binary):
    """Newest ``*-ffmpeg-headless-*-bin/bin/<binary>`` of the Nix store, or ``None``.

    Unrooted by nature: ``nix-collect-garbage`` deletes these paths.  Dev fallback only.
    """
    candidates = [p for p in STORE.glob(f"*-ffmpeg-headless-*-bin/bin/{binary}") if p.is_file()]
    return str(max(candidates, key=lambda p: p.stat().st_mtime)) if candidates else None


def resolve_ffmpeg(environ=None):
    """The ffmpeg to run: the pin, else ``PATH``, else the newest store build."""
    environ = os.environ if environ is None else environ
    pinned = _pinned(FFMPEG_VAR, environ)
    if pinned:
        return pinned
    found = shutil.which("ffmpeg")
    if found:
        return found
    newest = _newest_in_store("ffmpeg")
    if newest:
        return newest
    raise MediaBinaryMissing(
        f"ffmpeg is unavailable on this host: put it on PATH or set {FFMPEG_VAR}")


def resolve_ffprobe(environ=None, beside=None):
    """The ffprobe to run: the pin, else beside *beside*, else ``PATH``, else the store."""
    environ = os.environ if environ is None else environ
    pinned = _pinned(FFPROBE_VAR, environ)
    if pinned:
        return pinned
    if beside:
        sibling = Path(beside).with_name("ffprobe")
        if sibling.is_file():
            return str(sibling)
    found = shutil.which("ffprobe")
    if found:
        return found
    newest = _newest_in_store("ffprobe")
    if newest:
        return newest
    raise MediaBinaryMissing(
        f"ffprobe is unavailable on this host: put it on PATH or set {FFPROBE_VAR}")
