"""Skip a test whose footage or saved artifact this checkout does not have.

``data/`` and every ``out/`` artifact are gitignored, so a fresh clone has none of
them: a test that opens one used to end in ``FileNotFoundError`` - or in a decoder's
``RuntimeError``/``TypeError`` - rather than in a skip.  Call :func:`require` (or
:func:`require_any`) where the path is actually used: the test skips naming the
missing path, and every assertion stays in place for the checkout that has it.
"""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


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
