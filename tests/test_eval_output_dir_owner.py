"""The eval output directory has one home, and one case reads both tools.

Two shipped tools write one directory, and no case read both of them:

  * ``src/eval_table_detect.py`` holds the one spelling of the path.  The constant
    ``OUT_DIR`` stands below the comment that names this module, and the evaluator
    writes its report there.
  * ``src/check_app_quad.py`` reads ``OUT_DIR`` from that module.  Until round 105
    it built its own ``OUT`` from ``Path(__file__).resolve().parent.parent``, so a
    moved output directory left one tool writing where the other one does not
    read.

The walk of round 105 read the pair as the ``OUT`` literal of the app quad tool
and the ``OUT_DIR`` of the evaluator.  Both numbers moved with the repair, so
this module locates the two sites by the name and reports them as ``path:line``.

This module reads the shipped tree as text and as objects:

  * the name ``table-detect-eval`` stands once under ``src/``, and a case counts
    the sites, so a second spelling reddens here;
  * the reader must bind the owner's name and hold no spelling of the path;
  * the two modules must answer one object, not two equal paths, so an ``is``
    case holds the reader to the owner's value;
  * a planted second spelling is reported as ``path:line: <line text>``, so a
    failure names the site to open.

Run: ``./scripts/pool-test.sh python test_eval_output_dir_owner``
"""
from pathlib import Path
import ast
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

#: The one home of the directory name.
HOME_SITE = 'src/eval_table_detect.py'

#: The name of that home.
HOME_NAME = 'OUT_DIR'

#: The reader that must bind the name and hold no spelling of the path.
READER_SITE = 'src/check_app_quad.py'

#: The one name of the directory, and the directory itself.
TOKEN = 'table-detect-eval'
DIRECTORY = ROOT / 'out' / TOKEN

#: The measured size of every scan, read in the shipped tree on 2026-10-13.  A
#: second spelling, a dropped binding or a shortened walk changes one of these
#: numbers, and the last case of this module reddens in the same run.
TOKEN_FILE_COUNT = 1
TOKEN_SITE_COUNT = 1
READER_BINDING_COUNT = 1


def lines_of(path):
    """`(number, line)` for every line of one file, read as UTF-8."""
    return list(enumerate(path.read_text(encoding='utf-8').splitlines(), start=1))


def display(path):
    """One path as a repository-relative name, or as itself when it is outside."""
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def site(path, number):
    """One site of one file, as ``path:line``."""
    return f'{display(path)}:{number}'


def report(path, number, why):
    """One offender, as ``path:line: <line text>``, with the reason below it."""
    text = lines_of(path)[number - 1][1]
    return f'{site(path, number)}: {text.strip()}\n  {why}'


def python_files():
    """Every ``src/*.py`` file of this checkout, sorted by path."""
    return sorted((ROOT / 'src').glob('*.py'))


def token_sites(path):
    """`(number, line)` for every line of one file that names the directory."""
    return [(number, line) for number, line in lines_of(path) if TOKEN in line]


def definition_line(path, name):
    """`(number, line)` of the module-level statement that binds ``name``, or None."""
    hits = [(number, line) for number, line in lines_of(path)
            if line.strip().startswith(f'{name} =')]
    return hits[0] if len(hits) == 1 else None


def reader_binding(path, module, name):
    """`(number, line)` of the import that binds ``name`` from ``module``, or None."""
    source = path.read_text(encoding='utf-8')
    tree = ast.parse(source, filename=display(path))
    lines = source.splitlines()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == module:
            for alias in node.names:
                if alias.name == name:
                    return node.lineno, lines[node.lineno - 1]
    return None


class EvalOutputDirOwnerTest(unittest.TestCase):
    def test_the_directory_name_stands_once_under_src(self):
        """One file under ``src/`` names the directory, and it names it once.

        The reader holds no list of the files it expects to pass.  It walks
        ``src/*.py`` and counts the files and the sites that hold the name, so a
        second spelling reddens here with the site to open.
        """
        holders = {path: sites for path, sites in
                   ((path, token_sites(path)) for path in python_files()) if sites}
        offenders = [report(path, number,
                            f'the directory name "{TOKEN}" has one home in {HOME_SITE}, and '
                            f'{site(path, number)} spells it a second time')
                     for path, sites in holders.items() if display(path) != HOME_SITE
                     for number, _ in sites]
        self.assertEqual(
            [], offenders,
            'a second file names the eval output directory, so one move of the '
            'directory would leave one tool behind:\n' + '\n'.join(offenders))
        self.assertEqual(
            TOKEN_FILE_COUNT, len(holders),
            f'{len(holders)} files under src/ name "{TOKEN}", not {TOKEN_FILE_COUNT}: '
            + ', '.join(sorted(display(path) for path in holders)))
        sites = holders.get(ROOT / HOME_SITE, [])
        self.assertEqual(
            TOKEN_SITE_COUNT, len(sites),
            f'{HOME_SITE} names "{TOKEN}" {len(sites)} times, not {TOKEN_SITE_COUNT}:\n'
            + '\n'.join(f'{site(ROOT / HOME_SITE, number)}: {line.strip()}'
                        for number, line in sites))

    def test_the_owner_answers_the_directory_the_two_tools_write(self):
        """``OUT_DIR`` of the owner is the directory, from the repository root.

        The walk of round 105 read this value as ``out/table-detect-eval``.  A
        value that answers anything else sends the evaluator's report somewhere
        the checker does not read.
        """
        from src import eval_table_detect
        home = ROOT / HOME_SITE
        bound = definition_line(home, HOME_NAME)
        why = f'{HOME_NAME} answers {eval_table_detect.OUT_DIR}, not {DIRECTORY}'
        if bound is None:
            self.fail(f'{HOME_SITE} binds {HOME_NAME} on no single line, so this reader '
                      'cannot name the site that drifted')
        number, line = bound
        self.assertEqual(DIRECTORY, eval_table_detect.OUT_DIR, report(home, number, why))
        self.assertTrue(eval_table_detect.OUT_DIR.is_absolute(),
                        report(home, number, f'{HOME_NAME} is not an absolute path, so the '
                              'two tools resolve it from their working directory'))

    def test_the_reader_binds_the_owner_and_holds_no_spelling(self):
        """``src/check_app_quad.py`` reads the name and spells the path nowhere.

        The binding is the one import that makes the checker and the evaluator
        read one directory.  A reader that stops binding the name answers the
        directory from somewhere else, and a reader that spells the path a second
        time is a copy that no case held.
        """
        reader = ROOT / READER_SITE
        bound = reader_binding(reader, 'src.eval_table_detect', HOME_NAME)
        self.assertEqual(
            READER_BINDING_COUNT, 0 if bound is None else 1,
            f'{READER_SITE} no longer binds {HOME_NAME} from src.eval_table_detect, so the '
            'checker and the evaluator may write two directories')
        offenders = [report(reader, number,
                            f'the directory name has one home in {HOME_SITE}; '
                            f'{READER_SITE} must read {HOME_NAME} instead of spelling it')
                     for number, _ in token_sites(reader)]
        self.assertEqual(
            [], offenders,
            'the reader spells the eval output directory a second time:\n' + '\n'.join(offenders))
        self.assertIsNotNone(bound, f'{READER_SITE} binds {HOME_NAME} on no line')

    def test_the_two_tools_answer_one_object(self):
        """The checker and the evaluator read the same ``Path`` object.

        Two equal paths are two spellings that agree today.  One object is one
        home: the checker imports the name, so an edit of the owner moves both.
        """
        from src import check_app_quad, eval_table_detect
        self.assertIs(
            eval_table_detect.OUT_DIR, check_app_quad.OUT_DIR,
            f'{READER_SITE} answers its own {HOME_NAME} object, so the two tools no longer '
            f'read the one home in {HOME_SITE}')

    def test_a_planted_second_spelling_is_reported_with_its_file_and_line(self):
        """The reporter of this module names the file, the line and the text.

        This case writes a small script to a temporary file.  One of its lines
        spells the directory the way ``src/check_app_quad.py`` spelled it before
        round 105, and the reporter must name that line as ``path:line: <line
        text>``.
        """
        planted = ('from pathlib import Path\n'
                   "OUT = Path(__file__).resolve().parent.parent / 'out' / 'table-detect-eval'\n")
        holder = tempfile.TemporaryDirectory(prefix='eval-output-dir-owner-')
        self.addCleanup(holder.cleanup)
        script = Path(holder.name) / 'check_app_quad.py'
        script.write_text(planted, encoding='utf-8')
        sites = token_sites(script)
        self.assertEqual([(2, planted.splitlines()[1])], sites,
                         'the reader of the directory name dropped a planted spelling')
        number, _ = sites[0]
        offender = report(script, number,
                          f'the directory name has one home in {HOME_SITE}; '
                          f'{display(script)} spells it a second time')
        self.assertIn(f'{script}:2:', offender)
        self.assertIn("'out' / 'table-detect-eval'", offender)

    def test_the_scan_of_each_place_keeps_its_measured_size(self):
        """The scans keep the size this module measured, so none passes empty.

        A reader that finds no site answers an empty list, and an empty list
        passes the cases above.  The numbers are the counts of the shipped tree
        on 2026-10-13.
        """
        measured = {
            'files that name the directory': (
                len([path for path in python_files() if token_sites(path)]), TOKEN_FILE_COUNT),
            'sites of the home': (len(token_sites(ROOT / HOME_SITE)), TOKEN_SITE_COUNT),
            'binding of the reader': (
                0 if reader_binding(ROOT / READER_SITE, 'src.eval_table_detect', HOME_NAME) is None
                else 1, READER_BINDING_COUNT),
        }
        for scan, (found, wanted) in measured.items():
            with self.subTest(scan=scan):
                self.assertEqual(
                    wanted, found,
                    f'the scan "{scan}" found {found} sites, not {wanted}.  The number is the '
                    'count this module measured in the shipped tree.  A second spelling, a '
                    'dropped binding or a shortened walk changes it, and every other case of '
                    'this module then reads less than the pair it holds.')


if __name__ == '__main__':
    unittest.main()
