"""Train the smallest ball-identity classifier that reaches 90%.

Teacher labels come from SAM3 per-class text prompts (out/ball_labels).  We
train small ImageNet-initialised CNNs on ball crops and evaluate per-frame
leave-one-out (train on crops of N-1 frames, test on the held-out frame) -
the honest generalization test for a fixed camera.

Usage: python train_ball_id.py [labels_dir]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import cv2
import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Dataset
import torchvision
from torchvision import transforms

N_CLASSES = 16
IMG = 96


class BallCrops(Dataset):
    def __init__(self, items, tf):
        self.items = items
        self.tf = tf

    def __len__(self):
        return len(self.items)

    def __getitem__(self, i):
        path, cls = self.items[i]
        img = cv2.imread(path)
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        img = cv2.resize(img, (IMG, IMG))
        return self.tf(torch.from_numpy(img).permute(2, 0, 1).float() / 255.0), cls


def make_model(name: str, weights):
    if name == "mobilenetv3_small":
        m = torchvision.models.mobilenet_v3_small(weights=weights)
        m.classifier[3] = nn.Linear(m.classifier[3].in_features, N_CLASSES)
    elif name == "squeezenet1_0":
        m = torchvision.models.squeezenet1_0(weights=weights)
        m.classifier[1] = nn.Conv2d(512, N_CLASSES, kernel_size=1)
    elif name == "resnet18":
        m = torchvision.models.resnet18(weights=weights)
        m.fc = nn.Linear(512, N_CLASSES)
    else:
        raise ValueError(name)
    return m


def main():
    labels_dir = Path(sys.argv[1] if len(sys.argv) > 1 else "out/ball_labels")
    use_label_file = (labels_dir / "labels.json").exists()
    if use_label_file:
        # human-labeled crops: file -> 0..15 (0 = cue/white) or "u" (unsure)
        lab = json.load(open(labels_dir / "labels.json"))
        meta = json.load(open(labels_dir / "meta.json"))
        by_file = {r["file"]: r for r in meta}
        rows = []
        for f, v in lab.items():
            if not isinstance(v, int):
                continue  # skip "u" unsure / junk
            r = by_file.get(f)
            t = r["t"] if r else 0.0
            rows.append({"t": t, "file": f, "class": v})
        meta = rows
        print(f"using {len(meta)} human labels (unsure/skipped excluded)", flush=True)
    else:
        meta = json.load(open(labels_dir / "meta.json"))
    # group by frame for leave-one-frame-out
    by_frame = {}
    for row in meta:
        by_frame.setdefault(int(row["t"]), []).append((row["file"], row["class"]))
    frames = sorted(by_frame)
    print(f"{len(meta)} crops across {len(frames)} frames: {frames}", flush=True)
    tf_train = transforms.Compose([
        transforms.RandomHorizontalFlip(),
        transforms.RandomAffine(10, translate=(0.1, 0.1)),
    ])
    tf_eval = transforms.Compose([])

    results = {}
    for name in ["squeezenet1_0", "mobilenetv3_small", "resnet18"]:
        accs = []
        for held in frames:
            train_items = [it for f in frames if f != held for it in by_frame[f]]
            test_items = by_frame[held]
            if len(set(c for _, c in test_items)) < 2:
                continue
            torch.manual_seed(0)
            model = make_model(name, torchvision.models.get_weight(
                {"mobilenetv3_small": "MobileNet_V3_Small_Weights.IMAGENET1K_V1",
                 "squeezenet1_0": "SqueezeNet1_0_Weights.IMAGENET1K_V1",
                 "resnet18": "ResNet18_Weights.IMAGENET1K_V1"}[name]))
            opt = torch.optim.Adam(model.parameters(), lr=1e-3)
            lossf = nn.CrossEntropyLoss()
            train_ds = BallCrops(train_items, tf_train)
            dl = DataLoader(train_ds, batch_size=16, shuffle=True)
            model.train()
            for epoch in range(12):
                for x, y in dl:
                    opt.zero_grad()
                    lossf(model(x), y).backward()
                    opt.step()
            model.eval()
            with torch.no_grad():
                td = BallCrops(test_items, tf_eval)
                xs = torch.stack([td[i][0] for i in range(len(td))])
                ys = torch.tensor([td[i][1] for i in range(len(td))])
                preds = model(xs).argmax(1)
                accs.append(float((preds == ys).float().mean()))
        n_params = sum(p.numel() for p in make_model(name, None).parameters())
        mean_acc = float(np.mean(accs)) if accs else 0.0
        results[name] = {"acc": round(mean_acc, 3), "params_m": round(n_params / 1e6, 2),
                         "folds": len(accs)}
        print(f"{name}: params={n_params/1e6:.2f}M  leave-one-frame acc={mean_acc:.3f} "
              f"({len(accs)} folds)", flush=True)
    json.dump(results, open("out/ball_id_results.json", "w"), indent=1)


if __name__ == "__main__":
    main()
