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

sys.path.insert(0, '/home/operator/projects/pool/src')
from train_ball_id import BallCrops, make_model, N_CLASSES, IMG  # noqa

NAME = 'resnet18'
labels_dir = Path('/home/operator/projects/pool/out/unlabeled_crops')
lab = json.load(open(labels_dir / 'labels.json'))
meta = json.load(open(labels_dir / 'meta.json'))
by_file = {r['file']: r for r in meta}
rows = [{'t': r['t'], 'file': f, 'class': v} for f, v in lab.items() if isinstance(v, int) and f in by_file for r in [by_file[f]]]
by_frame = {}
for row in rows:
    by_frame.setdefault(int(row['t']), []).append((row['file'], row['class']))
frames = sorted(by_frame)

tf_train = transforms.Compose([transforms.RandomHorizontalFlip()])
tf_eval = transforms.Compose([])

conf = np.zeros((N_CLASSES, N_CLASSES), dtype=int)
correct = 0
total = 0
for held in frames:
    train_items = [it for f in frames if f != held for it in by_frame[f]]
    test_items = by_frame[held]
    torch.manual_seed(0)
    model = make_model(NAME, torchvision.models.get_weight('ResNet18_Weights.IMAGENET1K_V1'))
    opt = torch.optim.Adam(model.parameters(), lr=1e-3)
    lossf = nn.CrossEntropyLoss()
    dl = DataLoader(BallCrops(train_items, tf_train), batch_size=16, shuffle=True)
    model.train()
    for epoch in range(12):
        for x, y in dl:
            opt.zero_grad()
            lossf(model(x), y).backward()
            opt.step()
    model.eval()
    td = BallCrops(test_items, tf_eval)
    with torch.no_grad():
        for i in range(len(td)):
            x, y = td[i]
            pred = int(model(x.unsqueeze(0)).argmax(1))
            conf[y, pred] += 1
            if pred == y:
                correct += 1
            total += 1
NAMES = {0:'cue W',1:'1 yl',2:'2 bl',3:'3 rd',4:'4 pk',5:'5 or',6:'6 gr',7:'7 br',8:'8 blk',
         9:'9 yls',10:'10 bls',11:'11 rds',12:'12 pks',13:'13 ors',14:'14 grs',15:'15 brs'}
print(f'overall: {correct}/{total} = {correct/total:.3f}')
print('confusion (rows=true, cols=pred):')
hdr = '     ' + ' '.join(f'{c:>6}' for c in range(16))
print(hdr)
for t in range(16):
    row = conf[t]
    if row.sum() == 0:
        continue
    top = np.argsort(-row)[:3]
    print(f'{t:>3} {NAMES[t]:<7} n={row.sum():<3} preds: ' + ' '.join(f'{NAMES[c]}={row[c]}' for c in top if row[c] > 0))
