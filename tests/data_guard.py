"""Skip a test whose footage or saved artifact this checkout does not have.

``data/`` and every ``out/`` artifact are gitignored, so a fresh clone has none of
them: a test that opens one used to end in ``FileNotFoundError`` - or in a decoder's
``RuntimeError``/``TypeError`` - rather than in a skip.  Call :func:`require` (or
:func:`require_any`) where the path is actually used: the test skips naming the
missing path, and every assertion stays in place for the checkout that has it.

The second fact here is the workspace shape.  A temp root that a test hands to the
product is a workspace root: it needs the checkout's ``data/`` and the store document
where the store reads it.  Four writers spelled that layout by hand (this suite, two
run scripts, the browser fixture), so one function names each part.
"""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def store_document(root) -> Path:
    """Where the store reads the operations document under a workspace root.

    ``src/store.py`` JsonStore -> ``annotator/operations.py`` Operations.path.  A writer
    that copies the path instead keeps working until the store moves one directory.
    """
    return Path(root) / 'out' / 'corner-pocket' / 'state.json'


def link_data(root) -> Path:
    """Link this checkout's ``data/`` into a workspace root, once.

    The temp root stays a workspace root: recordings and calibration files are read
    through the link, and no media is copied.  Idempotent, because a case that asks for
    the workspace twice must still get one link.
    """
    root = Path(root)
    link = root / 'data'
    if not (link.is_symlink() or link.exists()):
        link.symlink_to(ROOT / 'data')
    return link


def label(path) -> str:
    """The path as a checkout-relative name when it lives inside the repository."""
    path = Path(path)
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


def require(*paths):
    """Return the path (or list of paths) once every one exists, else skip."""
    missing = [label(path) for path in paths if not Path(path).exists()]
    if missing:
        raise unittest.SkipTest('missing ' + ', '.join(sorted(set(missing))))
    paths = [Path(path) for path in paths]
    return paths[0] if len(paths) == 1 else paths


def require_any(*paths):
    """Return the first existing path, or skip naming all the candidates."""
    for path in paths:
        if Path(path).exists():
            return Path(path)
    raise unittest.SkipTest('missing all of: ' + ', '.join(label(path) for path in paths))
