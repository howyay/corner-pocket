"""The only module in this repository that writes one file in one step.

Every writer that must not leave a half file calls `write_atomic`. The callers do
not make a temp name, do not call `os.fsync`, and do not call `os.replace`.

What `write_atomic` guarantees:
  * A successful call puts all the new bytes in the target file.
  * A failed call keeps all the old bytes in the target file.
  * No reader sees a mixture of the old bytes and the new bytes. The last step is
    one `os.replace` call.

What `write_atomic` does not guarantee:
  * The parent directory of the target. Make it before the call. A missing parent
    directory gives FileNotFoundError.
  * The result of two writers on one path. Two writers can lose one result. Use a
    lock, as the callers do.
  * The bytes after a power loss. Set fsync=True to tell the operating system to
    write the bytes to the disk before the replace. fsync=True does not write the
    directory entry to the disk.
  * A second file system. The temp file is always in the target directory, so
    `os.replace` stays in one file system.
  * The mode, the owner, and the ACL of an old target file. The new file keeps the
    mode of the temp file. See `temp_prefix` and `temp_name`.
  * The file behind a symlink or a hard link. `os.replace` replaces the name.

The callers that do not set fsync=True are: src/face_id.py store_faces,
src/person_identity.py IdentityIndex.save, src/store.py JsonStore.identity_save,
and src/enroll_from_tracklet.py _write_json. Those callers keep the behavior they
had. Do not add fsync for them without a decision.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Callable, TextIO

__all__ = ["write_atomic"]

DEFAULT_PREFIX = "."  # the default temp name is hidden and unique: "." + the target name
FIELDS = ("name", "stem", "pid")


def _sibling_path(path: Path, pattern: str) -> Path:
    """The temp path for `pattern`. The fields are {name}, {stem} and {pid}."""
    try:
        name = pattern.format(name=path.name, stem=path.stem, pid=os.getpid())
    except (KeyError, IndexError, ValueError) as error:
        raise ValueError(f"bad temp_name pattern {pattern!r}: {error}") from None
    if not name:
        raise ValueError(f"temp_name pattern {pattern!r} gives an empty name")
    if "/" in name or name in (".", ".."):
        raise ValueError(f"temp_name pattern {pattern!r} does not give a file name beside the target")
    return path.with_name(name)


def write_atomic(
    path,
    write: Callable[[TextIO], None],
    *,
    fsync: bool = False,
    temp_prefix: str | None = None,
    temp_name: str | None = None,
    encoding: str | None = None,
    remove_on_failure: bool = True,
) -> Path:
    """Write `path` with the bytes that `write` puts in the stream.

    `write` is one function with one argument, an open text stream. It writes the
    new contents. It does not close the stream and does not make the temp file.
    Each caller keeps its own serialization. This module does not know about JSON.

    fsync=False does not call `os.fsync`. fsync=True calls `os.fsync` after the
    write and before the replace. The callers differ here, so this module does not
    decide for them.

    `temp_prefix` gives the temp file name a prefix and `tempfile.mkstemp` makes
    the file. That name is unique, and the mode is 0600. `temp_name` is the other
    way: a pattern for a temp name beside the target, where `{name}` is the target
    name, `{stem}` is that name without its last suffix, and `{pid}` is
    `os.getpid()`. `open()` makes that file, so its mode follows the umask. This
    name is not unique. Give one of the two, or give neither for the default
    prefix, `DEFAULT_PREFIX` + the target name (a hidden, unique name, as in
    `.state.json.a1b2c3`).

    `encoding` is the encoding of the stream. None means the platform default, as
    in `open()`.

    remove_on_failure=True removes the temp file when `write` or `os.replace`
    fails. remove_on_failure=False leaves it. The callers differ here.

    Returns the target path. The target has the new bytes, or it keeps the old
    bytes.
    """
    path = Path(path)
    if temp_prefix is not None and temp_name is not None:
        raise ValueError("give temp_prefix or temp_name, not both")
    if temp_name is not None:
        temp = _sibling_path(path, temp_name)
        stream = open(temp, "w", encoding=encoding)
    else:
        fd, name = tempfile.mkstemp(prefix=DEFAULT_PREFIX + path.name if temp_prefix is None else temp_prefix,
                                    dir=path.parent)
        temp = Path(name)
        stream = os.fdopen(fd, "w", encoding=encoding)
    try:
        with stream:
            write(stream)
            stream.flush()
            if fsync:
                os.fsync(stream.fileno())
        os.replace(temp, path)
    except BaseException:
        if remove_on_failure:
            try:
                os.unlink(temp)
            except OSError:
                pass
        raise
    return path
