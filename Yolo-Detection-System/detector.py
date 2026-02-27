# ==============================================================================
# detector.py - YOLOv8 Ball Detection (Smart Device Auto-Detection)
# Supports: CUDA (NVIDIA), NPU (Ryzen AI/Intel), CPU (fallback)
# Portable across Windows PC, Linux, Mac, Jetson
# ==============================================================================

import os
import sys

# Fix OpenMP conflict in conda environments
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

import torch
from ultralytics import YOLO


def get_best_device():
    """
    Auto-detects and returns the best available compute device.
    Priority: CUDA (NVIDIA) → DirectML (AMD/Intel) → CPU
    
    Returns: torch device object or "cpu" string
    """
    # Check for NVIDIA CUDA
    if torch.cuda.is_available():
        device_name = torch.cuda.get_device_name(0)
        print(f"[Detector] ✓ Using NVIDIA CUDA: {device_name}")
        return "cuda"
    
    # Check for DirectML (Windows GPU acceleration)
    try:
        import torch_directml
        device = torch_directml.device()
        print(f"[Detector] ✓ Using DirectML (AMD NPU/GPU or Intel Arc)")
        return device
    except ImportError:
        pass
    except Exception as e:
        print(f"[Detector] DirectML available but init failed: {e}")
    
    # Fallback to CPU
    print("[Detector] Using CPU (no GPU/NPU detected)")
    return "cpu"


class BallDetector:
    """YOLOv8 detector with smart device selection and fast inference."""
    
    def __init__(self, model_path: str):
        self.model_path = model_path
        self.device = get_best_device()
        
        print(f"[Detector] Loading model: {model_path}")
        self.model = YOLO(model_path)
        
        # Move to device if CUDA
        if self.device == "cuda":
            self.model.to("cuda")
        
        # Optimize for inference
        if hasattr(self.model.model, 'eval'):
            self.model.model.eval()
        
        print(f"[Detector] ✓ Model ready\n")
    
    def detect(self, frame, confidence_threshold: float = 0.4, imgsz: int = 416):
        """
        Run inference on frame.
        
        Returns list of detections, each with:
        - x_center, y_center: ball center in pixels
        - width_px, height_px: bounding box size
        - confidence: 0.0-1.0
        - bbox: (x1, y1, x2, y2) corner coordinates
        - label: class name
        """
        try:
            with torch.no_grad():
                results = self.model(
                    frame,
                    device=self.device,
                    conf=confidence_threshold,
                    verbose=False,
                    imgsz=imgsz
                )
            
            detections = []
            for result in results:
                if not hasattr(result, 'boxes') or len(result.boxes) == 0:
                    continue
                
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
                        "x_center": x_center,
                        "y_center": y_center,
                        "width_px": width_px,
                        "height_px": height_px,
                        "confidence": confidence,
                        "bbox": (x1, y1, x2, y2),
                        "label": label
                    })
            
            # Sort by confidence (best first)
            detections.sort(key=lambda d: d["confidence"], reverse=True)
            return detections
            
        except Exception as e:
            print(f"[Detector] Error during inference: {e}")
            return []

