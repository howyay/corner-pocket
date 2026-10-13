"""The fallback content type of an unknown file has two homes, and this guard holds them together.

Two servers answer a request for a static file with a content type taken from
``mimetypes.guess_type``.  When the module function answers ``None``, each server
states its own fallback string:

    annotator/server.py:117        ctype = mimetypes.guess_type(str(p))[0] or "application/octet-stream"
    annotator/unified_server.py:2909   self.send_header("Content-Type", mimetypes.guess_type(path.name)[0] or "application/octet-stream")

Both sites are live.  The string stands in no other file of the project, so no
test held the two copies together: one realm can change its fallback alone, and
the two servers then answer ``Content-Type`` differently for the one file.  This
module reads the two files as text and holds the fallback of the second server to
the fallback of the first.  ``annotator/server.py`` is the owner, because it is
the older server and its fallback rides on a named variable that a reader can
test.

The scan reads one statement per site and does not parse Python.  A reader that
only looks for the text ``application/octet-stream`` cannot tell which value a
site holds after a change, and a bare string constant of the same text would
report as a site.  The pattern below reads the ``or`` fallback that follows a
``mimetypes.guess_type(...)`` call, so it reads the value the site holds, and it
reads no string constant that stands on its own.

One case pins the count of sites at two, so a scan that reads nothing cannot pass
in silence.  The scan is honest about its own limit: it reads the text of a line,
so a line of prose that spells a complete ``mimetypes.guess_type(...) or '...'``
call would report as a site.  The two servers hold no such line, and a bare string
constant reports nothing.  The two production files are read only: this module
changes no production file.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: The server that owns the fallback.  A reader holds every other site to it.
OWNER = "annotator/server.py"
#: The server that must agree with the owner.
FOLLOWER = "annotator/unified_server.py"

#: One site: a ``mimetypes.guess_type(...)`` call whose ``or`` fallback is a string
#: literal.  ``MIMETYPES_CALL`` reads the call and the fallback in any statement
#: shape, because one site assigns the result and the other passes it straight to
#: ``send_header``.
MIMETYPES_CALL = re.compile(
    r"mimetypes\s*\.\s*guess_type\s*\(.*?\)\[0\]\s*or\s*"
    r"""(?P<quote>['"])(?P<ctype>[^'"]*)(?P=quote)"""
)


def scan_sites(path, text):
    """Every fallback site in one file: ``((line number, character, value), ...)``.

    One site is one line that reads a fallback value.  A bare string constant of
    the same text is not a site, because the pattern needs the ``mimetypes.guess_type``
    call in front of it.  The character is the first character of the fallback
    literal, as a person counts a column with 1 for the first character of the line.
    """
    found = []
    for number, line in enumerate(text.splitlines(), start=1):
        for match in MIMETYPES_CALL.finditer(line):
            quote = match.group("quote")
            value = match.group("ctype")
            character = line.index(quote + value + quote) + 1
            found.append((number, character, value))
    return found


def mismatch_report(owner_label, owner_sites, follower_label, follower_sites):
    """The follower sites that disagree with the owner value: one report per site.

    The report names the follower as ``path:line`` and quotes the offending text.
    An empty list means the two files agree, or that a file holds no such site;
    ``OwnerFallbackTests`` holds the count of sites, so an empty scan cannot pass
    this module in silence.
    """
    if not owner_sites:
        return []
    owner_value = owner_sites[0][2]
    return [
        "%s:%d: fallback content type %r disagrees with %s %r; change it to %r "
        "or read the owner value"
        % (follower_label, number, value, owner_label, owner_value, owner_value)
        for number, _character, value in follower_sites
        if value != owner_value
    ]


def read_sites(label):
    """The sites of one server file, read from the working tree."""
    return scan_sites(label, (ROOT / label).read_text(encoding="utf-8"))


class OwnerFallbackTests(unittest.TestCase):
    """The fallback of the follower, held to the fallback of the owner."""

    def test_every_site_holds_one_fallback_and_the_two_servers_agree(self):
        """Both servers answer the same content type for a file of unknown type."""
        owner_sites = read_sites(OWNER)
        follower_sites = read_sites(FOLLOWER)
        self.assertTrue(owner_sites, "%s holds no mimetypes fallback site" % OWNER)
        self.assertTrue(follower_sites, "%s holds no mimetypes fallback site" % FOLLOWER)
        self.assertEqual(
            [], mismatch_report(OWNER, owner_sites, FOLLOWER, follower_sites),
            "a fallback content type disagrees with the owner %s; both servers answer "
            "Content-Type for the one unknown file, so the two values must agree" % OWNER)

    def test_the_scan_finds_two_live_sites(self):
        """The counts prove the scan is not vacuous when both files agree."""
        owner_sites = read_sites(OWNER)
        follower_sites = read_sites(FOLLOWER)
        self.assertEqual(1, len(owner_sites),
                         "the owner %s must hold exactly one fallback site: %r" % (OWNER, owner_sites))
        self.assertEqual(1, len(follower_sites),
                         "the follower %s must hold exactly one fallback site: %r"
                         % (FOLLOWER, follower_sites))
        self.assertEqual(2, len(owner_sites) + len(follower_sites),
                         "the scan found %d sites in the two servers; the guard needs 2"
                         % (len(owner_sites) + len(follower_sites)))

    def test_a_planted_mismatch_is_reported_with_its_line_and_text(self):
        """A changed fallback in the follower reports its own line and text."""
        owner_sites = scan_sites(OWNER, "        ctype = mimetypes.guess_type(str(p))[0] or 'application/octet-stream'\n")
        follower_text = (
            "    def file(self, path):\n"
            "        self.send_response(200)\n"
            "        self.send_header(\"Content-Type\", mimetypes.guess_type(path.name)[0] or \"application/x-planted\")\n"
        )
        follower_sites = scan_sites(FOLLOWER, follower_text)
        self.assertEqual([(3, 80, "application/x-planted")], follower_sites,
                         "the planted follower site was not read as one site")
        report = mismatch_report(OWNER, owner_sites, FOLLOWER, follower_sites)
        self.assertEqual(1, len(report), "the planted mismatch did not report once: %r" % (report,))
        self.assertIn("%s:3" % FOLLOWER, report[0],
                      "the report must name the follower file and the line: %r" % (report[0],))
        self.assertIn("application/x-planted", report[0],
                      "the report must quote the offending text: %r" % (report[0],))
        self.assertIn("application/octet-stream", report[0],
                      "the report must name the owner value: %r" % (report[0],))

    def test_the_scan_does_not_read_a_bare_string_or_prose(self):
        """A string constant of the same text that stands alone is not a site."""
        prose = (
            '"""The fallback was mimetypes.guess_type(p)[0] or "application/octet-stream".\n'
            "\n"
            "A reader must not read that sentence as the site of a live route.\n"
            '"""\n'
            "# ctype = mimetypes.guess_type(str(p))[0] or 'application/x-planted'\n"
            "VALUE = 'application/octet-stream'\n"
        )
        sites = scan_sites(FOLLOWER, prose)
        self.assertNotIn((6, 9, "application/octet-stream"), sites,
                         "a bare string constant was read as a fallback site: %r" % (sites,))
        self.assertEqual([(1, 51, "application/octet-stream"), (5, 46, "application/x-planted")], sites,
                         "the scan reads the fallback of each mimetypes.guess_type call in the text, "
                         "and it reads no bare string constant: %r" % (sites,))


if __name__ == "__main__":
    unittest.main()
