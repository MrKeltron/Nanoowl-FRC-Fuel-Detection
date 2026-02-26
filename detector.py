# ==============================================================================
# detector.py - YOLOv8 ball detection
# Loads the model and runs inference on each frame
# ==============================================================================

import torch
from ultralytics import YOLO


def get_device(preference: str) -> str:
    """Resolves the compute device based on config preference."""
    if preference == "auto":
        if torch.cuda.is_available():
            device = "cuda"
            print(f"[Detector] GPU detected: {torch.cuda.get_device_name(0)}")
        else:
            device = "cpu"
            print("[Detector] No GPU found, using CPU.")
    else:
        device = preference
        print(f"[Detector] Using device from config: {device}")
    return device


class BallDetector:
    def __init__(self, config):
        self.config = config
        self.device = get_device(config.DEVICE)

        print(f"[Detector] Loading model: {config.MODEL_PATH}")
        self.model = YOLO(config.MODEL_PATH)
        self.model.to(self.device)
        print(f"[Detector] Model loaded on {self.device}")

    def detect(self, frame):
        """
        Runs YOLOv8 on a frame and returns a list of detected balls.

        Returns a list of dicts, each containing:
            x_center   - horizontal center of ball in pixels from left
            y_center   - vertical center of ball in pixels from top
            width_px   - width of bounding box in pixels
            height_px  - height of bounding box in pixels
            confidence - detection confidence 0.0-1.0
            bbox       - (x1, y1, x2, y2) raw bounding box corners
            label      - class label string
        """
        results = self.model(
            frame,
            device=self.device,
            conf=self.config.CONFIDENCE_THRESHOLD,
            verbose=False
        )

        detections = []
        for result in results:
            for box in result.boxes:
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                width_px = x2 - x1
                height_px = y2 - y1
                x_center = x1 + width_px // 2
                y_center = y1 + height_px // 2
                confidence = float(box.conf[0])
                class_id = int(box.cls[0])
                label = self.model.names[class_id]

                detections.append({
                    "x_center":   x_center,
                    "y_center":   y_center,
                    "width_px":   width_px,
                    "height_px":  height_px,
                    "confidence": confidence,
                    "bbox":       (x1, y1, x2, y2),
                    "label":      label
                })

        # Sort by confidence, best detection first
        detections.sort(key=lambda d: d["confidence"], reverse=True)
        return detections
