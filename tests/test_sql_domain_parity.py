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

import ast
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
# here would be a second spelling of the vocabulary.  The note bound of the same table
# reads ANNOTATION_NOTE_MAX for the same reason: the route refuses a longer note, the
# migration refuses a longer row, and a literal number here would be a third spelling.
# The track_seeds pair reads the service constant SEED_ROLES for the same reason: round 70
# made that constant the one python home of the three role words, so a literal list here
# would be the second python spelling that this module exists to refuse.  The shooter pair
# is the exception of the three: its value list stands here as a literal, because the
# migration holds the four values and the module holds no constant for the empty string
# and the question mark in one place yet.
from annotator.unified_server import (ANNOTATION_NOTE_MAX, SEED_ROLES, SHOOTER_WORDS,
                                      VERDICT_WORDS)

# The number rules read the constants of the validator, so the CHECK of the migration and
# the check of the request cannot drift apart.  A literal number in this module would be a
# third spelling of the bound: the bounds table below names these constants instead.
from annotator.operations import (LONGEST_NAME, RACE_TO_MAX, RACE_TO_MIN, RATING_MAX,
                                  RATING_MIN, TABLES_MAX, TABLES_MIN)

# The rank of a face sample is below the count src/person_identity.py keeps, so the
# migration's three ranks and PERSIST_FACES hold one number.  This module reads the count
# and states the relation, so a fourth sample cannot pass the validator and fail the DDL.
from src.person_identity import PERSIST_FACES

# The shipped package tree has one home, tests/_shipped.py.  A second copy of the tree
# in this module is a defect, and the guard tests/test_one_shipped_tree.py walks for it.
from _shipped import SHIPPED

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / 'db' / 'migrations'
#: The module whose constants the bounds table names, and whose checks refuse a value
#: outside a bound.  Each bound names the module it reads, so no copy of a module stands
#: here.
OWNER = 'annotator/operations.py'

#: The syntax tree of one module, parsed once per run.
_TREES: dict = {}


def tree_of(relative):
    """The syntax tree of one repository file, parsed once per run."""
    if relative not in _TREES:
        _TREES[relative] = ast.parse(source(relative))
    return _TREES[relative]

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
#: One ``CHECK (column BETWEEN low AND high)`` rule.  A CHECK that ends in BETWEEN
#: carries the column first; a CHECK that wraps the column in a call, such as
#: ``CHECK (length(btrim(name)) BETWEEN 1 AND 200)``, carries it after the call.
CHECK_NUMERIC = re.compile(r'CHECK \((.*?) BETWEEN (-?\d+) AND (-?\d+)\)')
#: One length rule and its low end: ``length(btrim(name)) BETWEEN 1 AND 200``.
LENGTH_RULE = re.compile(r'length\(.*?\) BETWEEN (\d+) AND')
#: The column word of a BETWEEN rule that a call wraps, for example ``btrim(name)``.
WRAPPED_COLUMN = re.compile(r'\((\w+)\)')
#: Two or more spaces, which one text may use where the other uses one.
SPACES = re.compile(r' {2,}')
#: One argument of a check call that is a name, not a literal number.
NAME_ARGUMENT = re.compile(r'[A-Za-z_]\w*')
#: A number in a comment or a limit that never stands as an argument of a check call,
#: because it touches a letter or a bracket.  A site that still spells the bound inline
#: is found at either side of the pair, and this pattern is the measured reason.
INLINE_NUMBER = re.compile(r'(?:^|[,\s(])(-?\d+)(?=\s*[,)])')
#: One ``CHECK (length(column) <= number)`` rule.  Round 69 measured this shape: it is
#: invisible to ``CHECK_NUMERIC`` and to ``LENGTH_RULE``, because neither text holds
#: ``BETWEEN``, so the one guard of this module read neither side of the rule.
CHECK_CEILING = re.compile(r'CHECK \(length\((\w+)\) <= (\d+)\)')
#: One ``CHECK`` line of the design document, and the column of its rule.
DOC_CHECK = re.compile(r'^\s*(\w+)\s+\w.*?(CHECK \(.*BETWEEN.*\))', re.MULTILINE)

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


def collection_sites(module, values):
    """The lines of one module that hold a literal collection of exactly ``values``."""
    return [line for line, found in collections_in(source(module))
            if set(found) == set(values)]


def between_columns(sql_text):
    """Yield ``(column, low, high, rule)`` for each ``BETWEEN`` rule of one SQL text.

    The rule text is the one the migration spells, from ``CHECK`` to the closing
    bracket.  The scan reads the text, so a rule that moves keeps its answer, and a
    rule that changes its numbers changes the answer.
    """
    for match in CHECK_NUMERIC.finditer(sql_text):
        body, low, high = match.group(1), int(match.group(2)), int(match.group(3))
        wrapped = WRAPPED_COLUMN.findall(body)
        column = wrapped[-1] if wrapped else body.strip()
        yield column, low, high, match.group(0)


def ceiling_columns(sql_text):
    """Yield ``(column, limit, rule)`` for each ``<=`` rule of one SQL text.

    A ceiling rule names one end only: a text column holds at least one character, so
    the low end of the rule is 1.  The rule text is the one the migration spells, from
    ``CHECK`` to the closing bracket, so a rule that moves keeps its answer and a rule
    that changes its number changes the answer.
    """
    for match in CHECK_CEILING.finditer(sql_text):
        yield match.group(1), int(match.group(2)), match.group(0)


def agreement(rule, side, other):
    """The one text that reports two spellings of one rule that disagree, or None.

    ``rule`` names the rule and ``side`` names the text it was read from.  The answer
    is None when the two spellings hold the same number.
    """
    if side[0] != other[0]:
        return f'{rule}: {side[1]} spells {side[0]}; {other[1]} spells {other[0]}'
    return None


def migration_bounds():
    """Yield ``(table, column, low, high, rule)`` for each ``BETWEEN`` rule of a migration."""
    for path in sorted(MIGRATIONS.glob('*.sql')):
        for table, block in tables_in(path.read_text(encoding='utf-8')):
            for column, low, high, rule in between_columns(block):
                yield table, column, low, high, rule


def migration_ceilings():
    """Yield ``(table, column, limit, rule)`` for each ``<=`` rule of a migration."""
    for path in sorted(MIGRATIONS.glob('*.sql')):
        for table, block in tables_in(path.read_text(encoding='utf-8')):
            for column, limit, rule in ceiling_columns(block):
                yield table, column, limit, rule


def constant_sites(module, name):
    """The lines of one module that read the name of a constant, as one sorted list.

    The scan reads the syntax tree, so a comment or a docstring that mentions the name is
    not a site.  The answer holds line numbers so that a person can read each site.
    """
    return sorted(node.lineno for node in ast.walk(tree_of(module))
                  if isinstance(node, ast.Name) and node.id == name)


def named_low(bound, names):
    """The low end of one bound: the number the migration states beside the high end.

    A length rule such as ``CHECK (length(btrim(name)) BETWEEN 1 AND 200)`` names only
    its high end, because a column of text holds at least one character.  A rank starts
    at zero.  Every other rule names both ends, so the smaller name is its low number.
    """
    if bound.sql_low is not None:
        return bound.sql_low
    length = LENGTH_RULE.search(bound.sql_constraint)
    if length is not None:
        return int(length.group(1))
    return min(names.values())


def bound_sites(bound):
    """The call sites of the owner module that read the bound of one rule.

    The scan reads the syntax tree, so a site that passes the number inline, or one
    that passes a name other than the one the bounds table pins, is not a site.  A line
    number drifts and is not part of the answer.

    ``integer(value, low, high, name)`` states both ends.  ``text(value, name,
    maximum=...)`` states the longest name, and the default of that parameter carries
    the bound when a call leaves it out; a call that leaves it out passes no keyword.
    """
    sites = []
    for node in ast.walk(tree_of(bound.owner)):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Name) or node.func.id != bound.validator:
            continue
        if bound.validator == 'text':
            if len(node.args) != 2 or node.keywords:
                continue
            sites.append(node)
            continue
        if len(node.args) != 4 or node.keywords:
            continue
        if not all(isinstance(argument, ast.Name) for argument in node.args[1:3]):
            continue
        if bound.python:
            if [argument.id for argument in node.args[1:3]] != [name for name, _ in bound.python]:
                continue
        sites.append(node)
    return sites


def bound_default_problems(bound):
    """The problems of the signature of a check whose one name is a default."""
    if len(bound.python) != 1 or bound.validator is None:
        return []
    name = bound.python[0][0]
    for node in ast.walk(tree_of(bound.owner)):
        if not isinstance(node, ast.FunctionDef) or node.name != bound.validator:
            continue
        spelled = ast.dump(node.args)
        if name not in spelled:
            return [f'{bound.column}: the signature of {bound.validator} does not hold the '
                    f'name {name}; the bounds table pins it']
        return []
    return [f'{bound.column}: {bound.owner} holds no function {bound.validator}']


def bound_ceiling_problems(bound, sql_text=None):
    """The disagreements of one ceiling rule, as one text line each.

    A ceiling rule states one end, ``CHECK (length(column) <= number)``, so the scan of
    ``BETWEEN`` rules above cannot read it.  This reader holds the migration text, the
    constant of the owner module and the call sites of that name together.
    """
    if sql_text is None:
        sql_text = source(f'db/migrations/{bound.sql_file}')
    problems = []
    found = []
    for table, block in tables_in(sql_text):
        for column, limit, rule in ceiling_columns(block):
            if f'{table}.{column}' == bound.column:
                found.append((table, column, limit, rule))
    if not found:
        return [f'{bound.column}: {bound.sql_file} holds no ceiling rule for this column']
    _, _, limit, rule = found[0]
    if rule != bound.sql_constraint:
        problems.append(f'{bound.column}: {bound.sql_file} spells "{rule}"; the bounds table '
                        f'pins "{bound.sql_constraint}"')
    names = dict(bound.python)
    if not names:
        problems.append(f'{bound.column}: the bounds table pins no constant for this rule, '
                        f'so no Python side is compared')
        return problems
    owner = source(bound.owner)
    missing = sorted(name for name in names if name not in owner)
    if missing:
        problems.append(f'{bound.column}: {bound.owner} does not hold the name(s) {missing} '
                        f'the bounds table pins')
    if not set(names.values()) & {limit}:
        problems.append(f'{bound.column}: the migration binds at most {limit}; the constants '
                        f'hold {sorted(set(names.values()))}')
    for name, number in sorted(names.items()):
        disagreement = agreement(bound.column, (number, f'{bound.owner} {name}'),
                                 (limit, bound.sql_file))
        if disagreement:
            problems.append(disagreement)
        sites = constant_sites(bound.owner, name)
        if len(sites) != bound.sites:
            problems.append(f'{bound.column}: {bound.owner} reads {name} at {len(sites)} '
                            f'sites {sites}; the bounds table pins {bound.sites}')
    return problems


def bound_problems(bound, sql_text=None):
    """The disagreements of one number rule, as one text line each.

    ``sql_text`` is the migration text the scan reads.  A caller may pass the text of
    another migration to measure the guard itself.  A bound whose rule is a ceiling
    states its ``limit_rule``, and the ceiling reader answers for it.
    """
    if bound.limit_rule:
        return bound_ceiling_problems(bound, sql_text)
    if sql_text is None:
        sql_text = source(f'db/migrations/{bound.sql_file}')
    problems = []
    found = []
    for table, block in tables_in(sql_text):
        for column, low, high, rule in between_columns(block):
            if f'{table}.{column}' == bound.column:
                found.append((low, high, rule))
    if not found:
        return [f'{bound.column}: {bound.sql_file} holds no BETWEEN rule for this column']
    low, high, rule = found[0]
    if rule != bound.sql_constraint:
        problems.append(f'{bound.column}: {bound.sql_file} spells "{rule}"; the bounds table '
                        f'pins "{bound.sql_constraint}"')
    names = dict(bound.python)
    owner = source(bound.owner)
    missing = sorted(name for name in names if not re.search(rf'\b{name}\b', owner))
    if missing:
        problems.append(f'{bound.column}: {bound.owner} does not hold the name(s) {missing} '
                        f'the bounds table pins')
    wants = set(names.values())
    bound_low = named_low(bound, names)
    if low != bound_low or high not in wants:
        problems.append(f'{bound.column}: the migration binds {low}..{high}; the constants '
                        f'bind {bound_low}..{sorted(wants)}')
    if bound.validator is None:
        return problems
    sites = bound_sites(bound)
    if len(sites) != bound.sites:
        problems.append(f'{bound.column}: {bound.validator} holds {len(sites)} call sites in '
                        f'{bound.owner} whose two bound arguments are the bound names; the '
                        f'bounds table pins {bound.sites}')
    problems += bound_default_problems(bound)
    return problems


def design_doc_problems(sql_text):
    """The problems of the design document copy of the DDL, as one text line each.

    ``db/migrations/0002_user_data.sql`` owns the DDL the store applies.  The design
    document repeats that DDL as text, and no guard read the copy before this one.
    """
    doc = source('docs/postgres-design.md')
    born = {normalised(match.group(0)) for match in CHECK_NUMERIC.finditer(sql_text)}
    seen = 0
    drifted = []
    for match in DOC_CHECK.finditer(doc):
        seen += 1
        rule = normalised(match.group(2))
        if rule not in born:
            drifted.append(f'{match.group(1)}: the document spells "{rule}"; the migration '
                           f'holds no such rule')
    if not seen:
        drifted.append('docs/postgres-design.md holds no CHECK ... BETWEEN line; the document '
                       'copy of the DDL moved or was deleted')
    if seen < len(born):
        drifted.append(f'the document spells {seen} CHECK ... BETWEEN rules and the '
                       f'migration holds {len(born)}; this guard reads every {len(born)}')
    return drifted


def normalised(rule):
    """One rule text with every run of spaces reduced to one space."""
    return SPACES.sub(' ', rule).strip()


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
class Bound:
    """One number rule of a SQL column and the Python validator that repeats it.

    Round 48 gave a word domain one pair.  A number domain needs the same treatment:
    the migration states the bound for the database and Python states it for the
    validator.  ``validator`` names the check of ``annotator/operations.py`` that
    refuses a value outside the bound, and ``python`` names the constants that hold
    the bound beside the other names of that module.
    """

    column: str            # "tournaments.tables": the SQL table and column
    sql_file: str          # the migration that holds the rule
    sql_constraint: str    # the exact rule text, as the migration writes it
    owner: str             # the module that holds the names below
    python: tuple = ()     # (("RATING_MIN", 0), ("RATING_MAX", 1000)); the first item is
                           # the name the module holds, the second is the bound it holds
    sql_low: int = None    # the low end of the rule, when no name of the module holds it
                           # (a length rule, or a rank that starts at 0)
    validator: str = None  # "integer", the check whose two arguments are the bound;
                           # None when no validator of the owner module owns this bound
    sites: int = 0         # how many call sites of the check read the two names
    limit_rule: str = ''   # the exact ``CHECK (length(column) <= number)`` text of the
                           # migration, when the rule names one end only.  Round 69 bound
                           # ``event_verdicts.note`` this way: a ``<=`` rule holds no
                           # ``BETWEEN``, so the two regexes above read neither side of it.
                           # An empty text means the rule of this bound is a ``BETWEEN``
                           # rule, and the scan above reads it.


#: The number domains this module binds.  Each rule holds the exact migration text and
#: the Python names that repeat it.  A sixth rule, ``track_seeds.label``, is both a word
#: list and a length bound, and the pair of that domain above holds it.
#:
#: ``players.name`` is bound here as well: the column refuses a name of 0 or of 201
#: characters, and ``LONGEST_NAME`` is the default of ``text``.  Three call sites of
#: ``_do_player_save``, ``_do_tournament_rename`` and ``_do_pool_remove`` read that
#: default and pass no maximum, so the site scan counts them and tests/test_operations.py
#: drives a name at the bound and at the next character.
#:
#: ``identity_face_samples.rank`` is bound to the count of ``src/person_identity.py``:
#: the CHECK reads a rank, and PERSIST_FACES holds how many samples one cluster keeps.
BOUNDS = (
    Bound(column='players.rating',
          sql_file='0002_user_data.sql',
          sql_constraint='CHECK (rating BETWEEN 0 AND 1000)',
          owner=OWNER,
          python=(('RATING_MIN', RATING_MIN), ('RATING_MAX', RATING_MAX)),
          validator='integer',
          sites=1),
    Bound(column='tournaments.tables',
          sql_file='0002_user_data.sql',
          sql_constraint='CHECK (tables BETWEEN 1 AND 32)',
          owner=OWNER,
          python=(('TABLES_MIN', TABLES_MIN), ('TABLES_MAX', TABLES_MAX)),
          validator='integer',
          sites=2),
    Bound(column='tournaments.race_to',
          sql_file='0002_user_data.sql',
          sql_constraint='CHECK (race_to BETWEEN 1 AND 99)',
          owner=OWNER,
          python=(('RACE_TO_MIN', RACE_TO_MIN), ('RACE_TO_MAX', RACE_TO_MAX)),
          validator='integer',
          sites=2),
    Bound(column='players.name',
          sql_file='0002_user_data.sql',
          sql_constraint='CHECK (length(btrim(name)) BETWEEN 1 AND 200)',
          owner=OWNER,
          python=(('LONGEST_NAME', LONGEST_NAME),),
          validator='text',
          sites=3),
    Bound(column='identity_face_samples.rank',
          sql_file='0002_user_data.sql',
          sql_constraint='CHECK (rank BETWEEN 0 AND 2)',
          owner='src/person_identity.py',
          sql_low=0,
          python=(('PERSIST_FACES', PERSIST_FACES - 1),)),
    # The one ceiling rule of the migrations.  Round 69 bound it: the route of
    # annotator/unified_server.py refused a longer note and the table refused the same
    # note, and no rule of this module read either side, because the two regexes above read
    # ``BETWEEN`` only.  The owner is the service module, not the validator module, and the
    # route spells the comparison inside its own body rather than a check function, so no
    # ``validator`` stands here.  ``sites`` is the count of the name below in the owner: the
    # definition at the top of the module and the one read in the route.  A route that
    # spells the number inline drops the read and fails this count, and the boundary case of
    # tests/test_unified_server.py drives the route.
    Bound(column='event_verdicts.note',
          sql_file='0002_user_data.sql',
          sql_constraint='CHECK (length(note) <= 10000)',
          owner='annotator/unified_server.py',
          python=(('ANNOTATION_NOTE_MAX', ANNOTATION_NOTE_MAX),),
          sites=2,
          limit_rule='CHECK (length(note) <= 10000)'),
)

#: The column of one pair that also carries a length bound.  The pair above holds the
#: rule text and the word values; the bounds scan below reads the same line again.
PAIR_LENGTH_BOUND = 'track_seeds.label'


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
         values=tuple(SEED_ROLES),
         sql_file='0002_user_data.sql',
         sql_table='track_seeds',
         sql_column='label',
         sql_constraint="CHECK (label IN ('A','B','ignore') OR length(label) BETWEEN 1 AND 60)",
         python=(('annotator/unified_server.py', 1),)),
    # The verdict values are the service constant VERDICT_WORDS, imported above.  A second
    # case reads that constant, so a change in the validator shows up as one failure here.
    Pair(domain='event_verdicts.verdict',
         values=tuple(VERDICT_WORDS),
         sql_file='0002_user_data.sql',
         sql_table='event_verdicts',
         sql_column='verdict',
         sql_constraint="CHECK (verdict IN ('correct','wrong','unsure'))",
         python=(('annotator/unified_server.py', 1),)),
    # Round 70 gave the shooter four values one python home, SHOOTER_WORDS in
    # annotator/unified_server.py, and the route reads that constant.  The values stand here
    # as a literal on purpose: this module reads no schema and the pair is the record of the
    # migration text.  The case below holds the literal to the constant.  The one python site
    # is the constant itself, and a second literal list of the four values in the service is
    # a failure of that case and of this count.
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

#: One ceiling rule of the migrations that this module does not bind, and the measured
#: reason.  The completeness case of the ceilings reads this table, so the rule keeps a
#: record and a new ceiling rule still fails the case.
CEILINGS_DEFERRED = {
    'players.notes': 'the note bound of a saved regular stands four times: the migration '
                     'at db/migrations/0002_user_data.sql:23 holds '
                     'CHECK (length(notes) <= 4000), annotator/operations.py holds '
                     'NOTE_MAX = 4000 at :45 and reads it at :886 and :1316, and '
                     'docs/console-redesign.md records the row.  Round 69 binds the '
                     'annotation note, event_verdicts.note, and leaves this rule: the four '
                     'copies are one rule in two languages and one round cannot unify them',
}

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

    def test_the_word_pairs_read_their_service_constant(self):
        """Each word pair below holds the values of one constant of the service module.

        Round 70 gave the shooter four values one python home, ``SHOOTER_WORDS`` in
        annotator/unified_server.py, and the route reads that constant.  The pair table holds
        the four values as a literal, and this case holds that literal to the constant, so a
        value that the route accepts and the pair table does not name is a failure here.  The
        pair table reads ``SEED_ROLES`` itself, and this case pins that read as well: a change
        of the constant must reach the pair table.
        """
        cases = (('event_verdicts.shooter', SHOOTER_WORDS),
                 ('track_seeds.label', SEED_ROLES))
        for domain, constant in cases:
            with self.subTest(domain=domain):
                pairs = [pair for pair in PAIRS if pair.domain == domain]
                self.assertEqual(1, len(pairs), f'this module binds {domain} once')
                self.assertEqual(tuple(constant), pairs[0].values,
                                 f'{domain}: the pair table and the service constant disagree')

    def test_the_migration_spells_the_shooter_constant(self):
        """The event_verdicts CHECK spells the four values of ``SHOOTER_WORDS``, in order."""
        pairs = [pair for pair in PAIRS if pair.domain == 'event_verdicts.shooter']
        self.assertEqual(1, len(pairs), 'this module binds event_verdicts.shooter once')
        sql = source(f'db/migrations/{pairs[0].sql_file}')
        block = dict(tables_in(sql))[pairs[0].sql_table]
        values = [tuple(words) for _, words in checks_in(block)]
        self.assertIn(tuple(SHOOTER_WORDS), values,
                      'the migration spells the values of SHOOTER_WORDS, in that order')

    def test_each_bound_holds_one_value_list(self):
        """For each number rule, the migration text and the Python names must hold it.

        The case reads the exact ``CHECK ... BETWEEN`` text of the migration and the two
        constants of annotator/operations.py.  It also counts the call sites whose two
        bound arguments are those names, so a site that spells the number inline is a
        failure and not a pass.
        """
        problems = []
        for bound in BOUNDS:
            problems += bound_problems(bound)
        self.assertEqual([], problems,
                         'a SQL number rule and its Python bound disagree; a value that the '
                         'database accepts can fail in Python, or the other way round:\n'
                         + '\n'.join(problems))

    def test_every_between_rule_of_the_migrations_is_bound(self):
        """Each ``BETWEEN`` rule of the migrations must have one bound in this module.

        The case fails with the list of the rules that no record names, so a new
        constraint cannot be added without a Python home and a case.
        """
        bound = {entry.column for entry in BOUNDS}
        pairs = {pair.domain for pair in PAIRS if pair.domain == PAIR_LENGTH_BOUND}
        unbound = sorted(f'{table}.{column} BETWEEN {low} AND {high}'
                         for table, column, low, high, _ in migration_bounds()
                         if f'{table}.{column}' not in bound | pairs)
        self.assertEqual([], unbound,
                         'these SQL number rules hold no bound in '
                         'tests/test_sql_domain_parity.py. Name the bound beside the other '
                         'names of its module, add it to the bounds table, and add a case: '
                         + repr(unbound))

    def test_the_unbound_rule_report_names_the_rule(self):
        """The completeness rule must report an unbound rule, and must not stay quiet.

        The case drops the rating bound from the table and measures the report the
        completeness case above would print for it.
        """
        kept = [entry for entry in BOUNDS if entry.column != 'players.rating']
        bound = {entry.column for entry in kept}
        pairs = {pair.domain for pair in PAIRS if pair.domain == PAIR_LENGTH_BOUND}
        reported = sorted(f'{table}.{column} BETWEEN {low} AND {high}'
                          for table, column, low, high, _ in migration_bounds()
                          if f'{table}.{column}' not in bound | pairs)
        self.assertEqual(['players.rating BETWEEN 0 AND 1000'], reported,
                         'a bound that the table drops is named, with its rule')

    def test_the_bound_rule_reports_a_planted_bound(self):
        """The bound rule must report a migration copy whose number differs.

        This is the defect the module exists for: one side states the rule, the other
        side keeps the old number, and nothing fails.  The case plants the widen.
        """
        bound = [entry for entry in BOUNDS if entry.column == 'players.rating'][0]
        sql = source(f'db/migrations/{bound.sql_file}')
        planted = sql.replace('CHECK (rating BETWEEN 0 AND 1000)',
                              'CHECK (rating BETWEEN 0 AND 2000)')
        self.assertNotEqual(sql, planted, 'the case plants the widen of the rating rule')
        problems = bound_problems(bound, planted)
        self.assertTrue(any('0 AND 2000' in problem for problem in problems),
                        'the planted rule is reported; the guard answered ' + repr(problems))

    def test_every_ceiling_rule_of_the_migrations_is_bound(self):
        """Each ``<=`` rule of the migrations must have one bound in this module.

        Round 69 added this rule.  The case above reads ``BETWEEN`` rules only, and the
        note bound of ``event_verdicts`` stood in the route and in the migration with no
        reader.  A new ceiling rule fails here until a bound names it.
        """
        bound = {entry.column for entry in BOUNDS if entry.limit_rule}
        unbound = sorted(f'{table}.{column} <= {limit}'
                         for table, column, limit, _ in migration_ceilings()
                         if f'{table}.{column}' not in bound | set(CEILINGS_DEFERRED))
        self.assertEqual([], unbound,
                         'these SQL ceiling rules hold no bound in '
                         'tests/test_sql_domain_parity.py. Name the bound beside the other '
                         'names of its module, add it to the bounds table with its '
                         'limit_rule, and add a case: ' + repr(unbound))

    def test_the_bound_rule_reports_a_planted_ceiling(self):
        """The ceiling rule must report a migration copy whose number differs.

        This is the defect the round-69 case exists for: the route keeps one note bound
        and the table keeps another, and neither side fails.
        """
        bound = [entry for entry in BOUNDS if entry.column == 'event_verdicts.note'][0]
        sql = source(f'db/migrations/{bound.sql_file}')
        planted = sql.replace('CHECK (length(note) <= 10000)',
                              'CHECK (length(note) <= 20000)')
        self.assertNotEqual(sql, planted, 'the case plants the widen of the note rule')
        problems = bound_ceiling_problems(bound, planted)
        self.assertTrue(any('20000' in problem for problem in problems),
                        'the planted ceiling is reported; the guard answered '
                        + repr(problems))

    def test_the_design_document_copy_holds_the_migration_rules(self):
        """The design document must spell each ``BETWEEN`` rule of the migration.

        ``docs/postgres-design.md`` repeats the DDL of db/migrations/0002_user_data.sql
        as document text, and the guard read the migration only.  A change of one
        ``CHECK`` in the migration left the document stating the old rule.  This case
        reads both texts, and the migration stays the owner of the rule.
        """
        sql = source('db/migrations/0002_user_data.sql')
        problems = design_doc_problems(sql)
        self.assertEqual([], problems,
                         'the design document and the migration disagree on a CHECK ... '
                         'BETWEEN rule:\n' + '\n'.join(problems))
