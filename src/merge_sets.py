"""Merge two labeled crop sets into one dir, then run the leave-one-frame-out sweep.

Usage: merge_sets.py <dir1> <dir2> <merged_dir>
Crops are copied with unique prefixes (v1_, v2_); meta/labels/ctx.json rebuilt;
labels.json values 0..15 (ints) carried over.
"""
import json
import shutil
import sys
from pathlib import Path

d1, d2, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
out.mkdir(parents=True, exist_ok=True)
(out / 'ctx').mkdir(exist_ok=True)

meta_rows = []
ctx_map = {}
for prefix, d in (('v1', d1), ('v2', d2)):
    meta = json.loads((d / 'meta.json').read_text()) if (d / 'meta.json').exists() else []
    ctx = json.loads((d / 'ctx.json').read_text()) if (d / 'ctx.json').exists() else {}
    lab = json.loads((d / 'labels.json').read_text()) if (d / 'labels.json').exists() else {}
    for r in meta:
        p = Path(r['file'])
        new_name = f"{prefix}_{p.name}"
        dst = out / new_name
        if p.exists() and not dst.exists():
            shutil.copy2(p, dst)
        c = ctx.get(r['file'])
        if c:
            ctx_src = Path(c)
            ctx_dst = out / 'ctx' / f'{prefix}_' + ctx_src.name
            if ctx_src.exists() and not ctx_dst.exists():
                shutil.copy2(ctx_src, ctx_dst)
            ctx_map[str(dst)] = str(ctx_dst)
        row = {'t': r['t'], 'file': str(dst), 'score': r.get('score')}
        lv = lab.get(r['file'])
        if isinstance(lv, int):
            row['label'] = lv
        meta_rows.append(row)

(out / 'meta.json').write_text(json.dumps(meta_rows, indent=1))
(out / 'ctx.json').write_text(json.dumps(ctx_map, indent=1))
lab_out = {r['file']: r['label'] for r in meta_rows if 'label' in r}
(out / 'labels.json').write_text(json.dumps(lab_out, indent=1))
n_lab = len(lab_out)
frames = sorted({int(r['t']) for r in meta_rows})
print(f'merged: {len(meta_rows)} crops, {n_lab} labeled, frames {frames}')
