"""The class hooks and the action names of the shipped annotator pages keep one owner.

Three pairs of shipped files state one agreement.  A reader of this module reads
both sides of each pair, and it names every offender as ``path:line: <line text>``.

**Finding A, the ball label popover.**  The emitter is the function `paintPopover`
of ``annotator/app.js``.  The block at ``annotator/app.js:1844-1847`` writes the
popover markup, and the element at ``annotator/app.js:858`` carries the host hook.
`annotator/app.css` holds the rules of those hooks.  The two action names of the
markup are keys of the dispatcher table of ``annotator/vision-stage.js``, which
starts at ``annotator/vision-stage.js:1456`` and ends with the key at
``annotator/vision-stage.js:1569``.  The pair meets on one page only:
``annotator/ops.html`` loads ``/app.js``, ``/vision-stage.js`` and ``/ops.js``.
`annotator/app.html` is the review template, and no page serves it.

**Finding B, `vs-chiprow`.**  Four emitter sites write the token:
``annotator/ops.js:1240`` and ``annotator/vision-stage.js:652``, ``:1071``,
``:1076``.  Three rules of `annotator/ops.css` hold it: ``annotator/ops.css:353``,
``:549``, ``:1286``.

**Finding C, the VOD chip markup.**  Four lines of `annotator/ops.js` build the
chip: ``:417``, ``:418``, ``:421``, ``:422``.  Each class token of that markup has
a rule in `annotator/ops.css`, at ``annotator/ops.css:1203-1207``.

The tree held no case for these pairs.  The closest case reads another pair:
``tests/test_app_timeline.js:1016`` reads the stylesheet text for ``.stage-popover``
and ``.pop-grid`` only, so it holds no action name and no rule of the other two
families.  The reader of the class tokens of ``annotator/board.css`` stands at
``tests/test_board.js:458``.

This module holds the two sides equal.  A rename on one side alone reddens a case
here, and the failure names the site to open.  The module reads the tokens out of
the emitters and the selectors out of the stylesheets.  It holds no list of the
tokens it expects to pass.

Run: ``./scripts/pool-test.sh python test_js_class_hooks_owner``
"""
from pathlib import Path
import re
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

#: The emitter of the popover markup, and the element that hosts it.
POPOVER_SITE = 'annotator/app.js'
POPOVER_EMIT_RANGE = (1844, 1847)
POPOVER_HOST_LINE = 858

#: The reader of the popover hooks, and the reader of the dispatcher table.
APP_CSS_SITE = 'annotator/app.css'
STAGE_SCRIPT_SITE = 'annotator/vision-stage.js'

#: The head of the dispatcher table.  The reader walks from this line to the line
#: that closes the block, so a table that moves stays one table.
STAGE_TABLE_HEAD = 'const table = {'

#: The four emitter sites of the `vs-chiprow` token, and their stylesheet.
CHIPROW_EMITTER_SITES = (('annotator/ops.js', 1240),
                         ('annotator/vision-stage.js', 652),
                         ('annotator/vision-stage.js', 1071),
                         ('annotator/vision-stage.js', 1076))
CHIPROW_TOKEN = 'vs-chiprow'
OPS_CSS_SITE = 'annotator/ops.css'

#: The four emitter lines of the VOD chip markup, and the classes that the rest of
#: the shell writes too.  A rule of a shared class says nothing about the chip, so
#: the measured rule count of this family holds the four own classes alone.
VOD_CHIP_SITE = 'annotator/ops.js'
VOD_CHIP_EMITTER_LINES = (417, 418, 421, 422)
VOD_CHIP_SHARED = frozenset({'badge', 'muted'})

#: The served page, and the two modules that must meet on it.
OPS_PAGE_SITE = 'annotator/ops.html'
PAGE_SCRIPT_ASSET = re.compile(r'<script\s+src="([^"]+)"')

#: One class attribute of a markup string.
CLASS_ATTRIBUTE = re.compile(r'class="([^"]*)"')

#: One `data-vs-action` name of a markup string.
ACTION_ATTRIBUTE = re.compile(r'data-vs-action="([^"]*)"')

#: One quoted key of the dispatcher table.
DISPATCHER_KEY = re.compile(r"'([a-z][\w-]*)'\s*:")

#: The text that may stand between the name of a class and the `{` of its block while
#: the class stays the target of that block: the brackets of an attribute test, or the
#: colon and the name of a pseudo class.  A space, a comma, an element name or a longer
#: class name ends the text, so the class is no target of that block.  The reader
#: therefore counts `.stage-popover[hidden]` for `stage-popover`, and it counts neither
#: `.pop-row-x` nor `.pop-row button` for `pop-row`.
CLASS_RULE_TAIL = r'(?:\[[^\]]*\]|::?[A-Za-z][\w-]*(?:\([^)]*\))?)*'

#: One class name of a selector line.
CLASS_NAME = re.compile(r'\.([A-Za-z][\w-]*)')

#: The measured size of every scan.  A renamed file, a moved table or a shortened
#: scan changes one of these numbers, and a case below reddens in the same run.
POPOVER_HOOK_COUNT = 5
POPOVER_ACTION_COUNT = 2
POPOVER_STYLESHEET_RULE_COUNT = 6
POPOVER_EMITTER_SITE_COUNT = 2
PAGE_SCRIPT_COUNT = 5
PAGE_MODULE_COUNT = 2
DISPATCHER_KEY_COUNT = 63
CHIPROW_EMITTER_SITE_COUNT = 4
CHIPROW_RULE_SITE_COUNT = 3
CHIPROW_RULE_LINE_COUNT = 3
VOD_CHIP_HOOK_COUNT = 7
VOD_CHIP_EMITTER_SITE_COUNT = 4
VOD_CHIP_RULE_LINE_COUNT = 6


def offline_text(relative_path):
    """The text of one repository file, read as UTF-8."""
    return (ROOT / relative_path).read_text(encoding='utf-8')


def class_tokens(markup):
    """Every class token of one markup string, in the order of the string."""
    return [token for value in CLASS_ATTRIBUTE.findall(markup) for token in value.split()]


def action_names(markup):
    """Every `data-vs-action` name of one markup string, in the order of the string."""
    return ACTION_ATTRIBUTE.findall(markup)


def line_text(relative_path, number):
    """The text of one line of one file, with no end-of-line character."""
    return offline_text(relative_path).splitlines()[int(number) - 1]


def dispatcher_table_end(relative_path, head):
    """The number of the line that closes the block the head line opens."""
    lines = offline_text(relative_path).splitlines()
    for start, line in enumerate(lines):
        if not line.strip().startswith(head):
            continue
        depth = 0
        for number in range(start, len(lines)):
            depth += lines[number].count('{') - lines[number].count('}')
            if depth <= 0:
                return number + 1
    return None


def dispatcher_keys(relative_path, head):
    """`(key, line)` for every quoted key of the dispatcher table."""
    end = dispatcher_table_end(relative_path, head)
    if end is None:
        return []
    lines = offline_text(relative_path).splitlines()
    return [(match.group(1), number)
            for number, line in enumerate(lines[:end], start=1)
            for match in [DISPATCHER_KEY.match(line.strip())] if match]


def code_lines(relative_path):
    """`(line, line text)` for every line of one file that no comment holds.

    A stylesheet explains itself in comments, and a comment names a class that it
    does not define.  This reader drops a line of a comment, so a rule alone
    answers for a class.
    """
    return [(number, line) for number, line in
            enumerate(offline_text(relative_path).splitlines(), start=1)
            if not line.lstrip().startswith(('/*', '*', '//'))]


def class_mention(class_name):
    """One pattern for every line of code that names one class.

    The name must stand alone, so a line of `.pop-row-x` holds no mention of
    `pop-row`.
    """
    return re.compile(r'(?<![\w-])\.' + re.escape(class_name) + r'(?![\w-])')


def style_lines(relative_path, class_name):
    """`(line, line text)` for every line of code of one stylesheet that names a class.

    The name must stand alone.  So the line of `.pop-row` names the class `pop-row`,
    and the line of `.pop-row-x` names another class and does not answer here.
    """
    selector = class_mention(class_name)
    return [(number, line.strip()) for number, line in code_lines(relative_path)
            if selector.search(line)]


def near_lines(relative_path, class_name):
    """`(line, line text)` for every line of code that names a class near one name.

    A near class starts with the name of the class and a hyphen, or the name of the
    class starts with the near class and a hyphen.  Such a line is no rule of the
    class, but a small change of the name makes the emitter and the stylesheet
    disagree, so an offender report names the line.
    """
    answer = []
    for number, line in code_lines(relative_path):
        for token in CLASS_NAME.findall(line):
            if token != class_name and (token.startswith(class_name + '-')
                                       or class_name.startswith(token + '-')):
                answer.append((number, line.strip()))
                break
    return answer


def class_selector(class_name):
    """One pattern for every rule of a stylesheet that targets one class.

    The pattern reads the dot, the name, the tail of `CLASS_RULE_TAIL` and the `{` of
    the block.  A longer class name, for example `.pop-row-x`, or an element name
    after a space, for example `.pop-row button`, does not answer for `pop-row`.
    """
    return re.compile(r'\.' + re.escape(class_name) + CLASS_RULE_TAIL + r'\s*\{')


def selector_defines(relative_path, class_name):
    """`(line, line text)` for every rule of one stylesheet that defines a class.

    A rule holds one declaration block, and the class must be the target of that
    block.  A rule that only extends another rule of the same class or of an element,
    for example `.pop-grid button` or `.stage *, .stage-popover *`, holds no
    declaration of that class alone, so this reader does not count it.  A comment line
    is no rule.
    """
    selector = class_selector(class_name)
    return [(number, line.strip()) for number, line in code_lines(relative_path)
            if selector.search(line)]


def defined_lines(relative_path, class_names):
    """Every line of one stylesheet that holds a rule of the class names."""
    return sorted({number for name in class_names
                   for number, _ in selector_defines(relative_path, name)})


def rule_sites(relative_path, class_names):
    """`(line, line text)` for every rule line of one stylesheet, with no repeat."""
    lines = dict(code_lines(relative_path))
    return [(number, lines[number]) for number in defined_lines(relative_path, class_names)]


def defined_hooks(relative_path, hooks):
    """Every hook pair whose token one rule of the stylesheet defines."""
    return [(token, site) for token, site in hooks
            if selector_defines(relative_path, token)]


def unstyled(relative_path, hooks):
    """The hook pairs that no rule of one stylesheet defines."""
    return [(token, site) for token, site in hooks
            if not selector_defines(relative_path, token)]


def names_offenders(relative_path, hooks, defines):
    """One record for each offender, as `path:line: <line text>` and the class name.

    One hook is a pair of a class token and the site that writes it.  `defines`
    answers True for a token that a stylesheet defines.  A line of a near class of the
    token follows the record, with its file and its line, because such a line is the
    likely cause of the disagreement.  This helper is the reporter of the guard, so a
    case below proves its shape.
    """
    answer = []
    for token, site in hooks:
        if defines(token):
            continue
        record = [f'{site}: {line_text(*site.rsplit(":", 1))}',
                  f'  the class "{token}" has no rule in {relative_path}']
        record += [f'  {relative_path}:{number}: {text}'
                   for number, text in near_lines(relative_path, token)]
        answer.append('\n'.join(record))
    return answer


def unstyled_report(relative_path, hooks):
    """The report of the hook pairs that no rule of one stylesheet defines."""
    return '\n'.join(names_offenders(relative_path, hooks,
                                     lambda token: bool(selector_defines(relative_path, token))))


def script_assets(relative_path):
    """Every `<script src=...>` value of one page, in the order of the page."""
    return PAGE_SCRIPT_ASSET.findall(offline_text(relative_path))


def script_names(relative_path):
    """The bare name of every `<script src=...>` value of one page."""
    return [source.split('?', 1)[0].rsplit('/', 1)[-1] for source in script_assets(relative_path)]


def popover_hooks():
    """`(token, site)` for every class hook the popover emitter writes.

    The block of `POPOVER_EMIT_RANGE` writes the markup, and the element of
    `POPOVER_HOST_LINE` carries the host hook.  The tokens come from the emitted
    markup, and each site is the line that writes the token, so a token that the
    emitter loses leaves this answer at once.
    """
    first, last = POPOVER_EMIT_RANGE
    hooks = [(token, site) for site, tokens in
             class_hook_sites(POPOVER_SITE, range(first, last + 1))
             for token in tokens]
    host = offline_text(POPOVER_SITE).splitlines()[POPOVER_HOST_LINE - 1]
    hooks += [(token, f'{POPOVER_SITE}:{POPOVER_HOST_LINE}') for token in class_tokens(host)]
    seen, answer = set(), []
    for token, site in hooks:
        if token not in seen:
            seen.add(token)
            answer.append((token, site))
    return answer


def popover_actions():
    """`(name, site)` for every action name the popover emitter writes."""
    first, last = POPOVER_EMIT_RANGE
    lines = offline_text(POPOVER_SITE).splitlines()
    seen, answer = set(), []
    for number in range(first, last + 1):
        for name in action_names(lines[number - 1]):
            if name not in seen:
                seen.add(name)
                answer.append((name, f'{POPOVER_SITE}:{number}'))
    return answer


def popover_emitter_sites():
    """The two sites of the popover emitter: its markup block and its host element."""
    first, last = POPOVER_EMIT_RANGE
    return [f'{POPOVER_SITE}:{first}-{last}',
            f'{POPOVER_SITE}:{POPOVER_HOST_LINE}']


def mark_sites(relative_path, token):
    """`(line, line text)` for every line of one file that holds one token."""
    text = offline_text(relative_path)
    return [(number, line.strip())
            for number, line in enumerate(text.splitlines(), start=1)
            if token in line]


def class_hook_sites(relative_path, numbers):
    """`(site, tokens)` for each line of one file that writes a class attribute."""
    lines = offline_text(relative_path).splitlines()
    return [(f'{relative_path}:{number}', class_tokens(lines[number - 1]))
            for number in numbers]


def vod_chip_hooks():
    """`(token, site)` for every class hook of the VOD chip markup.

    The lines of `VOD_CHIP_EMITTER_LINES` build the chip.  The tokens come from
    that markup, so the answer changes with the emitter and not with a list.
    """
    seen, answer = set(), []
    for site, tokens in class_hook_sites(VOD_CHIP_SITE, VOD_CHIP_EMITTER_LINES):
        for token in tokens:
            if token not in seen:
                seen.add(token)
                answer.append((token, site))
    return answer


def vod_chip_own(hooks):
    """`(token, site)` for the class hooks that only the VOD chip markup writes.

    The emitter shares a few generic classes with the rest of the shell, for example
    the badge of a chip.  A rule of such a class says nothing about the chip, so the
    measured rule count of this family holds the own hooks alone.
    """
    return [(token, site) for token, site in hooks if token not in VOD_CHIP_SHARED]


def sites_report(sites):
    """One line per site, as `path:line: <line text>`."""
    return '\n'.join(f'{site}: {text}' for site, text in sites)


class JsClassHooksOwnerTest(unittest.TestCase):
    def test_every_popover_class_hook_has_a_stylesheet_rule(self):
        """The popover hooks of the emitter and the rules of app.css agree.

        The emitter writes the hooks at `annotator/app.js:1844-1847`, and the host
        element carries the hook at `annotator/app.js:858`.  This case reads the
        tokens out of both sites and the selectors out of the stylesheet.  A token
        that loses its rule, or a rule that loses its token, reddens here.
        """
        hooks = popover_hooks()
        self.assertEqual(
            POPOVER_HOOK_COUNT, len(hooks),
            'the popover emitter no longer writes its class hooks, so the pair of '
            f'{POPOVER_SITE} and {APP_CSS_SITE} is not held:\n' + str(hooks))
        offenders = unstyled(APP_CSS_SITE, hooks)
        self.assertEqual(
            [], offenders,
            'a class hook the popover paints has no rule, so the popover loses its '
            'shape:\n' + unstyled_report(APP_CSS_SITE, hooks))
        rules = [(f'{APP_CSS_SITE}:{number}', text) for number, text in
                 rule_sites(APP_CSS_SITE, [token for token, _ in hooks])]
        self.assertEqual(
            POPOVER_STYLESHEET_RULE_COUNT, len(rules),
            f'the {len(hooks)} hooks of the popover no longer meet '
            f'{POPOVER_STYLESHEET_RULE_COUNT} rules of {APP_CSS_SITE}:\n'
            + sites_report(rules))

    def test_every_popover_action_name_is_a_dispatcher_key(self):
        """The action names of the markup and the keys of the table agree.

        The dispatcher table of `annotator/vision-stage.js` starts at the line
        `const table = {` and ends at the line that closes the block.  The page
        listener at `annotator/vision-stage.js:1832` sends a click to this table.
        """
        keys = dispatcher_keys(STAGE_SCRIPT_SITE, STAGE_TABLE_HEAD)
        names = popover_actions()
        known = {key for key, _ in keys}
        self.assertEqual(
            DISPATCHER_KEY_COUNT, len(known),
            f'the dispatcher table of {STAGE_SCRIPT_SITE} no longer holds '
            f'{DISPATCHER_KEY_COUNT} keys, so this reader walks another table:\n'
            + sites_report(keys))
        self.assertEqual(
            POPOVER_ACTION_COUNT, len(names),
            'the popover emitter no longer writes its two action names:\n' + str(names))
        key_sites = [(f'{STAGE_SCRIPT_SITE}:{number}', line_text(STAGE_SCRIPT_SITE, number))
                     for _, number in keys]
        offenders = [f'{site}: {line_text(*site.rsplit(":", 1))}'
                     f'\n  the action "{name}" is no key of the dispatcher table of '
                     f'{STAGE_SCRIPT_SITE}'
                     for name, site in names if name not in known]
        self.assertEqual(
            [], offenders,
            'an action the popover writes reaches no row, so a click on it does '
            'nothing:\n' + '\n'.join(offenders)
            + '\nthe keys of the table stand below with the line of each one:\n'
            + sites_report(key_sites))

    def test_the_served_page_loads_the_emitter_and_the_dispatcher(self):
        """The popover pair meets on one page only, and that page is ops.html.

        The review template `annotator/app.html` is not served: the alias table at
        `annotator/unified_server.py:199` answers the route `/` with `ops.html`, the
        redirect table at `annotator/unified_server.py:204` sends `/app.html` to `/`,
        and the route at `annotator/unified_server.py:2993` hands the template to
        `annotator/ops.js` as a string for the review root.  The dispatcher stands in
        `/vision-stage.js` and the emitter stands in `/app.js`, so
        `annotator/ops.html` must load both of them.
        """
        names = script_names(OPS_PAGE_SITE)
        self.assertEqual(
            PAGE_SCRIPT_COUNT, len(names),
            f'{OPS_PAGE_SITE} no longer loads {PAGE_SCRIPT_COUNT} scripts:\n'
            + '\n'.join(script_assets(OPS_PAGE_SITE)))
        wanted = [Path(STAGE_SCRIPT_SITE).name, Path(POPOVER_SITE).name]
        self.assertEqual(
            PAGE_MODULE_COUNT, len(wanted),
            f'the pair of the popover reads two modules, not {len(wanted)}')
        missing = [name for name in wanted if name not in names]
        self.assertEqual(
            [], missing,
            'the page that shows the review panel loads no module of the popover '
            f'pair, so the two sides never meet:\n{OPS_PAGE_SITE}: {names}')

    def test_every_chiprow_emitter_site_stands_beside_a_stylesheet_rule(self):
        """The four `vs-chiprow` sites of the emitters and the rules of ops.css agree.

        Two modules write the token: `annotator/ops.js` writes it once, and
        `annotator/vision-stage.js` writes it three times.  The stylesheet holds
        three rules.  This case reports both sets.
        """
        sites = [(f'{site}:{number}', line_text(site, number))
                 for site, number in CHIPROW_EMITTER_SITES]
        emitters = [site for site in sites if CHIPROW_TOKEN in class_tokens(site[1])]
        self.assertEqual(
            CHIPROW_EMITTER_SITE_COUNT, len(emitters),
            f'the emitters no longer write {CHIPROW_TOKEN} at '
            f'{CHIPROW_EMITTER_SITE_COUNT} sites.  The expected sites stand below with '
            'the line that each one holds now:\n' + sites_report(sites))
        defined = selector_defines(OPS_CSS_SITE, CHIPROW_TOKEN)
        rules = [(f'{OPS_CSS_SITE}:{number}', text) for number, text in defined]
        self.assertEqual(
            CHIPROW_RULE_LINE_COUNT, len(rules),
            f'{OPS_CSS_SITE} no longer holds {CHIPROW_RULE_LINE_COUNT} rule lines for '
            f'{CHIPROW_TOKEN}, so the row of chips loses its layout:\n' + sites_report(rules))
        self.assertEqual(
            CHIPROW_RULE_SITE_COUNT, len({site for site, _ in rules}),
            f'the {CHIPROW_RULE_LINE_COUNT} rule lines of {CHIPROW_TOKEN} no longer agree '
            f'with {CHIPROW_RULE_SITE_COUNT} sites:\n' + sites_report(rules))
        self.assertEqual(
            [], [site for site, _ in emitters if not defined],
            f'an emitter writes {CHIPROW_TOKEN} and no rule of {OPS_CSS_SITE} holds it, '
            'so the row of chips loses its layout:\n' + sites_report(sites))

    def test_every_vod_chip_class_hook_has_a_stylesheet_rule(self):
        """The class hooks of the VOD chip markup and the rules of ops.css agree.

        The four emitter lines of `annotator/ops.js` build the chip of a linked
        broadcast and the chip of a covered night.  This case reads the tokens out
        of that markup and the selectors out of the stylesheet.
        """
        hooks = vod_chip_hooks()
        self.assertEqual(
            VOD_CHIP_HOOK_COUNT, len(hooks),
            f'the VOD chip markup no longer writes {VOD_CHIP_HOOK_COUNT} class hooks, so '
            f'the pair of {VOD_CHIP_SITE} and {OPS_CSS_SITE} is not held:\n' + str(hooks))
        offenders = unstyled(OPS_CSS_SITE, hooks)
        self.assertEqual(
            [], offenders,
            'a class hook of the VOD chip has no rule, so the chip loses its shape:\n'
            + unstyled_report(OPS_CSS_SITE, hooks))
        rules = [(f'{OPS_CSS_SITE}:{number}', text) for number, text in
                 rule_sites(OPS_CSS_SITE, [token for token, _ in vod_chip_own(hooks)])]
        self.assertEqual(
            VOD_CHIP_RULE_LINE_COUNT, len(rules),
            f'the {len(vod_chip_own(hooks))} own class hooks of the VOD chip no longer '
            f'meet {VOD_CHIP_RULE_LINE_COUNT} rule lines of {OPS_CSS_SITE}.  The four '
            'own hooks are the classes that only this markup writes; the measured '
            'number holds their rule lines alone:\n' + sites_report(rules))

    def test_the_scan_of_each_pair_keeps_its_measured_size(self):
        """The three scans keep the size this module measured, so none passes empty.

        One number per scan.  A number means the count of the sites the scan found
        in the shipped tree on 2026-10-13.  A reader that finds no site answers an
        empty list, and an empty list passes every case above.  These numbers stop
        that silence.
        """
        measured = {
            'popover emitter sites': (len(popover_emitter_sites()), POPOVER_EMITTER_SITE_COUNT),
            'popover class hooks': (len(popover_hooks()), POPOVER_HOOK_COUNT),
            'popover action names': (len(popover_actions()), POPOVER_ACTION_COUNT),
            'popover stylesheet rules': (
                len(defined_lines(APP_CSS_SITE, [token for token, _ in popover_hooks()])),
                POPOVER_STYLESHEET_RULE_COUNT),
            'dispatcher keys': (
                len(dispatcher_keys(STAGE_SCRIPT_SITE, STAGE_TABLE_HEAD)), DISPATCHER_KEY_COUNT),
            'page scripts': (len(script_names(OPS_PAGE_SITE)), PAGE_SCRIPT_COUNT),
            'chiprow emitter sites': (len(CHIPROW_EMITTER_SITES), CHIPROW_EMITTER_SITE_COUNT),
            'chiprow rule sites': (
                len(defined_lines(OPS_CSS_SITE, [CHIPROW_TOKEN])), CHIPROW_RULE_LINE_COUNT),
            'vod chip class hooks': (len(vod_chip_hooks()), VOD_CHIP_HOOK_COUNT),
            'vod chip rule lines': (
                len(rule_sites(OPS_CSS_SITE, [token for token, _ in
                                              vod_chip_own(vod_chip_hooks())])),
                VOD_CHIP_RULE_LINE_COUNT),
            'vod chip emitter sites': (len(VOD_CHIP_EMITTER_LINES), VOD_CHIP_EMITTER_SITE_COUNT),
        }
        for scan, (found, wanted) in measured.items():
            with self.subTest(scan=scan):
                self.assertEqual(
                    wanted, found,
                    f'the scan "{scan}" found {found} sites, not {wanted}.  The number is the '
                    'count this module measured in the shipped tree.  A renamed file, a moved '
                    'table or a shortened walk changes it, and every other case of this module '
                    'then reads less than the pair it holds.')

    def test_a_planted_offender_is_reported_with_its_file_and_line(self):
        """A helper of this module names every offender with its file and its line.

        This case writes a small stylesheet to a temporary file.  The file holds
        one near name, `.pop-note-x`, that must not answer for the hook `pop-note`.
        The reporter of this module then reads that file and must name the offender
        with the file, the line and the text of the line.
        """
        planted = ('.pop-head { color: red; }\n'
                   '.pop-note-x { color: red; }\n'
                   '.pop-row { color: red; }\n')
        holder = tempfile.TemporaryDirectory(prefix='class-hooks-owner-')
        self.addCleanup(holder.cleanup)
        sheet = Path(holder.name) / 'styles.css'
        sheet.write_text(planted, encoding='utf-8')
        hooks = [('pop-head', f'{sheet}:1'), ('pop-note', f'{sheet}:2'), ('pop-row', f'{sheet}:3')]
        self.assertEqual(
            ['pop-head', 'pop-row'],
            [token for token, _ in hooks if style_lines(sheet, token)],
            'the reader answers for a hook that the planted stylesheet holds, or it '
            'drops a hook that the stylesheet holds')
        self.assertEqual(
            [], selector_defines(sheet, 'pop-note'),
            'the planted stylesheet defines `pop-note`, so this case plants no hazard')
        report = '\n'.join(names_offenders(
            sheet, hooks, lambda token: bool(selector_defines(sheet, token))))
        self.assertIn(f'{sheet}:2: .pop-note-x {{ color: red; }}', report,
                      'the report drops the file, the line or the text of the offender')
        self.assertIn('the class "pop-note" has no rule', report,
                      'the report drops the name of the offender')
        self.assertNotIn('the class "pop-head"', report,
                         'the report names a class the planted stylesheet defines')
        self.assertNotIn('the class "pop-row"', report,
                         'the report names a class the planted stylesheet defines')


if __name__ == '__main__':
    unittest.main()
