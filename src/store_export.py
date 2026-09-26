"""Export the user data from Postgres back to files, byte-exact (docs/postgres-design.md 7.4).

    PYTHONPATH=. .venv/bin/python -m src.store_export --to <dir> [--compare <root>]

Writes, under <dir>/out/, every user-data file in exactly the format its application
writer produces (src/store_files.py): documents come back as their stored text; the
identity index and the face store are rendered from their rows in the writers' fixed
key order. Files are written atomically and only under <dir>; nothing else is touched.

--compare <root> checks the export byte for byte against the files under <root>/out
(each file: identical, or the first differing byte offset and the text around it)
and prints the row count of every user-data table.  Uses: rollback after the
database has taken writes (design 7.6), and the offline tools that read files.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

from src.store_files import INDENT1, dump, documents, fmt_of

TABLES = ("ops_meta", "players", "tournaments", "entrants", "entrant_members", "matches", "notes", "sources",
          "ops_events", "identity_clusters", "identity_face_samples", "face_embeddings", "track_seeds",
          "event_verdicts", "ball_labels", "frame_corrections", "pocket_anchors", "json_documents")


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix="." + path.name, dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def export_texts(conn) -> dict[str, str]:
    """{relative path: exact file text} for everything the database holds."""
    from src.store_import import FacesSet, IdentitySet
    texts = dict(documents(conn))
    clusters = IdentitySet().render(conn)
    if clusters:
        texts["out/identity/clusters.json"] = dump(clusters, INDENT1)
    faces = FacesSet().render(conn)
    if faces:
        texts["out/corner-pocket/face_embeddings.json"] = dump(faces, fmt_of("out/corner-pocket/face_embeddings.json"))
    return texts


def export(conn, to: Path) -> list[str]:
    """Write every file under `to`; returns the relative paths written."""
    written = []
    for relative, text in sorted(export_texts(conn).items()):
        target = Path(to) / relative
        if not target.resolve().is_relative_to(Path(to).resolve()):
            raise ValueError(f"refusing to write outside {to}: {relative}")
        _atomic_write(target, text)
        written.append(relative)
    return written


def first_byte_difference(a: bytes, b: bytes):
    """None when equal, else (offset, reason) for the first differing byte."""
    if a == b:
        return None
    offset = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))
    if offset == min(len(a), len(b)):
        reason = f"one is a prefix of the other ({len(a)} vs {len(b)} bytes)"
    else:
        reason = f"original {a[max(0, offset - 30):offset + 30]!r} vs export {b[max(0, offset - 30):offset + 30]!r}"
    return offset, reason


def compare(exported_root: Path, original_root: Path, relatives) -> list[dict]:
    rows = []
    for relative in sorted(relatives):
        original, exported = Path(original_root) / relative, Path(exported_root) / relative
        if not original.is_file() or not exported.is_file():
            rows.append({"file": relative, "identical": False, "original": original.is_file(),
                         "exported": exported.is_file()})
            continue
        found = first_byte_difference(original.read_bytes(), exported.read_bytes())
        rows.append({"file": relative, "identical": found is None, "bytes": original.stat().st_size,
                     **({} if found is None else {"offset": found[0], "reason": found[1]})})
    return rows


def row_counts(conn) -> dict[str, int]:
    return {t: conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in TABLES
            if conn.execute("SELECT to_regclass(%s)", (t,)).fetchone()[0] is not None}


def main(argv=None) -> int:
    from src import db
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--to", required=True, help="directory to write <to>/out/... into")
    parser.add_argument("--compare", help="workspace root whose out/ files the export must equal byte for byte")
    args = parser.parse_args(argv)
    try:
        with db.connect() as conn:
            conn.read_only = True
            with conn.transaction():
                written = export(conn, Path(args.to))
                counts = row_counts(conn)
    except db.DatabaseNotConfigured as error:
        print(error, file=sys.stderr)
        return 2
    print(json.dumps({"written": written, "rows": counts}, indent=1))
    if args.compare:
        rows = compare(Path(args.to), Path(args.compare), written)
        for row in rows:
            print(("identical  " if row["identical"] else "DIFFERENT  ") + row["file"] +
                  ("" if row["identical"] else f"  at byte {row.get('offset')}: {row.get('reason')}"))
        return 0 if all(row["identical"] for row in rows) else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
