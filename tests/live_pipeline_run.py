"""Real end-to-end run of the identity pipeline on data/vod_30min_260815.mp4.

No mocks, no injected fakes: real YOLOv8n detector, vendored OSNet re-ID
encoder, insightface buffalo_l face engine. All mutable state (identity
clusters.json + face embedding store) lives under a TempDir root; the
production out/ tree and the video file are read-only.

What it does:
  Phase 1  decode frames 8000-12000 (t ~ 266.7-400s), feed
           PersonPipeline.process_frame every 2nd frame, collect tracking,
           clustering, cross-exit re-association, face-quality and timing data.
           Assert every player_id is None (no enrollment -> no identities).
  Phase 2  pick the clearest quality face belonging to the dominant cluster,
           enroll it as 'e2e-player-A' in the TEMP face store, re-run the
           segment from that frame with a FRESH identity index (same real
           detector/encoder/face engine), and verify the cluster binds to
           'e2e-player-A' and keeps the binding across view exits.

Run: .venv/bin/python tests/live_pipeline_run.py
Writes a JSON report into the temp dir and prints a summary.
"""
import json
import os
import shutil
import sys
import tempfile
import time
from collections import Counter, defaultdict
from pathlib import Path

import cv2
import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from src.face_id import (  # noqa: E402
    DEFAULT_FACE_STORE,
    FaceEngine,
    load_faces,
    store_faces,
)
from src.person_identity import IdentityIndex  # noqa: E402
from src.person_pipeline import PersonPipeline  # noqa: E402

VIDEO = REPO / "data" / "vod_30min_260815.mp4"
FPS = 30.0003
F0 = int(os.environ.get("E2E_F0", 8000))
F1 = int(os.environ.get("E2E_F1", 12000))
STEP = int(os.environ.get("E2E_STEP", 2))
ENROLL_PID = "e2e-player-A"


def center(face_bbox):
    return (face_bbox[0] + face_bbox[2]) / 2, (face_bbox[1] + face_bbox[3]) / 2


def inside(face, person_bbox):
    x, y = center(face)
    return person_bbox[0] <= x <= person_bbox[2] and person_bbox[1] <= y <= person_bbox[3]


class TimedEngine:
    """Delegates to the real FaceEngine; records per-call cost and outputs."""

    def __init__(self, inner):
        self.inner = inner
        self.frame_no = None
        self.analyze_ms = []
        self.match_ms = []
        self.matches = []  # (frame_no, player_id, similarity, margin)
        self.faces = []  # (frame_no, bbox, eye_px, det_score)

    def analyze(self, frame):
        t = time.perf_counter()
        out = self.inner.analyze(frame)
        self.analyze_ms.append((time.perf_counter() - t) * 1000)
        for f in out:
            self.faces.append((self.frame_no, list(f["bbox"]), f["eye_px"], f["det_score"]))
        return out

    def quality(self, face):
        return self.inner.quality(face)

    def best_match(self, emb, gallery):
        t = time.perf_counter()
        out = self.inner.best_match(emb, gallery)
        self.match_ms.append((time.perf_counter() - t) * 1000)
        if out is not None:
            self.matches.append((self.frame_no, out.get("player_id"),
                                 float(out.get("similarity", 0.0)),
                                 float(out.get("margin", 0.0))))
        return out


def prod_snapshot():
    snap = {}
    for p in (REPO / "out").rglob("*"):
        if p.is_file():
            st = p.stat()
            snap[str(p)] = (st.st_mtime_ns, st.st_size)
    return snap


def stats(xs):
    if not xs:
        return {"n": 0}
    a = np.asarray(xs, float)
    return {"n": len(a), "mean": round(float(a.mean()), 2), "p50": round(float(np.percentile(a, 50)), 2),
            "p95": round(float(np.percentile(a, 95)), 2), "max": round(float(a.max()), 2)}


def run_segment(pipeline, engine, cap, start, end, step, log):
    """Process [start, end] every `step` frames; returns per-frame records."""
    cap.set(cv2.CAP_PROP_POS_FRAMES, start)
    rows = []
    idx = start
    while idx <= end:
        ok, frame = cap.read()
        if not ok:
            log(f"  decode ended early at frame {idx}")
            break
        if (idx - start) % step == 0:
            engine.frame_no = idx
            t = time.perf_counter()
            res = pipeline.process_frame(frame, idx, idx / FPS)
            dt = (time.perf_counter() - t) * 1000
            persons = [{"track_id": p["track_id"], "cluster_id": p["cluster_id"],
                        "player_id": p["player_id"], "bbox": p["bbox"],
                        "face_sim": p["face_sim"]} for p in res["persons"]]
            rows.append({"frame": idx, "t": round(idx / FPS, 2), "ms": round(dt, 2),
                         "persons": persons, "events": res["events"]})
            if len(rows) % 200 == 0:
                log(f"  frame {idx} (t={idx / FPS:.0f}s): {len(rows)} processed, "
                    f"{dt:.0f} ms last, persons={len(persons)}")
        idx += 1
    return rows


def analyze_phase1(rows, engine, log):
    person_counts = [len(r["persons"]) for r in rows]
    clusters = set()
    track_first = {}       # track_id -> (frame, cluster)
    cluster_birth = {}     # cluster -> frame of first appearance
    cluster_frames = defaultdict(set)
    no_id = True
    for r in rows:
        for p in r["persons"]:
            c = p["cluster_id"]
            clusters.add(c)
            cluster_frames[c].add(r["frame"])
            cluster_birth.setdefault(c, r["frame"])
            if p["track_id"] not in track_first:
                track_first[p["track_id"]] = (r["frame"], c)
            if p["player_id"] is not None:
                no_id = False
    # cross-exit re-association: a new track joins a cluster that already existed
    reassoc = []
    for tid, (fr, c) in track_first.items():
        if cluster_birth[c] < fr:
            reassoc.append({"track_id": tid, "frame": fr, "cluster": c,
                            "cluster_born": cluster_birth[c]})
    # face quality per cluster (center-inside association)
    per_frame_persons = {r["frame"]: r["persons"] for r in rows}
    cluster_face_obs = defaultdict(list)
    for fr, bbox, eye, det in engine.faces:
        for p in per_frame_persons.get(fr, []):
            if inside(bbox, p["bbox"]):
                cluster_face_obs[p["cluster_id"]].append({"frame": fr, "eye_px": eye,
                                                          "det_score": det, "bbox": bbox,
                                                          "person_bbox": p["bbox"]})
                break
    log(f"phase1: {len(rows)} frames, persons/frame mean="
        f"{np.mean(person_counts):.2f} max={max(person_counts)}, "
        f"zero-person frames={sum(1 for c in person_counts if c == 0)}")
    log(f"phase1: distinct clusters={sorted(clusters)}, tracks={len(track_first)}, "
        f"cross-exit re-associations={len(reassoc)}")
    log(f"phase1: all player_id None: {no_id}")
    for c in sorted(cluster_face_obs):
        eyes = [o["eye_px"] for o in cluster_face_obs[c] if o["eye_px"] is not None]
        if eyes:
            log(f"  cluster {c}: {len(cluster_face_obs[c])} face obs, eye_px p50="
                f"{np.percentile(eyes, 50):.1f} max={max(eyes):.1f}")
    return {"no_id": no_id, "clusters": sorted(clusters),
            "n_tracks": len(track_first), "reassoc": reassoc,
            "person_counts": person_counts, "cluster_face_obs": cluster_face_obs}


def main():
    log = lambda msg: print(msg, flush=True)
    log(f"video: {VIDEO} exists={VIDEO.exists()}")
    tmp = Path(tempfile.mkdtemp(prefix="e2e-identity-"))
    log(f"TEMP ROOT: {tmp}")
    shutil.copy2(REPO / "yolov8n.pt", tmp / "yolov8n.pt")  # pipeline default looks in root
    before = prod_snapshot()

    identity_path = tmp / "out" / "identity" / "clusters.json"
    face_store = tmp / Path(DEFAULT_FACE_STORE).relative_to(REPO)
    log(f"identity state file : {identity_path}")
    log(f"face store file     : {face_store}")

    pipeline = PersonPipeline(tmp)
    log("[warm] loading detector (YOLOv8n, CPU)...")
    t = time.perf_counter()
    detector = pipeline._get_detector()
    detector(np.zeros((720, 1280, 3), np.uint8))
    det_warm = time.perf_counter() - t
    log(f"[warm] detector cold: {det_warm:.2f}s")
    log("[warm] loading OSNet encoder...")
    t = time.perf_counter()
    encoder = pipeline._get_encoder()
    encoder([np.zeros((64, 32, 3), np.uint8)])
    log(f"[warm] encoder cold: {time.perf_counter() - t:.2f}s")
    log("[warm] loading face engine (buffalo_l, CPU)...")
    engine = TimedEngine(pipeline._get_engine())
    t = time.perf_counter()
    engine.frame_no = -1
    engine.analyze(np.zeros((720, 1280, 3), np.uint8))
    log(f"[warm] face engine cold: {time.perf_counter() - t:.2f}s")
    # instrument the real components with timers
    det_calls, enc_calls = [], []

    def timed_detector(frame):
        t = time.perf_counter()
        out = detector(frame)
        det_calls.append((time.perf_counter() - t) * 1000)
        return out

    def timed_encoder(crops):
        t = time.perf_counter()
        out = encoder(crops)
        enc_calls.append((time.perf_counter() - t) * 1000)
        return out

    pipeline.detector = timed_detector
    pipeline.body_encoder = timed_encoder
    pipeline._face_engine = engine

    report = {"video": str(VIDEO), "temp_root": str(tmp),
              "warmup_s": {"detector": round(det_warm, 2)}}
    cap = cv2.VideoCapture(str(VIDEO))
    assert cap.isOpened(), "cannot open video"

    # ---------------- phase 1: no enrollment ----------------
    log(f"[phase1] frames {F0}-{F1} step {STEP} "
        f"(t={F0 / FPS:.1f}-{F1 / FPS:.1f}s), identity={identity_path}")
    t_start = time.perf_counter()
    rows1 = run_segment(pipeline, engine, cap, F0, F1, STEP, log)
    wall1 = time.perf_counter() - t_start
    ph1 = analyze_phase1(rows1, engine, log)
    assert ph1["no_id"], "FAIL: player_id set without enrollment"
    report["phase1"] = {
        "frames_processed": len(rows1),
        "person_counts": {"mean": round(float(np.mean(ph1["person_counts"])), 2),
                          "max": int(np.max(ph1["person_counts"]))},
        "distinct_clusters": ph1["clusters"],
        "n_tracks": ph1["n_tracks"],
        "cross_exit_reassoc": ph1["reassoc"],
        "timing_ms": {"total": stats([r["ms"] for r in rows1]),
                      "detector": stats(det_calls), "encoder": stats(enc_calls),
                      "face": stats(engine.analyze_ms), "face_match": stats(engine.match_ms)},
        "wall_s": round(wall1, 1),
    }
    det1, enc1 = list(det_calls), list(enc_calls)

    # ---------------- enrollment ----------------
    # dominant cluster = most quality face observations
    clusterA = max(ph1["cluster_face_obs"], key=lambda c: len(ph1["cluster_face_obs"][c]))
    obs = ph1["cluster_face_obs"][clusterA]
    cand = [o for o in obs if o["eye_px"] is not None and o["eye_px"] >= 9 and o["det_score"] >= 0.5]
    assert cand, "no enrollment-quality face observed for cluster A"
    pick = max(cand, key=lambda o: (o["eye_px"], o["det_score"]))
    X = pick["frame"]
    log(f"[enroll] cluster A={clusterA}: clearest face at frame {X} (t={X / FPS:.2f}s) "
        f"eye_px={pick['eye_px']:.1f} det_score={pick['det_score']:.3f}")
    cap.set(cv2.CAP_PROP_POS_FRAMES, X)
    ok, frameX = cap.read()
    assert ok
    facesX = [f for f in engine.inner.analyze(frameX) if engine.inner.quality(f)]
    mine = [f for f in facesX if inside(f["bbox"], pick["person_bbox"])]
    assert mine, "enrollment face not re-detected at frame X"
    gallery = load_faces(face_store)
    assert gallery == {}, "face store not empty before enrollment"
    recs = mine[:1]
    gallery[ENROLL_PID] = [{**f, "source": f"e2e:frame{X}"} for f in recs]
    store_faces(face_store, gallery)
    log(f"[enroll] enrolled {len(recs)} face(s) as {ENROLL_PID} into {face_store} "
        f"(eye_px={recs[0]['eye_px']:.1f}, det_score={recs[0]['det_score']:.3f})")

    # ---------------- phase 2: fresh identity, real gallery ----------------
    engine2 = TimedEngine(engine.inner)
    identity2_path = tmp / "out" / "identity" / "clusters_run2.json"
    pipeline2 = PersonPipeline(tmp, detector=timed_detector, body_encoder=timed_encoder,
                               face_engine=engine2,
                               identity=IdentityIndex(identity2_path))
    # Re-run the WHOLE segment with a fresh identity: the enrolled person may
    # exit the view right after X (observed: exits at ~t=382.1s) and never
    # return within the segment, so binding must be verified wherever the
    # person actually appears. This still includes all frames after X.
    log(f"[phase2] re-running frames {F0}-{F1} with fresh identity {identity2_path}, "
        f"gallery={list(load_faces(face_store))}")
    engine2.frame_no = F0
    rows2 = run_segment(pipeline2, engine2, cap, F0, F1, STEP, log)
    binds, bound_frame, bound_cluster = [], None, None
    post_bind_ok, post_bind_bad, exits = True, [], []
    seen_frames = {}
    for r in rows2:
        for e in r["events"]:
            if e.get("kind") == "bind":
                binds.append({"frame": r["frame"], "t": r["t"], **e})
        for p in r["persons"]:
            if p["cluster_id"] not in seen_frames:
                seen_frames[p["cluster_id"]] = {"first": r["frame"], "last": r["frame"],
                                                "tracks": set()}
            sf = seen_frames[p["cluster_id"]]
            sf["last"] = r["frame"]
            sf["tracks"].add(p["track_id"])
            if p["player_id"] == ENROLL_PID and bound_frame is None:
                bound_frame, bound_cluster = r["frame"], p["cluster_id"]
                log(f"[phase2] BOUND at frame {r['frame']} (t={r['t']:.2f}s) "
                    f"cluster={bound_cluster} face_sim={p['face_sim']}")
            if bound_cluster is not None and p["cluster_id"] == bound_cluster:
                if p["player_id"] != ENROLL_PID:
                    post_bind_ok = False
                    post_bind_bad.append({"frame": r["frame"], "player_id": p["player_id"]})
    # exit analysis for the bound cluster using per-frame presence
    presence = {r["frame"]: {p["cluster_id"] for p in r["persons"]} for r in rows2}
    frames_sorted = sorted(presence)
    cur_absent = 0
    for fr in frames_sorted:
        if bound_cluster is None:
            break
        if bound_cluster in presence[fr]:
            if cur_absent >= 10:
                exits.append({"reenter_frame": fr, "absent_frames": cur_absent})
            cur_absent = 0
        else:
            cur_absent += 1
    log(f"[phase2] bind events={binds}")
    log(f"[phase2] player_id persisted across exits: {post_bind_ok} "
        f"(violations={post_bind_bad}, view exits of bound cluster={exits})")
    report["phase2"] = {
        "start_frame": F0, "enroll_frame": X, "frames_processed": len(rows2),
        "enroll": {"eye_px": recs[0]["eye_px"], "det_score": recs[0]["det_score"],
                   "n_faces": len(recs)},
        "binds": binds,
        "bound_frame": bound_frame, "bound_cluster": bound_cluster,
        "persisted": post_bind_ok, "post_bind_violations": post_bind_bad[:10],
        "view_exits_after_bind": exits,
        "matches_seen": [{"frame": fr, "sim": round(s, 4), "margin": round(m, 4)}
                         for fr, pid, s, m in engine2.matches if pid == ENROLL_PID][-30:],
        "timing_ms": {"total": stats([r["ms"] for r in rows2]),
                      "detector": stats(det_calls[len(det1):]),
                      "encoder": stats(enc_calls[len(enc1):]),
                      "face": stats(engine2.analyze_ms)},
    }

    # ---------------- isolation checks ----------------
    after = prod_snapshot()
    changed = [k for k in set(before) | set(after)
               if before.get(k) != after.get(k)]
    assert not changed, f"FAIL: production out/ modified: {changed[:5]}"
    log(f"[isolation] production out/ unchanged ({len(before)} files checked)")
    log(f"[isolation] identity state under temp: {identity_path.parent} "
        f"exists={identity_path.exists()}")
    log(f"[isolation] face store under temp: {face_store} "
        f"exists={face_store.exists()}")
    report["isolation"] = {"prod_out_unchanged": True, "n_files_checked": len(before),
                           "identity_path": str(identity_path),
                           "face_store": str(face_store)}

    cap.release()
    out = tmp / "e2e_report.json"
    out.write_text(json.dumps(report, indent=2))
    log(f"report written: {out}")
    log(json.dumps({k: report[k] for k in ("phase1", "phase2")}, indent=2, default=str)[:4000])


if __name__ == "__main__":
    main()
