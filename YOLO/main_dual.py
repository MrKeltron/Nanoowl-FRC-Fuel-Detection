# ==============================================================================
# main.py - FRC Ball Detection System (Dual CSI Camera)
#
# Runs both CSI cameras simultaneously using threads.
# Each camera gets its own AI detection, display window, and NetworkTables output.
#
# To run:   python3 main.py
# To quit:  Press 'q' in either display window or Ctrl+C
# ==============================================================================

import cv2
import time
import sys
import os
import threading

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

CAMERA_FPS = 30

# Wide angle camera (sensor-id=0)
WIDE_SENSOR_ID = 0
WIDE_WIDTH = 1280
WIDE_HEIGHT = 720

# Zoom camera (sensor-id=1)
ZOOM_SENSOR_ID = 1
ZOOM_WIDTH = 1280
ZOOM_HEIGHT = 720

# Model
MODEL_PATH = "best.pt"
CONFIDENCE_THRESHOLD = 0.4

# Ball calibration
BALL_DIAMETER_INCHES = 9.5
FOCAL_LENGTH_PX = 700

# Display
SHOW_DISPLAY = True
DISPLAY_FPS = True
WIDE_BOX_COLOR = (0, 255, 0)       # Green for wide angle
ZOOM_BOX_COLOR = (0, 255, 255)     # Yellow for zoom

# NetworkTables
ENABLE_NETWORKTABLES = False
ROBOT_IP = "10.0.0.2"
NT_TABLE_NAME = "Vision"

TRAINING_IMAGES_DIR = "training_images"


# ==============================================================================
# HELPERS
# ==============================================================================

def make_csi_pipeline(sensor_id, width, height, fps):
    return (
        f"nvarguscamerasrc sensor-id={sensor_id} ! "
        f"video/x-raw(memory:NVMM), width={width}, height={height}, framerate={fps}/1 ! "
        "nvvidconv ! video/x-raw, format=BGRx ! "
        "videoconvert ! video/x-raw, format=BGR ! appsink"
    )


def open_camera(sensor_id, width, height, fps):
    pipeline = make_csi_pipeline(sensor_id, width, height, fps)
    print(f"[Camera {sensor_id}] Opening CSI sensor-id={sensor_id}...")
    cap = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
    if cap.isOpened():
        print(f"[Camera {sensor_id}] Opened at {width}x{height} @ {fps} FPS")
    else:
        print(f"[Camera {sensor_id}] ERROR: Failed to open!")
    return cap


def estimate_distance(width_px):
    if width_px <= 0:
        return 0.0
    return round((BALL_DIAMETER_INCHES * FOCAL_LENGTH_PX) / width_px, 2)


def draw_detections(frame, detections, distances, box_color, cam_label):
    frame_h, frame_w = frame.shape[:2]
    cx, cy = frame_w // 2, frame_h // 2
    cv2.line(frame, (cx - 20, cy), (cx + 20, cy), (200, 200, 200), 1)
    cv2.line(frame, (cx, cy - 20), (cx, cy + 20), (200, 200, 200), 1)
    cv2.putText(frame, cam_label, (10, frame_h - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, box_color, 2, cv2.LINE_AA)

    for i, (det, dist) in enumerate(zip(detections, distances)):
        x1, y1, x2, y2 = det["bbox"]
        bx, by = det["x_center"], det["y_center"]
        color = box_color if i == 0 else (100, 100, 100)
        thickness = 2 if i == 0 else 1
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, thickness)
        cv2.drawMarker(frame, (bx, by), color,
                       markerType=cv2.MARKER_CROSS, markerSize=16, thickness=2)
        if i == 0:
            lines = [
                f"X: {bx}px  Y: {by}px",
                f"Width: {det['width_px']}px",
                f"Dist: {dist:.1f} in",
                f"Conf: {det['confidence']:.0%}"
            ]
            lx, ly, lh = x1, y1 - 10, 18
            max_w = max(cv2.getTextSize(l, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)[0][0] for l in lines)
            cv2.rectangle(frame, (lx, max(ly - len(lines)*lh, 0)),
                         (lx + max_w + 6, ly + 4), (0, 0, 0), -1)
            for j, line in enumerate(reversed(lines)):
                ty = ly - j * lh
                if ty > 0:
                    cv2.putText(frame, line, (lx + 3, ty),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA)
    return frame


def draw_fps(frame, fps):
    cv2.putText(frame, f"FPS: {fps:.1f}", (10, 25),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2, cv2.LINE_AA)


def draw_no_detection(frame):
    cv2.putText(frame, "No ball detected", (10, 55),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2, cv2.LINE_AA)


# ==============================================================================
# NETWORKTABLES
# ==============================================================================

class NTPublisher:
    def __init__(self):
        self.enabled = ENABLE_NETWORKTABLES and NT_AVAILABLE
        self.wide_table = None
        self.zoom_table = None
        if not self.enabled:
            return
        print(f"[NetworkTables] Connecting to {ROBOT_IP}...")
        NetworkTables.initialize(server=ROBOT_IP)
        self.wide_table = NetworkTables.getTable(f"{NT_TABLE_NAME}/wide")
        self.zoom_table = NetworkTables.getTable(f"{NT_TABLE_NAME}/zoom")
        print("[NetworkTables] Tables: Vision/wide and Vision/zoom")

    def publish(self, table, detection, distance, fw, fh):
        if not self.enabled or table is None:
            return
        if detection:
            table.putBoolean("ball_detected", True)
            table.putNumber("ball_x", detection["x_center"])
            table.putNumber("ball_y", detection["y_center"])
            table.putNumber("ball_width_px", detection["width_px"])
            table.putNumber("ball_distance", distance)
            table.putNumber("ball_confidence", detection["confidence"])
        else:
            table.putBoolean("ball_detected", False)
            table.putNumber("ball_x", -1)
            table.putNumber("ball_y", -1)
            table.putNumber("ball_width_px", 0)
            table.putNumber("ball_distance", -1)
            table.putNumber("ball_confidence", 0)
        table.putNumber("frame_width", fw)
        table.putNumber("frame_height", fh)


# ==============================================================================
# CAMERA THREAD
# ==============================================================================

class CameraThread(threading.Thread):
    def __init__(self, sensor_id, width, height, detector, nt, nt_table,
                 window_name, box_color, cam_label):
        super().__init__(daemon=True)
        self.sensor_id = sensor_id
        self.width = width
        self.height = height
        self.detector = detector
        self.nt = nt
        self.nt_table = nt_table
        self.window_name = window_name
        self.box_color = box_color
        self.cam_label = cam_label
        self.running = True
        self.save_next = False
        self.save_count = 0

    def run(self):
        cap = open_camera(self.sensor_id, self.width, self.height, CAMERA_FPS)
        if not cap.isOpened():
            print(f"[Camera {self.sensor_id}] Could not open, thread exiting.")
            return

        fw = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        fh = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = 0.0
        frame_count = 0
        fps_timer = time.time()

        while self.running:
            ret, frame = cap.read()
            if not ret:
                print(f"[Camera {self.sensor_id}] Failed to read frame.")
                break

            detections = self.detector.detect(frame, CONFIDENCE_THRESHOLD)
            distances = [estimate_distance(d["width_px"]) for d in detections]
            best = detections[0] if detections else None
            best_dist = distances[0] if distances else 0.0

            if best:
                print(
                    f"[{self.cam_label}] "
                    f"X: {best['x_center']:4d}px  "
                    f"Y: {best['y_center']:4d}px  "
                    f"Width: {best['width_px']:4d}px  "
                    f"Dist: {best_dist:6.1f}in  "
                    f"Conf: {best['confidence']:.0%}  "
                    f"FPS: {fps:.1f}"
                )

            self.nt.publish(self.nt_table, best, best_dist, fw, fh)

            if SHOW_DISPLAY:
                raw_frame = frame.copy()
                draw_detections(frame, detections, distances,
                                self.box_color, self.cam_label)
                if DISPLAY_FPS:
                    draw_fps(frame, fps)
                if not best:
                    draw_no_detection(frame)
                cv2.imshow(self.window_name, frame)

                if self.save_next:
                    os.makedirs(TRAINING_IMAGES_DIR, exist_ok=True)
                    fname = os.path.join(TRAINING_IMAGES_DIR,
                                        f"{self.cam_label}_{int(time.time()*1000)}.jpg")
                    cv2.imwrite(fname, raw_frame)
                    self.save_count += 1
                    print(f"[{self.cam_label}] Saved: {fname} (total: {self.save_count})")
                    self.save_next = False

            frame_count += 1
            elapsed = time.time() - fps_timer
            if elapsed >= 0.5:
                fps = frame_count / elapsed
                frame_count = 0
                fps_timer = time.time()

        cap.release()
        print(f"[Camera {self.sensor_id}] Thread stopped.")


# ==============================================================================
# MAIN
# ==============================================================================

def main():
    print("=" * 50)
    print("  FRC Ball Detection - Dual Camera")
    print("=" * 50 + "\n")

    os.makedirs(TRAINING_IMAGES_DIR, exist_ok=True)

    print("[Main] Loading AI model...")
    detector = BallDetector(MODEL_PATH)
    nt = NTPublisher()

    wide_thread = CameraThread(
        sensor_id=WIDE_SENSOR_ID, width=WIDE_WIDTH, height=WIDE_HEIGHT,
        detector=detector, nt=nt, nt_table=nt.wide_table,
        window_name="Wide Angle", box_color=WIDE_BOX_COLOR, cam_label="WIDE"
    )
    zoom_thread = CameraThread(
        sensor_id=ZOOM_SENSOR_ID, width=ZOOM_WIDTH, height=ZOOM_HEIGHT,
        detector=detector, nt=nt, nt_table=nt.zoom_table,
        window_name="Zoom", box_color=ZOOM_BOX_COLOR, cam_label="ZOOM"
    )

    wide_thread.start()
    zoom_thread.start()
    print("[Main] Both cameras running. Press 'q' to quit, 's' to save frames.\n")

    while True:
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            print("[Main] Quit requested.")
            break
        elif key == ord('s'):
            wide_thread.save_next = True
            zoom_thread.save_next = True
        if not wide_thread.is_alive() and not zoom_thread.is_alive():
            break

    wide_thread.running = False
    zoom_thread.running = False
    wide_thread.join(timeout=3)
    zoom_thread.join(timeout=3)
    cv2.destroyAllWindows()
    print("[Main] Done.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[Main] Interrupted by user.")
        sys.exit(0)
