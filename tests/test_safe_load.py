"""Checkpoints load weights-only (security audit D-2).

``torch.load(weights_only=False)`` unpickles arbitrary objects, so a replaced
weights file would run code inside the server. The guards:

- no ``weights_only=False`` in our own sources (``src/sam3/`` is the vendored
  upstream checkout, not ours);
- ultralytics decides once, when it is first imported, whether YOLO weights load
  weights-only (``ULTRALYTICS_SAFE_LOAD``); unset, it unpickles freely. Every module
  that imports ultralytics sets the flag in code first, so the server, fixtures and
  tests behave alike without depending on the systemd unit;
- a checkpoint that carries code is refused where the server loads one, and the
  code never runs.
"""
import os
import pickle
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
VENDORED = REPO / 'src' / 'sam3'
UNSAFE_LOAD = re.compile(r'weights_only\s*=\s*False')
ULTRALYTICS_IMPORT = re.compile(r'^\s*(from|import)\s+ultralytics\b', re.M)
SAFE_LOAD_FLAG = re.compile(
    r'''os\.environ\.setdefault\(\s*['"]ULTRALYTICS_SAFE_LOAD['"]\s*,\s*['"]1['"]\s*\)''')
# The ultralytics importers that import without side effects; the offline scripts
# run on import, so the source-order check covers them.
MODULES = ('src.person_pipeline', 'src.frame_inference', 'src.info_complete_scan')
# Offline scripts still to switch (D-2, second commit). Nothing else may.
PENDING = {'src/fast_ball_labels.py', 'src/pid_associate.py', 'src/pid_osnet.py',
           'src/pid_osnet_tight.py', 'src/pid_osnet_tracks.py'}


def own_sources():
    for top in ('src', 'annotator'):
        for path in sorted((REPO / top).rglob('*.py')):
            if VENDORED not in path.parents:
                yield path


def scratch(case):
    temp = tempfile.TemporaryDirectory()
    case.addCleanup(temp.cleanup)
    return Path(temp.name)


def python(probe):
    """Run ``probe`` in a fresh interpreter whose environment lacks the flag."""
    env = {k: v for k, v in os.environ.items() if k != 'ULTRALYTICS_SAFE_LOAD'}
    return subprocess.run([sys.executable, '-c', probe], cwd=REPO, env=env,
                          capture_output=True, text=True, timeout=180)


class CodeCarrier:
    """Pickles to a call of exec: an unrestricted load creates ``marker``."""

    def __init__(self, marker):
        self.marker = str(marker)

    def __reduce__(self):
        return exec, (f'open({self.marker!r}, "w").close()',)


class WeightsOnlyTest(unittest.TestCase):

    def test_no_checkpoint_load_unpickles_freely(self):
        hits = [f'{path.relative_to(REPO)}:{number}'
                for path in own_sources() if str(path.relative_to(REPO)) not in PENDING
                for number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1)
                if UNSAFE_LOAD.search(line)]
        self.assertEqual(hits, [], 'load checkpoints with weights_only=True')

    def test_the_ball_checkpoint_loads_and_one_carrying_code_is_refused(self):
        import torch
        from src.tiny_ball_net import build_model, load_checkpoint
        tmp = scratch(self)
        # the payload the trainer writes
        torch.save({'state': build_model().state_dict(), 'train': [1.0], 'held': [2.0],
                    'size': [960, 540], 'sigma': 3.75, 'round': '960x540-scratch'},
                   tmp / 'good.pt')
        self.assertEqual(load_checkpoint(tmp / 'good.pt', (1280, 720))[1], [960, 540])
        marker = tmp / 'ran'
        torch.save({'state': CodeCarrier(marker)}, tmp / 'bad.pt')
        with self.assertRaises(pickle.UnpicklingError):
            load_checkpoint(tmp / 'bad.pt', (960, 540))
        self.assertFalse(marker.exists(), 'the checkpoint ran code')


class UltralyticsSafeLoadTest(unittest.TestCase):

    def test_every_ultralytics_import_comes_after_the_flag(self):
        missing = []
        for path in own_sources():
            text = path.read_text(encoding='utf-8')
            first_import = ULTRALYTICS_IMPORT.search(text)
            if first_import is None:
                continue
            flag = SAFE_LOAD_FLAG.search(text)
            if flag is None or flag.start() > first_import.start():
                missing.append(str(path.relative_to(REPO)))
        self.assertEqual(missing, [], "set os.environ.setdefault('ULTRALYTICS_SAFE_LOAD', '1') "
                                      'before the first ultralytics import')

    def test_importing_the_module_turns_safe_load_on(self):
        for module in MODULES:
            with self.subTest(module=module):
                run = python(f'import os, {module}\n'
                             'flag = os.environ.get("ULTRALYTICS_SAFE_LOAD")\n'
                             'import ultralytics.utils\n'
                             'print(repr((flag, ultralytics.utils.SAFE_LOAD)))')
                self.assertEqual(run.returncode, 0, run.stderr[-2000:])
                self.assertEqual(run.stdout.strip().splitlines()[-1], "('1', True)")

    def test_the_person_detector_refuses_a_checkpoint_carrying_code(self):
        import torch
        root = scratch(self)
        marker = root / 'ran'
        torch.save({'model': CodeCarrier(marker)}, root / 'yolov8n.pt')
        # ultralytics re-raises the unpickler's refusal as a TypeError; the cause names it
        run = python('import pickle, numpy\n'
                     'from src.person_pipeline import PersonPipeline\n'
                     'try:\n'
                     f'    PersonPipeline({str(root)!r}).process_frame('
                     'numpy.zeros((64, 64, 3), numpy.uint8))\n'
                     'except Exception as error:\n'
                     '    while error is not None and not isinstance(error, pickle.UnpicklingError):\n'
                     '        error = error.__cause__\n'
                     '    print("refused" if error is not None else "failed otherwise")\n')
        self.assertFalse(marker.exists(), 'the detector checkpoint ran code')
        self.assertEqual(run.stdout.strip().splitlines()[-1:], ['refused'], run.stderr[-2000:])


if __name__ == '__main__':
    unittest.main()
