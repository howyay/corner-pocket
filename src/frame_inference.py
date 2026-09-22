"""Lazy, local-weights-only selected-frame inference. No temporal event claims."""
from pathlib import Path


def inference_device():
    """AMD/ROCm and NVIDIA GPUs both expose torch.cuda; fall back to CPU."""
    import torch
    return 'cuda' if torch.cuda.is_available() else 'cpu'
from threading import Lock


_person_lock = Lock()
_person_model = None
_person_weights = None


def infer_frame(frame, detectors, root, progress=lambda stage: None):
    """Return raw-pixel detections using the existing table/SAM3 pipeline helpers."""
    import cv2
    from src.table_detect import detect_table

    boxes = []
    polygon = None
    table = None
    if 'table' in detectors or 'balls' in detectors:
        progress('detecting table')
        table = detect_table(frame)
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
