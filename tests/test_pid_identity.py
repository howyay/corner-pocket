"""Two facts of the identity document have one home.

The k-means labels of ``out/pid_identity_v0.json`` carry no order.  Two shooter
scripts derive "A is the light cluster and B is the dark one" from the cluster
centres.  ``src/pid_identity.py`` holds that rule once, and both scripts ask it.
The four person passes ask the detector for class 0 at one confidence.
``src/pid_identity.py`` holds that number once too, and the four call sites read
the name.  The walk of this module reads ``src/*.py``.
"""

import ast
import re
import unittest
from pathlib import Path

from src.pid_identity import PERSON_CONF, classify_ab, light_dark

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
OWNER = "pid_identity.py"
SHOOTERS = ("pid_shooter.py", "pid_shooter2.py")
# The four call sites of the person pass, and the one confidence they share.
SITES = ("pid_associate.py", "pid_shooter.py", "pid_shooter2.py", "yolo_track.py")
CONF_KEYWORD = "conf"
PERSON_CONF_NAME = "PERSON_CONF"
# The bar the four person sites were measured with.  The detector keeps a row when the
# row score is greater than the bar, so the bar is strict: a box on the value is dropped
# and the box above it survives.  A case below holds this number against the owner.
MEASURED_PERSON_CONF = 0.35

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


def confidence_sites(source, name):
    """Answer the ``conf`` value of every ``predict`` call of one source.

    One answer is the text ``name:line: text``.  A call without the keyword
    answers the word ``default``, because the detector applies its own value
    then.
    """
    found = []
    for node in ast.walk(ast.parse(source, filename=name)):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr != "predict":
            continue
        value = "default"
        for keyword in node.keywords:
            if keyword.arg == CONF_KEYWORD:
                value = ast.unparse(keyword.value)
        found.append("%s:%d: %s" % (name, node.lineno, value))
    return found


def owner_names(source, name):
    """Answer the names of one source that come from the owner module."""
    imported = set()
    for node in ast.walk(ast.parse(source, filename=name)):
        if isinstance(node, ast.ImportFrom) and (node.module or "").endswith("pid_identity"):
            imported |= {alias.name for alias in node.names}
    return imported


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


class ThePersonConfidenceHasOneHomeTest(unittest.TestCase):
    """One number, four sites.  The shape, the value and the walk each have their own case.

    The value itself is a person-detection threshold at four production sites, so it must
    fail a case before a later round tunes it.
    """

    def test_the_owner_binds_the_confidence_once_as_a_number_in_range(self):
        """The shape of the binding, not the value: one name, one number, a range.

        The value is held by ``test_the_owner_holds_the_value_the_four_sites_use`` below.
        """
        source = (SRC / OWNER).read_text(encoding="utf-8")
        bound = []
        for node in ast.parse(source, filename=OWNER).body:
            if not isinstance(node, ast.Assign):
                continue
            names = [target.id for target in node.targets if isinstance(target, ast.Name)]
            if PERSON_CONF_NAME in names:
                bound.append(node.value)
        self.assertEqual(1, len(bound), "the owner binds %s once" % PERSON_CONF_NAME)
        self.assertIsInstance(
            bound[0].value, float, "the owner spells the confidence as one number"
        )
        self.assertIsInstance(
            PERSON_CONF, float, "the owner hands a number to every reader"
        )
        self.assertGreater(PERSON_CONF, 0.0, "a confidence is above zero")
        self.assertLess(PERSON_CONF, 1.0, "a confidence is below one")

    def test_the_owner_holds_the_value_the_four_sites_use(self):
        """The value itself, at the bar the four person sites were measured with.

        The detector keeps a row when the row score is greater than the bar, and the
        ultralytics predictor gives the ``conf`` keyword of the caller to that argument.
        The bar is therefore strict.  The boundary measurement of round 75 showed it: the
        NMS call drops a box whose score is exactly 0.35 and keeps the box above it.  The
        four person sites (``pid_associate.py``, ``pid_shooter.py``, ``pid_shooter2.py``
        and ``yolo_track.py``) need this number, and no lower one holds those people.

        A changed value moves the person pass at four sites, so the case names both
        numbers in its message.  The case above holds the range, and
        ``test_the_bar_keeps_the_box_above_it`` holds the boundary.
        """
        self.assertEqual(
            MEASURED_PERSON_CONF,
            PERSON_CONF,
            "the four person sites were measured with a confidence of %r, but the owner "
            "holds %r: keep the measured value, or measure the four sites again"
            % (MEASURED_PERSON_CONF, PERSON_CONF),
        )

    def test_no_module_spells_the_confidence_as_a_number(self):
        found = []
        for path in sorted(SRC.glob("*.py")):
            source = path.read_text(encoding="utf-8")
            for node in ast.walk(ast.parse(source, filename=path.name)):
                if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                    continue
                if node.func.attr != "predict":
                    continue
                for keyword in node.keywords:
                    if keyword.arg == CONF_KEYWORD and isinstance(keyword.value, ast.Constant):
                        found.append(
                            "%s:%d: %s"
                            % (path.name, node.lineno, ast.unparse(keyword.value))
                        )
        self.assertEqual(
            [],
            found,
            "these lines spell the person-pass confidence outside the owner: %r" % found,
        )

    def test_the_four_person_sites_read_the_owner(self):
        for name in SITES:
            source = (SRC / name).read_text(encoding="utf-8")
            self.assertIn(
                PERSON_CONF_NAME,
                owner_names(source, name),
                "%s must import the confidence from the owner" % name,
            )
            values = [report.rsplit(": ", 1)[-1] for report in confidence_sites(source, name)]
            self.assertEqual(
                1,
                values.count(PERSON_CONF_NAME),
                "%s must ask the detector with the owner's name: %r" % (name, values),
            )

    def test_the_walk_sees_a_planted_confidence(self):
        planted = "res = MODEL.predict(bgr, conf=0.35, classes=[0], verbose=False)\n"
        self.assertEqual(
            ["forged.py:1: 0.35"],
            confidence_sites(planted, "forged.py"),
            "the walk of the case above must see a planted copy",
        )
        self.assertEqual(
            ["forged.py:1: 0.25"],
            confidence_sites(planted.replace("0.35", "0.25"), "forged.py"),
            "a second number is a second copy",
        )

    def test_the_bar_keeps_the_box_above_it(self):
        """The value itself, measured at the function the detector applies.

        ``non_max_suppression`` keeps a row when the row score is greater than
        ``conf_thres``, and the ultralytics predictor gives the ``conf`` keyword
        of the caller to that argument.  Therefore one box below the owner's
        value, one box on it and one box above it measure the number.
        """
        import torch
        from ultralytics.utils.nms import non_max_suppression

        scores = (PERSON_CONF - 0.01, PERSON_CONF, PERSON_CONF + 0.01)
        prediction = torch.zeros(1, 5, 3)
        for index, score in enumerate(scores):
            prediction[0, 0, index] = 200.0 + 20.0 * index  # centre x
            prediction[0, 1, index] = 20.0  # centre y
            prediction[0, 2, index] = 10.0  # width
            prediction[0, 3, index] = 10.0  # height
            prediction[0, 4, index] = score  # the score of class 0
        kept = non_max_suppression(prediction, conf_thres=PERSON_CONF, classes=[0])
        rows = kept[0]
        self.assertEqual(
            1, len(rows), "one box is above the owner's bar, and two are not: %r" % (rows,)
        )
        self.assertAlmostEqual(
            scores[2],
            float(rows[0][4]),
            places=5,
            msg="the surviving box is the one above the bar",
        )


if __name__ == "__main__":
    unittest.main()
