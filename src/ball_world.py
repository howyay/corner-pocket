"""World-state ball permanence on the table plane.

Division of labour with ``src/ball_census.py``: the census turns detections into
identities per clip, with a per-track constant-velocity prediction and a
speed-scaled pixel gate.  This module keeps the *known set of balls* as a world
state in table millimetres: every ball owns a slot, a slot is retired only by
pocket evidence (or an explicit rack reset), and a missing detection is a
visibility question, not an identity question.

What the state carries
    One slot per known ball.  Position and velocity are in millimetres on the
    table plane (``Table``).  Physics is closed-form: rolling friction gives a
    constant deceleration, cushions reflect and keep a share of the speed, and a
    pocket ends the ball.  ``predict(t)`` is the physical position, not a linear
    extrapolation of pixels.

Why the assignment is global
    The set is known, so an observation either claims a slot or it is rejected.
    Every frame builds a cost matrix (prediction distance, colour disagreement,
    speed sanity) and solves it with ``scipy.optimize.linear_sum_assignment``.
    A ball that is hidden for a hundred frames keeps its slot, and its colour
    plus the geometry decide which slot a new observation claims.

Three states decide the words, and one of them needs the caller
    ``ACTIVE`` - matched this frame.
    ``COAST`` - unmatched, the predicted spot is visible, inside ``coast_s``.
    ``OCCLUDED`` - unmatched, the predicted spot lies under an occluder.
    ``LOST`` - unmatched beyond the patience; the slot stays, the words say so.
    The caller supplies ``occluded(x_mm, y_mm, t)``: it projects table points to
    pixels and answers whether an occluder covers them.  This module imports no
    cv2 and no torch, so the tests can drive it with synthesis.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

#: The table in its landscape reading (length on x).  ``src/table_geometry.py`` owns the
#: numbers; this module reads them so the world and the canonical frame cannot drift.
from src.table_geometry import LANDSCAPE_H as TABLE_H_MM, LANDSCAPE_W as TABLE_W_MM

#: How long a visible ball may go unseen before its slot reads ``lost``.  It is a coast
#: patience, not an event window, so it has its own name.
COAST_PATIENCE_S = 1.5

#: Corner pockets and the two side pockets on the long rails.
POCKET_RADIUS_MM = 62.0

#: Colours a coarse classifier may swap between without losing identity.  A ball
#: read as "maroon" in one frame and "red" in the next is one ball; "red" and
#: "yellow" are never one ball.
COLOUR_GROUPS = (
    frozenset({"red", "maroon", "pink"}),
    frozenset({"blue", "purple"}),
    frozenset({"yellow", "orange"}),
    frozenset({"green", "cyan"}),
    frozenset({"white"}),
    frozenset({"black"}),
)


def colours_compatible(a: str, b: str) -> bool:
    """May one ball be read as ``a`` in one frame and ``b`` in another?"""
    if a == b or a == "unknown" or b == "unknown":
        return True
    return any(a in group and b in group for group in COLOUR_GROUPS)


#: Status words.  One home: the demo, the tests and the console read these.
ACTIVE = "active"
COAST = "coast"
OCCLUDED = "occluded"
LOST = "lost"
POTTED = "potted"


@dataclass(frozen=True)
class Physics:
    """Closed-form rolling ball on cloth."""

    friction_mm_s2: float = 250.0     # fitted from the VOD; a = mu * g, mu ~ 0.025
    cushion_retain: float = 0.85      # share of speed kept through a cushion
    stop_mm_s: float = 8.0            # below this a ball is at rest
    pocket_radius_mm: float = POCKET_RADIUS_MM

    def travel(self, speed_mm_s: float, dt: float) -> float:
        """Distance a rolling ball covers in ``dt`` from ``speed_mm_s``."""
        if dt <= 0:
            return 0.0
        stop_t = speed_mm_s / self.friction_mm_s2 if self.friction_mm_s2 > 0 else dt
        t = min(dt, stop_t)
        return speed_mm_s * t - 0.5 * self.friction_mm_s2 * t * t

    def speed_after(self, speed_mm_s: float, dt: float) -> float:
        return max(0.0, speed_mm_s - self.friction_mm_s2 * dt)


@dataclass(frozen=True)
class Table:
    width_mm: float = TABLE_W_MM
    height_mm: float = TABLE_H_MM
    pocket_radius_mm: float = POCKET_RADIUS_MM

    @property
    def pockets(self) -> tuple:
        w, h = self.width_mm, self.height_mm
        return ((0.0, 0.0), (w / 2.0, 0.0), (w, 0.0), (0.0, h), (w / 2.0, h), (w, h))

    def pocket_at(self, x: float, y: float, radius_mm: float | None = None) -> bool:
        radius = self.pocket_radius_mm if radius_mm is None else radius_mm
        return any(math.hypot(x - px, y - py) <= radius for px, py in self.pockets)

    def clamp(self, x: float, y: float) -> tuple:
        return (min(max(x, 0.0), self.width_mm), min(max(y, 0.0), self.height_mm))


@dataclass(frozen=True)
class Observation:
    """One ball detection promoted to the table plane."""

    x_mm: float
    y_mm: float
    color: str = "unknown"
    conf: float = 1.0
    source: str = "detector"


@dataclass
class Slot:
    """One known ball.  It exists until pocket evidence or a rack reset."""

    index: int
    color: str
    x: float
    y: float
    vx: float = 0.0
    vy: float = 0.0
    status: str = ACTIVE
    last_seen_t: float = 0.0
    state_t: float = 0.0
    hits: int = 1
    occluded_since: float | None = None
    lost_since: float | None = None
    reacquired: int = 0
    #: Keep the last positions for the trail and the velocity fit.
    history: list = field(default_factory=list)

    def speed(self) -> float:
        return math.hypot(self.vx, self.vy)

    def predict(self, t: float, physics: "Physics | None" = None) -> tuple:
        """Physical position at ``t`` from the state time, with closed-form friction."""
        physics = physics or Physics()
        dt = max(0.0, t - self.state_t)
        speed = self.speed()
        if speed <= 1e-9:
            return self.x, self.y
        distance = physics.travel(speed, dt)
        ux, uy = self.vx / speed, self.vy / speed
        return self.x + ux * distance, self.y + uy * distance

    def step(self, t: float, physics: Physics, table: Table) -> None:
        """Advance the slot to ``t``: friction, cushions, pockets."""
        dt = max(0.0, t - self.state_t)
        if dt <= 0:
            return
        speed = self.speed()
        if speed > 1e-9:
            distance = physics.travel(speed, dt)
            ux, uy = self.vx / speed, self.vy / speed
            x, y = self.x + ux * distance, self.y + uy * distance
            # Cushion reflection: clamp and flip the component, keeping the share.
            if x < 0.0 or x > table.width_mm:
                x = min(max(x, 0.0), table.width_mm)
                self.vx = -self.vx * physics.cushion_retain
            if y < 0.0 or y > table.height_mm:
                y = min(max(y, 0.0), table.height_mm)
                self.vy = -self.vy * physics.cushion_retain
            remaining = physics.speed_after(speed, dt)
            if remaining <= physics.stop_mm_s:
                remaining = 0.0
            scale = remaining / speed if speed > 1e-9 else 0.0
            self.vx *= scale
            self.vy *= scale
            self.x, self.y = x, y
        self.state_t = t


class World:
    """The known set of balls, frame by frame.

    ``gate_mm`` is the base match radius in millimetres (about two ball
    diameters).  A rolling ball widens it by ``gate_slack * speed * dt`` - the
    same shape ball_census uses, now in physical units.  ``patience_s`` is how
    long an unoccluded miss stays COAST before it is called LOST; the slot is
    kept either way.  An occlusion suspends that patience, up to
    ``occluded_patience_s``.
    """

    def __init__(self, table: Table | None = None, physics: Physics | None = None,
                 gate_mm: float = 55.0, gate_slack: float = 0.35,
                 bootstrap_gate_mm: float = 90.0,
                 patience_s: float = COAST_PATIENCE_S, occluded_patience_s: float = 60.0,
                 color_penalty: float = 40.0):
        self.table = table or Table()
        self.physics = physics or Physics()
        self.gate_mm = gate_mm
        self.gate_slack = gate_slack
        self.bootstrap_gate_mm = bootstrap_gate_mm
        self.patience_s = patience_s
        self.occluded_patience_s = occluded_patience_s
        self.color_penalty = color_penalty
        self.slots: list = []
        self.t = 0.0
        self.events: list = []
        self.stats = {"frames": 0, "matched": 0, "unmatched_obs": 0,
                      "occluded_episodes": 0, "reacquired": 0, "lost_episodes": 0,
                      "potted": 0, "id_switch_suspects": 0, "coast_frames": 0,
                      "occluded_frames": 0}

    # -- lifecycle ---------------------------------------------------------
    def seed(self, t: float, observations) -> None:
        """Open one slot per observation.  Called once, on a full rack or first frame."""
        self.t = t
        self.slots = []
        for i, obs in enumerate(observations):
            slot = Slot(index=i + 1, color=obs.color, x=obs.x_mm, y=obs.y_mm)
            slot.last_seen_t = slot.state_t = t
            slot.history.append((t, obs.x_mm, obs.y_mm))
            self.slots.append(slot)

    def _event(self, kind: str, slot: "Slot", t: float, **extra) -> None:
        record = {"t": round(t, 3), "kind": kind, "slot": slot.index,
                  "color": slot.color, "x_mm": round(slot.x, 1), "y_mm": round(slot.y, 1)}
        record.update(extra)
        self.events.append(record)

    # -- one frame ---------------------------------------------------------
    def observe(self, t: float, observations, occluded=None) -> dict:
        """Assign one frame of observations; advance every slot's status.

        Returns a dict: ``matched`` {slot_index: observation_index},
        ``unmatched_observations``, and ``states`` (the slots after the step).
        """
        self.t = t
        self.stats["frames"] += 1
        occluded = occluded or (lambda x, y, tt: False)
        predictions = {slot.index: slot.predict(t, self.physics) for slot in self.slots}
        if not observations or not self.slots:
            for slot in self.slots:
                self._advance_unmatched(slot, t, occluded)
            return {"matched": {}, "unmatched_observations": list(range(len(observations))),
                    "states": self.snapshot()}

        cost = self._cost_matrix(t, predictions, observations)
        from scipy.optimize import linear_sum_assignment

        # The solver wants a feasible matrix; a rejected pair becomes BIG and is
        # filtered after the solve, so a frame where nothing can match still solves.
        big = 1e6
        import numpy as np
        solver_cost = np.where(np.isfinite(cost), cost, big)
        rows, cols = linear_sum_assignment(solver_cost)
        matched = {}
        taken_obs = set()
        for row, col in zip(rows, cols):
            if cost[row, col] >= big / 2.0:
                continue
            slot = self.slots[row]
            obs = observations[col]
            self._accept(slot, obs, t)
            matched[slot.index] = col
            taken_obs.add(col)
            self.stats["matched"] += 1
            if slot.color != "unknown" and obs.color != "unknown" and \
                    slot.color != obs.color and not colours_compatible(slot.color, obs.color):
                self.stats["id_switch_suspects"] += 1
                self._event("color_mismatch", slot, t, observed=obs.color)
        for slot in self.slots:
            if slot.index not in matched:
                self._advance_unmatched(slot, t, occluded)
        unmatched_obs = [i for i in range(len(observations)) if i not in taken_obs]
        self.stats["unmatched_obs"] += len(unmatched_obs)
        return {"matched": matched, "unmatched_observations": unmatched_obs,
                "states": self.snapshot()}

    def _cost_matrix(self, t: float, predictions, observations):
        n_slots, n_obs = len(self.slots), len(observations)
        cost = [[math.inf] * n_obs for _ in range(n_slots)]
        for r, slot in enumerate(self.slots):
            if slot.status == POTTED:
                continue
            px, py = predictions[slot.index]
            dt = max(0.0, t - slot.last_seen_t)
            gate = self.gate_mm + self.gate_slack * slot.speed() * dt
            if slot.hits < 2:
                # One sighting has no speed to predict from; a break-frame ball
                # can travel most of the table between two frames.
                gate = max(gate, self.bootstrap_gate_mm)
            for c, obs in enumerate(observations):
                dist = math.hypot(obs.x_mm - px, obs.y_mm - py)
                if dist > gate:
                    continue
                penalty = 0.0
                if slot.color != "unknown" and obs.color != "unknown" and slot.color != obs.color:
                    if slot.hits >= 2 and not colours_compatible(slot.color, obs.color):
                        continue          # a settled ball's colour is its identity
                    penalty += self.color_penalty
                cost[r][c] = dist + penalty + (1.0 - obs.conf) * 10.0
        import numpy as np
        return np.array(cost, dtype=float)

    def _accept(self, slot: "Slot", obs: Observation, t: float) -> None:
        dt = max(0.0, t - slot.last_seen_t)
        prev = slot.history[-1] if slot.history else (t, obs.x_mm, obs.y_mm)
        was = slot.status
        if was in (OCCLUDED, LOST, COAST):
            slot.reacquired += 1
            self.stats["reacquired"] += 1
            self._event("reacquired", slot, t, from_status=was,
                        gap_s=round(dt, 3))
            # A reappearance after a real gap says nothing about speed.
            slot.vx = slot.vy = 0.0
        else:
            move_t = t - prev[0]
            if move_t > 1e-6:
                vx = (obs.x_mm - prev[1]) / move_t
                vy = (obs.y_mm - prev[2]) / move_t
                alpha = 0.5 if slot.hits >= 2 else 1.0
                slot.vx = alpha * vx + (1 - alpha) * slot.vx
                slot.vy = alpha * vy + (1 - alpha) * slot.vy
        slot.x, slot.y = obs.x_mm, obs.y_mm
        slot.last_seen_t = slot.state_t = t
        slot.hits += 1
        slot.status = ACTIVE
        slot.occluded_since = None
        slot.lost_since = None
        if obs.color != "unknown":
            slot.color = obs.color
        slot.history.append((t, obs.x_mm, obs.y_mm))

    def _advance_unmatched(self, slot: "Slot", t: float, occluded) -> None:
        dt = max(0.0, t - slot.last_seen_t)
        slot.step(t, self.physics, self.table)
        px, py = slot.x, slot.y
        if self.table.pocket_at(px, py):
            slot.status = POTTED
            self.stats["potted"] += 1
            self._event("potted", slot, t)
            return
        if occluded(px, py, t):
            if slot.status == LOST and slot.lost_since is not None:
                self.stats["occluded_frames"] += 1
                return              # stays LOST under the occluder
            if slot.status != OCCLUDED:
                slot.occluded_since = t
                self.stats["occluded_episodes"] += 1
                self._event("occluded", slot, t, speed_mm_s=round(slot.speed(), 1))
            if slot.occluded_since is not None and \
                    t - slot.occluded_since > self.occluded_patience_s:
                slot.status = LOST
                slot.lost_since = t
                self.stats["lost_episodes"] += 1
                self._event("occlusion_expired", slot, t,
                            occluded_s=round(t - slot.occluded_since, 3))
                self.stats["occluded_frames"] += 1
                return
            slot.status = OCCLUDED
            self.stats["occluded_frames"] += 1
            return
        # Visible but not detected.
        if slot.status == OCCLUDED:
            slot.occluded_since = None
        if dt <= self.patience_s:
            slot.status = COAST
            self.stats["coast_frames"] += 1
        else:
            if slot.status != LOST:
                slot.lost_since = t
                self.stats["lost_episodes"] += 1
                self._event("lost", slot, t, gap_s=round(dt, 3))
            slot.status = LOST

    # -- reads -------------------------------------------------------------
    def snapshot(self) -> list:
        return [{"index": slot.index, "color": slot.color, "x_mm": round(slot.x, 1),
                 "y_mm": round(slot.y, 1), "vx": round(slot.vx, 1), "vy": round(slot.vy, 1),
                 "status": slot.status, "hits": slot.hits,
                 "occluded_since": slot.occluded_since,
                 "reacquired": slot.reacquired}
                for slot in self.slots]

    def summary(self) -> dict:
        counts = {}
        for slot in self.slots:
            counts[slot.status] = counts.get(slot.status, 0) + 1
        return {"slots": len(self.slots), "by_status": counts, "stats": dict(self.stats)}
