# ==============================================================================
# main.py - FRC Ball Detection System (Self-Contained, Portable)
# 
# Runs on:  Windows PC, Linux, Mac, Jetson Orin Nano
#           Auto-detects: CUDA (NVIDIA) → DirectML (AMD/Intel) → CPU
#
# To run:   python main.py
# To quit:  Press 'q' in display window or Ctrl+C
# ==============================================================================

import cv2
import time
import sys
import os

# Try to import NetworkTables (optional)
try:
    from networktables import NetworkTables
    NT_AVAILABLE = True
except ImportError:
    NT_AVAILABLE = False

from detector import BallDetector

# ==============================================================================
# CONFIGURATION - CHANGE THESE SETTINGS
# ==============================================================================

# Camera settings
CAMERA_INDEX = 0                    # 0 = first USB webcam
USE_CSI_CAMERA = False              # Set True on Jetson for CSI camera
CAMERA_WIDTH = 416
CAMERA_HEIGHT = 416
CAMERA_FPS = 30

CSI_PIPELINE = (
    "nvarguscamerasrc ! "
    "video/x-raw(memory:NVMM), width=1280, height=720, framerate=30/1 ! "
    "nvvidconv ! video/x-raw, format=BGRx ! "
    "videoconvert ! video/x-raw, format=BGR ! appsink"
)

# Model and device
MODEL_PATH = "runs/detect/train3/weights/best.pt"
CONFIDENCE_THRESHOLD = 0.4

# Ball calibration (for distance estimation)
BALL_DIAMETER_INCHES = 9.5         # FRC 2024 ball diameter
FOCAL_LENGTH_PX = 700               # Calibrate by measuring distance vs pixel width

# Display settings
SHOW_DISPLAY = True
DISPLAY_FPS = True
BOX_COLOR = (0, 255, 0)             # Green bounding boxes

# NetworkTables (optional, for FRC robots)
ENABLE_NETWORKTABLES = False        # Set True to connect to roboRIO
ROBOT_IP = "10.0.0.2"
NT_TABLE_NAME = "Vision"

TRAINING_IMAGES_DIR = "training_images"


# ==============================================================================
# HELPER FUNCTIONS
# ==============================================================================

def get_camera():
    """Open camera (USB or CSI on Jetson)."""
    if USE_CSI_CAMERA:
        print("[Camera] Trying CSI camera pipeline...")
        cap = cv2.VideoCapture(CSI_PIPELINE, cv2.CAP_GSTREAMER)
        if cap.isOpened():
            print("[Camera] CSI camera opened successfully.")
            return cap
        else:
            print("[Camera] CSI failed, falling back to USB camera.")

    print(f"[Camera] Opening USB camera at index {CAMERA_INDEX}...")
    cap = cv2.VideoCapture(CAMERA_INDEX, cv2.CAP_DSHOW)

    if not cap.isOpened():
        print(f"[Camera] ERROR: Could not open camera at index {CAMERA_INDEX}.")
        sys.exit(1)

    # Set resolution and FPS
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAMERA_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_HEIGHT)
    cap.set(cv2.CAP_PROP_FPS, CAMERA_FPS)

    actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    actual_fps = cap.get(cv2.CAP_PROP_FPS)
    print(f"[Camera] Opened at {actual_w}x{actual_h} @ {actual_fps:.1f} FPS")

    return cap


def estimate_distance(width_px: int) -> float:
    """Estimate distance to ball using pinhole camera model."""
    if width_px <= 0:
        return 0.0
    distance = (BALL_DIAMETER_INCHES * FOCAL_LENGTH_PX) / width_px
    return round(distance, 2)


def draw_detections(frame, detections: list, distances: list):
    """Draw bounding boxes and detection info on frame."""
    frame_h, frame_w = frame.shape[:2]

    # Draw center crosshair
    cx, cy = frame_w // 2, frame_h // 2
    cv2.line(frame, (cx - 20, cy), (cx + 20, cy), (200, 200, 200), 1)
    cv2.line(frame, (cx, cy - 20), (cx, cy + 20), (200, 200, 200), 1)

    for i, (det, dist) in enumerate(zip(detections, distances)):
        x1, y1, x2, y2 = det["bbox"]
        bx, by = det["x_center"], det["y_center"]

        # Best detection bright, others dim
        color = BOX_COLOR if i == 0 else (100, 100, 100)
        thickness = 2 if i == 0 else 1

        cv2.rectangle(frame, (x1, y1), (x2, y2), color, thickness)
        cv2.drawMarker(frame, (bx, by), color,
                       markerType=cv2.MARKER_CROSS, markerSize=16, thickness=2)

        # Label only on best detection
        if i == 0:
            label_lines = [
                f"X: {bx}px  Y: {by}px",
                f"Width: {det['width_px']}px",
                f"Dist: {dist:.1f} in",
                f"Conf: {det['confidence']:.0%}"
            ]
            label_x = x1
            label_y = y1 - 10
            line_height = 18

            max_text_w = max(cv2.getTextSize(l, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)[0][0]
                             for l in label_lines)
            bg_y1 = max(label_y - (len(label_lines) * line_height), 0)
            cv2.rectangle(frame, (label_x, bg_y1), (label_x + max_text_w + 6, label_y + 4),
                         (0, 0, 0), -1)

            for j, line in enumerate(reversed(label_lines)):
                text_y = label_y - j * line_height
                if text_y > 0:
                    cv2.putText(frame, line, (label_x + 3, text_y),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.5, BOX_COLOR, 1, cv2.LINE_AA)

    return frame


def draw_fps(frame, fps: float):
    """Draw FPS on frame."""
    cv2.putText(frame, f"FPS: {fps:.1f}", (10, 25),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2, cv2.LINE_AA)


def draw_no_detection(frame):
    """Draw 'no detection' message."""
    cv2.putText(frame, "No ball detected", (10, 55),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2, cv2.LINE_AA)


class NTPublisher:
    """Optional NetworkTables publisher for FRC robots."""
    
    def __init__(self):
        self.enabled = ENABLE_NETWORKTABLES and NT_AVAILABLE
        self.table = None

        if not self.enabled:
            if ENABLE_NETWORKTABLES:
                print("[NetworkTables] WARNING: pynetworktables not installed.")
            return

        print(f"[NetworkTables] Connecting to robot at {ROBOT_IP}...")
        NetworkTables.initialize(server=ROBOT_IP)
        self.table = NetworkTables.getTable(NT_TABLE_NAME)
        print(f"[NetworkTables] Using table: '{NT_TABLE_NAME}'")

    def publish(self, detection: dict, distance: float, frame_width: int, frame_height: int):
        """Publish ball detection data to NetworkTables."""
        if not self.enabled or self.table is None:
            return

        if detection:
            self.table.putBoolean("ball_detected", True)
            self.table.putNumber("ball_x", detection["x_center"])
            self.table.putNumber("ball_y", detection["y_center"])
            self.table.putNumber("ball_width_px", detection["width_px"])
            self.table.putNumber("ball_distance", distance)
            self.table.putNumber("ball_confidence", detection["confidence"])
        else:
            self.table.putBoolean("ball_detected", False)
            self.table.putNumber("ball_x", -1)
            self.table.putNumber("ball_y", -1)
            self.table.putNumber("ball_width_px", 0)
            self.table.putNumber("ball_distance", -1)
            self.table.putNumber("ball_confidence", 0)

        self.table.putNumber("frame_width", frame_width)
        self.table.putNumber("frame_height", frame_height)


# ==============================================================================
# MAIN
# ==============================================================================

def main():
    print("=" * 50)
    print("  FRC Ball Detection System")
    print("=" * 50 + "\n")

    # Create training images folder
    os.makedirs(TRAINING_IMAGES_DIR, exist_ok=True)
    save_count = len([f for f in os.listdir(TRAINING_IMAGES_DIR) if f.endswith(".jpg")])
    print(f"[Capture] Training images folder: '{TRAINING_IMAGES_DIR}' ({save_count} images)\n")

    # Initialize
    cap = get_camera()
    detector = BallDetector(MODEL_PATH)
    nt = NTPublisher()

    frame_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    # FPS tracking
    fps = 0.0
    frame_count = 0
    fps_timer = time.time()

    print("[Main] Running. Press 'q' to quit. Press 'S' to save a training image.\n")

    while True:
        ret, frame = cap.read()
        if not ret:
            print("[Main] ERROR: Failed to read frame from camera.")
            break

        # Detect
        detections = detector.detect(frame, CONFIDENCE_THRESHOLD)

        # Calculate distances
        distances = [estimate_distance(d["width_px"]) for d in detections]

        # Get best detection
        best = detections[0] if detections else None
        best_dist = distances[0] if distances else 0.0

        # Print to console
        if best:
            print(
                f"[Detection] "
                f"X: {best['x_center']:4d}px  "
                f"Y: {best['y_center']:4d}px  "
                f"Width: {best['width_px']:4d}px  "
                f"Distance: {best_dist:6.1f}in  "
                f"Conf: {best['confidence']:.0%}  "
                f"FPS: {fps:.1f}"
            )
        else:
            print(f"[Detection] No ball found  |  FPS: {fps:.1f}")

        # Publish to NetworkTables
        nt.publish(best, best_dist, frame_w, frame_h)

        # Display
        if SHOW_DISPLAY:
            raw_frame = frame.copy()
            draw_detections(frame, detections, distances)

            if DISPLAY_FPS:
                draw_fps(frame, fps)

            if not best:
                draw_no_detection(frame)

            cv2.imshow("Ball Detection", frame)

            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                print("[Main] Quit requested.")
                break
            elif key == ord('s'):
                timestamp = int(time.time() * 1000)
                filename = os.path.join(TRAINING_IMAGES_DIR, f"frame_{timestamp}.jpg")
                cv2.imwrite(filename, raw_frame)
                save_count += 1
                print(f"[Capture] Saved: {filename}  (total: {save_count})")

        # FPS calculation
        frame_count += 1
        elapsed = time.time() - fps_timer
        if elapsed >= 0.5:
            fps = frame_count / elapsed
            frame_count = 0
            fps_timer = time.time()

    # Cleanup
    print("[Main] Shutting down...")
    cap.release()
    if SHOW_DISPLAY:
        cv2.destroyAllWindows()
    print("[Main] Done.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[Main] Interrupted by user.")
        sys.exit(0)

