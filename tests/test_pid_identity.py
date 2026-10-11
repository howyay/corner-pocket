"""The A/B colour rule of the identity document has one home.

The k-means labels of ``out/pid_identity_v0.json`` carry no order.  Two shooter
scripts derive "A is the light cluster and B is the dark one" from the cluster
centres.  ``src/pid_identity.py`` holds that rule once, and both scripts ask it.
The walk of this module reads ``src/*.py``.
"""

import ast
import re
import unittest
from pathlib import Path

from src.pid_identity import classify_ab, light_dark

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
OWNER = "pid_identity.py"
SHOOTERS = ("pid_shooter.py", "pid_shooter2.py")

# The two shapes that state the rule: an order of the clusters by brightness,
# and a cluster index taken from that order.
BRIGHTNESS_ORDER = re.compile(r"argsort\([^)]*mean\(axis=1\)")
INDEXED_ORDER = re.compile(r"int\(order\[")


def rule_sites(source, name):
    """Answer the lines of one source that state the A/B order.

    One answer is the text ``name:line: text``.
    """
    found = []
    for number, line in enumerate(source.splitlines(), start=1):
        if BRIGHTNESS_ORDER.search(line) or INDEXED_ORDER.search(line):
            found.append("%s:%d: %s" % (name, number, line.strip()))
    return found


class TheAbRuleHasOneHomeTest(unittest.TestCase):
    def test_no_second_module_states_the_ab_order(self):
        found = []
        for path in sorted(SRC.glob("*.py")):
            if path.name == OWNER:
                continue
            found += rule_sites(path.read_text(encoding="utf-8"), path.name)
        self.assertEqual(
            [], found, "these lines state the A/B order outside the owner: %r" % found
        )

    def test_the_walk_sees_a_planted_copy(self):
        planted = (
            "order = np.argsort(centers.mean(axis=1))\n"
            "B_CLUSTER = int(order[0])\n"
        )
        self.assertEqual(
            [
                "forged.py:1: order = np.argsort(centers.mean(axis=1))",
                "forged.py:2: B_CLUSTER = int(order[0])",
            ],
            rule_sites(planted, "forged.py"),
            "the walk of the case above must see a planted copy",
        )

    def test_both_shooters_read_the_owner(self):
        for name in SHOOTERS:
            source = (SRC / name).read_text(encoding="utf-8")
            imported = set()
            for node in ast.walk(ast.parse(source, filename=name)):
                if isinstance(node, ast.ImportFrom) and node.module == "pid_identity":
                    imported |= {alias.name for alias in node.names}
            self.assertIn("light_dark", imported, "%s must import the A/B rule" % name)
            self.assertIn("classify_ab", imported, "%s must import the verdict" % name)
            self.assertIn(
                "classify_ab(", source, "%s must ask the owner for the verdict" % name
            )

    def test_the_rule_answers_the_light_cluster(self):
        clusters = [[0.0, 0.0, 0.0], [200.0, 200.0, 200.0]]  # BGR rows, dark first
        a_index, b_index = light_dark(clusters)
        self.assertEqual((1, 0), (a_index, b_index), "A is the light cluster")
        self.assertEqual("A", classify_ab((210, 210, 210), clusters, a_index, b_index))
        self.assertEqual("B", classify_ab((5, 5, 5), clusters, a_index, b_index))
        self.assertEqual(
            "A",
            classify_ab((100, 100, 100), clusters, a_index, b_index),
            "a tie answers A",
        )


if __name__ == "__main__":
    unittest.main()
