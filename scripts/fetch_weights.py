#!/usr/bin/env python3
"""Download the model weights that the repository does not commit.

    python scripts/fetch_weights.py

Each file is pinned to a URL, a full SHA-256 and a size. A file that is
already present with the pinned checksum is skipped, so re-running is safe.
A download goes to a temporary file next to its destination and is moved into
place only when its checksum matches. On a mismatch the temporary file is
deleted, anything already at the destination is left as it was, and the
script exits with status 1. Standard library only. Licences: see NOTICE.
"""
import hashlib
import os
import ssl
import sys
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHUNK = 1 << 20
CA_BUNDLES = ("/etc/ssl/certs/ca-certificates.crt",  # Debian, Ubuntu, Arch, NixOS
              "/etc/pki/tls/certs/ca-bundle.crt",     # Fedora, RHEL
              "/etc/ssl/cert.pem")                    # macOS, Alpine, BSDs

# (path under the repository root, URL, SHA-256, size in bytes)
WEIGHTS = [
    ("yolov8n.pt",
     "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8n.pt",
     "f59b3d833e2ff32e194b5bb8e08d211dc7c5bdf144b90d2c8412c47ccfc83b36",
     6549796),
    # Hugging Face kaiyangzhou/osnet, pinned to commit a5c5cc0; trained on
    # MSMT17, whose terms are academic and non-commercial (see NOTICE).
    ("src/reid/weights/osnet_x0_25_msmt17.pth",
     "https://huggingface.co/kaiyangzhou/osnet/resolve/"
     "a5c5cc037c24235cda3b21085b93ad77c9616224/"
     "osnet_x0_25_msmt17_combineall_256x128_amsgrad_ep150_stp60_lr0.0015"
     "_b64_fb10_softmax_labelsmooth_flip_jitter.pth",
     "cf55163d78fc44c62c82f85ab62d39f10438679b5abe8c698ae08cfa84aa6e18",
     9336983),
]


class ChecksumError(ValueError):
    """The downloaded bytes are not the pinned file."""


def sha256_of(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def tls_context():
    """The default verifying context. Some standalone Python builds (uv's, for
    one) find no CA certificates on some systems; then load the system bundle.
    Certificate verification is never turned off."""
    context = ssl.create_default_context()
    if not context.cert_store_stats()["x509_ca"]:
        bundle = next((b for b in CA_BUNDLES if os.path.isfile(b)), None)
        if bundle:
            context.load_verify_locations(cafile=bundle)
    return context


def open_url(request, timeout):
    return urllib.request.urlopen(request, timeout=timeout, context=tls_context())


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
