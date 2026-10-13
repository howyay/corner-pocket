"""The identity of a refusal: python owns it, and the console reads it.

The service writes each refusal sentence in English.  The console (annotator/ops.js) held its
own Chinese copy of 48 of those sentences, keyed by the English text.  A rewording in python
then dropped the Chinese, and no test caught it.

``annotator/refusals.py`` owns that identity now: one stable code and one Chinese sentence for
each refusal the console must know.  This module walks the modules that raise, and the registry
rows that refuse a missing payload field.  A new refusal cannot arrive without a row, and a row
cannot name a sentence that no raise site and no registry row states.  Every raised sentence has
a row: the 48 that moved out of the console, and the 121 that had no Chinese line and were given
one.

The module that raises is the fourth entry of the list below.  ``annotator/twitch_vod_source.py``
raises the query refusal, and ``annotator/operations.py`` and ``annotator/unified_server.py`` pass
its sentence on, so the walk reads the raise site itself.  That walk also finds sentences this
module judges and keeps in English: ``JUDGED_SENTENCES`` holds each one, with the fact that proves
the decision.  Those sentences have no row, and the table and the judged list together name every
raised sentence.
"""
import ast
import hashlib
from pathlib import Path
import unittest

import console_text
from annotator import refusals
from annotator.unified_server import APIError, operator_message, refusal_body

ROOT = Path(__file__).resolve().parents[1]
# The modules that raise a refusal sentence the operator reads.  The route that answers
# (annotator/unified_server.py) builds one body for both of them.  The database store
# (src/store_pg.py) raises the three sentences of the operations document too, so its
# raise sites are read here as well: a fourth sentence in that module fails this walk.
# The Twitch VOD source states the query refusal its caller passes on, so the raise site itself
# is the fourth owner: a rewording there drops the code the console reads.  The two callers are
# annotator/operations.py vod_id() and annotator/unified_server.py replay_request().
RAISING_MODULES = ('annotator/operations.py', 'annotator/unified_server.py',
                   'src/store_pg.py', 'annotator/twitch_vod_source.py')
CONSOLE = 'annotator/ops.js'
RAISER = 'annotator/twitch_vod_source.py'

# The two classes that build a registry row, and the argument a row states a refusal in.  A row
# refuses a missing payload field with the second element of one ``requires`` pair, and that
# sentence reaches the operator through ``Operation.refuse_missing`` (annotator/operations.py),
# so it is a sentence this table must name.  ``Operation`` states the argument as its fourth
# positional argument.  ``OperatorAction`` states it by name, because its fourth positional
# argument is ``takes``: a pair read from that position would be a mistake.
REGISTRY_NAMES = ('Operation', 'OperatorAction')
REQUIRES_POSITION = {'Operation': 3}

# How many raised sentences carry no row, no judged entry and no waiting entry.  The console
# shows its generic Chinese line for each one, and the English sentence stays.  This number is
# a decision, not a measurement: change it only when you decide about a sentence.  It reached
# zero when the 121 sentences that had no Chinese line were given a row, and it stays zero:
# JUDGED_SENTENCES holds every sentence the widened walk reads that stays English by a fact,
# and UNROWN_SENTENCES holds the sentences that wait for the decision of the Lead.
RAISED_SENTENCES_WITHOUT_A_ROW = 0

# The console owns its own English/Chinese word pairs (annotator/ops.js ``words``).  One pair
# repeats a refusal sentence by coincidence: the enroll form shows it for a name that is a bye
# placeholder.  The pair has its own English text and its own purpose, so it stays.  A new copy
# of a refusal sentence in javascript fails this test.  tests/console_text.py owns that fact and
# the one below it, as one row per exception.  This module reads the rows and holds neither
# literal, so the two facts cannot disagree with the copy the job module reads.

# One console sentence contains the words of a refusal sentence inside a longer line of its own:
# annotator/app.js says 'Frame inference or JPEG encoding failed; check local detector weights
# and runtime' for the live panel.  That line has its own purpose and its own longer text, so it
# stays.  A pair is (file, sentence): the scan below stays a plain substring search, so a new
# copy of a refusal sentence in javascript still fails this test.

# The 48 Chinese sentences as the console held them before round 41.  This digest is the record
# of the move: the table left javascript byte for byte, and no translation happened.  The 121
# rows added after them were written below those 48 and stay there, so the moved block is still
# the table's first MOVED_ROWS rows.
MOVED_ROWS = 48
CHINESE_SENTENCES_DIGEST = '194fce1ca9d59243f67f9994dc1054ea14dbec8e'
SENTENCES_DIGEST = '4c1f5c7e255f55dbcd69b0051b58f9374e47a2c4'

# The whole table, both languages.  The English key is the sentence a raise site or a registry
# row states, and the Chinese is the line the operator reads: a rewording of either one is a
# decision, not an accident.  Three rows arrived with src/store_pg.py, the database store: it
# raised three sentences of its own, and a sentence without a row reaches the operator as
# English only.  Eight more arrived with the registry rows of annotator/operations.py, whose
# ``requires`` pairs refused a missing payload field in English only.
TABLE_SENTENCES_DIGEST = 'b9854f755c9c00a180e38e1ed7e523c18b296825'
TABLE_CHINESE_DIGEST = '80940b29804ce66c83b2b94bd2e696521793238d'

# The sentences annotator/twitch_vod_source.py raises and this module judges to stay English.
# The key is the owner path, the line of the raise site and the sentence; the value is the fact
# that proves the decision.  The guard reads each sentence from that owner, so the sentence
# stands here no third time.  A fault of the network and the TLS client of this box is judged
# too: the console can phrase one act for it, so those sites are reported to the Lead rather
# than listed here.  A sentence that a console phrase cannot help does not belong in
# annotator/refusals.py: that row is a decision for the Lead, because it changes what the
# console can say.
JUDGED_SENTENCES = {
    f'{RAISER}:213: Twitch thumbnail request failed; check network and TLS connectivity': (
        '_validate_thumb returns this sentence inside the picture fetch, and vod_import '
        'keeps the row and gives it no thumbnail, so nothing reaches the operator'),
    f'{RAISER}:218: Twitch returned an empty preview picture': (
        'the reached raise site tests the picture body of the fetch that _validate_thumb '
        'accepted, so a fault of the body is not a network fault'),
    f'{RAISER}:238: Twitch returned an invalid API response': (
        'the raise site reads the body that the GraphQL answer returned, so the transport '
        'of the request already succeeded'),
    f'{RAISER}:253: Expected a canonical Twitch channel login': (
        'the check reads a saved source of this box, and the login is lowercased before the '
        'watch, so a Twitch answer cannot reach this raise site'),
    f'{RAISER}:378: Twitch returned no playable VOD variant': (
        'the raise site counts the variants of a Twitch master playlist that loaded, so the '
        'console can phrase no act for it'),
    f'{RAISER}:393: Twitch returned an invalid VOD media playlist': (
        'the reached raise site names a playlist body that loaded, so the transport of the '
        'request already succeeded'),
    f'{RAISER}:399: Twitch returned a playlist that is not a finished VOD': (
        'the raise site reads the playlist type of a Twitch answer that loaded, so the '
        'console can phrase no act for it'),
    f'{RAISER}:456: rate must be a positive number': (
        'VodRealtimeCapture reads the rate that replay_request already checked '
        '(annotator/unified_server.py), and no other caller starts a live replay'),
    f'{RAISER}:458: start_s must be a non-negative number': (
        'VodRealtimeCapture reads start_s that replay_request already checked '
        '(annotator/unified_server.py), and no other caller starts a live replay'),
    f'{RAISER}:460: max_catchup_s must be a positive number': (
        'VodRealtimeCapture reads a max_catchup_s that no request carries, so the default '
        'of the constructor is the only value a live replay gives it'),
}

# How many sentences this module judges.  The number is a decision: a sentence that joins the
# judged list or leaves it fails the case below until a writer reads the fact again.
JUDGED_SENTENCE_COUNT = 10

# The sentences the widened walk surfaced that have no row and no judgement yet.  Each one
# reaches the operator as English only, and the console shows its generic Chinese line for it.
# A row in annotator/refusals.py would give it a code and a Chinese sentence, and that row
# changes what the console can say, so the Lead decides it.  Each line number is the raise site
# this round surfaced, and each sentence is read from that site.  The five are one class: a
# value the operator sent, or a saved source of this box that Twitch does not answer.  The
# value is the file and the line of the raise site, separated by a colon.
UNROWN_SENTENCES = {
    f'{RAISER}:209': 'the broadcast a preview picture was asked for is gone from Twitch',
    f'{RAISER}:259': 'a saved source of this box names a channel Twitch does not answer',
    f'{RAISER}:232': 'the API helper reports the network of this box, over both call sites',
    f'{RAISER}:373': 'the resolver reports the network of this box for the master playlist',
    f'{RAISER}:385': 'the resolver reports the network of this box for the media playlist',
}

# How many surfaced sentences wait for that decision.  The number is a decision too: a sentence
# that joins the set or leaves it fails the case below.
UNROWN_SENTENCE_COUNT = 5

_SENTENCES = {}


def raised_sentence(node):
    """The sentence a raise statement passes first, or None.

    A plain string constant counts.  A name counts too when it is bound to a sentence of
    this table: annotator/operations.py and src/store_pg.py raise the three sentences of
    the operations document by name (``JSON_OBJECT_REQUIRED`` and its two neighbours), so
    a walk that read string constants only would lose those sentences.  An f-string
    builds its pieces, not a sentence, so it stays out.
    """
    if not isinstance(node, ast.Raise) or not isinstance(node.exc, ast.Call) or not node.exc.args:
        return None
    first = node.exc.args[0]
    if isinstance(first, ast.Constant) and isinstance(first.value, str):
        return first.value
    if isinstance(first, ast.Name):
        held = getattr(refusals, first.id, None)
        if isinstance(held, str) and held in refusals.REFUSALS:
            return held
    return None


def requires_argument(node):
    """The ``requires`` argument of one registry call, or None.

    A call is one row of a registry: ``Operation`` (annotator/operations.py) or
    ``OperatorAction`` (annotator/unified_server.py).  A name that builds neither row stays
    out.  The argument comes from the keyword when one is present, otherwise from the
    position of ``REQUIRES_POSITION``.
    """
    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
        return None
    if node.func.id not in REGISTRY_NAMES:
        return None
    for keyword in node.keywords:
        if keyword.arg == 'requires':
            return keyword.value
    position = REQUIRES_POSITION.get(node.func.id)
    if position is not None and len(node.args) > position:
        return node.args[position]
    return None


def requires_sentence(node):
    """The sentence one ``requires`` pair states second, or None.

    A pair is ``(field, refusal)``.  Both elements are plain string constants in the two
    registries, so a pair whose elements are something else stays out: an f-string builds its
    pieces, not a sentence.
    """
    if not isinstance(node, ast.Tuple) or len(node.elts) != 2:
        return None
    field, refusal = node.elts
    if not (isinstance(field, ast.Constant) and isinstance(field.value, str)):
        return None
    if isinstance(refusal, ast.Constant) and isinstance(refusal.value, str):
        return refusal.value
    return None


def registry_sentences(node):
    """Every sentence the ``requires`` pairs of one registry call state, else none."""
    argument = requires_argument(node)
    if argument is None:
        return set()
    found = set()
    for pair in ast.walk(argument):
        sentence = requires_sentence(pair)
        if sentence is not None:
            found.add(sentence)
    return found


def raised_sentences(relative_path):
    """Every distinct refusal sentence this module states.

    Two owners state one in these modules: an ``ast.Raise``, and the ``requires`` pair of a
    registry row.  The sentence is read through the readers above: a plain string constant, a
    name that the refusal table holds, or the second element of a pair.  A sentence that an
    f-string builds is not a string this table can name: its pieces are fragments, not
    sentences.
    """
    if relative_path not in _SENTENCES:
        found = set()
        for node in ast.walk(ast.parse((ROOT / relative_path).read_text())):
            sentence = raised_sentence(node)
            if sentence is not None:
                found.add(sentence)
            found |= registry_sentences(node)
        _SENTENCES[relative_path] = found
    return set(_SENTENCES[relative_path])


def all_raised_sentences():
    """Every distinct refusal sentence the service can raise, from the modules above."""
    found = set()
    for relative_path in RAISING_MODULES:
        found |= raised_sentences(relative_path)
    return found


def raise_site_lines():
    """Every distinct raised sentence, with the file and the line of its raise sites.

    A failure must name the site a writer opens, so this reading keeps the line of each
    ``ast.Raise``.  The sites come in file order, and one sentence can stand at several
    sites: ``annotator/twitch_vod_source.py`` states the VOD id sentence twice.
    """
    found = {}
    for relative_path in RAISING_MODULES:
        source = (ROOT / relative_path).read_text()
        for node in ast.walk(ast.parse(source)):
            sentence = raised_sentence(node)
            if sentence is not None:
                found.setdefault(sentence, []).append(f'{relative_path}:{node.lineno}')
    return {sentence: sorted(set(sites)) for sentence, sites in found.items()}


def judged_sentences():
    """The sentence of each judged entry, read from its own key.

    The key names the owner, the line of the raise site and the sentence.  The sentence is
    the part after the second colon, so this module holds no second statement of it.
    """
    return {key.split(': ', 1)[1].strip() for key in JUDGED_SENTENCES}


def raised_sentences_without_a_row():
    """The raised sentences with no row, no judgement and no waiting entry.

    A judged sentence stays English by a decision that JUDGED_SENTENCES records, and a
    waiting sentence is a decision the Lead still owes.  Every sentence here needs a row in
    annotator/refusals.py: without one it reaches the operator as English only, and the
    console shows its generic Chinese line.
    """
    return (all_raised_sentences() - set(refusals.REFUSALS) - judged_sentences()
            - unrown_sentences())


def line_sentences():
    """The sentence each raise site of RAISING_MODULES states, keyed by file and line.

    The walk reads the same sites as ``raise_site_lines``, so a list of lines cannot name a
    raise site that the walk does not read.
    """
    return {site: sentence for sentence, sites in raise_site_lines().items() for site in sites}


def unrown_sentences():
    """The sentence of each entry of UNROWN_SENTENCES, read from its raise site.

    The key names the owner and the line; the sentence comes from the file, so this module
    holds no second statement of it.
    """
    sites = line_sentences()
    return {sites[site] for site in UNROWN_SENTENCES if site in sites}


def unrown_sentences_report():
    """The file and the line of every sentence that waits for the decision, with the sentence.

    A writer reads this report to decide a row: it names the site to open and the sentence to
    translate.
    """
    sites = line_sentences()
    return '\n'.join(f'{site}\n  {sites[site]}' for site in UNROWN_SENTENCES)


def declared_names(path):
    """Every name one test module binds, with the line that binds it.

    A binding is an assignment, an annotated assignment or a walrus.  An import is not a
    binding: it reads a name another module owns, and that is the wanted form here.
    """
    tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
    found = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        elif isinstance(node, ast.NamedExpr):
            targets = [node.target]
        else:
            continue
        for target in targets:
            for child in ast.walk(target):
                if isinstance(child, ast.Name):
                    found.append((child.id, node.lineno))
    return found


def console_texts(path):
    """Every string literal in one test module, read from the source.

    The docstrings do not count.  A docstring describes a fact, while a literal holds one.
    """
    tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
    docstrings = {id(node.body[0].value) for node in ast.walk(tree)
                  if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
                  and node.body and isinstance(node.body[0], ast.Expr)
                  and isinstance(node.body[0].value, ast.Constant)
                  and isinstance(node.body[0].value.value, str)}
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings:
            found.append((node.lineno, node.value))
    return found


def digest(values):
    """One sha1 over sorted lines: a stable record of a set of sentences."""
    return hashlib.sha1('\n'.join(sorted(values)).encode()).hexdigest()


class RefusalIdentityTest(unittest.TestCase):
    def test_the_two_backings_raise_the_same_sentences(self):
        """The file backing and the database store refuse a bad request with one sentence.

        Both walk the operations document through the same code, so a rewording in one
        module alone would answer the operator in two different sentences."""
        file_backing = raised_sentences('annotator/operations.py')
        database_store = raised_sentences('src/store_pg.py')
        for sentence in ('JSON object required', 'integer revision required',
                         'State changed; reload before retrying'):
            with self.subTest(sentence=sentence):
                self.assertIn(sentence, file_backing,
                              f'annotator/operations.py no longer raises: {sentence}')
                self.assertIn(sentence, database_store,
                              f'src/store_pg.py no longer raises the same sentence: {sentence}')

    def test_every_code_the_console_reads_has_a_raising_site(self):
        """A code in the table is a promise: a raise site or a registry row states that sentence."""
        produced = all_raised_sentences()
        for sentence, refusal in refusals.REFUSALS.items():
            with self.subTest(code=refusal.code):
                self.assertIn(sentence, produced,
                              f'{refusal.code} names a sentence that nothing states: {sentence}')

    def test_the_table_names_every_raised_sentence(self):
        """One row per raised sentence that needs one, and one judgement or report for the rest.

        Every row names a sentence some raise site or registry row states, and the walked
        sentences fit in three sets: the rows, the judged sentences, and the sentences that
        wait for the decision of the Lead.  A row that is deleted fails here at once.  A new
        sentence that stands in none of the three sets also fails here.
        """
        raised = raised_sentences_without_a_row()
        unrown = unrown_sentences()
        self.assertEqual(UNROWN_SENTENCE_COUNT, len(unrown),
                         f'{len(unrown)} sentences wait for the decision of the Lead, not '
                         f'{UNROWN_SENTENCE_COUNT}.  Each one reaches the operator as English '
                         'only.  Add a row in annotator/refusals.py, then remove the entry '
                         'from UNROWN_SENTENCES:\n' + unrown_sentences_report())
        self.assertEqual(set(refusals.REFUSALS) | judged_sentences() | unrown,
                         all_raised_sentences(),
                         'a raised sentence has no row, or a row names a sentence nothing states')

    def test_no_code_is_dead(self):
        """Every row reaches a refusal body, so no code waits for a route that never sends it."""
        for sentence, refusal in refusals.REFUSALS.items():
            with self.subTest(code=refusal.code):
                body = refusal_body(ValueError(sentence))
                self.assertEqual(body[refusals.CODE_KEY], refusal.code)
                self.assertEqual(body[refusals.ZH_KEY], refusal.zh)
                self.assertEqual(body['error'], sentence)

    def test_the_codes_are_unique_tokens(self):
        codes = [refusal.code for refusal in refusals.REFUSALS.values()]
        self.assertEqual(len(codes), len(set(codes)), 'two rows share a code')
        for code in codes:
            with self.subTest(code=code):
                self.assertRegex(code, r'^[a-z][a-z0-9_]*$',
                                 'a code is a token the console reads, never a sentence')

    def test_a_body_keeps_the_english_sentence_and_adds_the_identity(self):
        refusal = refusals.REFUSALS['Source already added']
        body = refusal_body(ValueError('Source already added'))
        self.assertEqual(body, {'error': 'Source already added',
                                refusals.CODE_KEY: refusal.code,
                                refusals.ZH_KEY: refusal.zh})

    def test_a_body_for_an_unknown_sentence_carries_the_sentence_only(self):
        """A sentence with no row keeps the English text and adds no identity.

        Every raised sentence has a row now, so this case builds its own sentence.  The first
        assertion makes the case fail when a sentence loses its row: a row may not go while its
        sentence still reaches the operator.
        """
        without = sorted(raised_sentences_without_a_row())
        self.assertEqual(without, [],
                         'a raised sentence lost its row in annotator/refusals.py:\n'
                         + '\n'.join('\n'.join(raise_site_lines()[sentence]) + '\n  '
                                     + sentence for sentence in without)
                         + '\nIt now reaches the operator as English only.  Give it a code and a '
                           'Chinese sentence, or remove the raise site.')
        sentence = 'no row names this sentence'
        self.assertNotIn(sentence, refusals.REFUSALS)
        self.assertEqual(refusal_body(ValueError(sentence)), {'error': sentence})

    def test_extra_fields_survive_and_the_table_owns_the_identity(self):
        exc = APIError('Source already added', 409, nightId='n1')
        body = refusal_body(exc, getattr(exc, 'fields', {}))
        self.assertEqual((body['error'], body['nightId']), ('Source already added', 'n1'))
        # A raise site cannot send a wrong identity: the table owns those two keys.
        body = refusal_body(ValueError('Source already added'), {'code': 'fake', 'zh': '假的。'})
        self.assertEqual(body['code'], refusals.REFUSALS['Source already added'].code)

    def test_one_rule_builds_every_refusal_body(self):
        """Both refusal sites call one builder, so a new site cannot forget the identity."""
        source = (ROOT / 'annotator/unified_server.py').read_text()
        calls = [node for node in ast.walk(ast.parse(source))
                 if isinstance(node, ast.Call) and getattr(node.func, 'id', None) == 'refusal_body']
        self.assertEqual(len(calls), 2, 'the two refusal sites no longer build their body here')
        self.assertNotIn('{"error": operator_message(exc)', source,
                         'a refusal body is built by hand, without the identity')

    def test_every_row_survives_the_operator_message(self):
        """The body sends the sentence with absolute paths cut, so a row must keep its text."""
        for sentence in refusals.REFUSALS:
            with self.subTest(sentence=sentence):
                self.assertEqual(operator_message(ValueError(sentence)), sentence)

    def test_the_number_of_raised_sentences_without_a_row_is_pinned(self):
        """The sentences with no Chinese line are a known set.  A new one must be a decision."""
        without = raised_sentences_without_a_row()
        self.assertEqual(
            RAISED_SENTENCES_WITHOUT_A_ROW, len(without),
            f'the raised sentences with no row in annotator/refusals.py changed from '
            f'{RAISED_SENTENCES_WITHOUT_A_ROW} to {len(without)}.  They are now:\n'
            + '\n'.join('\n'.join(raise_site_lines()[sentence]) + '\n  ' + sentence
                         for sentence in sorted(without))
            + '\nEach sentence above reaches the operator as English only.  Add a row with a code '
              'and the Chinese sentence, then set the number in this test.')

    def test_no_javascript_file_holds_a_refusal_sentence(self):
        """No javascript file may hold a refusal sentence: python sends it in the body."""
        files = sorted((ROOT / 'annotator').glob('*.js'))
        self.assertTrue(files, 'the scan found no javascript file to read')
        for path in files:
            text = path.read_text()
            relative = path.relative_to(ROOT).as_posix()
            for sentence in refusals.REFUSALS:
                if (relative, sentence) in console_text.sentences_that_contain_a_refusal():
                    continue
                with self.subTest(file=path.name, sentence=sentence):
                    self.assertNotIn(sentence, text, f'{path.name} holds the English refusal sentence')
        for relative, sentence in console_text.sentences_that_contain_a_refusal():
            with self.subTest(file=relative, sentence=sentence):
                self.assertIn(sentence, (ROOT / relative).read_text(),
                              'the console line this exception names is gone')
        held = {}
        chinese = {refusal.zh for refusal in refusals.REFUSALS.values()}
        for path in files:
            text = path.read_text()
            for line in chinese:
                if line in text:
                    held.setdefault(path.relative_to(ROOT).as_posix(), set()).add(line)
        allowed = {name: set(words.values())
                   for name, words in console_text.words_that_repeat_a_refusal().items()}
        self.assertEqual(allowed, held,
                         'a javascript file holds a refusal sentence, or the console word pair moved')
        # Each exception above is the console's own word pair: the console shows it for its own
        # form check, so it is not a copy of a refusal.
        console = (ROOT / CONSOLE).read_text()
        for words in console_text.words_that_repeat_a_refusal().values():
            for key in words:
                with self.subTest(word=key):
                    self.assertIn(f"t('{key}')", console, 'the console no longer shows this word pair')

    def test_the_console_reads_the_served_identity(self):
        """The console reads the two keys the table declares beside the English sentence."""
        console = (ROOT / CONSOLE).read_text()
        for key in (refusals.CODE_KEY, refusals.ZH_KEY):
            with self.subTest(key=key):
                self.assertIn(f'served.{key}', console,
                              f'the console no longer reads the served {key} field')

    def test_the_moved_sentences_are_the_ones_the_console_held(self):
        """The English keys and the Chinese sentences are the table the console held."""
        moved = list(refusals.REFUSALS)[:MOVED_ROWS]
        self.assertEqual(MOVED_ROWS, len(moved), 'the table lost rows')
        self.assertEqual(SENTENCES_DIGEST, digest(moved),
                         'the English sentences that moved out of the console changed')
        self.assertEqual(CHINESE_SENTENCES_DIGEST,
                         digest(refusals.REFUSALS[sentence].zh for sentence in moved),
                         'a Chinese sentence changed, so the move was not byte for byte')

    def test_the_whole_table_is_pinned_in_both_languages(self):
        """Every row of the table, English and Chinese, is the text a reviewer accepted."""
        self.assertEqual(TABLE_SENTENCES_DIGEST, digest(refusals.REFUSALS),
                         'the English sentences of the table changed')
        self.assertEqual(TABLE_CHINESE_DIGEST,
                         digest(refusal.zh for refusal in refusals.REFUSALS.values()),
                         'a Chinese sentence of the table changed')

    def test_the_raiser_states_the_row_the_console_reads(self):
        """The Twitch VOD source raises the sentence of the vod_id_url_invalid row.

        The walk reads that module now, so this case proves the walk keeps reading it.  The
        sentence comes from the owner row and the raise site: this file states it no third
        time.  The second assertion is the defect this round removes: a rewording at the
        raise site left that row with no raise site at all.
        """
        owner = next(refusal for refusal in refusals.REFUSALS.values()
                     if refusal.code == 'vod_id_url_invalid')
        sentence = next(text for text, refusal in refusals.REFUSALS.items() if refusal is owner)
        self.assertIn(sentence, raised_sentences(RAISER),
                      f'{RAISER} no longer raises the {owner.code} sentence, so the code the '
                      'console reads has no raise site there')
        self.assertEqual({refusals.CODE_KEY: owner.code, refusals.ZH_KEY: owner.zh},
                         refusals.identity_fields(sentence),
                         'the raise site and the row answer different identities')

    def test_every_judged_sentence_comes_from_its_owner_without_a_row(self):
        """A judged sentence stands in the walk, it has no row, and its reason is not empty.

        A sentence that stays English is a decision this module records.  The key names the
        owner and the line that raises the sentence, so a moved raise site fails here.  A
        judged sentence has no row, so refusal_body adds no code and no Chinese for it: the
        console shows its generic Chinese line and keeps the English sentence.  A sentence
        that a raise site hands to refusal_body as a refusal of the request itself belongs in
        the table instead, and the Lead decides that row.
        """
        raised = raised_sentences(RAISER)
        for key, reason in JUDGED_SENTENCES.items():
            path, line, sentence = key.split(':', 2)
            sentence = sentence.strip()
            with self.subTest(sentence=sentence):
                self.assertEqual(RAISER, path, 'a judged entry names another owner')
                self.assertTrue(reason.strip(), 'a judged entry gives no reason')
                self.assertIn(sentence, raised,
                              f'{path}:{line.strip()} no longer raises this sentence, so the '
                              'judgement is stale and the decision needs a new reading')
                self.assertNotIn(sentence, refusals.REFUSALS,
                                 'a judged sentence has a row now, so the row and the judgement '
                                 'disagree: remove the judged entry')

    def test_the_lead_gets_a_row_for_every_sentence_that_waits(self):
        """Every sentence that waits for the decision names its raise site and its sentence.

        The report is the message the Lead reads, so it must name the file and the line to
        open.  No sentence of the set may have a row: a row and a waiting entry disagree.
        """
        sites = line_sentences()
        report = unrown_sentences_report()
        for site in UNROWN_SENTENCES:
            with self.subTest(site=site):
                self.assertIn(site, sites,
                              f'{site} no longer raises a sentence, so the report is stale')
                self.assertIn(site, report, 'the report drops a raise site the Lead must open')
                self.assertNotIn(sites[site], refusals.REFUSALS,
                                 'this sentence has a row now, so the report and the row disagree')

    def test_the_number_of_judged_sentences_is_pinned(self):
        """The judged set is a decision: a sentence that joins it or leaves it fails here."""
        self.assertEqual(JUDGED_SENTENCE_COUNT, len(JUDGED_SENTENCES),
                         f'the judged sentences changed to {len(JUDGED_SENTENCES)}:\n'
                         + '\n'.join(sorted(judged_sentences()))
                         + '\nEach sentence stays English by the fact beside it.  Read the '
                           'new sentence, then set the number in this test.')

    def test_the_console_exception_facts_live_in_one_module(self):
        """One module states each fact, and no test module states it again.

        The three names and the two literals were stated in two test modules before
        tests/console_text.py owned them.  A second statement of one fact can disagree with the
        first, so this case fails when a test module declares one of the names again or writes
        one of the literals again.  The case reads source text, so it sees a module that the
        runner has not loaded yet.
        """
        owner = Path(console_text.__file__).resolve()
        owner_source = owner.read_text(encoding='utf-8')
        missing = [name for name in console_text.DECLARATIONS if name not in owner_source]
        self.assertEqual([], missing,
                         'tests/console_text.py no longer declares these names, so the scan below '
                         'would pass for the wrong reason:\n' + '\n'.join(missing))
        # None of the three names may be bound again in a test module.  The name alone is not the
        # defect: the imports above bind two of them to the owner's view on purpose, and a reader
        # still finds the name in the module he read before.  A second *binding* is the second
        # statement that starts the drift this round removes.
        stated = []
        for path in sorted((ROOT / 'tests').glob('test_*.py')):
            if path.resolve() == owner:
                continue
            for name, line in declared_names(path):
                if name in console_text.DECLARATIONS:
                    stated.append(f'{path.name}:{line}: binds {name} again')
            for line, value in console_texts(path):
                if value in console_text.CONSOLE_EXCEPTION_TEXTS:
                    stated.append(f'{path.name}:{line}: {value}')
        self.assertEqual([], stated,
                         'a test module states a fact that tests/console_text.py owns. Keep one '
                         'row per exception in tests/console_text.py, and read the derived view '
                         'beside it:\n' + '\n'.join(stated))

if __name__ == '__main__':
    unittest.main()
