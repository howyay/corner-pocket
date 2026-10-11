"""The one owner of this repository's weight pins.

``scripts/fetch_weights.py`` downloads two model weights that git does not
commit.  Each weight is pinned to a URL, a full SHA-256 and a size in bytes.
``NOTICE`` states the same three facts for a reader, under the licence of each
weight.  Two owners of one pin drift apart without a guard, so this module owns
the table and ``tests/test_fetch_weights.py`` compares it with ``NOTICE`` in both
directions.

Standard library only, and no import from the repository.
"""
from pathlib import Path

#: The path under the repository root of the first pinned weight.
YOLO = "yolov8n.pt"

#: The path under the repository root of the second pinned weight.
OSNET = "src/reid/weights/osnet_x0_25_msmt17.pth"

#: Hugging Face hosts the OSNet weight under a repository and a revision.
OSNET_REPO = "https://huggingface.co/kaiyangzhou/osnet"
OSNET_REVISION = "a5c5cc037c24235cda3b21085b93ad77c9616224"
OSNET_FILENAME = (
    "osnet_x0_25_msmt17_combineall_256x128_amsgrad_ep150_stp60_lr0.0015"
    "_b64_fb10_softmax_labelsmooth_flip_jitter.pth")
OSNET_URL = f"{OSNET_REPO}/resolve/{OSNET_REVISION}/{OSNET_FILENAME}"

#: (path under the repository root, URL, SHA-256, size in bytes) for every weight.
#:
#: The revision pins the OSNet weight to a commit, not to ``main``.  The weights
#: come from datasets with their own terms; see ``NOTICE``.
WEIGHT_PINS = (
    (YOLO,
     "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8n.pt",
     "f59b3d833e2ff32e194b5bb8e08d211dc7c5bdf144b90d2c8412c47ccfc83b36",
     6549796),
    (OSNET,
     OSNET_URL,
     "cf55163d78fc44c62c82f85ab62d39f10438679b5abe8c698ae08cfa84aa6e18",
     9336983),
)

#: The same rows, keyed by the path under the repository root.
WEIGHTS_BY_PATH = {rel: (rel, url, sha256, size) for rel, url, sha256, size in WEIGHT_PINS}

#: The repository root, from this file's own location.
ROOT = Path(__file__).resolve().parents[1]
