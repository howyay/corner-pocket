"""The entry point runs one python module, and it says why the dotted name cannot work.

`scripts/pool-test.sh python` runs the whole suite.  A developer who needs one module
types the obvious form, and it fails with a message that contradicts the file system:

    PYTHONPATH=. .venv/bin/python -m unittest tests.test_store_files
    ModuleNotFoundError: No module named 'tests.test_store_files'

The name `tests` answers `.venv/lib/python3.14/site-packages/tests`, which is another
package, so that import never reaches `tests/` of this repository.  The three cases here
hold the working path open and hold the refusal honest.
"""
import os
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "pool-test.sh"
FAST_MODULE = "test_write_fingerprint"


def run_entry(*arguments: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PYTHON"] = sys.executable
    return subprocess.run(
        ["bash", str(SCRIPT), *arguments],
        cwd=REPO,
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )


class OneModuleTest(unittest.TestCase):
    def test_one_module_runs_that_module_and_not_the_suite(self):
        done = run_entry("python", FAST_MODULE)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn(f"== python: unittest {FAST_MODULE}", done.stdout)
        # The unittest summary goes to stderr, not to stdout.
        self.assertIn("OK", done.stderr)
        self.assertIn("Ran ", done.stderr)
        self.assertNotIn("discover -s tests", done.stdout + done.stderr)

    def test_a_dotted_name_is_refused_and_the_message_names_the_bare_form(self):
        done = run_entry("python", f"tests.{FAST_MODULE}")
        self.assertEqual(done.returncode, 2, done.stdout)
        self.assertIn("without dots", done.stderr)
        self.assertIn(FAST_MODULE, done.stderr)

    def test_a_name_that_is_no_module_names_the_file_it_looked_for(self):
        done = run_entry("python", "test_no_such_module")
        self.assertEqual(done.returncode, 2, done.stdout)
        self.assertIn("tests/test_no_such_module.py", done.stderr)

    def test_the_usage_line_states_every_mode(self):
        done = run_entry("bogus")
        self.assertEqual(done.returncode, 2)
        self.assertIn("usage:", done.stderr)
        for mode in ("all", "python", "module", "js"):
            self.assertIn(mode, done.stderr)

    def test_the_script_states_the_reason_the_dotted_name_fails(self):
        text = SCRIPT.read_text()
        self.assertIn("site-packages", text)
        self.assertIn("ModuleNotFoundError", text)


if __name__ == "__main__":
    unittest.main()
