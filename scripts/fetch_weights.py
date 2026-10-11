#!/usr/bin/env python3
"""Download the model weights that the repository does not commit.

    python scripts/fetch_weights.py

Each file is pinned in `src/weight_pins.py` to a URL, a full SHA-256 and a size.
A file that is already present with the pinned checksum is skipped, so re-running
is safe.  A download goes to a temporary file next to its destination and is moved
into place only when its checksum matches.  On a mismatch the temporary file is
deleted, anything already at the destination is left as it was, and the script
exits with status 1. Standard library only. Licences: see NOTICE.
"""
import hashlib
import os
import sys
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))  # `__main__` puts scripts/ first, not the repository root
from src.tls_trust import trusted_context
from src.weight_pins import WEIGHT_PINS
CHUNK = 1 << 20

#: The pin table itself.  `src/weight_pins.py` owns it, so one import serves this
#: script and the test that compares the table with NOTICE.
WEIGHTS = WEIGHT_PINS


class ChecksumError(ValueError):
    """The downloaded bytes are not the pinned file."""


def sha256_of(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def open_url(request, timeout):
    return urllib.request.urlopen(request, timeout=timeout, context=trusted_context())


def fetch(dest, url, sha256, size, urlopen=open_url):
    """Make ``dest`` the pinned file: 'present', 'downloaded' or 'replaced'."""
    dest = Path(dest)
    existed = dest.exists()
    if dest.is_file() and sha256_of(dest) == sha256:
        return "present"
    request = urllib.request.Request(
        url, headers={"User-Agent": "corner-pocket-fetch-weights"})
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix="." + dest.name + ".", suffix=".part",
                               dir=dest.parent)
    try:
        digest, total = hashlib.sha256(), 0
        with os.fdopen(fd, "wb") as out, urlopen(request, timeout=60) as response:
            for block in iter(lambda: response.read(CHUNK), b""):
                total += len(block)
                if total > size:
                    raise ChecksumError(f"{dest.name}: more than the pinned {size} bytes")
                digest.update(block)
                out.write(block)
            out.flush()
            os.fsync(out.fileno())
        if digest.hexdigest() != sha256:
            raise ChecksumError(f"{dest.name}: got sha256 {digest.hexdigest()}, "
                                f"pinned {sha256}")
        umask = os.umask(0)
        os.umask(umask)
        os.chmod(tmp, 0o666 & ~umask)  # mkstemp makes 0600; match a plain open()
        os.replace(tmp, dest)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return "replaced" if existed else "downloaded"


def main():
    failed = False
    for rel, url, sha256, size in WEIGHTS:
        try:
            print(f"{fetch(ROOT / rel, url, sha256, size):10} {rel}", flush=True)
        except (OSError, ChecksumError) as error:
            print(f"FAILED     {rel}: {error}", file=sys.stderr, flush=True)
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
