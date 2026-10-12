"""Hold each SQL domain (a word list, a number rule, a width) to the Python owner of it.

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

* this module binds 7 of them, one pair each (``PAIRS``);
* two other test modules already bind one domain each (``BOUND_ELSEWHERE``);
* two have no Python copy of this shape (``NO_PYTHON_COPY`` and ``UNBOUND``).

A rule can hold one number rather than a word list: ``identity_clusters.body_dim`` holds
``CHECK (body_dim IN (128))``, and three columns hold ``CHECK (cardinality(column) = 512)``.
Round 82 read these rules too.  The three 512 sites read ``EMBEDDING_DIM`` of
``src/face_id.py`` through the ``ONE_NUMBERS`` table below, and the two rules whose number
has no Python owner stand in ``ONE_NUMBERS_DEFERRED`` with the measured reason each one
stays unbound.

The completeness cases fail when a SQL rule appears that no record of this module names:
one case reads the value lists, one the ``BETWEEN`` rules, one the ``<=`` rules, and one
the one-number rules that round 82 added.  The scan reads the shipped packages only
(``SHIPPED``).  A test file states an expectation, so it is not a copy inside the
application.
"""

from __future__ import annotations

import ast
import re
import unittest
from dataclasses import dataclass, replace
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
# The ball label domain reads the two bounds of the service for the same reason: the route
# owns what it accepts, the console states its own two names in a static file, and the
# migration holds the bound in a regular expression.  The text bound table at the end of
# this module names the three spellings, so a literal number here would be a fourth.
from annotator.unified_server import (ANNOTATION_NOTE_MAX, BALL_LABEL_MAX, BALL_LABEL_MIN,
                                      SEED_ROLES, SHOOTER_WORDS, VERDICT_WORDS)

# The number rules read the constants of the validator, so the CHECK of the migration and
# the check of the request cannot drift apart.  A literal number in this module would be a
# third spelling of the bound: the bounds table below names these constants instead.
from annotator.operations import (LONGEST_NAME, RACE_TO_MAX, RACE_TO_MIN, RATING_MAX,
                                  RATING_MIN, TABLES_MAX, TABLES_MIN, TOURNAMENT_STATUSES)

# The rank of a face sample is below the count src/person_identity.py keeps, so the
# migration's three ranks and PERSIST_FACES hold one number.  This module reads the count
# and states the relation, so a fourth sample cannot pass the validator and fail the DDL.
from src.person_identity import PERSIST_FACES

# The width of one face embedding has one owner, src/face_id.py: EMBEDDING_DIM.  The
# migration states that width three times, as ``CHECK (cardinality(column) = 512)``, and
# the rows of ONE_NUMBERS below write the number as an f-string over this constant.  A
# width that moves in the owner then fails here until the migration moves too, and a
# literal 512 in this module would be a fourth spelling of the number.
from src.face_id import EMBEDDING_DIM

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
#: One ``CHECK (cardinality(column) = number)`` rule: the width of an array column.  The
#: rule can guard the column first, as ``CHECK (face IS NULL OR cardinality(face) = 512)``
#: does, so the text before ``cardinality`` may hold no closing bracket, and the column of
#: the rule is the argument of ``cardinality``.  Round 82 added this reader: the rule holds
#: one number, so ``CHECK_IN`` reads no value list and the three 512 sites stood unread.
CHECK_CARDINALITY = re.compile(r'CHECK \([^)]*?cardinality\((\w+)\) = (\d+)\)')
#: One ``CHECK (column IN (number))`` rule: a rule that holds one number, not a word list.
#: ``CHECK_IN`` reads the same shape, and the bracket of this pattern holds digits only, so
#: the two readers cannot both claim one rule.
CHECK_ONE_NUMBER_IN = re.compile(r'CHECK \((\w+) IN \((\d+)\)\)')
#: One ``CHECK`` line of the design document, and the column of its rule.
DOC_CHECK = re.compile(r'^\s*(\w+)\s+\w.*?(CHECK \(.*BETWEEN.*\))', re.MULTILINE)
#: The word map of one language of annotator/board.js: the object body after ``en: {``.
#: The body stops at the closing bracket of the map.
#: The map ends at the first closing bracket at the head of a line, which is the bracket
#: of the map itself, because every entry of the map stands on its own line.
BOARD_WORD_MAP_EN = re.compile(r'^\s*en: \{(.*?)^\s*\},', re.MULTILINE | re.DOTALL)
#: The same reader for the Chinese map.
BOARD_WORD_MAP_ZH = re.compile(r'^\s*zh: \{(.*?)^\s*\},', re.MULTILINE | re.DOTALL)
#: One key of a word map.  A key of this map spells the word itself, so the key of a
#: word is the word.  The other keys of the map name a table cell or a label, so the
#: three status words stand among the keys of the map.
BOARD_WORD_KEY = re.compile(r'(?:^|[,{])\s*([a-zA-Z][a-zA-Z0-9_]*)\s*:', re.MULTILINE)
#: Every key of the English word map of annotator/board.js, and the same list serves the
#: Chinese map, because the two maps hold one key list.  The count holds the current
#: state of the board.  A new word of the page changes this list, so a reader who adds a
#: page word updates this record in the same step.
BOARD_PAGE_KEYS = (
    'tonight', 'tables', 'next', 'bracket', 'standings', 'player', 'team', 'won', 'lost',
    'played', 'tableN', 'round', 'final', 'semi', 'quarter', 'singles', 'doubles', 'raceTo',
    'registration', 'active', 'complete', 'bye', 'tbd', 'vs', 'forfeit', 'ready', 'held',
    'live', 'champion', 'noTables', 'noNext', 'noBracket', 'noStandings', 'timeOnTable',
    'checkTable', 'underMinute', 'minutes', 'hours', 'connecting', 'updatedNow', 'updatedS',
    'updatedM', 'reconnecting', 'reconnectingEmpty', 'off', 'source',
)

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


def owner_number(row):
    """The number of the constant ``row.python`` of the owner module of one row, or None.

    The scan reads the assignment in the syntax tree of the owner, so a comment that names
    the number is not a site, and a constant that the owner dropped answers None.
    """
    for node in ast.walk(tree_of(row.owner)):
        if not isinstance(node, ast.Assign):
            continue
        if any(isinstance(target, ast.Name) and target.id == row.python for target in node.targets):
            try:
                return ast.literal_eval(node.value)
            except ValueError:
                return None
    return None


def cardinality_columns(sql_text):
    """Yield ``(column, number, rule)`` for each ``cardinality(column) = number`` rule."""
    for match in CHECK_CARDINALITY.finditer(sql_text):
        yield match.group(1), int(match.group(2)), match.group(0)


def one_number_in_columns(sql_text):
    """Yield ``(column, number, rule)`` for each ``CHECK (column IN (number))`` rule."""
    for match in CHECK_ONE_NUMBER_IN.finditer(sql_text):
        yield match.group(1), int(match.group(2)), match.group(0)


def one_numbers_in(sql_text):
    """Yield ``(table, column, number, rule)`` for each one-number rule of one SQL text.

    The two shapes of the migrations answer one list here, so the completeness case below
    reads every rule that holds one number, and not one shape of that rule.
    """
    for table, block in tables_in(sql_text):
        for column, number, rule in cardinality_columns(block):
            yield table, column, number, rule
        for column, number, rule in one_number_in_columns(block):
            yield table, column, number, rule


def migration_one_numbers():
    """Yield ``(sql_file, table, column, number, rule)`` for each one-number rule."""
    for path in sorted(MIGRATIONS.glob('*.sql')):
        for table, column, number, rule in one_numbers_in(path.read_text(encoding='utf-8')):
            yield path.name, table, column, number, rule


def one_number_problems(row, sql_text=None):
    """A line per disagreement between one SQL one-number rule and its Python owner.

    ``sql_text`` replaces the text of the migration, so a case can measure a planted drift
    without a write to the repository.
    """
    problems = []
    number = owner_number(row)
    if number != row.number:
        problems.append(f'{row.column}: {row.owner} holds {row.python} = {number!r}, and the '
                        f'row of this module states {row.number}')
    text = sql_text if sql_text is not None else source(f'db/migrations/{row.sql_file}')
    found = [(number, rule) for table, column, number, rule in one_numbers_in(text)
             if f'{table}.{column}' == row.column]
    if not found:
        problems.append(f'{row.column}: {row.sql_file} holds no one-number rule for the '
                        f'column; the row holds {row.sql_constraint!r}')
        return problems
    for number, rule in found:
        if number != row.number:
            problems.append(f'{row.column}: {row.sql_file} spells {rule!r}, so it holds '
                            f'{number}, and the owner holds {row.number}')
        elif rule != row.sql_constraint:
            problems.append(f'{row.column}: {row.sql_file} spells {rule!r}, and the row holds '
                            f'{row.sql_constraint!r}')
    return problems


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


def board_word_map_keys(board_text, language):
    """The key names of one word map of annotator/board.js, in the order of the file."""
    home = (BOARD_WORD_MAP_EN, BOARD_WORD_MAP_ZH)[language == 'zh'].search(board_text)
    return tuple(BOARD_WORD_KEY.findall(home.group(1))) if home else ()


def board_word_map_problems(board_text, statuses):
    """The word maps of annotator/board.js that do not hold ``statuses``, one line each.

    ``board_text`` replaces the file of the checkout, so a case can measure a planted
    copy.  The board holds two maps, the English one and the Chinese one, and each map
    keys the three words of the night in the order of the tuple.  A browser cannot read a
    python name, so the map repeats the word as its key and this reader holds the copy
    equal to the tuple.  The reader reads every key of a map, so a word added to a map, a
    word lost and a word that moved each fail here.  The reader reports a change of the
    key list of a map as a change of the list, because the list of the map is longer than
    the tuple.  The count of ``BOARD_PAGE_KEYS`` records the list of the board today.
    """
    problems = []
    for language in ('en', 'zh'):
        keys = board_word_map_keys(board_text, language)
        if keys != BOARD_PAGE_KEYS:
            added = [key for key in keys if key not in BOARD_PAGE_KEYS]
            lost = [key for key in BOARD_PAGE_KEYS if key not in keys]
            problems.append(f'BOARD WORD MAP {language}: the map keys {list(keys)}; the map '
                            f'held {list(BOARD_PAGE_KEYS)}, so this board page changed '
                            f'(added {added}, lost {lost})')
        found = [key for key in keys if key in tuple(statuses)]
        if found != list(statuses):
            problems.append(f'BOARD WORD MAP {language}: annotator/board.js spells {found}; '
                            f'the tuple publishes {list(statuses)}')
    if not problems and tuple(statuses) != TOURNAMENT_STATUSES:
        problems.append(f'THE TUPLE PUBLISHES {list(statuses)}; the board spells '
                        f'{list(TOURNAMENT_STATUSES)}')
    return problems


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


@dataclass(frozen=True)
class OneNumber:
    """One SQL rule that holds one number, and the Python owner of that number.

    Round 82 added this row kind.  A word domain holds a value list (``Pair``) and a bound
    holds two ends (``Bound``); a width holds one number, so the two readers of those kinds
    find neither side of it.  ``sql_constraint`` is written as an f-string over the owner
    constant, so a number that moves in the owner fails the cases below until the migration
    moves too.
    """

    column: str            # "face_embeddings.embedding": the SQL table and column
    sql_file: str          # the migration that holds the rule
    sql_constraint: str    # the exact rule text, as the migration writes it
    owner: str             # the module that owns the number
    python: str            # the name of the constant that owns the number
    number: int            # the number the owner holds


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

#: The one-number rules this module binds.  Three columns hold the width of a face
#: embedding, and ``src/face_id.py`` owns that width as ``EMBEDDING_DIM``.  The rule text of
#: each row is an f-string over the constant, so a change of the width moves the row with
#: the owner, and the row then disagrees with the migration text until the migration moves
#: too.  The two rules of ``identity_clusters`` whose number has no Python owner stand in
#: ``ONE_NUMBERS_DEFERRED`` below, with the measured reason of each one.
ONE_NUMBERS = (
    OneNumber(column='identity_clusters.face',
              sql_file='0002_user_data.sql',
              sql_constraint=f'CHECK (face IS NULL OR cardinality(face) = {EMBEDDING_DIM})',
              owner='src/face_id.py',
              python='EMBEDDING_DIM',
              number=EMBEDDING_DIM),
    OneNumber(column='identity_face_samples.embedding',
              sql_file='0002_user_data.sql',
              sql_constraint=f'CHECK (cardinality(embedding) = {EMBEDDING_DIM})',
              owner='src/face_id.py',
              python='EMBEDDING_DIM',
              number=EMBEDDING_DIM),
    OneNumber(column='face_embeddings.embedding',
              sql_file='0002_user_data.sql',
              sql_constraint=f'CHECK (cardinality(embedding) = {EMBEDDING_DIM})',
              owner='src/face_id.py',
              python='EMBEDDING_DIM',
              number=EMBEDDING_DIM),
)

#: The one-number rules whose number has no Python owner, and the measured reason of each
#: one.  The completeness case reads this table, so a new one-number rule cannot enter a
#: migration without a row of ``ONE_NUMBERS`` or a reason here.
ONE_NUMBERS_DEFERRED = {
    'identity_clusters.body_dim':
        'CHECK (body_dim IN (128)) is the width of the vendored OSNet body embedding.  The '
        'shipped tree holds no constant for that width (measured, round 82: only '
        'src/face_id.py EMBEDDING_DIM matches a width name), so a row of ONE_NUMBERS would '
        'name no owner.  The migration stays the owner of the number.',
    'identity_clusters.body_bank':
        'CHECK (body_dim IS NOT NULL OR cardinality(body_bank) = 0) refuses a bank that '
        'holds points while the former face is NULL.  The zero is a structural rule, not a '
        'width, so no Python constant owns it.',
}

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
    # The night's status has two copies on the far side of a language wall: the CHECK of
    # the migration and the two word maps of annotator/board.js.  Round 91 gave the three
    # words the python home TOURNAMENT_STATUSES, imported above, and the case below holds
    # that tuple, the pair table and the two maps of the board to one order.
    Pair(domain='tournaments.status',
         values=('registration', 'active', 'complete'),
         sql_file='0002_user_data.sql',
         sql_table='tournaments',
         sql_column='status',
         sql_constraint="CHECK (status IN ('registration','active','complete'))",
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
                     'NOTE_MAX = 4000 at :50 and reads it at :915 and :1346, and '
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

#: One word domain has no Python copy of this shape, so no pair exists.  The table
#: states the measurement, and a later copy fails the completeness case.  Round 91
#: removed the ``tournaments.status`` row of this table: annotator/operations.py now
#: publishes that domain as the tuple TOURNAMENT_STATUSES, so the table above binds
#: the pair and the completeness case finds the python copy.
NO_PYTHON_COPY = (
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
        of the constant must reach the pair table.  Round 91 added the same read for the
        night's status: the pair table holds the three words as a literal, because the pair
        is the record of the migration text, and this case holds that literal to
        ``TOURNAMENT_STATUSES`` in annotator/operations.py.
        """
        cases = (('event_verdicts.shooter', SHOOTER_WORDS),
                 ('track_seeds.label', SEED_ROLES),
                 ('tournaments.status', TOURNAMENT_STATUSES))
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

    def test_each_one_number_rule_holds_its_owner(self):
        """For each one-number rule, the migration text and the owner constant must agree.

        Round 82 added this case.  ``identity_clusters.face``,
        ``identity_face_samples.embedding`` and ``face_embeddings.embedding`` hold the width
        of an embedding, and ``src/face_id.py`` owns that width as ``EMBEDDING_DIM``.  A
        value that the database accepts can then fail in Python, or the other way round.
        """
        problems = []
        for row in ONE_NUMBERS:
            problems += one_number_problems(row)
        self.assertEqual([], problems,
                         'a SQL one-number rule and its Python owner disagree:\n'
                         + '\n'.join(problems))

    def test_every_one_number_rule_of_the_migrations_is_bound(self):
        """Each one-number rule of the migrations must have one row or one reason.

        The case fails with the list of the rules that no record names, so a new width
        cannot be added without a Python owner and a case.
        """
        bound = {row.column for row in ONE_NUMBERS}
        unbound = sorted(f'{table}.{column} = {number}  ({rule})'
                         for _, table, column, number, rule in migration_one_numbers()
                         if f'{table}.{column}' not in bound | set(ONE_NUMBERS_DEFERRED))
        self.assertEqual([], unbound,
                         'these SQL one-number rules hold no row in '
                         'tests/test_sql_domain_parity.py. Name the owner constant, add the '
                         'rule to ONE_NUMBERS, and add a case; or state the measured reason '
                         'in ONE_NUMBERS_DEFERRED: ' + repr(unbound))

    def test_the_one_number_report_names_an_unbound_rule(self):
        """The completeness rule must report an unbound one-number rule, and not stay quiet.

        The case drops the face width from the table and measures the report that the
        completeness case above would print for it.
        """
        kept = [row for row in ONE_NUMBERS if row.column != 'identity_clusters.face']
        bound = {row.column for row in kept}
        reported = sorted(f'{table}.{column} = {number}  ({rule})'
                          for _, table, column, number, rule in migration_one_numbers()
                          if f'{table}.{column}' not in bound | set(ONE_NUMBERS_DEFERRED))
        self.assertEqual(['identity_clusters.face = 512  '
                          '(CHECK (face IS NULL OR cardinality(face) = 512))'], reported,
                         'a row that the table drops is named, with its rule')

    def test_the_one_number_report_names_a_drifted_owner(self):
        """The case must report a one-number row whose constant holds another number.

        This is one half of the defect the module exists for: the migration keeps its
        number, the owner moves to another one, and no other case fails.
        """
        row = [entry for entry in ONE_NUMBERS if entry.column == 'identity_clusters.face'][0]
        drifted = replace(row, number=row.number + 1)
        problems = one_number_problems(drifted)
        self.assertTrue(any('EMBEDDING_DIM' in problem for problem in problems),
                        'the drifted owner is reported through its constant name; the guard '
                        'answered ' + repr(problems))

    def test_the_one_number_rule_reports_a_planted_drift(self):
        """The case must report a migration copy whose one number differs.

        Round 82 plants the drift of the face width in the migration text: the number of the
        owner becomes one more than the number of the migration, so the case holds whatever
        number the owner states now.
        """
        row = [entry for entry in ONE_NUMBERS if entry.column == 'identity_clusters.face'][0]
        sql = source(f'db/migrations/{row.sql_file}')
        planted = sql.replace(f'cardinality(face) = {EMBEDDING_DIM}',
                              f'cardinality(face) = {EMBEDDING_DIM + 1}')
        self.assertNotEqual(sql, planted, 'the case plants the drift of the face width')
        problems = one_number_problems(row, planted)
        self.assertTrue(any(str(EMBEDDING_DIM + 1) in problem for problem in problems),
                        'the planted number is reported; the guard answered ' + repr(problems))

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

    def test_the_board_word_maps_read_the_tournament_statuses(self):
        """Both word maps of annotator/board.js must hold the three words, in order.

        Round 91 gave the night's status the python home ``TOURNAMENT_STATUSES``.  The
        migration repeats the words in a CHECK, and this test module reads that text.
        The board cannot import python, so it repeats the words in two word maps, and
        the module scanner reads ``*.py`` only, so it cannot see the copies.  This case
        reads the board as text and holds the three keys of that domain, in both maps,
        equal to the tuple.  The helper also reads the whole key list of each map, so a
        word added to the board page fails here as well.
        """
        problems = board_word_map_problems(source('annotator/board.js'), TOURNAMENT_STATUSES)
        self.assertEqual([], problems,
                         'the board words and annotator/operations.py disagree on the '
                         'night status:\n' + '\n'.join(problems))

    def test_the_board_word_map_rule_reports_a_planted_word(self):
        """A word added to a word map of the board must fail the case above.

        The helper reads the file text, so this case plants one more key in a copy of that
        text and measures the answer of the same helper.  The answer names the new key,
        because the key list of a map is the record of the board page.  The case counts the
        anchor before it plants the word, so a lost anchor fails here with its own message.
        """
        anchor = "      registration: 'Registration open',"
        board = source('annotator/board.js')
        self.assertEqual(1, board.count(anchor),
                         'this case needs one anchor line in the English map of the board')
        planted = board.replace(anchor, "      abandoned: 'Abandoned',\n" + anchor, 1)
        self.assertNotEqual(board, planted, 'this case plants one more key in the English map')
        problems = board_word_map_problems(planted, TOURNAMENT_STATUSES)
        self.assertTrue(any('abandoned' in problem for problem in problems),
                        'the planted word is reported; the guard answered ' + repr(problems))


# The ball label domain stands in three realms with three spellings, and no case compared
# any pair until round 77.  The service owns what it accepts.  The console is a static
# file, so it states its own two names for the same domain.  The migration held the bound
# in a regular expression over the jsonb text form before either name existed, and a
# migration is applied history, so that expression stays as it is.  The table below names
# the three spellings, and the cases at the end of this module hold them equal.
#: One ``const BALL_LABEL_<end> = <number>;`` line of the console file.
CONSOLE_BOUND_HOME = re.compile(r'^const (BALL_LABEL_[A-Z]+) = (-?\d+);', re.MULTILINE)
#: The name table of the console, whose keys are the labels the file can draw.
CONSOLE_NAMES_HOME = re.compile(r'^const NAMES = \{(.*?)\};', re.MULTILINE | re.DOTALL)
#: One key of the name table, as the console spells it.
CONSOLE_NAME_KEY = re.compile(r'(\d+):')
#: One ``(column)::text ~ 'pattern'`` rule of a migration, and its jsonb column.
SQL_TEXT_RULE = re.compile(r"\((\w+)\)::text ~ '([^']*)'")


@dataclass(frozen=True)
class TextBound:
    """One number domain that no ``BETWEEN`` rule and no ``<=`` rule of a migration states.

    ``BOUNDS`` reads the ``BETWEEN`` rules and the ``<=`` rules of the migrations.  A
    regular expression over the jsonb text form is invisible to that table, so this row
    names the three spellings of one domain, and the cases compare them.
    """
    column: str          # the jsonb column, as 'table.column'
    sql_file: str        # the migration that holds the rule
    sql_regex: str       # the one regular expression of that rule
    owner: str           # the module that owns the two numbers
    owner_read: str      # the gate line of the owner, which reads the two names
    bound: tuple         # (('BALL_LABEL_MIN', 0), ('BALL_LABEL_MAX', 15)), by import
    console: str         # the static console file, which states its own two names
    console_read: str    # the loop line of the console, which reads its two names


TEXT_BOUNDS = (
    TextBound(column='ball_labels.label',
              sql_file='0002_user_data.sql',
              sql_regex='^(1[0-5]|[0-9])$',
              owner='annotator/unified_server.py',
              owner_read='type(label) is int and BALL_LABEL_MIN <= label <= BALL_LABEL_MAX',
              bound=(('BALL_LABEL_MIN', BALL_LABEL_MIN), ('BALL_LABEL_MAX', BALL_LABEL_MAX)),
              console='annotator/label.html',
              console_read='for (let nn = BALL_LABEL_MIN; nn <= BALL_LABEL_MAX; nn++)'),
)


def domain_texts(low, high):
    """The jsonb text form of each number of one closed domain, as one list."""
    return [str(number) for number in range(low, high + 1)]


def text_bound_problems(row, console_text=None, sql_text=None, owner_text=None):
    """The spellings of one text bound that disagree, as one line each.

    The answer is empty when the two names of the owner, the gate of the owner, the two
    names of the console, the name table of the console and the rule of the migration
    hold the same domain.  The three texts replace the files of the checkout, so a case
    can measure a planted copy.
    """
    problems = []
    ends = dict(row.bound)
    low, high = ends['BALL_LABEL_MIN'], ends['BALL_LABEL_MAX']
    owner_text = source(row.owner) if owner_text is None else owner_text
    console_text = source(row.console) if console_text is None else console_text
    sql_text = source(f'db/migrations/{row.sql_file}') if sql_text is None else sql_text
    table, _, column = row.column.partition('.')
    # The owner: the gate reads the two names, and the names hold the two numbers.
    if owner_text.count(row.owner_read) != 1:
        problems.append(f'{row.column}: {row.owner} reads its two names '
                        f'{owner_text.count(row.owner_read)} times, not once, in the gate '
                        f'{row.owner_read!r}')
    # The console: one name for each end, one loop that reads the two names, and a name
    # table whose keys are the labels of the same domain.
    homes = dict(CONSOLE_BOUND_HOME.findall(console_text))
    for name in ('BALL_LABEL_MIN', 'BALL_LABEL_MAX'):
        if name not in homes:
            problems.append(f'{row.column}: {row.console} states no {name}; the owner '
                            f'holds {ends[name]}')
        elif int(homes[name]) != ends[name]:
            problems.append(f'{row.column}: {row.console} states {name} = {homes[name]}; '
                            f'the owner holds {ends[name]}')
    if console_text.count(row.console_read) != 1:
        problems.append(f'{row.column}: {row.console} reads its two names '
                        f'{console_text.count(row.console_read)} times, not once, in the '
                        f'loop {row.console_read!r}')
    names = CONSOLE_NAMES_HOME.search(console_text)
    if names is None:
        problems.append(f'{row.column}: {row.console} holds no NAMES table')
    else:
        keys = sorted(int(key) for key in CONSOLE_NAME_KEY.findall(names.group(1)))
        if keys != list(range(low, high + 1)):
            problems.append(f'{row.column}: {row.console} names the labels {keys}; the '
                            f'domain is {low} to {high}')
    # The migration: one text rule on the column, and the rule accepts the domain and
    # nothing outside its two edges.
    blocks = dict(tables_in(sql_text))
    rules = [pattern for name, pattern in SQL_TEXT_RULE.findall(blocks.get(table, ''))
             if name == column]
    if len(rules) != 1:
        problems.append(f'{row.column}: {row.sql_file} holds {len(rules)} '
                        f'``{column}::text`` rules; the row names one')
    elif rules[0] != row.sql_regex:
        problems.append(f'{row.column}: {row.sql_file} spells the rule {rules[0]!r}; the '
                        f'row names {row.sql_regex!r}')
    else:
        rule = re.compile(rules[0])
        refused = [text for text in domain_texts(low, high) if not rule.match(text)]
        if refused:
            problems.append(f'{row.column}: {row.sql_file} refuses {refused} inside the '
                            f'domain {low} to {high}')
        outside = [str(end) for end in (low - 1, high + 1) if rule.match(str(end))]
        if outside:
            problems.append(f'{row.column}: {row.sql_file} accepts {outside} outside the '
                            f'domain {low} to {high}')
    return problems


class BallLabelDomainTests(unittest.TestCase):
    """The ball label domain: one number, three spellings, one case that holds them.

    The route accepts a label of 0 to 15 and refuses 16 and -3, and
    tests/test_unified_server.py measures that behaviour at both edges.  The console draws
    one button for each label of the same domain, and the migration refuses a stored
    number outside it.  Before round 77 nothing compared the three texts.
    """

    def test_the_ball_label_domain_holds_one_bound_in_three_realms(self):
        """Each spelling of the ball label domain must agree with the other two."""
        problems = []
        for row in TEXT_BOUNDS:
            problems.extend(text_bound_problems(row))
        self.assertEqual([], problems,
                         'the ball label domain disagrees with itself:\n'
                         + '\n'.join(problems))

    def test_the_ball_label_rule_refuses_the_number_outside_each_edge(self):
        """The migration rule must accept both edge numbers and refuse both neighbours.

        The answer is the answer of the database, because the case asks the rule text
        itself, and the rule stays the one home of the SQL side of the domain.
        """
        row = TEXT_BOUNDS[0]
        ends = dict(row.bound)
        rule = re.compile(row.sql_regex)
        for outside, inside in ((ends['BALL_LABEL_MIN'] - 1, ends['BALL_LABEL_MIN']),
                                (ends['BALL_LABEL_MAX'] + 1, ends['BALL_LABEL_MAX'])):
            self.assertTrue(rule.match(str(inside)),
                            f'{row.sql_regex!r} must accept {inside}')
            self.assertFalse(rule.match(str(outside)),
                             f'{row.sql_regex!r} must refuse {outside}, one step outside '
                             f'{inside}')

    def test_the_ball_label_rule_reports_a_planted_widen(self):
        """A console that states a wider domain must fail the case above.

        This is the defect round 77 measured: the console held the number in its loop, the
        gate held it in a comparison, and the migration held it in a regular expression,
        so a change of one copy left the other two stating the old bound.
        """
        row = TEXT_BOUNDS[0]
        console = source(row.console)
        planted = console.replace('const BALL_LABEL_MAX = 15;', 'const BALL_LABEL_MAX = 16;')
        self.assertNotEqual(console, planted, 'the case plants a wider console domain')
        problems = text_bound_problems(row, console_text=planted)
        self.assertTrue(any('BALL_LABEL_MAX = 16' in problem for problem in problems),
                        'the planted console bound is reported; the guard answered '
                        + repr(problems))
