"""The storage seam for Corner Pocket's persisted data (docs/postgres-design.md section 7).

`Store` is the interface every storage backend implements; `JsonStore` is today's
file storage behind it and stays the default, so the suite and a server without
POOL_DATABASE_URL behave exactly as before.  The Postgres implementation is added
by later, reviewed steps; until then `open_store` refuses to pretend it exists.

Nothing calls this module yet: the server and the tools still use their own file
code, and they switch to `open_store(root)` one caller at a time.

JsonStore reuses the writers the application already has, so the formats and the
concurrency rules are identical to today's:
  * operations  -> annotator.operations.Operations (revisioned document, 409 on a
                   stale revision, one process-wide lock per path);
  * face store  -> src.face_id.add_faces / remove_faces (locked merge per path);
  * everything else -> a locked read-modify-write of the same JSON file, written
                   with the same atomic temp-file + fsync + os.replace as
                   annotator.unified_server.atomic_save.
Read methods never write (the read-only contract, tested for every read).
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from src.face_id import add_faces, load_faces, remove_faces

ENV = "POOL_DATABASE_URL"
# dataset -> the scan folder under out/ that holds its queue, verdicts and frame results
DATASETS = {"vod30": "scan30", "highlight": "scan_highlight"}
BALL_SETS = ("unlabeled_crops", "unlabeled_crops2", "vod30_event_crops")
# precomputed artifacts the server reads whole: kind -> file under out/ ({ds} = dataset)
ARTIFACTS = {
    "queue_report": "{scan}/dense_queue_report.json",
    "queue_retired": "{scan}/dense_queue_retired.json",
    "calibration_segments": "calib_{ds}_segments.json",
    "calibration": "calib_{ds}.json",
    "seed_propagation": "pid_seed_tracks.json",
    "seed_prototypes": "pid_seed_protos.json",
    "event_actors": "events_actors.json",
}


@runtime_checkable
class Store(Protocol):
    # operations (design section 2)
    def ops_get(self) -> dict: ...
    def ops_post(self, payload: dict) -> dict: ...
    def enroll_player(self, player: dict, context: dict) -> dict: ...
    # identity (section 3)
    def identity_load(self) -> dict: ...
    def faces_load(self) -> dict: ...
    def faces_add(self, additions: dict) -> dict: ...
    def faces_remove(self, player_id: str) -> int: ...
    def seeds_get(self, dataset: str) -> dict: ...
    def seed_put(self, dataset: str, key: str, record: dict | None) -> dict: ...
    # operator records (section 4)
    def verdicts_get(self, dataset: str) -> dict: ...
    def verdict_put(self, dataset: str, event_id, fields: dict) -> dict: ...
    def labels_get(self, crop_set: str) -> dict: ...
    def label_put(self, crop_set: str, crop_file: str, label) -> None: ...
    def correction_get(self, dataset: str, frame_index: int) -> dict | None: ...
    def correction_put(self, dataset: str, frame_index: int, payload: dict) -> None: ...
    def anchors_get(self, dataset: str) -> dict: ...
    def anchors_put(self, dataset: str, t_key: str, pts: list) -> None: ...
    # precomputed, read-only for the server (sections 5 and 6)
    def artifact(self, kind: str, dataset: str) -> Any: ...
    def queue(self, dataset: str) -> list: ...
    def queue_window(self, dataset: str, t0: float, t1: float) -> list: ...
    def tracklets(self, dataset: str) -> dict: ...
    def frame_detections(self, dataset: str, frame_index: int) -> dict | None: ...


def open_store(root) -> Store:
    """The store for `root`: Postgres when POOL_DATABASE_URL is set, else the JSON files."""
    if os.environ.get(ENV):
        raise NotImplementedError(
            f"{ENV} is set, but the Postgres store is not built yet (docs/postgres-design.md "
            "section 8); unset it to use the JSON files")
    return JsonStore(root)


def _read(path: Path, default):
    return json.loads(path.read_text()) if path.is_file() else default


def _write(path: Path, data) -> None:
    """annotator.unified_server.atomic_save, byte for byte (indent=2, trailing newline)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix="." + path.name, dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(data, stream, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


class JsonStore:
    """Today's files under <root>/out, behind the Store interface."""

    _locks: dict = {}
    _locks_guard = threading.Lock()

    def __init__(self, root):
        self.root = Path(root).resolve()
        self.out = self.root / "out"
        self._ops = None

    # -- helpers ------------------------------------------------------------
    def _lock(self, path: Path):
        with self._locks_guard:
            return self._locks.setdefault(path.resolve(), threading.RLock())

    def _scan(self, dataset: str) -> Path:
        if dataset not in DATASETS:
            raise ValueError(f"unknown dataset: {dataset}")
        return self.out / DATASETS[dataset]

    def _operations(self):
        if self._ops is None:
            from annotator.operations import Operations
            self._ops = Operations(self.root)
        return self._ops

    # -- operations ---------------------------------------------------------
    def ops_get(self) -> dict:
        return self._operations().get()

    def ops_post(self, payload: dict) -> dict:
        return self._operations().post(payload)

    def enroll_player(self, player: dict, context: dict) -> dict:
        return self._operations().enroll_player(player, context)

    # -- identity -----------------------------------------------------------
    def identity_path(self) -> Path:
        return self.out / "identity" / "clusters.json"

    def identity_load(self) -> dict:
        return _read(self.identity_path(), {})

    def _faces_path(self) -> Path:
        return self.out / "corner-pocket" / "face_embeddings.json"

    def faces_load(self) -> dict:
        return load_faces(self._faces_path())

    def faces_add(self, additions: dict) -> dict:
        return add_faces(self._faces_path(), additions)

    def faces_remove(self, player_id: str) -> int:
        return remove_faces(self._faces_path(), player_id)

    def _seeds_path(self, dataset: str) -> Path:
        if dataset != "vod30":
            raise ValueError("seeds exist for vod30 only")
        return self.out / "pid_seed.json"

    def seeds_get(self, dataset: str) -> dict:
        return _read(self._seeds_path(dataset), {"seeds": {}}).get("seeds", {})

    def seed_put(self, dataset: str, key: str, record: dict | None) -> dict:
        path = self._seeds_path(dataset)
        with self._lock(path):
            saved = _read(path, {"seeds": {}})
            seeds = saved.setdefault("seeds", {})
            if record is None:
                seeds.pop(key, None)
            else:
                seeds[key] = dict(seeds.get(key, {}), **record)
            _write(path, saved)
            return seeds

    # -- operator records ---------------------------------------------------
    def verdicts_get(self, dataset: str) -> dict:
        return _read(self._scan(dataset) / "annotations.json", {})

    def verdict_put(self, dataset: str, event_id, fields: dict) -> dict:
        path = self._scan(dataset) / "annotations.json"
        key = str(event_id)
        with self._lock(path):
            annotations = _read(path, {})
            record = dict(annotations.get(key, {}), **fields)
            record["updated_at"] = datetime.now(timezone.utc).isoformat()
            annotations[key] = record
            _write(path, annotations)
            return record

    def _labels_path(self, crop_set: str) -> Path:
        if crop_set not in BALL_SETS:
            raise ValueError(f"unknown ball set: {crop_set}")
        return self.out / crop_set / "labels.json"

    def labels_get(self, crop_set: str) -> dict:
        return _read(self._labels_path(crop_set), {})

    def label_put(self, crop_set: str, crop_file: str, label) -> None:
        """Set or clear (None) the label of one crop, matched by basename; an existing
        key keeps its original (often absolute) spelling, as the server does today."""
        path = self._labels_path(crop_set)
        with self._lock(path):
            labels = _read(path, {})
            keys = [k for k in labels if Path(k).name == crop_file]
            key = keys[0] if keys else crop_file
            for old in keys:
                labels.pop(old)
            if label is not None:
                labels[key] = label
            _write(path, labels)

    def _correction_path(self, dataset: str, frame_index: int) -> Path:
        return self._scan(dataset) / "frame_results" / str(int(frame_index)) / "correction.json"

    def correction_get(self, dataset: str, frame_index: int) -> dict | None:
        return _read(self._correction_path(dataset, frame_index), None)

    def correction_put(self, dataset: str, frame_index: int, payload: dict) -> None:
        path = self._correction_path(dataset, frame_index)
        with self._lock(path):
            _write(path, payload)

    def _anchors_path(self, dataset: str) -> Path:
        self._scan(dataset)
        return self.out / f"pid_anchors_{dataset}.json"

    def anchors_get(self, dataset: str) -> dict:
        return _read(self._anchors_path(dataset), {"anchors": {}})

    def anchors_put(self, dataset: str, t_key: str, pts: list) -> None:
        path = self._anchors_path(dataset)
        with self._lock(path):
            saved = _read(path, {"anchors": {}})
            key = next((k for k in saved["anchors"] if float(k) == float(t_key)), str(t_key))
            saved["anchors"][key] = pts
            _write(path, saved)

    # -- precomputed (read-only) ---------------------------------------------
    def artifact(self, kind: str, dataset: str) -> Any:
        if kind not in ARTIFACTS:
            raise ValueError(f"unknown artifact kind: {kind}")
        relative = ARTIFACTS[kind].format(ds=dataset, scan=DATASETS.get(dataset, dataset))
        return _read(self.out / relative, None)

    def queue(self, dataset: str) -> list:
        return _read(self._scan(dataset) / "events.json", [])

    def queue_window(self, dataset: str, t0: float, t1: float) -> list:
        return [e for e in self.queue(dataset)
                if isinstance(e.get("t"), (int, float)) and t0 <= e["t"] <= t1]

    def tracklets(self, dataset: str) -> dict:
        if dataset != "vod30":
            return {}
        return _read(self.out / "pid2_tracklets.json", {})

    def frame_detections(self, dataset: str, frame_index: int) -> dict | None:
        """The JSON store has no precomputed overlays: callers compute them live."""
        return None
