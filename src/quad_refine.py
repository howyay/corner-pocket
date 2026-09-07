"""Strip-refined table corners: refine a prior quad using local edge evidence.

For each side of the prior quad, cut a perpendicular strip (~2.5x prior side
length wide, +/-W px), find the strongest cloth->non-cloth boundary line INSIDE
the strip (treating the strip as a 1-D signal along the normal), and move the
side there. Iterate twice. Robust for static cameras: per-frame refinements are
small, so a MAD-filtered temporal median gives the segment corners.
"""
import sys
import numpy as np
import cv2

sys.path.insert(0, '/home/operator/projects/pool/src')
from quad_fit import cloth_mask_tight


def refine_quad(bgr, prior, band_px=70, n_steps=25, iters=2):
    """prior: (4,2) ordered TL,TR,BR,BL. Returns refined (4,2) or None."""
    mask, hue = cloth_mask_tight(bgr)
    if mask is None:
        return None
    quad = np.asarray(prior, np.float64).copy()
    h, w = mask.shape[:2]
    # normalize mask to 0/255
    mm = (mask > 0).astype(np.uint8) * 255
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    mm = cv2.morphologyEx(mm, cv2.MORPH_CLOSE, k)
    for _ in range(iters):
        moved = []
        for s in range(4):
            a = quad[s]
            b = quad[(s + 1) % 4]
            mid = (a + b) / 2.0
            # outward normal (towards outside of the quad, i.e., away from centroid)
            c = quad.mean(axis=0)
            nvec = a - b
            nlen = np.hypot(nvec[0], nvec[1])
            if nlen < 1:
                return None
            nrm = np.array([-nvec[1], nvec[0]]) / nlen
            if np.dot(nrm, mid - c) < 0:
                nrm = -nrm
            # profile along normal across the strip through the side's midpoint
            prof_lo = np.zeros(n_steps)
            step = 2.0 * band_px / n_steps
            prev_on = None
            best_off = None
            for kk in range(n_steps):
                off = -band_px + kk * step
                p = mid + nrm * off
                pi = p.astype(int)
                if not (0 <= pi[0] < w and 0 <= pi[1] < h):
                    continue
                on = mm[pi[1], pi[0]] > 0
                if prev_on is not None and prev_on and not on:
                    best_off = off
                    break
                prev_on = on
            if best_off is None:
                # fall back: strongest transition over multiple samples along side
                trans = []
                for frac in np.linspace(0.15, 0.85, 7):
                    p0 = a + (b - a) * frac
                    prev = None
                    for kk in range(n_steps):
                        off = -band_px + kk * step
                        p = p0 + nrm * off
                        pi = p.astype(int)
                        if not (0 <= pi[0] < w and 0 <= pi[1] < h):
                            continue
                        on = mm[pi[1], pi[0]] > 0
                        if prev is not None and prev and not on:
                            trans.append(off)
                            break
                        prev = on
                if trans:
                    best_off = float(np.median(trans))
                else:
                    return None
            moved.append(nrm * best_off)
        for s in range(4):
            quad[s] = quad[s] + moved[s]
    return quad.astype(np.float32)


if __name__ == "__main__":
    import json
    ref = np.array(json.load(open("/home/operator/projects/pool/out/corners_30min.json"))["corners"], np.float32)
    TIMES = list(range(60, 1741, 120))
    cap = cv2.VideoCapture("/home/operator/projects/pool/data/vod_30min_260815.mp4")
    errs, fails = [], []
    for t in TIMES:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
        ok, f = cap.read()
        if not ok:
            continue
        q = refine_quad(f, ref)
        if q is None:
            fails.append(t)
            print(f"t={t}: FAIL")
            continue
        e = float(np.linalg.norm(q - ref, axis=1).mean())
        errs.append(e)
        print(f"t={t}: ok mean_px_err={e:.1f}")
    cap.release()
    if errs:
        errs.sort()
        print(f"summary: ok {len(errs)}/{len(TIMES)} median={errs[len(errs)//2]:.1f} "
              f"p90={errs[int(len(errs)*0.9)]:.1f} fails={fails}")
