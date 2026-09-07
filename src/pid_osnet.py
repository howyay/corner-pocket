"""PID-4 v1: OSNet x0.25 embeddings over table-zone person crops.

Takes the pid_identity feats (t, bbox, colour cluster A/B), re-decodes each
crop, embeds with MSMT17-pretrained osnet_x0_25, and reports:
  - intra/inter cosine separation by colour cluster,
  - leave-one-out nearest-neighbour cluster agreement,
  - mean colour distance for comparison.
"""
import json
import sys

import cv2
import numpy as np
import torch

sys.path.insert(0, "/home/operator/projects/pool/src/reid")
import osnet as O  # noqa

VIDEO = "/home/operator/projects/pool/data/vod_30min_260815.mp4"
FEATS = json.load(open("/home/operator/projects/pool/out/pid_identity_v0.json"))["feats"]
W = "/home/operator/projects/pool/src/reid/weights/osnet_x0_25_msmt17.pth"
MEAN = np.array([0.485, 0.456, 0.406], np.float32)
STD = np.array([0.229, 0.224, 0.225], np.float32)

model = O.osnet_x0_25(pretrained=False, num_classes=1000)
sd = torch.load(W, map_location="cpu", weights_only=False)
sd = sd.get("state_dict", sd)
sd = {k: v for k, v in sd.items() if not k.startswith("classifier")}
model.load_state_dict(sd, strict=False)
model.eval()

cap = cv2.VideoCapture(VIDEO)
embs = []
for f in FEATS:
    t, bb = f["t"], f["bbox"]
    cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
    ok, bgr = cap.read()
    if not ok:
        continue
    x0, y0, x1, y1 = bb
    pad = 25
    h, w = bgr.shape[:2]
    x0, y0 = max(0, x0 - pad), max(0, y0 - pad)
    x1, y1 = min(w, x1 + pad), min(h, y1 + pad)
    crop = bgr[y0:y1, x0:x1]
    if crop.size == 0:
        continue
    crop = cv2.resize(crop, (128, 256))  # reid convention WxH
    rgb = crop[:, :, ::-1].astype(np.float32) / 255.0
    rgb = (rgb - MEAN) / STD
    x = torch.from_numpy(rgb.transpose(2, 0, 1)).unsqueeze(0)
    with torch.no_grad():
        emb = model(x)[0].numpy()
    embs.append({"t": t, "cluster": f["cluster"], "emb": emb})
cap.release()

E = np.array([e["emb"] for e in embs])
E /= np.linalg.norm(E, axis=1, keepdims=True) + 1e-9
lab = np.array([e["cluster"] for e in embs])
sim = E @ E.T
np.fill_diagonal(sim, np.nan)
same = lab[:, None] == lab[None, :]
intra = sim[same & ~np.isnan(sim)]
inter = sim[~same & ~np.isnan(sim)]
print(f"persons embedded: {len(embs)}")
print(f"intra cosine mean {np.nanmean(intra):.3f}  inter {np.nanmean(inter):.3f}  "
      f"gap {np.nanmean(intra)-np.nanmean(inter):.3f}")
nn_same = []
for i in range(len(embs)):
    j = int(np.nanargmax(sim[i]))
    nn_same.append(int(lab[j] == lab[i]))
print(f"leave-one-out NN same-cluster: {sum(nn_same)}/{len(embs)} = {sum(nn_same)/len(embs):.2f}")
json.dump({"n": len(embs),
           "intra_cos": round(float(np.nanmean(intra)), 3),
           "inter_cos": round(float(np.nanmean(inter)), 3),
           "nn_same_cluster": f"{sum(nn_same)}/{len(embs)}"},
          open("/home/operator/projects/pool/out/pid_osnet_eval.json", "w"), indent=1)
print("wrote out/pid_osnet_eval.json")
