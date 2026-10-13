"""The board heading ids have one owner pair, and one case reads both sides.

Two shipped files state one agreement, and no case read both of them:

  * ``annotator/board.html`` holds the ids and the ``aria-labelledby`` values of
    the page.  The id ``standings-title`` stands at ``annotator/board.html:43``
    and a section points at it from ``annotator/board.html:42``.
  * ``annotator/board.js`` holds the map ``const labels`` at
    ``annotator/board.js:263``.  The pair of ``standings-title`` stands at
    ``annotator/board.js:264``, and the loop at ``annotator/board.js:274``
    reads the id of each row with ``doc.getElementById``.

``grep -rn "standings-title" tests/`` answered nothing, so a rename on one side
alone was silent: the paint loop called ``$(id).innerHTML`` on a missing
element, the heading kept its text, and the suite stayed green.

The two neighbours in the suite read other facts about these files.
``tests/test_board.js:458`` reads the class tokens of ``annotator/board.css``.
The page case of ``tests/test_board.js`` reads the script tags and the inline
handlers of ``annotator/board.html``.  Neither one reads an id.

This module reads both sides as text and holds them equal.  A rename on one
side alone reddens a case here, and the failure names the site to open as
``path:line: <line text>``.  The reader holds no list of the ids it expects to
pass; it counts them, so a new row of the map reddens the count case.

One case reads the three places that must answer one id together: the label
target at ``annotator/board.html:42``, the id at ``annotator/board.html:43`` and
the first word of the map row at ``annotator/board.js:264``.  A rename of the id
or of the map key reddens it with both sites named.

Run: ``./scripts/pool-test.sh python test_board_heading_ids_owner``
"""
from pathlib import Path
import re
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

#: The page that holds the ids and the ``aria-labelledby`` values.
HTML_SITE = 'annotator/board.html'

#: The script that holds the map of the ids it paints.
JS_SITE = 'annotator/board.js'

#: The head of the map that binds an element id to a word of the board.
LABELS_HEAD = 'const labels = ['

#: One ``id="..."`` attribute of a markup file.
ID_ATTRIBUTE = re.compile(r'id="([^"]*)"')

#: One ``aria-labelledby="..."`` attribute of a markup file.
LABELLED_BY = re.compile(r'aria-labelledby="([^"]*)"')

#: One ``['id', 'key']`` pair of the map.
MAP_PAIR = re.compile(r"\['([^']*)',\s*'([^']*)'\]")

#: The section whose heading, label target and map row must answer one id.  The
#: head of that section stands at ``annotator/board.html:42``, its heading at
#: ``annotator/board.html:43`` and its map row at ``annotator/board.js:264``.
STANDINGS_CLASS = 'standings'

#: One opening section tag with a class attribute, and one heading with an id.
SECTION_OPEN = re.compile(r'<section\b[^>]*class="([^"]*)"')
H2_OPEN = re.compile(r'<h2\b[^>]*id="([^"]*)"')

#: The measured size of every scan.  A renamed id, an added row or a shortened
#: walk changes one of these numbers, and a case below reddens in the same run.
ID_ATTRIBUTE_COUNT = 22
LABELS_ROW_COUNT = 9
LABELS_KEY_COUNT = 9
LABELLED_BY_TARGET_COUNT = 4


def offline_lines(relative_path):
    """`(number, line)` for every line of one repository file, read as UTF-8."""
    text = (ROOT / relative_path).read_text(encoding='utf-8')
    return list(enumerate(text.splitlines(), start=1))


def id_attributes(relative_path):
    """`(id, number, line)` for every ``id`` attribute of one markup file."""
    return [(match.group(1), number, line)
            for number, line in offline_lines(relative_path)
            for match in ID_ATTRIBUTE.finditer(line)]


def labelled_by_targets(relative_path):
    """`(target, number, line)` for every label target of one markup file.

    One attribute may name more than one target, so each name answers alone.
    """
    return [(target, number, line)
            for number, line in offline_lines(relative_path)
            for match in LABELLED_BY.finditer(line)
            for target in match.group(1).split()]


def labels_head_line(relative_path, head):
    """The number of the line that holds the head of the map."""
    hits = [number for number, line in offline_lines(relative_path)
            if line.strip().startswith(head)]
    if len(hits) != 1:
        raise AssertionError(f'{relative_path} holds {len(hits)} lines that start with '
                             f'"{head}"; this reader walks one map')
    return hits[0]


def map_rows(relative_path, head):
    """`(id, key, number, line)` for every row of the map.

    The walk starts at the head line and keeps every row until the line that
    closes the block, so a row added below the head answers here.
    """
    lines = offline_lines(relative_path)
    start = labels_head_line(relative_path, head)
    depth = 0
    rows = []
    for number, line in lines[start - 1:]:
        depth += line.count('[') - line.count(']')
        for match in MAP_PAIR.finditer(line):
            rows.append((match.group(1), match.group(2), number, line))
        if depth <= 0 and number > start:
            break
    return rows


def section_block(relative_path, class_token):
    """`(number, line)` of the section whose class holds ``class_token``.

    The walk starts at the opening tag and keeps the lines until the closing tag,
    so a heading inside the section answers here.  ``None`` means the page holds
    no such section.
    """
    lines = offline_lines(relative_path)
    start = None
    for number, line in lines:
        match = SECTION_OPEN.search(line)
        if match and class_token in match.group(1).split():
            start = number
            break
    if start is None:
        return None
    block = []
    for number, line in lines[start - 1:]:
        block.append((number, line))
        if '</section>' in line:
            break
    return block


def site(relative_path, number):
    """One site of one file, as ``path:line``."""
    return f'{relative_path}:{number}'


def text_of(relative_path, number):
    """The text of one line of one file, with no end-of-line character."""
    return (ROOT / relative_path).read_text(encoding='utf-8').splitlines()[number - 1]


def report(offender, why):
    """One offender, as ``path:line: <line text>``, with the reason below it."""
    relative_path, number, text = offender
    return f'{site(relative_path, number)}: {text.strip()}\n  {why}'


def rows_report(rows):
    """One line per row of the map, as ``path:line: <line text>``."""
    return '\n'.join(f'{site(JS_SITE, number)}: {line.strip()}' for _, _, number, line in rows)


class BoardHeadingIdsOwnerTest(unittest.TestCase):
    def test_every_painted_id_exists_in_the_page(self):
        """Every id of the map stands in the page, or the paint loop fails.

        The reader holds no list of the ids.  It reads the first word of every
        row of the map and every ``id`` attribute of the page, and it holds the
        two sets equal.
        """
        rows = map_rows(JS_SITE, LABELS_HEAD)
        self.assertEqual(
            LABELS_ROW_COUNT, len(rows),
            f'the map of {JS_SITE} no longer holds {LABELS_ROW_COUNT} rows, so this '
            'reader holds less of the pair than the page needs:\n' + rows_report(rows))
        ids = id_attributes(HTML_SITE)
        self.assertEqual(
            ID_ATTRIBUTE_COUNT, len(ids),
            f'{HTML_SITE} no longer holds {ID_ATTRIBUTE_COUNT} id attributes:\n'
            + '\n'.join(f'{site(HTML_SITE, number)}: {line.strip()}' for _, number, line in ids))
        known = {name for name, _, _ in ids}
        offenders = [report((JS_SITE, number, line),
                            f'the id "{name}" has no id attribute in {HTML_SITE}, so the '
                            'paint loop reaches no element')
                     for name, _, number, line in rows if name not in known]
        self.assertEqual(
            [], offenders,
            'a row of the map names an element the page does not hold, so the board '
            'paints nothing there:\n' + '\n'.join(offenders))

    def test_every_label_target_of_the_page_is_one_id(self):
        """Every ``aria-labelledby`` value of the page names an id of that page.

        A target that no element carries leaves the section without a name.  A
        target may hold more than one name, so each name answers alone.
        """
        targets = labelled_by_targets(HTML_SITE)
        self.assertEqual(
            LABELLED_BY_TARGET_COUNT, len(targets),
            f'{HTML_SITE} no longer holds {LABELLED_BY_TARGET_COUNT} label targets:\n'
            + '\n'.join(f'{site(HTML_SITE, number)}: {line.strip()}' for _, number, line in targets))
        known = {name for name, _, _ in id_attributes(HTML_SITE)}
        offenders = [report((HTML_SITE, number, line),
                            f'the label target "{target}" has no id attribute in '
                            f'{HTML_SITE}, so the section has no name')
                     for target, number, line in targets if target not in known]
        self.assertEqual(
            [], offenders,
            'a section points at a name that no element of the page carries:\n'
            + '\n'.join(offenders))

    def test_every_map_key_is_distinct(self):
        """Two rows with one key paint one word twice and leave another unpainted.

        The key is the second word of the row, and it is the word the map
        answers from the language table.  A repeated key is a row that the loop
        at ``annotator/board.js:274`` paints twice.
        """
        rows = map_rows(JS_SITE, LABELS_HEAD)
        keys = [key for _, key, _, _ in rows]
        self.assertEqual(
            LABELS_KEY_COUNT, len(set(keys)),
            f'the {len(rows)} rows of the map of {JS_SITE} no longer hold '
            f'{LABELS_KEY_COUNT} distinct keys:\n' + rows_report(rows))

    def test_the_scan_of_each_pair_keeps_its_measured_size(self):
        """The scans keep the size this module measured, so none passes empty.

        One number per scan.  A number means the count of the sites the scan
        found in the shipped tree on 2026-10-13.  A reader that finds no site
        answers an empty list, and an empty list passes every case above.
        """
        measured = {
            'page id attributes': (len(id_attributes(HTML_SITE)), ID_ATTRIBUTE_COUNT),
            'page label targets': (len(labelled_by_targets(HTML_SITE)), LABELLED_BY_TARGET_COUNT),
            'map rows': (len(map_rows(JS_SITE, LABELS_HEAD)), LABELS_ROW_COUNT),
            'map keys': (len({key for _, key, _, _ in map_rows(JS_SITE, LABELS_HEAD)}),
                         LABELS_KEY_COUNT),
        }
        for scan, (found, wanted) in measured.items():
            with self.subTest(scan=scan):
                self.assertEqual(
                    wanted, found,
                    f'the scan "{scan}" found {found} sites, not {wanted}.  The number is '
                    'the count this module measured in the shipped tree.  A renamed id, an '
                    'added row or a shortened walk changes it, and every other case of this '
                    'module then reads less than the pair it holds.')

    def test_the_standings_pair_is_one_name_in_three_places(self):
        """The section, its heading and its map row carry one id.

        The walk of round 105 read the three places that must answer one name:
        the ``aria-labelledby`` target of the standings section, the ``id`` of
        its heading and the first word of the map row whose key is that section's
        class.  A rename on one side alone leaves the section without a name or
        the heading without a painted word, and no case read the three together.
        """
        block = section_block(HTML_SITE, STANDINGS_CLASS)
        self.assertIsNotNone(
            block, f'{HTML_SITE} holds no section of class "{STANDINGS_CLASS}", so this '
                   'reader holds no pair')
        numbers = [number for number, _ in block]
        targets = [row for row in labelled_by_targets(HTML_SITE) if row[1] in numbers]
        headings = [(match.group(1), number, line)
                    for number, line in block for match in H2_OPEN.finditer(line)]
        rows = [row for row in map_rows(JS_SITE, LABELS_HEAD) if row[1] == STANDINGS_CLASS]
        offenders = []
        if len(targets) != 1:
            offenders.append(f'{site(HTML_SITE, numbers[0])}: the section of class '
                             f'"{STANDINGS_CLASS}" carries {len(targets)} label targets, not 1')
        if len(headings) != 1:
            offenders.append(f'{site(HTML_SITE, numbers[0])}: the section of class '
                             f'"{STANDINGS_CLASS}" carries {len(headings)} headings with an '
                             'id, not 1')
        if len(rows) != 1:
            offenders.append(f'{site(JS_SITE, labels_head_line(JS_SITE, LABELS_HEAD))}: the map '
                             f'carries {len(rows)} rows keyed "{STANDINGS_CLASS}", so no row '
                             'paints that heading')
        if offenders:
            self.fail('the standings pair is not one name in three places:\n'
                      + '\n'.join(offenders))
        target, target_number, target_line = targets[0]
        heading_id, heading_number, _ = headings[0]
        row_id, _, row_number, row_line = rows[0]
        if target != heading_id:
            offenders.append(report((HTML_SITE, target_number, target_line),
                                    f'the section names "{target}", and its heading at '
                                    f'{site(HTML_SITE, heading_number)} carries "{heading_id}"'))
        if heading_id != row_id:
            offenders.append(report((JS_SITE, row_number, row_line),
                                    f'the row answers "{row_id}", and the heading of the '
                                    f'section at {site(HTML_SITE, heading_number)} carries '
                                    f'"{heading_id}"'))
        self.assertEqual([], offenders,
                         'the three places that must answer one id no longer agree:\n'
                         + '\n'.join(offenders))

    def test_a_planted_row_of_another_id_is_reported_with_its_file_and_line(self):
        """The reporter of this module names the file, the line and the text.

        This case writes two small scripts to temporary files.  In the first
        script one row of the map names an id that the page does not hold, and
        that row stands alone on its line.  In the second script the same row
        shares its line with its neighbour - the shape the shipped map has at
        ``annotator/board.js:264``, where five rows stand on one line.  The
        reporter must name the drifted site as ``path:line: <line text>`` in both
        shapes, so the drift is seen even when the line text carries the rows
        around it.
        """
        known = {name for name, _, _ in id_attributes(HTML_SITE)}
        shapes = (
            ('one-row-per-line',
             'const labels = [\n'
             "  ['h-won', 'won'],\n"
             "  ['standings-title-x', 'standings'],\n"
             '];\n', 3),
            ('two-rows-on-one-line',
             'const labels = [\n'
             "  ['h-won', 'won'], ['standings-title-x', 'standings'],\n"
             '];\n', 2),
        )
        holder = tempfile.TemporaryDirectory(prefix='board-heading-ids-owner-')
        self.addCleanup(holder.cleanup)
        for shape, planted, line in shapes:
            with self.subTest(shape=shape):
                script = Path(holder.name) / f'{shape}.js'
                script.write_text(planted, encoding='utf-8')
                rows = map_rows(script, LABELS_HEAD)
                self.assertEqual(
                    [('h-won', 'won'), ('standings-title-x', 'standings')],
                    [(row_id, key) for row_id, key, _, _ in rows],
                    f'the reader of the map dropped a row of the planted script ({shape})')
                offenders = [report((script, number, text),
                                    f'the id "{row_id}" has no id attribute in {HTML_SITE}')
                             for row_id, _, number, text in rows if row_id not in known]
                self.assertEqual(1, len(offenders), f'{shape}: {offenders}')
                self.assertTrue(
                    offenders[0].startswith(
                        f'{script}:{line}: {planted.splitlines()[line - 1].strip()}'),
                    f'the reporter of the {shape} drift no longer names the drifted row as '
                    f'path:line: <line text>: {offenders[0]}')
                self.assertIn("['standings-title-x', 'standings']", offenders[0])


if __name__ == '__main__':
    unittest.main()
