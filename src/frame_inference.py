"""Lazy, local-weights-only selected-frame inference. No temporal event claims."""
import json
from pathlib import Path


def inference_device():
    """AMD/ROCm and NVIDIA GPUs both expose torch.cuda; fall back to CPU."""
    import torch
    return 'cuda' if torch.cuda.is_available() else 'cpu'
from threading import Lock


_person_lock = Lock()
_person_model = None
_person_weights = None


def _saved_anchor_quad(path, n=4):
    """First ``n`` saved hand anchors as an ordered quad, or None.

    ``out/pid_anchors_<dataset>.json`` holds the operator's hand-placed pocket
    points.  The earliest saved time is used: the camera is static per segment
    and that is the time the viewer opens on.
    """
    try:
        saved = json.loads(Path(path).read_text())
    except Exception:
        return None
    return anchor_quad(saved, n)


def anchor_quad(saved, n=4):
    """The ordered quad of the earliest saved anchor set in ``{"anchors": {t: pts}}``,
    or None - the same rule as :func:`_saved_anchor_quad`, for a document already
    read (the server reads it through the store)."""
    try:
        import numpy as np
        anchors = saved['anchors']
        key = min(anchors, key=float)
        pts = np.asarray(anchors[key][:n], np.float32)
    except Exception:
        return None
    if pts.shape != (n, 2) or not np.isfinite(pts).all():
        return None
    from src.table_detect import _order_corners
    return _order_corners(pts)


def app_prior_source(dataset, root=None):
    """Path of the anchor file the app path's seed comes from, or None.

    Split out from :func:`app_prior_for` so a caller can state *where* its search
    centre came from: the measurement harnesses use it to assert that no detector is
    ever seeded from a file it is scored against (the reference
    ``out/corners_30min_v2.json`` was both, which is what made the vod30 score
    circular - docs/app-path-refusal.md).
    """
    base = Path(root) if root is not None else Path(__file__).resolve().parent.parent
    path = base / 'out' / f'pid_anchors_{dataset}.json'
    return path if _saved_anchor_quad(path) is not None else None


def app_prior_for(dataset, root=None):
    """Saved table geometry the app path searches around for ``dataset``, or None.

    The viewer clears the automatic cloth quad against the dataset's hand-placed
    pocket anchors (``annotator/app.js`` ``validateCloth``) and projects the pocket
    markers from those same points, so the app path searches around that geometry.
    On vod30 those anchors track the visible cloth's left edge within 6-13 px, while
    ``out/corners_30min_v2.json`` - the reference this used to search around - sits
    67-90 px off it (docs/app-path-refusal.md), which is why the refinement never
    reached the boundary and the viewer refused every frame.  That file is a
    measured-bad seed and is never used here again.

    No hand anchors means no refinement prior: the caller keeps its own documented
    fallback (``detect_table_for_frame`` returns the naive detector's result with
    ``reason='no_prior'``) instead of guessing from a reference of unknown quality.
    """
    source = app_prior_source(dataset, root=root)
    return None if source is None else _saved_anchor_quad(source)


def detect_table_for_frame(frame, dataset=None, prior=None, root=None):
    """App-path table detection: static-camera prior plus local refinement.

    Returns the improved detector's dict (``corners``/``mask``/``debug`` plus
    ``confidence``/``reason``/``source``).  The search centre is ``prior`` when
    given, else :func:`app_prior_for` for the named dataset.  When neither is
    available the call falls back to the naive detector, so a caller that cannot
    name its dataset still gets the old behaviour rather than an error.
    """
    from src.table_refine import detect_table_refined
    centre = prior if prior is not None else (app_prior_for(dataset, root=root) if dataset else None)
    return detect_table_refined(frame, prior=centre)


def table_quad_note(result, seed_file=None, refused=None):
    """What the table detection decided about the quad, for a viewer payload.

    ``result`` is the dict the caller used, ``refused`` the refinement result whose
    refusal forced the naive fallback (None when the refinement was used or never
    ran).  Without this the viewer only sees ``corners: null``: the reason codes and
    the per-side evidence stay inside the refine path and the operator is left
    looking at a silent absence (docs/app-path-refusal.md).

    Additive and code-only - the UI owns the wording.  Returns::

        {'state': 'refined' | 'naive_fallback' | 'no_seed',
         'reason': <top-level code or None>,      # why the refinement refused
         'confidence': <float or None>,
         'source': <detector source string>,
         'verified_sides': <int or None>,
         'sides': [{'side': 0..3, 'state': 'verified'|'inherited'|'unverified',
                    'reason': <per-side code>}],
         'seed_file': <path or None>}
    """
    decided = refused if refused is not None else result
    debug = decided.get('debug_info') or {}
    if isinstance(debug, dict) and isinstance(debug.get('tried'), list) and debug['tried']:
        debug = (debug['tried'][0].get('info') or {})     # the refused seed attempt
    sides = []
    for report in (debug.get('sides') or []):
        if not isinstance(report, dict) or 'side' not in report:
            continue
        code = report.get('reason')
        # An inherited side still reports verified=True in src/table_refine (it is the
        # side's own prior, not this frame's measurement), so check it first.
        if report.get('inherited') or code == 'side_inherited':
            state = 'inherited'
        elif report.get('verified'):
            state = 'verified'
        else:
            state = 'unverified'
        entry = {'side': int(report['side']), 'state': state}
        if code and code != 'side_inherited':
            entry['reason'] = str(code)
        sides.append(entry)
    if result.get('refined'):
        state = 'refined'
    else:
        state = 'naive_fallback' if refused is not None else 'no_seed'
    return {'state': state,
            'reason': decided.get('reason'),
            'confidence': result.get('confidence'),
            'source': result.get('source') or 'naive',
            'verified_sides': debug.get('verified_sides'),
            'sides': sides,
            'seed_file': None if seed_file is None else str(seed_file)}


def infer_frame(frame, detectors, root, progress=lambda stage: None, dataset=None):
    """Return raw-pixel detections using the existing table/SAM3 pipeline helpers.

    ``dataset`` selects the saved static-camera prior for the cloth-boundary
    detector (:func:`app_prior_for`: the dataset's hand anchors), resolved under
    ``root`` so a caller pointed at another tree never reads this one's artifacts;
    without it the call keeps the historical naive result, so existing callers are
    unaffected.
    """
    import cv2
    from src.table_detect import detect_table

    boxes = []
    polygon = None
    table = None
    if 'table' in detectors or 'balls' in detectors:
        progress('detecting table')
        table = detect_table_for_frame(frame, dataset=dataset, root=root)
        if 'table' in detectors and table['corners'] is not None:
            polygon = table['corners'].tolist()
    if 'person' in detectors:
        progress('loading local YOLOv8n / detecting persons')
        weights = Path(root) / 'yolov8n.pt'
        if not weights.is_file():
            raise RuntimeError('Local yolov8n.pt is missing; downloads are disabled')
        from ultralytics import YOLO
        global _person_model, _person_weights
        stamp = (weights.resolve(), weights.stat().st_mtime_ns, weights.stat().st_size)
        # Ultralytics predictors are mutable: serialize loading and prediction.
        with _person_lock:
            if _person_model is None or _person_weights != stamp:
                _person_model = YOLO(str(weights))
                _person_weights = stamp
            result = _person_model.predict(frame, classes=[0], device=inference_device(), verbose=False)[0]
            person_boxes = result.boxes.xyxy.cpu().tolist()
            person_scores = result.boxes.conf.cpu().tolist()
        for box, score in zip(person_boxes, person_scores):
            x1, y1, x2, y2 = box
            boxes.append({'label': 'person', 'bbox': box, 'center': [(x1+x2)/2, (y1+y2)/2], 'score': score})
    if 'balls' in detectors:
        progress('loading local SAM3 on CPU; this can take several minutes')
        # Reuse the exact PoC inference, classification and filtering helpers.
        checkpoint = Path(root) / 'data' / 'sam3.safetensors'
        if not checkpoint.is_file():
            raise RuntimeError('Local data/sam3.safetensors is missing; downloads are disabled')
        from src.pipeline import filter_instances
        from src.sam3_cpu import load_sam3_image_model, make_processor
        from PIL import Image
        import torch
        model = load_sam3_image_model(checkpoint_path=str(checkpoint), device='cpu')
        processor = make_processor(model)
        progress('running SAM3 balls on CPU (SAM3 is pinned to CPU, not GPU; expect minutes per frame)')
        device = inference_device()
        with torch.inference_mode(), torch.autocast(device_type=device, dtype=torch.bfloat16, enabled=device != 'cpu'):
            state = processor.set_image(Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)))
            state = processor.set_text_prompt(prompt='billiard ball', state=state)
        balls = filter_instances(state, table['mask'], frame)
        h, w = frame.shape[:2]
        for ball in balls:
            x, y, r = ball['cx'], ball['cy'], ball['r']
            boxes.append({'label': 'ball', 'bbox': [max(0, x-r), max(0, y-r), min(w, x+r), min(h, y+r)],
                          'center': [x, y], 'score': ball['score'], 'color': ball['color'], 'style': ball['style']})
    return {'boxes': boxes, 'table_polygon': polygon, 'detectors': list(detectors),
            'events_supported': False, 'event_note': 'Single frames cannot infer shots or events; time-window inference is deferred.'}
