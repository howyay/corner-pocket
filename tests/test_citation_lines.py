"""Every citation in a comment or a docstring names a line that holds a fact.

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
that the reader finds a line, not that the line holds the named fact.
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


def citations_of(path):
    """Every citation the scan reads in one file."""
    text = path.read_text(encoding='utf-8', errors='replace')
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
        text = path.read_text(encoding='utf-8', errors='replace')
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


if __name__ == '__main__':
    unittest.main()
