"""Identity validation harness: real footage, human-confirmable cluster evidence.

Runs the production PersonPipeline (face-binding-only mode: body clustering
disabled by default) over three ~60s windows of data/vod_30min_260815.mp4
centered on real events from out/scan30/events.json, every 2nd frame, with all
mutable state (identity clusters.json) in per-window temp dirs. The production
out/ tree is snapshotted before and after and verified untouched.

What a window report contains (JSON + printed table):
  - per sampled frame: every tracked person with track_id, cluster_id, bbox,
    and the face observation the pipeline used for that frame (eye_px,
    det_score, face bbox). player_id is always null here: out/pid_seed.json is
    empty, no human labels exist yet, and the production face gallery is empty,
    so nothing can bind — this is the baseline the human labeling step changes.
  - per identity cluster a "face appearance signature": the frames where that
    cluster showed a quality face, eye_px/det_score ranges, track_ids. This is
    the evidence a human needs to label "cluster 3 = Player A" quickly.
  - the co-occurrence graph: which clusters were simultaneously present and
    how many sampled frames they shared.
  - automatic consistency checks, reported honestly:
    (a) same-cluster face embeddings: pairwise cosine min/median vs the bind
        bar 0.47 (= match threshold 0.35 + margin 0.12; faces the pipeline
        would bind must exceed this), fraction of pairs below the bar.
    (b) cross-cluster face cosine max/p95 (calibration says cross-person is
        low; pairs above the bar are listed for human review — a high
        cross-cluster pair is either an association error or the same human
        re-entering as a fresh cluster).
    (c) detector misses: sampled frames with persons but no quality face vs
        frames with a quality face. Note: face observations are reused
        between analyze strides, so this measures face *binding evidence*
        availability, not instantaneous detector recall.

Shooter-association precision/recall is NOT measured here — that requires a
human to label the clusters in at least one window. This harness exists to
make that labeling fast.

Run: .venv/bin/python tests/live_identity_validation.py [--out DIR] [--seconds 60]
Writes reports into --out (default: fresh temp dir, printed at the end).
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import cv2  # noqa: E402

from src.face_id import quality as face_quality  # noqa: E402
from src.person_identity import IdentityIndex  # noqa: E402
from src.person_pipeline import PersonPipeline, _center_inside  # noqa: E402

VIDEO = REPO / "data" / "vod_30min_260815.mp4"
EVENTS = REPO / "out" / "scan30" / "events.json"
FPS = 30.0
STEP = 2  # every 2nd frame
BIND_BAR = 0.47  # face match threshold 0.35 + margin 0.12 (calibrated bind bar)
DEFAULT_CENTERS = [278.0, 364.0, 486.0]  # seconds; each window verified to contain real events


def log(msg):
    print(msg, flush=True)


def load_events():
    data = json.loads(EVENTS.read_text())
    evs = data["events"] if isinstance(data, dict) and "events" in data else data
    return [e for e in evs if isinstance(e.get("t"), (int, float))]


def events_in(evs, t0, t1):
    """Events with time strictly inside (t0, t1), excluding edge ticks."""
    return sorted((e for e in evs if t0 + 1.0 <= e["t"] <= t1 - 1.0), key=lambda e: e["t"])


def build_windows(evs, centers, seconds):
    """Windows [center - s/2, center + s/2] with verified real events inside."""
    windows = []
    for center in centers:
        t0, t1 = center - seconds / 2, center + seconds / 2
        inside = events_in(evs, t0, t1)
        if not inside:  # shift the window onto the nearest real event
            nearest = min(evs, key=lambda e: abs(e["t"] - center))
            center = nearest["t"]
            t0, t1 = center - seconds / 2, center + seconds / 2
            inside = events_in(evs, t0, t1)
        windows.append({"center_s": round(center, 1), "t0": t0, "t1": t1, "events": inside})
    return windows


class RecordingEngine:
    """Delegates to the real engine; counts analyze calls and their cost."""

    def __init__(self, inner):
        self.inner = inner
        self.frame_no = None
        self.analyze_calls = 0
        self.analyze_ms = []
        self.analyze_frames = []

    def analyze(self, frame):
        t = time.perf_counter()
        out = self.inner.analyze(frame)
        self.analyze_ms.append((time.perf_counter() - t) * 1000)
        self.analyze_calls += 1
        self.analyze_frames.append(self.frame_no)
        return out

    def quality(self, face):
        return self.inner.quality(face)

    def best_match(self, emb, gallery):
        return self.inner.best_match(emb, gallery)

    def analyze_resilient(self, frame):
        fn = getattr(self.inner, "analyze_resilient", None)
        return fn(frame) if fn else self.inner.analyze(frame)


def prod_snapshot():
    snap = {}
    for p in (REPO / "out").rglob("*"):
        if p.is_file():
            st = p.stat()
            snap[str(p)] = (st.st_mtime_ns, st.st_size)
    return snap


def cosine(a, b):
    a = np.asarray(a, np.float32).ravel()
    b = np.asarray(b, np.float32).ravel()
    na, nb = float(np.linalg.norm(a)), float(np.linalg.norm(b))
    if na <= 0.0 or nb <= 0.0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def _stats(xs):
    if not xs:
        return None
    a = np.asarray(xs, float)
    return {"n": len(a), "min": round(float(a.min()), 3),
            "median": round(float(np.median(a)), 3), "max": round(float(a.max()), 3)}


def run_window(win, win_idx, out_dir):
    """Process one window; returns (rows, report) with embeddings kept in memory."""
    f0 = int(win["t0"] * FPS)
    f1 = int(win["t1"] * FPS)
    log(f"\n=== Window {win_idx}: t={win['t0']:.0f}-{win['t1']:.0f}s "
        f"(frames {f0}-{f1}, step {STEP}, {len(win['events'])} events inside) ===")
    for e in win["events"]:
        log(f"    event t={e['t']:.1f} {e['type']}"
            f"{' VERIFIED' if e.get('verified') else ''}"
            f"{' linked_pot' if e.get('type') == 'pot' else ''}")

    tmp = tempfile.mkdtemp(prefix=f"identity-val-w{win_idx}-")
    try:
        identity = IdentityIndex(Path(tmp) / "clusters.json")
        engine = RecordingEngine(None)  # placeholder; real engine set below
        from src.face_id import get_face_engine
        engine.inner = get_face_engine()
        pipeline = PersonPipeline(REPO, face_engine=engine, identity=identity)

        cap = cv2.VideoCapture(str(VIDEO))
        cap.set(cv2.CAP_PROP_POS_FRAMES, f0)
        rows = []
        # per face observation: frame, cluster, track, eye_px, det_score, embedding
        face_obs = []
        idx = f0
        t_start = time.perf_counter()
        while idx <= f1:
            ok, frame = cap.read()
            if not ok:
                log(f"  decode ended early at frame {idx}")
                break
            if (idx - f0) % STEP == 0:
                engine.frame_no = idx
                t0 = time.perf_counter()
                res = pipeline.process_frame(frame, idx, idx / FPS)
                dt_ms = (time.perf_counter() - t0) * 1000
                # pipeline._face_obs is exactly the quality-filtered face list
                # process_frame just used (fresh on analyze frames, reused in
                # between) -- attach it to persons the same way the pipeline does.
                obs_by_person = []
                for p in res["persons"]:
                    face = next((f for f in pipeline._face_obs
                                 if _center_inside(f["bbox"], p["bbox"])), None)
                    rec = {"track_id": p["track_id"], "cluster_id": p["cluster_id"],
                           "player_id": p["player_id"], "bbox": p["bbox"],
                           "face": None}
                    if face is not None:
                        rec["face"] = {"eye_px": round(float(face["eye_px"]), 2),
                                       "det_score": round(float(face["det_score"]), 3),
                                       "bbox": [round(float(v), 1) for v in face["bbox"]]}
                        face_obs.append({"frame": idx, "cluster_id": p["cluster_id"],
                                         "track_id": p["track_id"],
                                         "face_bbox": tuple(round(float(v)) for v in face["bbox"]),
                                         "eye_px": float(face["eye_px"]),
                                         "det_score": float(face["det_score"]),
                                         "emb_hash": np.asarray(face["embedding"], np.float32).tobytes(),
                                         "embedding": np.asarray(face["embedding"], np.float32)})
                    obs_by_person.append(rec)
                rows.append({"frame": idx, "t": round(idx / FPS, 2), "ms": round(dt_ms, 1),
                             "persons": obs_by_person, "events": res["events"]})
                if len(rows) % 150 == 0:
                    log(f"  frame {idx} (t={idx / FPS:.0f}s): {len(rows)} processed, "
                        f"{dt_ms:.0f} ms last, persons={len(obs_by_person)}")
            idx += 1
        wall = time.perf_counter() - t_start
        cap.release()
        log(f"  done: {len(rows)} frames in {wall:.0f}s wall, "
            f"analyze_calls={engine.analyze_calls}")

        report = summarize(rows, face_obs, win, win_idx, engine, wall)
        # embeddings sidecar for later human-scoring tooling (temp out dir only)
        if face_obs:
            np.savez(out_dir / f"window-{win_idx}-face-embeddings.npz",
                     cluster=np.array([o["cluster_id"] for o in face_obs]),
                     frame=np.array([o["frame"] for o in face_obs]),
                     track=np.array([o["track_id"] for o in face_obs]),
                     embeddings=np.stack([o["embedding"] for o in face_obs]))
        (out_dir / f"window-{win_idx}-frames.txt").write_text(
            "\n".join(format_frame_row(r) for r in rows) + "\n")
        return rows, report
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def format_frame_row(r):
    parts = []
    for p in r["persons"]:
        x0, y0, x1, y1 = p["bbox"]
        seg = f"t{p['track_id']}/c{p['cluster_id']}@({x0},{y0},{x1 - x0}x{y1 - y0})"
        if p["face"]:
            seg += f" face(eye={p['face']['eye_px']:.1f}px,det={p['face']['det_score']:.2f})"
        parts.append(seg)
    return (f"f{r['frame']} t={r['t']:.1f}s {r['ms']:.0f}ms persons={len(r['persons'])} "
            + (" | ".join(parts) if parts else "-"))


def summarize(rows, face_obs, win, win_idx, engine, wall):
    clusters = defaultdict(lambda: {"frames": set(), "tracks": set(), "eye": [], "det": []})
    for o in face_obs:
        c = clusters[o["cluster_id"]]
        c["frames"].add(o["frame"])
        c["tracks"].add(o["track_id"])
        c["eye"].append(o["eye_px"])
        c["det"].append(o["det_score"])
    present = defaultdict(set)  # frame -> clusters
    for r in rows:
        for p in r["persons"]:
            present[r["frame"]].add(p["cluster_id"])
    pair_frames = defaultdict(list)
    for frame, cids in present.items():
        cids = sorted(cids)
        for i, a in enumerate(cids):
            for b in cids[i + 1:]:
                pair_frames[(a, b)].append(frame)

    # (a) same-cluster mutual cosine vs bind bar. Metrics use UNIQUE face
    # instances per cluster: the pipeline reuses the last analyzed embedding
    # between strides, so per-frame records repeat the same vector and would
    # inflate pairs with cos=1.0.
    per_cluster = []
    for cid in sorted(clusters):
        seen, embs = set(), []
        for o in face_obs:
            if o["cluster_id"] == cid and o["emb_hash"] not in seen:
                seen.add(o["emb_hash"])
                embs.append(o["embedding"])
        sims = [cosine(embs[i], embs[j]) for i in range(len(embs))
                for j in range(i + 1, len(embs))]
        c = clusters[cid]
        per_cluster.append({
            "cluster_id": cid,
            "track_ids": sorted(c["tracks"]),
            "player_id": None,
            "face_instances_unique": len(embs),
            "face_frames": sorted(c["frames"]),
            "eye_px": _stats(c["eye"]),
            "det_score": _stats(c["det"]),
            "same_cluster_cosine": _stats(sims),
            "pairs_below_bind_bar": sum(1 for s in sims if s < BIND_BAR) if sims else 0,
            "pairs_total": len(sims),
        })

    # (b) cross-cluster face cosine. The same analyzed face instance can attach
    # to two overlapping tracks (duplicate tracker box, and reused embeddings
    # across strides); identical-embedding pairs are counted separately as
    # duplicate attachments, not as cross-cluster evidence.
    cross, dup_attach = [], 0
    for i, a in enumerate(face_obs):
        for b in face_obs[i + 1:]:
            if a["cluster_id"] == b["cluster_id"]:
                continue
            if a["emb_hash"] == b["emb_hash"]:
                dup_attach += 1
                continue
            cross.append((cosine(a["embedding"], b["embedding"]),
                          a["cluster_id"], b["cluster_id"], a["frame"], b["frame"]))
    cross.sort(reverse=True)
    cross_stats = _stats([c[0] for c in cross])
    flagged = [{"cosine": round(s, 3), "clusters": [a, b], "frames": [fa, fb]}
               for s, a, b, fa, fb in cross[:8] if s >= BIND_BAR]
    if cross_stats:
        cross_stats["p95"] = round(float(np.percentile([c[0] for c in cross], 95)), 3)
    cross_stats = cross_stats or {}
    cross_stats["duplicate_face_attach_pairs"] = dup_attach

    # (c) detector/face availability
    frames_with_persons = sum(1 for r in rows if r["persons"])
    frames_with_faces = sum(1 for r in rows
                            if any(p["face"] for p in r["persons"]))
    no_face = frames_with_persons - frames_with_faces

    report = {
        "window": win_idx,
        "t0_s": round(win["t0"], 1), "t1_s": round(win["t1"], 1),
        "center_s": win["center_s"],
        "events_inside": [{"t": e["t"], "type": e["type"], "verified": bool(e.get("verified")),
                           "id": e.get("id")} for e in win["events"]],
        "frames_sampled": len(rows), "step": STEP,
        "wall_s": round(wall, 1),
        "face_analyze_calls": engine.analyze_calls,
        "latency_ms_last_frame": _stats([r["ms"] for r in rows]),
        "clusters_total": len({p["cluster_id"] for r in rows for p in r["persons"]}),
        "clusters": per_cluster,
        "co_occurrence": [{"a": a, "b": b, "frames_shared": len(fr),
                           "first_frame": fr[0], "last_frame": fr[-1]}
                          for (a, b), fr in sorted(pair_frames.items())],
        "consistency": {
            "bind_bar": BIND_BAR,
            "a_same_cluster": {
                "clusters_with_faces": sum(1 for c in per_cluster if c["pairs_total"]),
                "pairs_total": sum(c["pairs_total"] for c in per_cluster),
                "pairs_below_bind_bar": sum(c["pairs_below_bind_bar"] for c in per_cluster),
                "min_cosine": None,      # filled in below over all within-cluster pairs
                "median_cosine": None,
            },
            "b_cross_cluster_max": cross_stats,
            "cross_pairs_above_bind_bar": flagged,
            "c_face_availability": {
                "frames_sampled": len(rows),
                "frames_with_persons": frames_with_persons,
                "frames_with_face_evidence": frames_with_faces,
                "frames_persons_no_face": no_face,
                "no_face_ratio": round(no_face / frames_with_persons, 3)
                    if frames_with_persons else None,
            },
        },
    }
    # window-aggregate same-cluster min/median over all within-cluster pairs
    all_sims = []
    for c in per_cluster:
        cid = c["cluster_id"]
        seen, embs = set(), []
        for o in face_obs:
            if o["cluster_id"] == cid and o["emb_hash"] not in seen:
                seen.add(o["emb_hash"])
                embs.append(o["embedding"])
        all_sims += [cosine(embs[i], embs[j]) for i in range(len(embs))
                     for j in range(i + 1, len(embs))]
    if all_sims:
        report["consistency"]["a_same_cluster"]["min_cosine"] = round(float(min(all_sims)), 3)
        report["consistency"]["a_same_cluster"]["median_cosine"] = round(
            float(np.median(all_sims)), 3)
    return report


def print_summary(reports):
    for rep in reports:
        log(f"\n--- Window {rep['window']} summary "
            f"(t={rep['t0_s']}-{rep['t1_s']}s, events={[e['t'] for e in rep['events_inside']]}) ---")
        log(f"frames_sampled={rep['frames_sampled']} clusters_total={rep['clusters_total']} "
            f"face_analyze_calls={rep['face_analyze_calls']} "
            f"median_ms={rep['latency_ms_last_frame']['median']}")
        log(f"{'cluster':>8} {'tracks':<14} {'faces':>5} {'eye_px':<18} {'det':<18} "
            f"{'cos_min':>8} {'cos_med':>8} {'<bar':>5}")
        for c in rep["clusters"]:
            eye = (f"{c['eye_px']['min']:.0f}-{c['eye_px']['max']:.0f}"
                   if c["eye_px"] else "-")
            det = (f"{c['det_score']['min']:.2f}-{c['det_score']['max']:.2f}"
                   if c["det_score"] else "-")
            sc = c["same_cluster_cosine"] or {}
            cmin = f"{sc['min']:.3f}" if sc else "-"
            cmed = f"{sc['median']:.3f}" if sc else "-"
            log(f"c{c['cluster_id']:<7} {','.join('t' + str(t) for t in c['track_ids']):<14} "
                f"{c['face_instances_unique']:>5} {eye:<18} {det:<18} "
                f"{cmin:>8} {cmed:>8} "
                f"{c['pairs_below_bind_bar']:>5}")
        co = rep["co_occurrence"]
        log("co-occurrence: " + (", ".join(f"c{p['a']}+c{p['b']}:{p['frames_shared']}f"
                                           for p in co) or "none"))
        a = rep["consistency"]["a_same_cluster"]
        b = rep["consistency"]["b_cross_cluster_max"]
        c3 = rep["consistency"]["c_face_availability"]
        log(f"consistency: same-cluster pairs={a['pairs_total']} "
            f"min={a['min_cosine']} median={a['median_cosine']} "
            f"below_bar={a['pairs_below_bind_bar']} | cross-cluster max={b['max'] if b else None} "
            f"p95={b.get('p95') if b else None} above_bar={len(rep['consistency']['cross_pairs_above_bind_bar'])} "
            f"| frames persons={c3['frames_with_persons']} with_face={c3['frames_with_face_evidence']} "
            f"no_face_ratio={c3['no_face_ratio']}")
        for f in rep["consistency"]["cross_pairs_above_bind_bar"]:
            log(f"  REVIEW cross-cluster pair {f['clusters']} cos={f['cosine']} "
                f"frames={f['frames']} (association error or re-entry)")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default=None, help="report output dir (default: fresh temp dir)")
    ap.add_argument("--seconds", type=float, default=60.0, help="window length")
    ap.add_argument("--centers", default=",".join(str(c) for c in DEFAULT_CENTERS),
                    help="comma-separated window centers in seconds")
    args = ap.parse_args()

    out_dir = Path(args.out) if args.out else Path(tempfile.mkdtemp(prefix="identity-validation-"))
    out_dir.mkdir(parents=True, exist_ok=True)
    log(f"output dir: {out_dir}")

    evs = load_events()
    centers = [float(c) for c in args.centers.split(",")]
    windows = build_windows(evs, centers, args.seconds)

    snap_before = prod_snapshot()
    reports = []
    for i, win in enumerate(windows, 1):
        _, report = run_window(win, i, out_dir)
        (out_dir / f"window-{i}-report.json").write_text(json.dumps(report, indent=1))
        reports.append(report)
    snap_after = prod_snapshot()
    untouched = snap_before == snap_after
    log(f"\nproduction out/ tree untouched after run: {untouched}")

    print_summary(reports)
    run_report = {
        "video": str(VIDEO), "step": STEP, "windows": reports,
        "production_out_untouched": untouched,
        "pid_seed_empty": json.loads((REPO / "out" / "pid_seed.json").read_text())["seeds"] == {},
        "statement": ("Shooter-association precision/recall is UNMEASURED: no human labels "
                      "exist (out/pid_seed.json empty). Cluster labels must be assigned by a "
                      "human using the per-cluster face-appearance signatures above; this "
                      "harness exists to make that labeling fast."),
    }
    (out_dir / "validation-report.json").write_text(json.dumps(run_report, indent=1))
    log(f"\nfull report: {out_dir / 'validation-report.json'}")
    log("harness done")
    return 0 if untouched else 1


if __name__ == "__main__":
    sys.exit(main())
