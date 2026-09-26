"""The user-data files, their exact on-disk formats, and their byte-exact documents.

Every user-data file is written by one application writer, and each writer has one
format. `FORMATS` names it per file, and `dump()` reproduces it byte for byte:

  indent2+nl  json.dump(indent=2) + "\\n"   Operations._commit, unified_server.atomic_save,
                                            enroll_from_tracklet._write_json, src.store._write
  indent1     json.dumps(indent=1)          IdentityIndex.save, face_id.store_faces

Operations and operator-record files keep their key order as the application wrote
it, which no row model can rebuild (docs: db/migrations/0003_json_documents.sql), so
they are also stored whole in `json_documents` as the exact text. The identity index
and the face store are re-rendered from rows in their writers' fixed key order.
"""
from __future__ import annotations

import json
from pathlib import Path

DATASETS = {"vod30": "scan30", "highlight": "scan_highlight"}
BALL_SETS = ("unlabeled_crops", "unlabeled_crops2", "vod30_event_crops")

INDENT2_NL = "indent2+nl"
INDENT1 = "indent1"


def dump(value, fmt: str) -> str:
    if fmt == INDENT2_NL:
        return json.dumps(value, indent=2, allow_nan=False) + "\n"
    if fmt == INDENT1:
        return json.dumps(value, indent=1, allow_nan=False)
    raise ValueError(f"unknown format {fmt}")


def fmt_of(relative: str) -> str:
    """The writer format of a user-data file (relative to the workspace root)."""
    if relative in ("out/identity/clusters.json", "out/corner-pocket/face_embeddings.json"):
        return INDENT1
    return INDENT2_NL


def document_paths(set_name: str, root: Path | None = None) -> list[str]:
    """The files a document-backed data set consists of (fixed names; corrections
    are discovered under frame_results when a root is given)."""
    if set_name == "operations":
        return ["out/corner-pocket/state.json"]
    if set_name == "seeds":
        return ["out/pid_seed.json"]
    if set_name == "verdicts":
        return [f"out/{scan}/annotations.json" for scan in DATASETS.values()]
    if set_name == "labels":
        return [f"out/{crop_set}/labels.json" for crop_set in BALL_SETS]
    if set_name == "anchors":
        return [f"out/pid_anchors_{ds}.json" for ds in DATASETS]
    if set_name == "corrections":
        if root is None:
            return []
        return sorted(str(p.relative_to(root)) for scan in DATASETS.values()
                      for p in (Path(root) / "out" / scan / "frame_results").glob("*/correction.json"))
    return []


DOCUMENT_SETS = ("operations", "seeds", "verdicts", "labels", "anchors", "corrections")


def put_document(conn, relative: str, text: str) -> None:
    conn.execute("INSERT INTO json_documents (path, document) VALUES (%s, %s::json) "
                 "ON CONFLICT (path) DO UPDATE SET document = EXCLUDED.document, updated_at = now()",
                 (relative, text))


def get_document(conn, relative: str) -> str | None:
    row = conn.execute("SELECT document::text FROM json_documents WHERE path = %s", (relative,)).fetchone()
    return None if row is None else row[0]


def documents(conn, prefix: str = "out/") -> dict[str, str]:
    return dict(conn.execute("SELECT path, document::text FROM json_documents WHERE path LIKE %s ORDER BY path",
                             (prefix + "%",)).fetchall())


def has_documents_table(conn) -> bool:
    return conn.execute("SELECT to_regclass('json_documents')").fetchone()[0] is not None
