"""Rebuild OSNet identities from explicit A/B seeds; never infer B from bystanders.

Legacy unlabeled seeds are preserved but do not train identities. Without both
identities, propagation is unknown. Heavy dependencies load only inside run().
"""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]


def explicit_seeds(tracklets, seeds):
    """Return valid user-labeled track keys, ignoring legacy implicit-A seeds."""
    valid = {f'{track["id"]}:{win}' for win, window in tracklets.items()
             for track in window["tracklets"]}
    return {key: seed["label"] for key, seed in seeds.items()
            if key in valid and seed.get("label") in ("A", "B", "ignore")}


def run(root=ROOT):
    root = Path(root)
    sys.path.insert(0, str(ROOT))
    from annotator.unified_server import atomic_save
    out = root / "out"
    tracklets = json.loads((out / "pid2_tracklets.json").read_text())
    # the operator's seeds come from the store the server writes them to: the file by
    # default, Postgres when POOL_DATABASE_URL is set (inherited from the service)
    from src.store import open_store
    seeds = open_store(root).seeds_get("vod30")
    labels = explicit_seeds(tracklets, seeds)
    mapping = {f'{tk["id"]}:{win}': "?" for win, window in tracklets.items() for tk in window["tracklets"]}
    if not {"A", "B"}.issubset(set(labels.values())):
        reason = "Explicit usable A and B seeds are required; no identities inferred."
        atomic_save(out / "pid_seed_protos.json", {"A": None, "B": None, "n_per_identity": {"A": 0, "B": 0}, "reason": reason})
        atomic_save(out / "pid_seed_tracks.json", {"map": mapping, "detail": {}, "reason": reason})
        print(reason)
        return

    import cv2
    import numpy as np
    import torch
    sys.path.insert(0, str(ROOT / "src" / "reid"))
    import osnet
    weights = root / "src" / "reid" / "weights" / "osnet_x0_25_msmt17.pth"
    if not weights.is_file():
        raise RuntimeError(f"OSNet weights not found: {weights}")
    model = osnet.osnet_x0_25(pretrained=False, num_classes=1000)
    state = torch.load(weights, map_location="cpu", weights_only=True)
    state = state.get("state_dict", state)
    state = {k.removeprefix("module."): v for k, v in state.items()}
    state = {k: v for k, v in state.items() if not k.startswith("classifier")}
    result = model.load_state_dict(state, strict=False)
    missing = [k for k in result.missing_keys if not k.startswith("classifier")]
    if missing or result.unexpected_keys:
        raise RuntimeError(f"OSNet checkpoint mismatch: missing={missing}, unexpected={result.unexpected_keys}")
    model.eval()
    from src.datasets import media_path
    cap = cv2.VideoCapture(str(media_path(root, "vod30")))
    if not cap.isOpened():
        cap.release()
        raise RuntimeError("Cannot open vod30 video")
    cache = {}
    mean = np.array([0.485, 0.456, 0.406], np.float32)
    std = np.array([0.229, 0.224, 0.225], np.float32)
    try:
        def embeddings(win, track):
            key = f'{track["id"]}:{win}'
            if key in cache:
                return cache[key]
            values = []
            for t, box in track["samples"][::2]:
                cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
                ok, frame = cap.read()
                if not ok:
                    continue
                x0, y0, x1, y1 = map(int, box)
                h, w = frame.shape[:2]
                crop = frame[max(0, y0 - 15):min(h, y1 + 15), max(0, x0 - 15):min(w, x1 + 15)]
                if not crop.size:
                    continue
                pixels = cv2.resize(crop, (128, 256))[:, :, ::-1].astype(np.float32) / 255
                tensor = torch.from_numpy(((pixels - mean) / std).transpose(2, 0, 1)).unsqueeze(0)
                with torch.no_grad():
                    embedding = model(tensor)[0].numpy()
                if not np.isfinite(embedding).all() or np.linalg.norm(embedding) <= 1e-9:
                    raise RuntimeError("OSNet returned invalid embedding")
                values.append(embedding / np.linalg.norm(embedding))
            cache[key] = values
            return values

        trained = {"A": [], "B": []}
        for win, window in tracklets.items():
            for track in window["tracklets"]:
                label = labels.get(f'{track["id"]}:{win}')
                if label in trained:
                    values = embeddings(win, track)
                    if values:
                        trained[label].append(np.mean(values, axis=0))
        if not all(trained.values()):
            reason = "No usable frame embeddings for both explicit A/B identities."
            atomic_save(out / "pid_seed_protos.json", {"A": None, "B": None, "reason": reason})
            atomic_save(out / "pid_seed_tracks.json", {"map": mapping, "detail": {}, "reason": reason})
            print(reason)
            return
        prototypes = {}
        for label, values in trained.items():
            proto = np.mean(values, axis=0)
            prototypes[label] = proto / (np.linalg.norm(proto) + 1e-9)
        detail = {}
        for win, window in tracklets.items():
            for track in window["tracklets"]:
                key = f'{track["id"]}:{win}'
                if labels.get(key) == "ignore":
                    detail[key] = {"reason": "user ignored"}
                    continue
                values = embeddings(win, track)
                if not values:
                    continue
                vector = np.mean(values, axis=0)
                vector /= np.linalg.norm(vector) + 1e-9
                a, b = (float(vector @ prototypes[label]) for label in ("A", "B"))
                mapping[key] = labels.get(key) or (("A" if a > b else "B") if abs(a - b) > 0.02 else "?")
                detail[key] = {"cosA": a, "cosB": b, "margin": abs(a - b)}
        atomic_save(out / "pid_seed_protos.json", {**{k: v.tolist() for k, v in prototypes.items()}, "n_per_identity": {k: len(v) for k, v in trained.items()}})
        atomic_save(out / "pid_seed_tracks.json", {"map": mapping, "detail": detail, "seed_labels": labels})
        print(f"Rebuilt {len(mapping)} tracks using explicit A/B seeds")
    finally:
        cap.release()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    run(parser.parse_args().root)
