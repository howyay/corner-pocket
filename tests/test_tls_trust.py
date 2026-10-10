"""One owner for the TLS trust-anchor rule, and the proof that no copy comes back.

This interpreter finds no CA certificates by default (measured on this machine:
``ssl.create_default_context().cert_store_stats()['x509_ca'] == 0`` while
``/etc/ssl/certs/ca-certificates.crt`` exists), so the rule that decides which trust
anchors an HTTPS call uses is worth exactly one place: ``src/tls_trust.py``.

No network.  Case 1 reads source; the other three measure this machine's own store.
Run: PYTHONPATH=. .venv/bin/python -B tests/test_tls_trust.py
"""
import ssl
import unittest
from pathlib import Path

from src import tls_trust

ROOT = Path(__file__).resolve().parents[1]
OWNER = ROOT / 'src' / 'tls_trust.py'
#: The shipped python a second copy of the rule could hide in.
SHIPPED = ('annotator', 'src', 'scripts', 'tools')
#: The three ways a hand-written copy names the rule: the two ssl calls of the idiom, and
#: the one bundle path every copy of it spells out.
NEEDLES = ('create_default_context', 'load_verify_locations', 'ca-certificates')


def _source_files():
    """Every shipped python file, sorted, with the one owner excluded."""
    for directory in SHIPPED:
        for path in sorted((ROOT / directory).rglob('*.py')):
            if '__pycache__' in path.parts or path == OWNER:
                continue
            yield path


def _copies():
    """`relative/path.py:LINE: source` for every line that states the rule by hand."""
    found = []
    for path in _source_files():
        for number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
            if any(needle in line for needle in NEEDLES):
                found.append('%s:%d: %s' % (path.relative_to(ROOT), number, line.strip()))
    return found


class OneOwnerTests(unittest.TestCase):
    """The rule lives in ``src/tls_trust.py`` and nowhere else."""

    def test_the_rule_is_stated_once(self):
        copies = _copies()
        self.assertEqual(
            [], copies,
            'the TLS trust-anchor rule is stated outside its one owner '
            '(src/tls_trust.py). Call src.tls_trust.trusted_context() instead. '
            'Offending copies: ' + '; '.join(copies))


class BundlePathTests(unittest.TestCase):
    """Which files this machine offers as trust anchors, and in which order."""

    def test_the_three_layouts_are_named(self):
        self.assertEqual(
            ('/etc/ssl/certs/ca-certificates.crt',
             '/etc/pki/tls/certs/ca-bundle.crt',
             '/etc/ssl/cert.pem'),
            tls_trust.CA_BUNDLES,
            'the three layouts, in the order Debian, Fedora, macOS')

    def test_the_comments_stay_with_the_paths(self):
        source = OWNER.read_text(encoding='utf-8')
        for comment in ('# Debian, Ubuntu, Arch, NixOS', '# Fedora, RHEL', '# macOS, Alpine, BSDs'):
            self.assertIn(comment, source, 'the layout comment is part of the rule')

    def test_a_missing_path_is_skipped(self):
        real = tls_trust.CA_BUNDLES[0]
        self.assertTrue(Path(real).is_file(), 'this machine carries the Debian bundle')
        self.assertEqual(real, tls_trust.bundle_path(('nope-does-not-exist', real)))

    def test_no_such_file_answers_none(self):
        self.assertIsNone(tls_trust.bundle_path(('nope-does-not-exist',)))

    def test_this_machine_offers_a_bundle(self):
        self.assertEqual('/etc/ssl/certs/ca-certificates.crt', tls_trust.bundle_path())


class TrustedContextTests(unittest.TestCase):
    """What ``trusted_context()`` adds to the default context, and what it never drops."""

    def test_the_context_improves_on_the_default_when_the_default_is_empty(self):
        default = ssl.create_default_context().cert_store_stats()['x509_ca']
        trusted = tls_trust.trusted_context().cert_store_stats()['x509_ca']
        if default == 0:
            self.assertIsNotNone(
                tls_trust.bundle_path(),
                'the default store is empty and no system bundle exists, so no context can verify')
            self.assertGreater(
                trusted, 0,
                f'the default store is empty and bundle_path() answers '
                f'{tls_trust.bundle_path()}, but trusted_context() still holds no anchor')
        else:
            self.assertEqual(
                default, trusted,
                'the rule must not add anchors that the interpreter already found')

    def test_verification_stays_on(self):
        context = tls_trust.trusted_context()
        self.assertEqual(ssl.CERT_REQUIRED, context.verify_mode)
        self.assertTrue(context.check_hostname)


if __name__ == "__main__":
    unittest.main()
