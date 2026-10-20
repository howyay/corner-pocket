"""Synthetic-trajectory tests for the world-state ball permanence layer."""
import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.ball_world import (ACTIVE, COAST, LOST, OCCLUDED, POTTED, Observation,
                            Physics, Slot, Table, World)


def obs(x, y, color="yellow", conf=1.0):
    return Observation(x_mm=x, y_mm=y, color=color, conf=conf)


class PhysicsTest(unittest.TestCase):
    def test_rolling_friction_is_constant_deceleration(self):
        p = Physics(friction_mm_s2=250.0)
        self.assertAlmostEqual(p.speed_after(1000.0, 1.0), 750.0)
        self.assertAlmostEqual(p.speed_after(100.0, 1.0), 0.0)
        self.assertAlmostEqual(p.travel(1000.0, 1.0), 1000.0 - 0.5 * 250.0)

    def test_predict_matches_step(self):
        slot = Slot(index=1, color="yellow", x=500.0, y=400.0)
        slot.last_seen_t = slot.state_t = 0.0
        slot.vx, slot.vy = 600.0, 0.0
        px, py = slot.predict(0.5)
        slot.step(0.5, Physics(), Table())
        self.assertAlmostEqual(px, slot.x, places=6)
        self.assertAlmostEqual(py, slot.y, places=6)

    def test_cushion_reflects_and_keeps_a_share(self):
        slot = Slot(index=1, color="yellow", x=2400.0, y=600.0)
        slot.last_seen_t = slot.state_t = 0.0
        slot.vx, slot.vy = 400.0, 0.0
        slot.step(1.0, Physics(cushion_retain=0.5), Table())
        self.assertLess(slot.vx, 0.0)
        self.assertLessEqual(slot.x, 2540.0)


class WorldTest(unittest.TestCase):
    def test_occlusion_keeps_the_slot_and_reacquires_it(self):
        world = World()
        world.seed(0.0, [obs(600.0, 500.0)])
        world.observe(0.05, [obs(610.0, 500.0)])
        slot = world.slots[0]
        self.assertEqual(slot.status, ACTIVE)
        # The ball rolls at ~200 mm/s and something covers it for a second.
        for step in range(1, 21):
            t = 0.05 + step * 0.05
            world.observe(t, [], occluded=lambda x, y, tt: True)
        self.assertEqual(world.slots[0].status, OCCLUDED)
        self.assertEqual(world.stats["occluded_episodes"], 1)
        # It reappears where the physics says it should be.
        t = 1.05
        px, py = world.slots[0].predict(t)
        world.observe(t, [obs(px, py)])
        slot = world.slots[0]
        self.assertEqual(slot.status, ACTIVE)
        self.assertEqual(slot.reacquired, 1)
        self.assertEqual(world.stats["reacquired"], 1)
        self.assertEqual(len(world.slots), 1, "a reappearance must not open a second slot")

    def test_a_long_occlusion_expires_to_lost(self):
        world = World(occluded_patience_s=0.5)
        world.seed(0.0, [obs(600.0, 500.0)])
        world.observe(0.05, [obs(600.0, 500.0)])
        for step in range(1, 30):
            t = 0.05 + step * 0.05
            world.observe(t, [], occluded=lambda x, y, tt: True)
        self.assertEqual(world.slots[0].status, LOST)
        self.assertEqual(world.slots[0].lost_since is not None, True)
        self.assertEqual(len(world.slots), 1)
        self.assertEqual(world.stats["occluded_episodes"], 1)

    def test_a_visible_miss_coasts_then_is_lost_but_keeps_the_slot(self):
        world = World()
        world.seed(0.0, [obs(600.0, 500.0)])
        world.observe(0.05, [obs(600.0, 500.0)])
        world.observe(0.5, [], occluded=lambda x, y, tt: False)
        self.assertEqual(world.slots[0].status, COAST)
        world.observe(2.0, [], occluded=lambda x, y, tt: False)
        self.assertEqual(world.slots[0].status, LOST)
        self.assertEqual(len(world.slots), 1, "lost is a status, not a deletion")
        self.assertEqual(world.stats["lost_episodes"], 1)

    def test_pocket_evidence_retires_the_slot(self):
        world = World()
        world.seed(0.0, [obs(2510.0, 40.0)])
        world.observe(0.1, [obs(2530.0, 20.0)])
        world.slots[0].vx, world.slots[0].vy = 200.0, -150.0
        world.observe(0.3, [], occluded=lambda x, y, tt: False)
        self.assertEqual(world.slots[0].status, POTTED)
        self.assertEqual(world.stats["potted"], 1)

    def test_a_different_colour_cannot_claim_a_settled_slot(self):
        world = World()
        world.seed(0.0, [obs(600.0, 500.0, color="yellow")])
        world.observe(0.05, [obs(600.0, 500.0, color="yellow")])
        world.observe(0.10, [obs(600.0, 500.0, color="yellow")])
        world.observe(0.15, [obs(605.0, 500.0, color="red")])
        self.assertEqual(world.slots[0].color, "yellow", "the slot keeps its identity")
        self.assertIn(world.slots[0].status, (ACTIVE, COAST),
                      "a rejected observation is a miss, not a replacement")
        self.assertEqual(world.stats["id_switch_suspects"], 0)
        self.assertEqual(world.stats["unmatched_obs"], 1)

    def test_crossing_balls_keep_their_identities(self):
        world = World()
        world.seed(0.0, [obs(300.0, 600.0, color="yellow"), obs(900.0, 600.0, color="red")])
        for i in range(1, 31):
            t = i * 0.05
            world.observe(t, [obs(300.0 + 200.0 * t, 600.0, color="yellow"),
                              obs(900.0 - 200.0 * t, 600.0, color="red")])
        colors = sorted(slot.color for slot in world.slots)
        self.assertEqual(colors, ["red", "yellow"])
        self.assertEqual(world.stats["id_switch_suspects"], 0)


if __name__ == "__main__":
    unittest.main()
