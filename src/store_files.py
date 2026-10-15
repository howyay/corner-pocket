"""The user-data files, their exact on-disk formats, and their byte-exact documents.

Every user-data file is written by one application writer, and each writer has one
format. `FORMATS` names the format of each row file, `DOCUMENT_FORMAT` names the
format of every document the writers below produce, and `dump()` reproduces both
byte for byte:

  indent2+nl  json.dump(indent=2) + "\\n"   Operations._commit, unified_server.atomic_save,
                                            enroll_from_tracklet._write_json, src.store._write
  indent1     json.dumps(indent=1)          IdentityIndex.save, face_id.store_faces

`fmt_of` answers the format of one path and refuses a path that is no user-data
file, so a new file states its format here instead of receiving a silent default.

Operations and operator-record files keep their key order as the application wrote
it, which no row model can rebuild (docs: db/migrations/0003_json_documents.sql), so
they are also stored whole in `json_documents` as the exact text. The identity index
and the face store are re-rendered from rows in their writers' fixed key order.
"""
from __future__ import annotations

import json
from pathlib import Path

# The built-in datasets and their scan folders have one owner: STATIC_OUT in
# src/datasets.py.  This module reads that owner.  A map typed here again would stay
# old when the owner renames a scan folder.
from src.atomic_write import write_atomic
from src.datasets import STATIC_OUT
# The anchor file name of a dataset has one owner, src/calib_segments.py.  The two
# readers below read the head and the suffix of that name, so a document set and a
# name check cannot keep a second spelling of it.
from src.calib_segments import ANCHORS_HEAD, ANCHORS_SUFFIX, anchors_reference_path
# The refusal of an unknown dataset has one home, src/store_rules.py.  The three store
# backends read that home, so one wording change lands in one file.
from src.store_rules import unknown_dataset

# BALL_SETS is the one owner of the crop-set vocabulary: the sets a crop file can
# belong to. Every Python module imports it from here (`document_paths` above needs it
# too). The database cannot import Python, so `ball_labels.crop_set` repeats the names
# in its CHECK (db/migrations/0002_user_data.sql); tests/test_store_files.py proves
# that the two lists are the same, in the same order.
BALL_SETS = ("unlabeled_crops", "unlabeled_crops2", "vod30_event_crops")

# The operations document path has one owner: this name.  Every reader and every
# writer imports it, so the path stands once in the code.  A docstring or a comment
# may name the path in words, and it must not spell the path again.
STATE_DOCUMENT = "out/corner-pocket/state.json"
# The seed document path has one owner: this name.  Every reader and every writer
# imports it, so the path stands once in the code.  A docstring or a comment may
# name the path in words, and it must not spell the path again.
SEED_DOCUMENT = "out/pid_seed.json"
# The migration files the store layer needs, as (first, last).  db/migrations holds
# this range today; the case in tests/test_store_files.py holds the two to each other.
SCHEMA_RANGE = (1, 4)

# The face store path has one owner: this name, beside the two document names above.
# The format table below holds it, and every other reader imports the name, so the
# path stands once in the code.  tests/test_face_store_path_owner.py holds the tree.
FACE_STORE = "out/corner-pocket/face_embeddings.json"


def dataset_dir(dataset: str) -> str:
    """The folder under the workspace root that holds a dataset's operator data:
    out/scan30, out/scan_highlight, or out/vods/<id> for an imported VOD (the
    folders src.datasets.lookup resolves; the id's format is checked here, whether
    it is imported is the caller's check)."""
    from src.datasets import parse_imported_id
    if dataset in STATIC_OUT:
        return f"out/{STATIC_OUT[dataset]}"
    if parse_imported_id(dataset) is None:
        raise ValueError(unknown_dataset(dataset))
    return f"out/vods/{dataset}"


def dataset_of_dir(relative_dir: str) -> str | None:
    """The inverse of dataset_dir: 'out/scan30' -> 'vod30', 'out/vods/<id>' -> '<id>'."""
    from src.datasets import parse_imported_id
    for dataset, scan in STATIC_OUT.items():
        if relative_dir == f"out/{scan}":
            return dataset
    parts = relative_dir.split("/")
    if len(parts) == 3 and parts[:2] == ["out", "vods"] and parse_imported_id(parts[2]) is not None:
        return parts[2]
    return None


def dataset_dirs(root: Path) -> dict[str, str]:
    """{dataset: folder} for the built-in datasets and every canonical imported-VOD
    folder under root/out/vods - listed or not: a deleted VOD's operator data stays
    on disk (src.datasets.lookup) and is carried like any other record."""
    dirs = {dataset: dataset_dir(dataset) for dataset in STATIC_OUT}
    vods = Path(root) / "out" / "vods"
    if vods.is_dir():
        for folder in sorted(vods.iterdir()):
            if folder.is_dir() and dataset_of_dir(f"out/vods/{folder.name}") is not None:
                dirs[folder.name] = f"out/vods/{folder.name}"
    return dirs

INDENT2_NL = "indent2+nl"
INDENT1 = "indent1"
# The identity index document has one home: this name and `identity_document` below,
# which joins it to a caller's root.  The format table keys that same name.
IDENTITY_DOCUMENT = "out/identity/clusters.json"
# The format of a document: the writers append one newline, and their dataset folders
# come and go; is_document_path names the shapes.  A file in no table: fmt_of refuses it.
DOCUMENT_FORMAT = INDENT2_NL
# Each other user-data file, by path, indent=1 with no trailing newline.
FORMATS = {
    IDENTITY_DOCUMENT: INDENT1,
    FACE_STORE: INDENT1,
}


def dump(value, fmt: str) -> str:
    if fmt == INDENT2_NL:
        return json.dumps(value, indent=2, allow_nan=False) + "\n"
    if fmt == INDENT1:
        return json.dumps(value, indent=1, allow_nan=False)
    raise ValueError(f"unknown format {fmt}")


def dump_document(value) -> str:
    """The text of one document, for a writer that cannot name the format.

    ``tests/test_store_files.py`` refuses a format name in every other file, so a
    writer that renders a whole document cannot call :func:`dump` with a format.
    This function answers the bytes of ``DOCUMENT_FORMAT`` and nothing else.  The
    five JSON writers of the repository call it, so the bytes of a document have
    one home (tests/test_one_atomic_write.py holds them to it).
    """
    return dump(value, DOCUMENT_FORMAT)


def save_document(path, value) -> None:
    """Write one whole document beside its target, or leave the old bytes.

    This function joins the two owners: :func:`dump_document` answers the text and
    ``src.atomic_write.write_atomic`` writes the whole file or none of it.  Two
    stores used to hold the same three statements, and the duplicate-body walk of
    tests/test_duplicate_bodies.py reported the pair.  ``fsync=True`` because a
    document that a reader must see whole must also survive a crash.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    write_atomic(path, lambda stream: stream.write(dump_document(value)), fsync=True)


def is_document_path(relative: str) -> bool:
    """True when `relative` is a file name `document_paths` produces.

    The check reads the file name, not the disk: an imported VOD folder appears and
    disappears, and its documents keep the same names while it exists.
    """
    parts = relative.split("/")
    if relative in (SEED_DOCUMENT, STATE_DOCUMENT):
        return True
    if len(parts) == 2 and parts[0] == "out" and parts[1].startswith(ANCHORS_HEAD) \
            and parts[1].endswith(ANCHORS_SUFFIX):
        return True
    if len(parts) == 3 and parts[0] == "out" and parts[2] == document_name("labels") and parts[1] in BALL_SETS:
        return True
    if parts[-1] == document_name("verdicts"):
        return dataset_of_dir("/".join(parts[:-1])) is not None
    if len(parts) >= 4 and parts[-1] == document_name("corrections") and parts[-2].isdigit() \
            and parts[-3] == "frame_results":
        return dataset_of_dir("/".join(parts[:-3])) is not None
    return False


def fmt_of(relative: str) -> str:
    """The writer format of a user-data file (relative to the workspace root).

    A row file answers from `FORMATS`; a document answers `DOCUMENT_FORMAT`.  A path
    that is neither is refused, never guessed: a new user-data file must state its
    format in this module.
    """
    if relative in FORMATS:
        return FORMATS[relative]
    if is_document_path(relative):
        return DOCUMENT_FORMAT
    raise ValueError(f"no user-data file has the path {relative}")


def correction_path(folder: str, frame: int | str) -> str:
    """The path of one frame's correction document under one dataset folder.

    ``frame`` is the frame index, or the wildcard ``"*"`` that the discovery in
    :func:`document_paths` globs.  The frame folder and the file name stand here, and
    that discovery and the two stores read this function, so the three cannot drift.
    """
    return f"{folder}/frame_results/{'*' if frame == '*' else int(frame)}/correction.json"


def document_paths(set_name: str, root: Path | None = None) -> list[str]:
    """The files a document-backed data set consists of (fixed names; corrections
    are discovered under frame_results when a root is given)."""
    if set_name == "operations":
        return [STATE_DOCUMENT]
    if set_name == "seeds":
        return [SEED_DOCUMENT]
    if set_name == "verdicts":
        dirs = dataset_dirs(root).values() if root is not None else [dataset_dir(ds) for ds in STATIC_OUT]
        return [f"{folder}/annotations.json" for folder in dirs]
    if set_name == "labels":
        return [f"{crops_dir(crop_set)}/labels.json" for crop_set in BALL_SETS]
    if set_name == "anchors":
        return [anchors_reference_path(ds) for ds in STATIC_OUT]
    if set_name == "corrections":
        if root is None:
            return []
        return sorted(str(p.relative_to(root)) for folder in dataset_dirs(root).values()
                      for p in Path(root).glob(correction_path(folder, "*")))
    return []


def document_name(set_name: str) -> str:
    """The file name that every path of `document_paths` ends with.

    A reader that has its folder already, or that compares one file name, reads the
    name here: the map above owns it for the sets whose name is fixed, and
    :func:`correction_path` owns it for corrections, which the map discovers by a glob.
    A set whose paths carry different names - the anchors document carries the dataset
    id - has no one name, and this function refuses it instead of picking one.
    """
    if set_name == "corrections":
        return correction_path("", "*").rsplit("/", 1)[-1]
    paths = document_paths(set_name)
    if not paths:
        raise ValueError(f"no document name for the set {set_name}")
    names = {path.rsplit("/", 1)[-1] for path in paths}
    if len(names) != 1:
        raise ValueError(f"the set {set_name} has no single document name: {sorted(names)}")
    return names.pop()


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


def identity_document(root) -> Path:
    """The identity index document of one root: the root, then the owner's relative path.

    The caller keeps its own spelling of the root, as it does with `correction_path`: a
    repository root joins the whole relative path (``<root>/out/identity/clusters.json``),
    and a store whose root already ends in ``out`` joins the file name, the way
    ``JsonStore._faces_path`` joins ``FACE_STORE``.
    """
    relative = IDENTITY_DOCUMENT.split("/")
    if Path(root).name == relative[0]:
        relative = relative[-2:]
    return Path(root).joinpath(*relative)


# The crop set the review page reads and writes, and the two documents that set holds.
# The folder name is the set name, so BALL_SETS above owns which crop sets exist.
CTX_DOCUMENT = "ctx.json"
META_DOCUMENT = "meta.json"


def crops_dir(set_name: str) -> str:
    """The folder of a crop set, relative to the repository root.

    The set name is the folder name under `out/`.  An unknown name is refused in the same
    words as the store layer refuses it.
    """
    if set_name not in BALL_SETS:
        raise ValueError(f"unknown ball set: {set_name}")
    return f"out/{set_name}"
