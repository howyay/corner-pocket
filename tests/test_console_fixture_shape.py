"""The console fixture must be what its builder writes today.

`tests/console_fixture_state.json` is the club behind docs/console-shots.md, the workbench
fixture and the rating smoke.  It is generated, never hand-written, and until this module
nothing detected that it had gone stale: the committed file had lost the `links` and `vods`
collections the store had started to serve, and every consumer kept seeding a club with no
linked broadcast.  `tests/console_fixture_build.py --check` drives that build and compares
the field paths and the club's own counts, which is the mode its docstring had promised and
did not have.

Each case pays one build -- about three seconds, because the comparison is against a fresh
build and not against a recorded copy of the shape.
"""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
BUILDER = ROOT / 'tests' / 'console_fixture_build.py'
FIXTURE = ROOT / 'tests' / 'console_fixture_state.json'


class ConsoleFixtureShapeTests(unittest.TestCase):
    def check(self, *arguments):
        """Run the builder in check mode and return the finished process."""
        return subprocess.run([sys.executable, str(BUILDER), '--check', *arguments],
                              cwd=ROOT, capture_output=True, text=True, timeout=180)

    def test_the_committed_fixture_matches_a_fresh_build(self):
        before = FIXTURE.read_bytes()
        result = self.check()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('matches a fresh build', result.stdout)
        self.assertIn('nothing written', result.stdout)
        self.assertEqual(FIXTURE.read_bytes(), before, 'check mode rewrote the committed fixture')

    def test_a_stale_fixture_is_named_with_the_collection_and_the_field_it_lost(self):
        with tempfile.TemporaryDirectory() as folder:
            stale = Path(folder) / 'stale-state.json'
            state = json.loads(FIXTURE.read_text(encoding='utf-8'))
            self.assertIn('links', state, sorted(state))
            self.assertIn('joinedAt', state['players'][0], state['players'][0])
            del state['links']
            for row in state['players']:
                del row['joinedAt']
            stale.write_text(json.dumps(state, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
            before = stale.read_bytes()
            result = self.check('--out', str(stale))
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn('is stale-shaped', result.stdout)
            self.assertIn('only a fresh build has: .: ', result.stdout)
            self.assertIn('links', result.stdout)
            carried = [line for line in result.stdout.splitlines()
                       if 'only in a fresh build' in line and 'joinedAt' in line]
            self.assertTrue(carried, result.stdout)
            self.assertIn('players[', carried[0], carried)
            self.assertEqual(stale.read_bytes(), before, 'check mode wrote to the file it judged')


if __name__ == '__main__':
    unittest.main()
