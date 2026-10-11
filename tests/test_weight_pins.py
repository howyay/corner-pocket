"""The weight pin owns the OSNet path, and every loader reads the owner.

`src/weight_pins.py` states three facts of each downloaded weight: the path under
the repository root, the URL and the SHA-256.  `scripts/fetch_weights.py` reads
that table.  Six loaders under `src/` open the OSNet file.  A loader that spells
the path again holds a second copy of it, so the pin and the loader can name two
files, and nothing tells a reader that the copy exists.

Measured on 2026-10-11 with an ast walk of the string literals under `src/`: the
name of the OSNet weight stood in seven of them, one in each of the six loaders
and one in the pin.  Round 60 gave the path one spelling, in `src/weight_pins.py`,
and every loader reads that name.

Five rules, one class each:

* one string literal under `src/` names the OSNet file, and it is the pin;
* one string literal under `src/` names the detector file, and it is the pin;
* each of the six loaders imports `OSNET` from `src.weight_pins`, builds its path
  from that name, and holds no copy of the text.  The eight sites that named the
  detector file by hand read `weight_pins.YOLO` for the same reason;
* the environment name `POOL_DATABASE_URL` has one owner, `src/db.py`.  That module
  and `src/store.py` decide one backend together, so their two copies became one
  import, and `tests/test_store.py` fails when the refusal message and the variable
  part;
* the SHA-256 and the size of the pin describe the file on disk.  Measured in
  this checkout: the file is present with 9336983 bytes and SHA-256
  cf55163d78fc44c62c82f85ab62d39f10438679b5abe8c698ae08cfa84aa6e18, and both
  numbers are the pin.  No case here calls `self.skipTest`, and no case reads
  `data_guard`: a checkout that never downloaded the weight holds the reporter to
  the report it makes;
* a planted copy of the weight is reported.

Run: ``./scripts/pool-test.sh python test_weight_pins``
"""
import ast
import hashlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src import weight_pins  # noqa: E402

SRC = ROOT / "src"
#: The file that owns the pin table, and the only file that may spell the path.
OWNER = SRC / "weight_pins.py"
#: Vendored upstream code, not ours to change.  It is the exclusion that
#: `tests/test_duplicate_bodies.py` already uses, so one rule reads one tree.
VENDORED = SRC / "sam3"

#: The file name of the OSNet weight, read from the pin itself.
WEIGHT_NAME = Path(weight_pins.OSNET).name
#: The file name of the detector weight, read from the pin itself.  The pin
#: table owns two paths, so both names need one home and one guard.
DETECTOR_NAME = Path(weight_pins.YOLO).name
#: The pinned file, as the pin names it under the repository root.
WEIGHT_FILE = ROOT / weight_pins.OSNET
#: (path, url, SHA-256, size) of the OSNet weight, read from the pin.
PIN_SHA = weight_pins.WEIGHTS_BY_PATH[weight_pins.OSNET][2]
PIN_SIZE = weight_pins.WEIGHTS_BY_PATH[weight_pins.OSNET][3]

#: The six loaders that open the OSNet weight.  Each one reads `weight_pins`.
LOADERS = (
    "person_pipeline.py",
    "pid_associate.py",
    "pid_osnet.py",
    "pid_osnet_tight.py",
    "pid_osnet_tracks.py",
    "pid_seed_rebuild.py",
)


def _sources():
    """Every python source of `src/` that this repository owns, in a stable order."""
    return sorted(path for path in SRC.rglob("*.py") if VENDORED not in path.parents)


def _tree(path):
    """The syntax tree of one source file."""
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _names_a_file(text, name):
    """True when `text` is a file path whose file name is `name`.

    The pin holds the path under the repository root and a loader holds the bare file
    name, so both are read.  The pin's URL is not: a URL names a location on a server,
    not a file of this tree."""
    path = Path(text)
    if path.name != name:
        return False
    return all(part.isidentifier() for part in path.parents[0].parts)


def _name_sites(path, name):
    """The (line, text) of every string literal of `path` that names the file `name`."""
    return [(node.lineno, node.value) for node in ast.walk(_tree(path))
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
            and _names_a_file(node.value, name)]


def _imports_osnet(tree):
    """True when the tree reads `OSNET` from `src.weight_pins`."""
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "src.weight_pins":
            if any(alias.name == "OSNET" for alias in node.names):
                return True
    return False


def _builds_a_path_from(tree, identifier):
    """True when the name `identifier` is an operand of a path join or of a `/`."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and ast.unparse(node.func) == "os.path.join":
            holder = node
        elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            holder = node
        else:
            continue
        if any(isinstance(inner, ast.Name) and inner.id == identifier
               for inner in ast.walk(holder)):
            return True
    return False


def _exact_literal_sites(path, name):
    """The (line, text) of every string literal of `path` that is exactly `name`."""
    return [(node.lineno, node.value) for node in ast.walk(_tree(path))
            if isinstance(node, ast.Constant) and node.value == name]


def _text(node):
    """The text of a string literal, cut for a failure message."""
    return node[:60] if isinstance(node, str) else str(node)


def _reads_the_module(tree):
    """True when the tree reads the module `src.weight_pins` itself."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(alias.name == "src.weight_pins" for alias in node.names):
                return True
        elif isinstance(node, ast.ImportFrom) and node.module == "src":
            if any(alias.name == "weight_pins" for alias in node.names):
                return True
    return False


def _uses_the_module_name(tree, attribute):
    """True when the tree holds `weight_pins.<attribute>` in an expression.

    The import line alone is not a use: a loader that imports the owner and keeps
    its own copy of the text is the shape this rule forbids."""
    for node in ast.walk(tree):
        if (isinstance(node, ast.Attribute) and node.attr == attribute
                and isinstance(node.value, ast.Name) and node.value.id == "weight_pins"):
            return True
    return False


def _runs(code):
    """Run `code` in the environment of this test run, from the repository root."""
    return subprocess.run([sys.executable, "-c", code], cwd=ROOT,
                          capture_output=True, text=True, timeout=300)


def _sha256(path):
    """The SHA-256 of the bytes of one file, as 64 hexadecimal characters."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _mismatch(path):
    """Why `path` does not hold the pinned bytes, or None when it does."""
    if not path.is_file():
        return (f"{path} does not exist, and the pin names a file of {PIN_SIZE} bytes")
    size = path.stat().st_size
    digest = _sha256(path)
    if size == PIN_SIZE and digest == PIN_SHA:
        return None
    return (f"{path} holds {size} bytes with SHA-256 {digest}; "
            f"the pin states {PIN_SIZE} bytes with SHA-256 {PIN_SHA}")


def _flip_one_byte(path):
    """Change the first byte of a file, and keep its size."""
    with path.open("r+b") as handle:
        first = handle.read(1)
        handle.seek(0)
        handle.write(bytes([first[0] ^ 0xFF]))


class OneSpellingTest(unittest.TestCase):
    def _assert_one_home(self, name, value):
        """`name` stands in one string literal under src/, and that literal is the pin."""
        sites = [(path.relative_to(ROOT), line, text)
                 for path in _sources() for line, text in _name_sites(path, name)]
        found = ", ".join(f"{path}:{line} ({_text(text)})" for path, line, text in sites) or "none"
        self.assertEqual(
            len(sites), 1,
            f"the name {name} stands in {len(sites)} string literals under src/: "
            f"{found}. {OWNER.relative_to(ROOT)} owns the path, so every other file reads "
            f"weight_pins.OSNET or weight_pins.YOLO and holds no copy of the text.")
        self.assertEqual(
            sites[0][0], OWNER.relative_to(ROOT),
            f"the one literal that names {name} is in {sites[0][0]}, and "
            f"{OWNER.relative_to(ROOT)} must own it.")
        self.assertEqual(
            sites[0][2], value,
            f"the literal in {sites[0][0]} holds {sites[0][2]!r}, and the pin states "
            f"{value!r}.")

    def test_the_weight_name_stands_once_under_src(self):
        """The path has one home, so a second copy of the text fails this case."""
        self._assert_one_home(WEIGHT_NAME, weight_pins.OSNET)

    def test_the_detector_name_stands_once_under_src(self):
        """The pin table owns two paths, so the detector name has one home too."""
        self._assert_one_home(DETECTOR_NAME, weight_pins.YOLO)

    def test_the_two_names_have_one_home_each(self):
        """Each name home is inside the owner, and the two names differ."""
        self.assertNotEqual(
            weight_pins.YOLO, weight_pins.OSNET,
            "the pin table gives the detector and the OSNet weight one path, so one "
            "file would be loaded as two models.")
        for name in (WEIGHT_NAME, DETECTOR_NAME):
            homes = [path.relative_to(ROOT) for path in _sources()
                     if _name_sites(path, name)]
            self.assertEqual(
                homes, [OWNER.relative_to(ROOT)],
                f"the name {name} has {len(homes)} home(s) under src/: {homes}. The pin "
                f"table owns each name, and no other file may hold it.")


class DetectorLoaderTest(unittest.TestCase):
    """The eight files that spelled the detector name read the owner, and hold no copy."""

    NAMED = (
        "person_pipeline.py",
        "pid_associate.py",
        "pid_shooter.py",
        "pid_shooter2.py",
        "yolo_track.py",
        "info_complete_scan.py",
        "frame_inference.py",
        "eval_faces.py",
    )

    def _assert_reads_the_pin(self, name):
        path = SRC / name
        tree = _tree(path)
        self.assertTrue(
            _reads_the_module(tree),
            f"{name} does not read src.weight_pins, so it can name the detector file of "
            f"its own. It must import weight_pins from the pin table.")
        self.assertTrue(
            _uses_the_module_name(tree, "YOLO"),
            f"{name} imports the pin table and never reads weight_pins.YOLO, so it can "
            f"hold its own copy of the detector path.")
        sites = _name_sites(path, DETECTOR_NAME)
        self.assertEqual(
            sites, [],
            f"{name} spells the weight name {DETECTOR_NAME} on line "
            f"{sites[0][0] if sites else 0}, so the file and the pin can name two files.")

    def test_the_eight_sites_read_the_owner(self):
        for name in self.NAMED:
            with self.subTest(module=name):
                self._assert_reads_the_pin(name)


class LoaderTest(unittest.TestCase):
    """One case per loader: it reads the pin table, and it holds no copy."""

    def _assert_reads_the_owner(self, name):
        path = SRC / name
        tree = _tree(path)
        self.assertTrue(
            _imports_osnet(tree),
            f"{name} does not read OSNET from src.weight_pins, so it can name a file of "
            f"its own. It must import the name from the pin table.")
        self.assertTrue(
            _builds_a_path_from(tree, "OSNET"),
            f"{name} imports OSNET and does not build its weight path from the name. "
            f"The loader must join the repository root with weight_pins.OSNET.")
        sites = _name_sites(path, WEIGHT_NAME)
        self.assertEqual(
            sites, [],
            f"{name} spells the weight name {WEIGHT_NAME} on line "
            f"{sites[0][0] if sites else 0}, so the loader and the pin can name two files.")

    def test_person_pipeline_reads_the_owner(self):
        self._assert_reads_the_owner("person_pipeline.py")

    def test_pid_associate_reads_the_owner(self):
        self._assert_reads_the_owner("pid_associate.py")

    def test_pid_osnet_reads_the_owner(self):
        self._assert_reads_the_owner("pid_osnet.py")

    def test_pid_osnet_tight_reads_the_owner(self):
        self._assert_reads_the_owner("pid_osnet_tight.py")

    def test_pid_osnet_tracks_reads_the_owner(self):
        self._assert_reads_the_owner("pid_osnet_tracks.py")

    def test_pid_seed_rebuild_reads_the_owner(self):
        self._assert_reads_the_owner("pid_seed_rebuild.py")


class PinBytesTest(unittest.TestCase):
    def test_the_pin_describes_the_file_on_disk(self):
        """The recorded SHA-256 and size are the bytes that a loader opens."""
        present = WEIGHT_FILE.is_file()
        report = _mismatch(WEIGHT_FILE)
        if present:
            self.assertIsNone(
                report,
                f"the file on disk does not hold the pinned bytes: {report}")
        else:
            self.assertIsNotNone(
                report,
                f"{WEIGHT_FILE} is absent and the reporter stays silent, so the pin "
                f"table cannot be held to any file in this checkout.")
            self.assertIn(
                str(WEIGHT_FILE), report,
                f"the report does not name the missing file: {report}")

    def test_a_planted_copy_is_reported(self):
        """A copy that differs from the pin is reported, and a faithful one is not."""
        with tempfile.TemporaryDirectory(prefix="weight_pins_") as tmp:
            planted = Path(tmp) / WEIGHT_NAME
            if WEIGHT_FILE.is_file():
                shutil.copyfile(WEIGHT_FILE, planted)
                self.assertIsNone(
                    _mismatch(planted),
                    f"a faithful copy of the weight at {planted} failed the pin check")
                _flip_one_byte(planted)
            else:
                planted.write_bytes(b"a planted file that is not the pinned weight")
            report = _mismatch(planted)
            self.assertIsNotNone(
                report,
                f"the planted copy at {planted} passed the pin check with "
                f"{PIN_SIZE} bytes and {PIN_SHA}")
            self.assertIn(
                str(planted), report,
                f"the report does not name the planted copy: {report}")


class OneEnvironmentNameTest(unittest.TestCase):
    """The database variable has one home, and both readers ask that home."""

    def test_the_two_modules_read_one_name(self):
        from src import db, store
        self.assertIs(
            db.ENV, store.ENV,
            f"src/db.py holds ENV = {db.ENV!r} and src/store.py holds ENV = {store.ENV!r}, "
            f"so a rename of one leaves the other silent about the live club.")
        code = ("import os\n"
                "from src import db, store\n"
                "os.environ['POOL_DATABASE_URL'] = 'postgresql://u@127.0.0.1:1/x'\n"
                "print(db.ENV == store.ENV == 'POOL_DATABASE_URL'\n"
                "      and os.environ.get(db.ENV) == os.environ.get(store.ENV))\n")
        run = _runs(code)
        self.assertEqual(
            run.returncode, 0,
            f"a fresh interpreter that imports both modules failed: {run.stderr[-1500:]}")
        self.assertEqual(
            run.stdout.strip().splitlines()[-1:], ["True"],
            "the two modules do not read one environment name, so open_store can miss "
            "the variable that src/db.py connects with.")


if __name__ == "__main__":
    unittest.main()
