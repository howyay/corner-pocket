"""The storage seam for Corner Pocket's persisted data (docs/postgres-design.md section 7).

`Store` is the interface every storage backend implements; `JsonStore` is today's
file storage behind it and stays the default, so the suite and a server without
POOL_DATABASE_URL behave exactly as before.  With POOL_DATABASE_URL set,
`open_store` returns `src.store_pg.PostgresStore`, which passes the same contract
(tests/test_store_contract.py).

Nothing calls this module yet: the server and the tools still use their own file
code, and they switch to `open_store(root)` one caller at a time.

JsonStore reuses the writers the application already has, so the formats and the
concurrency rules are identical to today's:
  * operations  -> annotator.operations.Operations (revisioned document, 409 on a
                   stale revision, one process-wide lock per path);
  * face store  -> src.face_id.add_faces / remove_faces (locked merge per path);
  * everything else -> a locked read-modify-write of the same JSON file, written
                   by src.atomic_write.write_atomic with the same fsync and
                   os.replace as annotator.unified_server.atomic_save.
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

from src.atomic_write import write_atomic
from src.face_id import add_faces, load_faces, remove_faces

ENV = "POOL_DATABASE_URL"


class StoreConstraintError(ValueError):
    """A write the application rules accepted but a database constraint refused.

    The transaction was rolled back, so nothing was written. It is a ValueError, so
    the server's existing handlers answer 4xx; the message says it is a storage
    constraint and `constraint` names it for the technical detail."""

    def __init__(self, constraint: str | None, detail: str):
        self.constraint = constraint
        super().__init__(f"Refused by the database constraint {constraint or '(unnamed)'}; "
                         f"nothing was written. {detail}")


# Where one dataset lives has one owner: src/datasets.py.  JsonStore resolves every
# dataset through it, imported VODs included (out/vods/<id>/).  The map this module
# exported as DATASETS had no reader once artifact() stopped using it, so it is gone;
# src/store_files.py:20 still spells its own copy of the built-in two (out of scope here).
from src.datasets import lookup as dataset_lookup  # noqa: E402
# The crop-set vocabulary (the sets a crop file can belong to) has one owner:
# src.store_files.BALL_SETS, the module that also builds those files' paths. This
# module imports it, so the store and that owner cannot hold two different lists.
from src.store_files import BALL_SETS  # noqa: E402
# precomputed artifacts the server reads whole: kind -> file under out/.  A row here
# names a dataset, so artifact() resolves the dataset through src/datasets.py and reads
# the folder queue() reads (out/vods/<id>/ for an imported VOD, out/scan30/ for a
# built-in).  {scan} is that folder, relative to out/; {ds} is the dataset id, which
# names the calibration files at the out/ root (src/calib_segments.py:49 owns that name).
ARTIFACTS = {
    "queue_report": "{scan}/dense_queue_report.json",
    "queue_retired": "{scan}/dense_queue_retired.json",
    "calibration_segments": "calib_{ds}_segments.json",
    "calibration": "calib_{ds}.json",
}
# Artifacts that belong to no dataset: one file at the out/ root.  They take no dataset
# argument, so a caller cannot pass one and believe it selected something.
SHARED_ARTIFACTS = {
    "seed_propagation": "pid_seed_tracks.json",
    "seed_prototypes": "pid_seed_protos.json",
    "event_actors": "events_actors.json",
}


@runtime_checkable
class Store(Protocol):
    # operations (design section 2)
    def get(self) -> dict: ...
    def post(self, payload: dict) -> dict: ...
    def enroll_player(self, player: dict, context: dict) -> dict: ...
    # where a record set lives, for receipts
    def place(self, kind: str, key: str | None = None):
        """Where this backing keeps one record set. Receipts show the answer.

        `kind` is one of:
          * `operations` - the operations document. `key` is not used.
          * `faces` - the face embeddings. `key` is not used.
          * `anchors` - one dataset's pocket anchors. `key` is the dataset.
        A file backing answers with a Path. A database backing answers with the
        database name as text. The answer is for display only."""
        ...
    # identity (section 3)
    def identity_load(self) -> dict: ...
    def identity_save(self, clusters: dict) -> None: ...
    def faces_load(self) -> dict: ...
    def faces_add(self, additions: dict) -> dict: ...
    def faces_remove(self, player_id: str) -> int: ...
    def seeds_get(self, dataset: str) -> dict: ...
    def seed_put(self, dataset: str, key: str, record: dict | None) -> dict: ...
    def seed_file(self, dataset: str) -> dict: ...
    # operator records (section 4)
    def verdicts_get(self, dataset: str) -> dict: ...
    def verdict_put(self, dataset: str, event_id, fields: dict) -> dict: ...
    def labels_get(self, crop_set: str) -> dict: ...
    def label_put(self, crop_set: str, crop_file: str, label, new_key: str | None = None) -> None: ...
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


def scratch_root(root) -> bool:
    """True when `root` is a throwaway directory: a fixture test's temporary root.

    The database does not key its document by root (src/store_pg.py `STATE` is one
    path), so every rooted store with POOL_DATABASE_URL set is the same club.  A
    temporary root is therefore never the isolation it looks like."""
    temp = Path(tempfile.gettempdir()).resolve()
    try:
        resolved = Path(root).resolve()
    except OSError:                   # a root that cannot be resolved is not proven scratch
        return False
    return resolved == temp or temp in resolved.parents


def open_store(root) -> Store:
    """The store for `root`: Postgres when POOL_DATABASE_URL is set, else the JSON files.

    A scratch `root` is refused while the variable is set: the database holds one copy
    of the club whatever root is asked for, so a temporary root would be reading and
    writing the live club while believing it was isolated (docs/postgres.md)."""
    if os.environ.get(ENV):
        if scratch_root(root):
            raise SystemExit(
                f"open_store: POOL_DATABASE_URL is set, so the club's data lives in Postgres and the root "
                f"does not isolate anything: every rooted store with this database reads the same document "
                f"(out/corner-pocket/state.json). {root} is a scratch directory, so it would be handed the "
                f"live club. Refusing. Run without POOL_DATABASE_URL, or open a throwaway schema on purpose: "
                f"PostgresStore(root, search_path='...') (docs/postgres.md).")
        from src.store_pg import PostgresStore
        return PostgresStore(root)
    return JsonStore(root)


def refuse_file_writes_under_postgres(tool: str) -> None:
    """Exit with a clear message when POOL_DATABASE_URL is set.

    For the legacy tools that write user-data JSON files directly (their own small
    servers and one-off scripts). With the database as the store, a file they write
    is read by nothing and silently diverges, so they refuse to start instead. To
    use one anyway: unset POOL_DATABASE_URL and point it at an exported copy
    (python -m src.store_export --to DIR), never at the live out/."""
    if os.environ.get(ENV):
        raise SystemExit(f"{tool}: POOL_DATABASE_URL is set, so the user data lives in Postgres and this "
                         f"tool's file writes would silently diverge from it. Refusing to run. To use it on "
                         f"a copy: python -m src.store_export --to DIR, then run it against DIR with the "
                         f"variable unset (docs/postgres.md).")


def _read(path: Path, default):
    return json.loads(path.read_text()) if path.is_file() else default


def _write(path: Path, data) -> None:
    """annotator.unified_server.atomic_save, byte for byte (indent=2, trailing newline)."""
    path.parent.mkdir(parents=True, exist_ok=True)

    def dump(stream) -> None:
        json.dump(data, stream, indent=2, allow_nan=False)
        stream.write("\n")

    write_atomic(path, dump, fsync=True)


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
        found = dataset_lookup(self.root, dataset)
        if found is None:
            raise ValueError(f"unknown dataset: {dataset}")
        return found.out_dir

    def _operations(self):
        if self._ops is None:
            from annotator.operations import Operations
            self._ops = Operations(self.root)
        return self._ops

    # -- operations ---------------------------------------------------------
    def get(self) -> dict:
        return self._operations().get()

    def post(self, payload: dict) -> dict:
        return self._operations().post(payload)

    def enroll_player(self, player: dict, context: dict) -> dict:
        return self._operations().enroll_player(player, context)

    def place(self, kind: str, key: str | None = None):
        """The file this backing keeps `kind` in (Store.place).

        The answer is a real Path, never a copy of the literal. For `operations` the
        Path comes from the Operations object that owns the file. Thus the receipt and
        the writer cannot name different files."""
        if kind == "operations":
            return self._operations().path
        if kind == "faces":
            return self._faces_path()
        if kind == "anchors":
            return self._anchors_path(key)
        raise ValueError(f"unknown record set: {kind}")

    # -- identity -----------------------------------------------------------
    def identity_path(self) -> Path:
        return self.out / "identity" / "clusters.json"

    def identity_load(self) -> dict:
        return _read(self.identity_path(), {})

    def identity_save(self, clusters: dict) -> None:
        """Replace the index with `clusters`, in IdentityIndex.save's format (indent=1)."""
        path = self.identity_path()
        with self._lock(path):
            path.parent.mkdir(parents=True, exist_ok=True)
            # The temp file is <stem>.json.tmp beside the target, and a failed write
            # leaves it: the behavior this writer always had (no fsync, no cleanup).
            write_atomic(path, lambda stream: stream.write(json.dumps(clusters, indent=1)),
                         temp_name="{stem}.json.tmp", encoding="utf-8", remove_on_failure=False)

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
        return self.seed_file(dataset).get("seeds", {})

    def seed_file(self, dataset: str) -> dict:
        """The whole pid_seed.json document ({"seeds": {...}} plus any top-level keys)."""
        return _read(self._seeds_path(dataset), {"seeds": {}})

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

    def label_put(self, crop_set: str, crop_file: str, label, new_key: str | None = None) -> None:
        """Set or clear (None) the label of one crop, matched by basename; an existing
        key keeps its original (often absolute) spelling, as the server does today, and
        a crop labelled for the first time is keyed `new_key` (the server passes the
        crop's meta.json path) or else its basename."""
        path = self._labels_path(crop_set)
        with self._lock(path):
            labels = _read(path, {})
            keys = [k for k in labels if Path(k).name == crop_file]
            key = keys[0] if keys else (new_key or crop_file)
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
    def artifact(self, kind: str, dataset: str | None = None) -> Any:
        """A precomputed file this store reads whole, or None when it is absent.

        A kind in ``SHARED_ARTIFACTS`` belongs to no dataset and refuses a dataset
        argument.  Any other kind requires one and resolves it through
        :func:`src.datasets.lookup`, so the report sits in the folder ``queue()``
        reads: ``out/vods/<id>/`` for an imported VOD, ``out/scan30/`` for a built-in.
        """
        if kind in SHARED_ARTIFACTS:
            if dataset is not None:
                raise ValueError(f"{kind} belongs to no dataset; drop the dataset argument")
            return _read(self.out / SHARED_ARTIFACTS[kind], None)
        if kind not in ARTIFACTS:
            raise ValueError(f"unknown artifact kind: {kind}")
        if dataset is None:
            raise ValueError(f"{kind} names a dataset; pass one")
        scan = self._scan(dataset).relative_to(self.out)
        return _read(self.out / ARTIFACTS[kind].format(ds=dataset, scan=scan), None)

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
