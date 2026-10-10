"""src/qa.py: the bounds check reads the canonical frame from its owner.

src/qa.py decides whether a projected ball centre lies on the table. It used to
keep a private box, ``H, W = 500, 1000``, which is smaller than the table. The
tool then reported a violation for correct data: the centre (635.0, 1270.0) and
the far corner (1269.0, 2539.0) both printed as "OUT of bounds", and the report
line named the canonical table.

The canonical frame has one owner, src/table_geometry.py (CANON_W = 1270 mm on
x, CANON_H = 2540 mm on y). The tool imports those two names again, so a change
of the frame reaches the check.

The cases below run src/qa.py as a child process, on a temporary file. A mock
would not exercise the import of the owner, and that import is the repair:
without it the child stops with ModuleNotFoundError.
"""
import ast
from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
QA = REPO / 'src' / 'qa.py'
GEOMETRY = REPO / 'src' / 'table_geometry.py'

#: The private box that the tool used before the repair.
OLD_WINDOW = '= 500, 1000'

#: The table centre, and the far corner of the closed canonical frame.
TABLE_POINTS = ([635.0, 1270.0], [1269.0, 2539.0])

#: The message that src/qa.py prints when it finds no ball outside the frame.
INSIDE_LINE = 'all projected balls inside canonical table bounds'


def runner_env():
    """The environment of the child: this repository first on PYTHONPATH."""
    import os
    return dict(os.environ, PYTHONPATH=str(REPO))


def run_qa(payload):
    """Run src/qa.py on ``payload``, as a child process, and return its stdout.

    The input goes to a temporary file, because the tool reads ``sys.argv[1]``.
    The run is the same entry point that a caller uses at the command line.
    """
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / 'results.json'
        path.write_text(json.dumps(payload), encoding='utf-8')
        done = subprocess.run([sys.executable, str(QA), str(path)],
                              cwd=REPO, env=runner_env(),
                              capture_output=True, text=True, timeout=120)
    if done.returncode != 0:
        raise AssertionError(f'src/qa.py exited {done.returncode}: {done.stderr[-2000:]}')
    return done.stdout


def owner_frame():
    """``(CANON_W, CANON_H)`` as src/table_geometry.py states them.

    The node is executed, so this reads the owner and not a second copy of the
    two numbers in this test file.
    """
    tree = ast.parse(GEOMETRY.read_text(encoding='utf-8'))
    wanted = {'CANON_W', 'CANON_H'}
    namespace = {}
    for node in tree.body:
        names = set()
        if isinstance(node, ast.Assign):
            names = {target.id for target in node.targets if isinstance(target, ast.Name)}
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names = {node.target.id}
        if names & wanted:
            exec(compile(ast.Module([node], []), str(GEOMETRY), 'exec'), namespace)
    missing = wanted - set(namespace)
    if missing:
        raise AssertionError(f'{GEOMETRY.name} no longer states {sorted(missing)}')
    return namespace['CANON_W'], namespace['CANON_H']


def imported_frame():
    """The two frame names that the child process gets from src.qa."""
    code = 'from src.qa import CANON_W, CANON_H; print(CANON_W, CANON_H)'
    done = subprocess.run([sys.executable, '-c', code],
                          cwd=REPO, env=runner_env(),
                          capture_output=True, text=True, timeout=120)
    if done.returncode != 0:
        raise AssertionError(f'the import failed: {done.stderr[-2000:]}')
    width, height = done.stdout.split()
    return int(width), int(height)


def assigned_names(path):
    """Every name that ``path`` assigns, with its line number.

    The walk covers the whole tree, so an assignment inside ``main()`` counts.
    The old private box sat on such a line, and a module-level walk missed it.
    """
    found = {}
    for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        else:
            continue
        for target in targets:
            for name in ast.walk(target):
                if isinstance(name, ast.Name):
                    found.setdefault(name.id, node.lineno)
    return found


class QaBoundsTests(unittest.TestCase):
    def test_the_table_centre_and_the_far_corner_are_inside(self):
        # Measured on the fixed tool: "inside=2" and no "OUT of bounds" line.
        # The old private box printed both rows as violations.
        payload = [{'t': 0.0,
                    'balls': [{'table': TABLE_POINTS[0], 'color': 'white', 'style': 'solid'},
                              {'table': TABLE_POINTS[1], 'color': 'red', 'style': 'solid'}],
                    'corners': [[0, 0], [10, 0], [10, 10], [0, 10]]}]
        out = run_qa(payload)
        self.assertIn('inside=2', out, out)
        self.assertIn(INSIDE_LINE, out, out)
        self.assertNotIn('OUT of bounds', out, out)
        # No violation means no count line. This holds the two lines together.
        self.assertNotIn('out-of-bounds', out, out)

    def test_the_tool_reads_the_frame_of_its_owner(self):
        # A second copy of the frame is the defect itself. The two runs below
        # read the owner file and the module, and they must name one pair.
        self.assertEqual(owner_frame(), imported_frame())

    def test_a_second_window_has_no_name_in_the_module(self):
        # The old line was ``H, W = 500, 1000`` inside ``main()``. A new line
        # under any of these names is a second window again, so the case counts
        # the names that the module assigns, at any depth.
        width, height = owner_frame()
        names = assigned_names(QA)
        clashes = sorted({'H', 'W', 'CANON_W', 'CANON_H', 'WIDTH', 'HEIGHT'} & set(names))
        where = ', '.join(f'{name} at line {names[name]}' for name in clashes)
        self.assertEqual(clashes, [],
                         f'src/qa.py assigns a frame name again ({where}); '
                         f'import CANON_W and CANON_H from src.table_geometry instead')
        self.assertEqual((width, height), (1270, 2540))

    def test_the_private_window_has_not_returned_to_the_source(self):
        # The scan names the file and the line of a literal window, whatever
        # quotes it. MAX_LINE is short: the numbers ARE the signature.
        hits = []
        for path in sorted((REPO / 'src').rglob('*.py')):
            for number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
                if OLD_WINDOW in line:
                    hits.append(f'{path.relative_to(REPO)}:{number}: {line.strip()}')
        self.assertEqual(hits, [], 'a literal frame window is back: ' + '; '.join(hits))


if __name__ == '__main__':
    unittest.main()
