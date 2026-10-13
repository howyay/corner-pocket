"""Every citation in a comment or a docstring names a line that holds text.

The round-49 walk found six tracked citations that a reader cannot follow.  Some
named an empty line, one named a separator, one named a closing bracket, and one
named a comment.  No case held the citations true.

One rule: a citation `path.ext:NN` must resolve to a file, and line NN of that
file must hold a letter or a digit.  The scan reads the comment and docstring
spans of the .py, .js and .css files of the repository.  It does not read string
literals, because a test writes a wrong citation on purpose to prove that a
guard catches it.

Out of scope: `deploy/` (a unit file must not cite a Python line at all, and
tests/test_unit_render.py holds that rule) and `docs/` (the ledgers record the
history of older rounds and cite bare file names on purpose).

A citation to a line that holds other text passes this rule.  The rule proves
that the reader finds a line, not that the line holds the named fact.  Two limits
follow from that sentence, and the round-50 walk measured both:

* a comment that names a symbol and no line number is outside the rule, because
  the rule reads a line number only.  `tests/ball_dense_events.py` cited the name
  `src/motion_scan.PERSON_SHARE_MAX`, and the Lead repaired that citation by hand;
* a line whose text contradicts the comment passes, because the rule reads the
  target line and not the sentence around the citation.

The second rule below closes that gap for one file.  `annotator/duration.js`
writes seven citations, and each one names a seam of another file.  The case
reads the sentence that carries a citation, and it states the claim: the named
line must hold the seam that the sentence names.  A number that moved fails.
"""

import ast
import io
import re
import tokenize
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Directories the scan skips: generated output, vendor trees, and the two
# directories the module docstring names as out of scope.
SKIP_PARTS = {
    'out', 'node_modules', '.venv', '.pm', '.git', '__pycache__', 'data',
    'deploy', 'docs', 'dist', 'build',
}

# A citation is a path with one of the three extensions, a colon and a number.
# The lookbehind refuses a citation inside a URL or a longer word.
CITATION = re.compile(r'(?<![\w/:.-])([A-Za-z0-9_./-]+\.(?:py|js|css)):(\d+)')

# The scan found 89 citations when the case was written.  The floor fails a scan
# that reads no file at all, which would make the rule below pass for free.
MIN_CITATIONS = 60

# The directories that hold the modules a citation may name with a bare name.
RESCUE_DIRS = ('', 'src', 'annotator', 'tests', 'db', 'scripts', 'tools')


def scanned_files():
    """The .py, .js and .css files of the repository, minus the skipped parts."""
    found = []
    for path in sorted(ROOT.rglob('*')):
        if path.is_dir() or path.suffix not in ('.py', '.js', '.css'):
            continue
        parts = path.relative_to(ROOT).parts[:-1]
        if any(part in SKIP_PARTS or part.startswith('.') for part in parts):
            continue
        found.append(path)
    return found


def python_span_lines(text):
    """The line numbers a .py file gives to its comments and its docstrings."""
    docstring_starts = set()
    try:
        tree = ast.parse(text)
    except SyntaxError:
        tree = None
    if tree is not None:
        for node in ast.walk(tree):
            body = getattr(node, 'body', None)
            if not body or not isinstance(node, (ast.Module, ast.ClassDef,
                                                 ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            first = body[0]
            if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
                    and isinstance(first.value.value, str)):
                docstring_starts.add(first.lineno)
    lines = []
    try:
        tokens = tokenize.generate_tokens(io.StringIO(text).readline)
        for token in tokens:
            if token.type == tokenize.COMMENT:
                lines.append(token.start[0])
            elif token.type == tokenize.STRING and token.start[0] in docstring_starts:
                lines.extend(range(token.start[0], (token.end[0] or token.start[0]) + 1))
    except (tokenize.TokenError, IndentationError):
        pass
    return lines


def javascript_span_lines(text):
    """The line numbers a .js or .css file gives to its comments."""
    lines = []
    in_block = False
    for number, line in enumerate(text.splitlines(), 1):
        if in_block:
            lines.append(number)
            if '*/' in line:
                in_block = False
            continue
        if '/*' in line:
            lines.append(number)
            if '*/' not in line.split('/*', 1)[1]:
                in_block = True
        if '//' in line:
            lines.append(number)
    return lines


def span_lines(path, text):
    """The lines that may hold a citation: comments and docstrings."""
    if path.suffix == '.py':
        return python_span_lines(text)
    return javascript_span_lines(text)


def resolve(name):
    """The file a citation names, or None.  A bare name reads the module dirs."""
    for base in RESCUE_DIRS:
        candidate = ROOT / base / name
        if candidate.is_file():
            return candidate
    return None


def holds_text(line):
    """True when the line holds a letter or a digit, so a reader finds a fact.

    A citation to a separator line, to a closing bracket, or to an empty line
    gives the reader nothing to read.  All three answer False here.
    """
    return any(char.isalnum() for char in line)


def read_text_or_none(path):
    """The text of a scanned file, or None when the file went away mid-scan.

    ``tests/test_ball_scale.py`` writes a plant module under ``src/`` and removes
    it in a ``finally`` block.  A scan that reaches the plant after the remove
    must not fail: the plant is not a citation of the repository.
    """
    try:
        return path.read_text(encoding='utf-8', errors='replace')
    except FileNotFoundError:
        return None


def citations_of(path):
    """Every citation the scan reads in one file."""
    text = read_text_or_none(path)
    if text is None:
        return []
    covered = set(span_lines(path, text))
    return [match for match in CITATION.finditer(text)
            if text[:match.start()].count('\n') + 1 in covered]


def wrong_citations_in(text, name, spans):
    """The rule applied to one file's text, so the cases below can bite."""
    covered = set(spans(text))
    bad = []
    for match in CITATION.finditer(text):
        line = text[:match.start()].count('\n') + 1
        if line not in covered:
            continue
        target = resolve(match.group(1))
        number = int(match.group(2))
        if target is None:
            bad.append('%s:%d -> %s (no such file)' % (name, line, match.group(0)))
            continue
        lines = target.read_text(encoding='utf-8', errors='replace').splitlines()
        if number < 1 or number > len(lines):
            bad.append('%s:%d -> %s (the file holds %d lines)'
                       % (name, line, match.group(0), len(lines)))
        elif not holds_text(lines[number - 1]):
            bad.append('%s:%d -> %s (the line holds no text)'
                       % (name, line, match.group(0)))
    return bad


def wrong_citations():
    """Every citation of the repository that a reader cannot follow."""
    bad = []
    for path in scanned_files():
        text = read_text_or_none(path)
        if text is None:
            continue
        bad.extend(wrong_citations_in(text, str(path.relative_to(ROOT)),
                                      lambda body, p=path: span_lines(p, body)))
    return bad


class CitationScanTests(unittest.TestCase):
    """The scan reads citations, and the rule refuses a citation a reader loses."""

    def test_the_scan_reads_the_citations_of_the_repository(self):
        total = sum(len(citations_of(path)) for path in scanned_files())
        self.assertGreaterEqual(total, MIN_CITATIONS,
                                'the scan must read the citations of the repository')

    def test_a_citation_to_a_missing_file_is_refused(self):
        text = '"""See no_such_module.py:3 for the rule."""\n'
        self.assertEqual(wrong_citations_in(text, 'probe.py', python_span_lines),
                         ['probe.py:1 -> no_such_module.py:3 (no such file)'])

    def test_a_file_that_goes_away_mid_scan_is_skipped(self):
        """A plant that a test removes before the read is not a citation."""
        path = ROOT / 'tests' / 'probe_vanished_citation.py'
        path.write_text('"""See tests/test_citation_lines.py:1."""\n', encoding='utf-8')
        path.unlink()
        self.assertIsNone(read_text_or_none(path))

    def test_a_citation_past_the_end_of_the_file_is_refused(self):
        text = '"""See tests/test_citation_lines.py:99999 for the rule."""\n'
        answer = wrong_citations_in(text, 'probe.py', python_span_lines)
        self.assertEqual(len(answer), 1, answer)
        self.assertIn('the file holds', answer[0])

    def test_a_citation_to_a_line_without_text_is_refused(self):
        target = ROOT / 'tests' / 'test_citation_lines.py'
        lines = target.read_text(encoding='utf-8').splitlines()
        blank = next(number for number, line in enumerate(lines, 1) if not line.strip())
        text = '"""See tests/test_citation_lines.py:%d for the rule."""\n' % blank
        self.assertEqual(wrong_citations_in(text, 'probe.py', python_span_lines),
                         ['probe.py:1 -> tests/test_citation_lines.py:%d '
                          '(the line holds no text)' % blank])

    def test_a_separator_line_holds_no_text(self):
        self.assertFalse(holds_text('   // ' + '-' * 60))
        self.assertFalse(holds_text('}'))
        self.assertTrue(holds_text('// the frame tier'))

    def test_a_citation_outside_a_comment_is_not_read(self):
        text = "PROBE = 'no_such_module.py:3'\n"
        self.assertEqual(wrong_citations_in(text, 'probe.py', python_span_lines), [])

    def test_no_citation_names_a_line_without_text(self):
        self.assertEqual(wrong_citations(), [],
                         'every citation must name a line that holds text')


# The duration owner names the seam of each citation.  The scan above reads the
# target line only, so a stale number passes it.  The case below reads the
# sentence of the citation and states the claim that the sentence makes.
DURATION = ROOT / 'annotator' / 'duration.js'

# A citation, or the bare `:NN` form that continues the file named before it.
CITATION_OR_BARE = re.compile(
    r'(?:(?<![\w/:.-])([A-Za-z0-9_./-]+\.(?:py|js|css)))?:(\d+)')

# The words a sentence uses for a seam, and the text that the named line must
# hold.  Every pattern of a row must match the named line.
SEAMS = (
    ('window.Duration.hms', (r'window\.Duration\.hms',)),
    ('builds at_s', (r"params\[key \+ '_s'\] =",)),
    ('`\\d+` anchors', (r'\\d\+:',)),
    ('timestamp_seconds', (r'timestamp_seconds\s*=\s*value\s*/', r'fps')),
    ('guards its own time formatter', (r'Number\.isFinite', r'Math\.max\(0')),
)

# The greatest distance a claim phrase may sit from its citation.  A sentence
# that names no seam within this distance fails, so a rewritten sentence cannot
# pass the case.
NEAR = 200


def duration_comment_lines(text):
    """The (line number, text, offset) of each comment line of the owner."""
    covered = set(javascript_span_lines(text))
    rows, at = [], 0
    for number, line in enumerate(text.splitlines(), 1):
        if number not in covered:
            continue
        rows.append((number, line, at))
        at += len(line) + 1
    return rows


def duration_citations(text):
    """Each citation of the owner: (line, path, number, offset).

    A bare `:NN` continues the file that the sentence named before it.  A number
    below 1 is not a citation, because the rule text holds `0:00:00` twice.
    """
    found, path = [], None
    for number, line, offset in duration_comment_lines(text):
        for match in CITATION_OR_BARE.finditer(line):
            name, cited = match.group(1), int(match.group(2))
            if name is None:
                if path is None or cited < 1:
                    continue
                name = path
            else:
                path = name
            found.append((number, name, cited, offset + match.start()))
    return found


def seam_of(block, offset):
    """The nearest claim phrase of the comment, with its name and its patterns.

    The nearest phrase wins, because one sentence of the owner names two seams:
    the line that builds at_s, and the anchors that hold its digits.
    """
    best = None
    for words, patterns in SEAMS:
        at = block.find(words)
        while at != -1:
            gap = abs(offset - at)
            if best is None or gap < best[0]:
                best = (gap, words, patterns)
            at = block.find(words, at + 1)
    return best


def duration_bad_citations(text):
    """Each citation of the owner that does not name the seam of its sentence."""
    block = '\n'.join(line for _, line, _ in duration_comment_lines(text))
    bad = []
    for line, name, number, offset in duration_citations(text):
        target = resolve(name)
        if target is None:
            bad.append('%s:%d -> %s (no such file)' % (DURATION.name, line, name))
            continue
        seam = seam_of(block, offset)
        if seam is None or seam[0] > NEAR:
            bad.append('%s:%d -> %s:%d (no claim phrase near the citation)'
                       % (DURATION.name, line, name, number))
            continue
        lines = target.read_text(encoding='utf-8', errors='replace').splitlines()
        if number < 1 or number > len(lines):
            bad.append('%s:%d -> %s:%d (the file holds %d lines)'
                       % (DURATION.name, line, name, number, len(lines)))
            continue
        body = lines[number - 1]
        if any(not re.search(pattern, body) for pattern in seam[2]):
            bad.append('%s:%d -> %s:%d (the sentence names %s, the line reads %r)'
                       % (DURATION.name, line, name, number, seam[1], body.strip()))
    return bad


class DurationSeamTests(unittest.TestCase):
    """Each citation of the duration owner names the line that holds its seam."""

    def test_the_scan_reads_every_duration_citation(self):
        found = duration_citations(DURATION.read_text(encoding='utf-8'))
        self.assertEqual(
            len(found), 7,
            'the owner writes seven citations, and the case reads %d: %r' % (len(found), found))

    def test_every_duration_citation_names_its_seam(self):
        self.assertEqual(duration_bad_citations(DURATION.read_text(encoding='utf-8')), [],
                         'every citation must name the line that holds its seam')

    def test_a_moved_duration_citation_is_refused(self):
        text = DURATION.read_text(encoding='utf-8')
        moved = re.sub(r'(annotator/app\.js:)\d+', r'\g<1>1', text, count=1)
        self.assertNotEqual(moved, text, 'the owner must cite annotator/app.js with a number')
        bad = duration_bad_citations(moved)
        self.assertEqual(len(bad), 1, bad)
        self.assertIn('annotator/app.js:1 ', bad[0])


if __name__ == '__main__':
    unittest.main()
