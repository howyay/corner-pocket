"""Hold each SQL word domain to the Python literals that repeat it.

A migration spells a word domain in a CHECK constraint, for example
``CHECK (format IN ('singles','doubles'))``.  Python code repeats the same values as a
literal collection.  SQL cannot import Python, so the two spellings are two copies of one
list.  Round 48 measured the cost: no test compared a pair, so the two copies could
disagree with no failure.

This module reads the SQL text and the Python text.  It finds each site by its content.
It does not pin a line number, because a line number drifts.

Round 48 measured the tree.  ``db/migrations/0002_user_data.sql`` holds 13 ``IN (...)``
rules, and ``db/migrations/0004_imported_datasets.sql`` holds 3 more.  The migrations
spell 11 distinct word domains:

* this module binds 6 of them, one pair each (``PAIRS``);
* two other test modules already bind one domain each (``BOUND_ELSEWHERE``);
* three have no Python copy of this shape (``NO_PYTHON_COPY`` and ``UNBOUND``).

``identity_clusters.body_dim`` holds ``CHECK (body_dim IN (128))``.  That rule holds one
number, not a word, so this module does not read it.

The completeness case fails when a SQL domain value list appears as a Python literal
collection that no record of this module names.  The scan reads the shipped packages only
(``SHIPPED``).  A test file states an expectation, so it is not a copy inside the
application.
"""

from __future__ import annotations

import re
import unittest
from dataclasses import dataclass
from pathlib import Path

# The crop-set record below reads its values from the owner tuple.  A literal list here
# would be a second spelling of the vocabulary, and tests/test_store_files.py refuses
# that.  The import also makes this module compare the owner with the SQL text.
from src.store_files import BALL_SETS

# The event_verdicts pair reads the service constant, so the migration and the validator
# cannot drift apart.  annotator/app.js owns the same three words in javascript, and
# tests/test_console_vocabulary.py holds the console and the service together.  The import
# is also the reason no literal list of the three words stands in this module: a literal
# here would be a second spelling of the vocabulary.
from annotator.unified_server import VERDICT_WORDS

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / 'db' / 'migrations'
#: The shipped packages.  A second copy inside the application is a defect.  tests/ is not
#: here: a test states an expectation.  tools/ and scripts/ ship, so they are here.
SHIPPED = ('annotator', 'src', 'tools', 'scripts')

#: A bracketed run with no inner bracket: a tuple, a list, a set, or a call.
COLLECTION = re.compile(r'[\(\[]([^()\[\]]*)[\)\]]')
#: One quoted string.  The two groups are the single-quoted and the double-quoted form.
STRING = re.compile(r"'([^'\n]*)'|\"([^\"\n]*)\"")
#: A collection body that holds strings and commas only.  This is a value list.
VALUE_LIST = re.compile(
    r"\s*(?:'[^'\n]*'|\"[^\"\n]*\")(?:\s*,\s*(?:'[^'\n]*'|\"[^\"\n]*\"))*\s*,?\s*")
#: The first line of one table.
TABLE = re.compile(r'^CREATE TABLE (\w+) \(', re.MULTILINE)
#: One ``CHECK (column IN (values))`` rule.  The values stop at the first closing bracket.
CHECK_IN = re.compile(r'CHECK \((\w+) IN \(([^)]*)\)')
#: One ``IN (values)`` list, in a CHECK or in a function body.
IN_LIST = re.compile(r'IN \(([^)]*)\)')

_SOURCES: dict = {}


def source(relative):
    """The text of one repository file, read once per run."""
    if relative not in _SOURCES:
        _SOURCES[relative] = (ROOT / relative).read_text(encoding='utf-8')
    return _SOURCES[relative]


def strings_in(text):
    """The string values of one text, in order.  An empty string is a value."""
    return tuple(first or second for first, second in STRING.findall(text))


def collections_in(text):
    """Yield ``(line, values)`` for each literal collection of two or more strings.

    The scan reads the text.  A reformat that moves a site does not change the answer.  A
    site that changes its values does change the answer.
    """
    for match in COLLECTION.finditer(text):
        body = match.group(1)
        if VALUE_LIST.fullmatch(body) is None:
            continue
        values = strings_in(body)
        if len(values) >= 2:
            yield text.count('\n', 0, match.start()) + 1, values


def tables_in(sql_text):
    """Yield ``(name, block)`` for each ``CREATE TABLE`` block of one migration."""
    marks = list(TABLE.finditer(sql_text))
    for index, mark in enumerate(marks):
        end = marks[index + 1].start() if index + 1 < len(marks) else len(sql_text)
        yield mark.group(1), sql_text[mark.start():end]


def checks_in(block):
    """Yield ``(column, values)`` for each ``CHECK (column IN (...))`` rule of one block."""
    for match in CHECK_IN.finditer(block):
        values = strings_in(match.group(2))
        if values:
            yield match.group(1), values


def sql_domain_values(sql_text):
    """Yield one frozenset of values for each ``IN (...)`` list of strings.

    A list of numbers, such as ``IN (128)``, yields no string and is not a word domain.
    """
    for match in IN_LIST.finditer(sql_text):
        values = strings_in(match.group(1))
        if values:
            yield frozenset(values)


def shipped_copies():
    """Yield ``(module, values)`` for each literal string collection of the packages."""
    for folder in SHIPPED:
        for path in sorted((ROOT / folder).rglob('*.py')):
            if '__pycache__' in path.parts:
                continue
            relative = str(path.relative_to(ROOT))
            for _, values in collections_in(path.read_text(encoding='utf-8')):
                yield relative, frozenset(values)


def unrecorded_copies(copies, domains, recorded):
    """The copies of a SQL domain value list that no record names.

    ``copies`` holds the ``(module, values)`` pairs the scan found.  ``domains`` holds the
    value lists the migrations spell.  ``recorded`` holds the ``(module, values)`` pairs
    that the records of this module name.
    """
    return sorted((module, tuple(sorted(values))) for module, values in copies
                  if values in domains and (module, values) not in recorded)


@dataclass(frozen=True)
class Pair:
    """One SQL word domain and the Python sites that repeat it."""

    domain: str            # "tournaments.format": the SQL table and column
    values: tuple          # the values, as the SQL rule spells them
    sql_file: str          # the migration that holds the rule
    sql_table: str         # the table that holds the rule
    sql_column: str        # the column of the rule
    sql_constraint: str    # the exact rule text, as the migration writes it
    python: tuple          # ((module, number of sites), ...)


@dataclass(frozen=True)
class Record:
    """One SQL word domain that this module does not bind, and the measured reason."""

    domain: str
    values: tuple
    python: tuple          # ((module, number of sites), ...)
    reason: str


#: The six pairs this module binds.  The values are the SQL spelling; a pair holds when
#: both sides spell the same set of values, in any order.
PAIRS = (
    Pair(domain='tournaments.format',
         values=('singles', 'doubles'),
         sql_file='0002_user_data.sql',
         sql_table='tournaments',
         sql_column='format',
         sql_constraint="CHECK (format IN ('singles','doubles'))",
         python=(('annotator/operations.py', 2),)),
    Pair(domain='matches.status',
         values=('pending', 'scheduled', 'delayed', 'live', 'complete'),
         sql_file='0002_user_data.sql',
         sql_table='matches',
         sql_column='status',
         sql_constraint="CHECK (status IN ('pending','scheduled','delayed','live','complete'))",
         python=(('annotator/operations.py', 1),)),
    Pair(domain='matches.result',
         values=('played', 'forfeit', 'bye'),
         sql_file='0002_user_data.sql',
         sql_table='matches',
         sql_column='result',
         sql_constraint="CHECK (result IN ('played','forfeit','bye'))",
         python=(('annotator/operations.py', 1),)),
    Pair(domain='track_seeds.label',
         values=('A', 'B', 'ignore'),
         sql_file='0002_user_data.sql',
         sql_table='track_seeds',
         sql_column='label',
         sql_constraint="CHECK (label IN ('A','B','ignore') OR length(label) BETWEEN 1 AND 60)",
         python=(('annotator/unified_server.py', 2), ('src/pid_seed_rebuild.py', 1))),
    # The verdict values are the service constant VERDICT_WORDS, imported above.  A second
    # case reads that constant, so a change in the validator shows up as one failure here.
    Pair(domain='event_verdicts.verdict',
         values=tuple(VERDICT_WORDS),
         sql_file='0002_user_data.sql',
         sql_table='event_verdicts',
         sql_column='verdict',
         sql_constraint="CHECK (verdict IN ('correct','wrong','unsure'))",
         python=(('annotator/unified_server.py', 1),)),
    Pair(domain='event_verdicts.shooter',
         values=('A', 'B', '?', ''),
         sql_file='0002_user_data.sql',
         sql_table='event_verdicts',
         sql_column='shooter',
         sql_constraint="CHECK (shooter IN ('A','B','?',''))",
         python=(('annotator/unified_server.py', 1),)),
)

#: Two domains already have a parity case in another test module.  A second case here
#: would repeat that case and would add no coverage, so this module records them only.
BOUND_ELSEWHERE = (
    Record(domain='players.status',
           values=('Active', 'Visitor', 'Prospect', 'Inactive'),
           python=(('annotator/operations.py', 1),),
           reason='tests/test_player_status.py compares this rule, the owner tuple '
                  'PLAYER_STATUSES in annotator/operations.py and the console array in '
                  'annotator/ops.js'),
    Record(domain='ball_labels.crop_set',
           values=tuple(BALL_SETS),
           python=(('src/store_files.py', 1),),
           reason='tests/test_store_files.py compares this rule with the owner tuple '
                  'BALL_SETS in src/store_files.py, in the same order; this module reads '
                  'that tuple, so the SQL rule text is held to the owner too'),
)

#: One domain has Python copies of the shape this module reads, and no whole SQL rule
#: that a pair can hold.  The record names the copies, so the completeness case stays
#: quiet for them and fails for a new copy.
UNBOUND = (
    Record(domain='event_verdicts.dataset, frame_corrections.dataset',
           values=('vod30', 'highlight'),
           python=(('src/check_app_quad.py', 1), ('src/eval_faces.py', 1)),
           reason='db/migrations/0004_imported_datasets.sql drops both dataset rules and '
                  'adds dataset_id_ok(dataset), a format rule that also accepts an '
                  'imported VOD id; the built-in id list has one owner, the dict STATIC '
                  'in src/datasets.py, and this module reads literal collections only'),
)

#: Two word domains have no Python copy of this shape, so no pair exists.  The table
#: states the measurement, and a later copy fails the completeness case.
NO_PYTHON_COPY = (
    Record(domain='tournaments.status',
           values=('registration', 'active', 'complete'),
           python=(),
           reason='annotator/operations.py compares t["status"] with one string at a time, '
                  'for example t["status"] != "registration", so no literal collection '
                  'holds the three values'),
    Record(domain='sources.kind',
           values=('channel', 'video'),
           python=(),
           reason='annotator/operations.py returns kind="channel" and kind="video" as two '
                  'separate dict literals in parse_twitch_source_url, so no literal '
                  'collection holds the two values'),
)

RECORDS = BOUND_ELSEWHERE + UNBOUND + NO_PYTHON_COPY


def pair_problems(pair):
    """The disagreements of one pair, as one text line each."""
    problems = []
    where = f'db/migrations/{pair.sql_file}'
    blocks = dict(tables_in(source(where)))
    block = blocks.get(pair.sql_table)
    if block is None:
        return [f'{pair.domain}: {where} holds no table {pair.sql_table}']
    if pair.sql_constraint not in block:
        return [f'{pair.domain}: {where} no longer holds this rule text: '
                f'{pair.sql_constraint}']
    found = [values for column, values in checks_in(block) if column == pair.sql_column]
    if len(found) != 1:
        problems.append(f'{pair.domain}: {where} holds {len(found)} IN rules for column '
                        f'{pair.sql_column}; the pair table pins 1')
    elif set(found[0]) != set(pair.values):
        problems.append(f'{pair.domain}: {where} spells {sorted(set(found[0]))}; the pair '
                        f'table pins {sorted(set(pair.values))}')
    for module, expected in pair.python:
        sites = [line for line, values in collections_in(source(module))
                 if set(values) == set(pair.values)]
        if len(sites) != expected:
            problems.append(f'{pair.domain}: {module} holds {len(sites)} literal collections '
                            f'of {sorted(set(pair.values))} at lines {sites}; the pair table '
                            f'pins {expected}')
    return problems


def migration_domains():
    """The value lists the migrations spell, as one set of frozensets."""
    domains = set()
    for path in sorted(MIGRATIONS.glob('*.sql')):
        domains.update(sql_domain_values(path.read_text(encoding='utf-8')))
    return domains


class SqlDomainParityTests(unittest.TestCase):
    """The SQL word domains and their Python copies must spell the same values."""

    def test_each_pair_holds_one_value_list(self):
        """For each pair, the SQL rule and the Python sites must spell one value list.

        The case reports the line numbers that it found, so a person can read the site.
        It does not pin them, because a line number drifts.
        """
        problems = []
        for pair in PAIRS:
            problems += pair_problems(pair)
        self.assertEqual([], problems,
                         'a SQL word domain and its Python copy disagree; a value that the '
                         'database accepts can fail in Python, or the other way round:\n'
                         + '\n'.join(problems))

    def test_every_word_domain_of_the_migrations_is_recorded(self):
        """Each word domain of the migrations must have one record in this module."""
        recorded = {frozenset(pair.values) for pair in PAIRS}
        recorded |= {frozenset(record.values) for record in RECORDS}
        left = sorted(tuple(sorted(values)) for values in migration_domains() - recorded)
        self.assertEqual([], left,
                         'these SQL word domains have no record in '
                         'tests/test_sql_domain_parity.py. Add a pair, or a record with the '
                         'measured reason: ' + repr(left))

    def test_no_copied_domain_value_list_is_unrecorded(self):
        """Each Python copy of a SQL word domain must have a record in this module."""
        recorded = {(module, frozenset(pair.values))
                    for pair in PAIRS for module, _ in pair.python}
        for record in RECORDS:
            recorded.update((module, frozenset(record.values))
                            for module, _ in record.python)
        left = unrecorded_copies(set(shipped_copies()), migration_domains(), recorded)
        self.assertEqual([], left,
                         'these Python collections repeat a SQL word domain, and no record '
                         'in tests/test_sql_domain_parity.py names them. Bind the pair, or '
                         'record the site with the measured reason: ' + repr(left))

    def test_the_completeness_rule_reports_a_copy_that_no_record_names(self):
        """The completeness rule must report an unrecorded copy, and must not stay quiet."""
        domain = frozenset(('singles', 'doubles'))
        copies = {('annotator/operations.py', domain), ('src/pid_seed_rebuild.py', domain)}
        recorded = {('annotator/operations.py', domain)}
        self.assertEqual([('src/pid_seed_rebuild.py', ('doubles', 'singles'))],
                         unrecorded_copies(copies, {domain}, recorded))

    def test_the_verdict_pair_reads_the_service_constant(self):
        """The event_verdicts pair holds the values of the service constant VERDICT_WORDS.

        The pair above is one copy of the three words.  This case holds that copy to the
        owner in annotator/unified_server.py, and the SQL text of the same pair holds the
        migration to the same words.
        """
        verdict = [pair for pair in PAIRS if pair.domain == 'event_verdicts.verdict']
        self.assertEqual(1, len(verdict), 'this module binds event_verdicts.verdict once')
        self.assertEqual(tuple(VERDICT_WORDS), verdict[0].values)
        sql = source(f'db/migrations/{verdict[0].sql_file}')
        block = dict(tables_in(sql))[verdict[0].sql_table]
        values = [tuple(words) for _, words in checks_in(block)]
        self.assertIn(tuple(VERDICT_WORDS), values,
                      'the migration spells the values of VERDICT_WORDS, in that order')
