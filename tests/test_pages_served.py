"""The served page routes and the pages on disk must agree, in both directions.

annotator/unified_server.py serves the console from a closed list of page files. That list
was a tuple of literals inside the dispatch code, so a page that loaded a new module reached
a 404 in the browser while every node suite stayed green: those suites read the files and
never open a socket. Writer A met that wall with /duration.js in round 46.

The list lives in PAGE_FILES now, with PAGE_ALIASES for the path that answers with another
file's bytes and LEGACY_PAGE_REDIRECTS for the two bookmarked URLs that are not files. This
module drives the repository's own listener over the repository's own annotator/ directory
and binds the lists to the pages' own <script> and <link> tags:

* every asset a page loads answers 200, so the next console module must land in the list;
* every served page path answers the bytes of its file, so a shadowed name, a wrong alias
  and a stale entry fail here;
* a legacy URL answers a permanent redirect, so a name in the redirect table is never
  promised as a file;
* a path outside the lists answers 404, so the lists are proved closed and not a wildcard;
* every console page on disk is reachable, so a new page must land in a list too.

The public board has its own route list (BOARD_ROUTES) because the --public-port listener
(BOARD_FILES, below) answers under a prefix and its '/' is the board page.

Run: ./scripts/pool-test.sh python test_pages_served
"""
from __future__ import annotations

import http.client
import json
import re
import sys
import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from annotator.unified_server import (BOARD_ROUTE_ALIASES, BOARD_ROUTES, FAVICON_FILES,  # noqa: E402
                                      LEGACY_PAGE_REDIRECTS, PAGE_ALIASES, PAGE_FILES, Backend,
                                      BoundedHTTPServer, make_handler)

ANNOTATOR = ROOT / "annotator"
#: The page routes a browser opens. index.html and label.html belong to other tools.
CONSOLE_PAGES = ("/", "/display")
#: The route that hands the review template (app.html) to the browser.
TEMPLATE_ROUTE = "/api/review-template"
#: The two aliases, written as the contract and not read from the module, so a wrong
#: alias map fails here instead of steering the expectation.
EXPECTED_ALIASES = {"/": "ops.html", "/display": "board.html"}
#: The legacy page URLs and their one target, also written as the contract.
EXPECTED_LEGACY = {"/ops.html": "/", "/app.html": "/"}
#: The asset suffixes a page can load from this handler.
ASSET_SUFFIXES = (".js", ".css", ".woff2", ".png", ".svg", ".ico")


def local_assets(page_text):
    """The routes one page loads, with the query string removed and './' made absolute."""
    found = []
    for reference in re.findall(r'(?:src|href)="([^"]+)"', page_text):
        if reference.startswith("./"):
            reference = "/" + reference[2:]
        if not reference.startswith("/"):
            continue                      # an external URL is another host's business
        reference = reference.split("?")[0]
        if reference.endswith(ASSET_SUFFIXES):
            found.append(reference)
    return sorted(set(found))


class PagesServed(unittest.TestCase):
    """One real listener over the repository's annotator/ directory."""

    @classmethod
    def setUpClass(cls):
        cls.folder = TemporaryDirectory(prefix="pages-served-")
        cls.root = Path(cls.folder.name)
        (cls.root / "annotator").symlink_to(ANNOTATOR, target_is_directory=True)
        cls.server = BoundedHTTPServer(("127.0.0.1", 0), make_handler(Backend(cls.root)))
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, name="pages-served", daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.folder.cleanup()

    def get(self, path):
        """(status, body, headers) for one GET, on a fresh connection."""
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            connection.request("GET", path)
            response = connection.getresponse()
            return response.status, response.read(), dict(response.getheaders())
        finally:
            connection.close()

    def test_every_asset_a_page_loads_is_served(self):
        """A page that loads a module this handler refuses is a 404 in the browser only."""
        offenders = []
        pages = list(CONSOLE_PAGES) + [TEMPLATE_ROUTE]
        for page in pages:
            status, body, _ = self.get(page)
            self.assertEqual(200, status, f"{page} did not answer 200")
            for asset in local_assets(body.decode("utf-8")):
                asset_status, _, _ = self.get(asset)
                if asset_status != 200:
                    offenders.append(f"{page} loads {asset}, and the handler answers {asset_status}")
        self.assertEqual([], offenders, "the page list and the pages disagree:\n  " + "\n  ".join(offenders))

    def test_every_served_page_path_answers_the_bytes_of_its_file(self):
        """A route, its alias and its file must agree; a shadowed name breaks this."""
        self.assertEqual(EXPECTED_ALIASES["/"], PAGE_ALIASES["/"],
                         "PAGE_ALIASES must name ops.html for the page route")
        self.assertEqual(EXPECTED_ALIASES["/display"], BOARD_ROUTE_ALIASES["/display"],
                         "BOARD_ROUTE_ALIASES must name board.html for the board route")
        paths = list(dict.fromkeys(PAGE_FILES + BOARD_ROUTES + FAVICON_FILES))
        for path in paths:
            with self.subTest(path=path):
                status, body, _ = self.get(path)
                self.assertEqual(200, status, f"{path} did not answer 200")
                expected = (ANNOTATOR / EXPECTED_ALIASES.get(path, path[1:])).read_bytes()
                self.assertEqual(expected, body, f"{path} answered other bytes than its file")

    def test_a_legacy_page_url_answers_a_permanent_redirect(self):
        """'/ops.html' and '/app.html' are not files; PAGE_FILES must not promise them."""
        self.assertEqual(EXPECTED_LEGACY, LEGACY_PAGE_REDIRECTS, "the redirect table changed")
        for path, target in EXPECTED_LEGACY.items():
            with self.subTest(path=path):
                status, body, headers = self.get(path)
                self.assertEqual(308, status, f"{path} must answer a permanent redirect")
                self.assertEqual(target, headers.get("Location"), f"{path} redirects elsewhere")
                self.assertEqual(b"", body, f"{path} redirects with a body")
                self.assertNotIn(path, PAGE_FILES, f"{path} is a redirect and must not be in PAGE_FILES")

    def test_a_path_outside_the_lists_is_not_served(self):
        """A closed list must refuse what it does not name, and must not leak source."""
        for path in ("/unlisted-console-module.js", "/board.html", "/annotator/unified_server.py"):
            with self.subTest(path=path):
                status, _, _ = self.get(path)
                self.assertEqual(404, status, f"{path} is not a page route and must answer 404")

    def test_the_lists_hold_no_duplicate_and_every_alias_points_inside_its_list(self):
        """A duplicate entry is dead weight; an alias outside its list serves nothing."""
        for name, entries in (("PAGE_FILES", PAGE_FILES), ("BOARD_ROUTES", BOARD_ROUTES),
                              ("FAVICON_FILES", FAVICON_FILES)):
            self.assertEqual(sorted(set(entries)), sorted(entries), f"{name} repeats a path")
        self.assertTrue(set(PAGE_ALIASES) <= set(PAGE_FILES), "PAGE_ALIASES names a path PAGE_FILES refuses")
        self.assertTrue(set(BOARD_ROUTE_ALIASES) <= set(BOARD_ROUTES),
                        "BOARD_ROUTE_ALIASES names a path BOARD_ROUTES refuses")
        self.assertTrue(set(LEGACY_PAGE_REDIRECTS.values()) <= set(PAGE_FILES),
                        "a legacy URL redirects to a path PAGE_FILES refuses")

    def test_every_console_page_on_disk_is_reachable(self):
        """A page file that no route hands to a browser is a page nobody can open."""
        served = {PAGE_ALIASES.get(path, path[1:]) for path in PAGE_FILES}
        served |= {BOARD_ROUTE_ALIASES.get(path, path[1:]) for path in BOARD_ROUTES}
        served.add("app.html")            # through TEMPLATE_ROUTE, asserted below
        on_disk = {path.name for path in ANNOTATOR.glob("*.html")}
        missing = [name for name in ("ops.html", "app.html", "board.html") if name not in served]
        self.assertEqual([], missing, "these console pages are on disk and in no route list: " + ", ".join(missing))
        self.assertLessEqual({"ops.html", "app.html", "board.html"}, on_disk)
        status, body, _ = self.get(TEMPLATE_ROUTE)
        self.assertEqual(200, status, f"{TEMPLATE_ROUTE} did not answer 200")
        self.assertEqual((ANNOTATOR / "app.html").read_text(), json.loads(body).get("html"),
                         f"{TEMPLATE_ROUTE} must answer the text of app.html")


if __name__ == "__main__":
    unittest.main()
