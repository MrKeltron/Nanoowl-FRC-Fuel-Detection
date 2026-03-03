# ==============================================================================
# main.py - FRC Ball Detection System (Dual CSI Camera, Zero Delay)
#
# Uses producer/consumer threading pattern:
# - Camera threads ONLY capture frames (no waiting for AI)
# - AI threads ONLY run inference on latest frame
# - Display thread shows results
# This eliminates delay completely.
#
# To run:   python3 main.py
# To quit:  Press 'q' or Ctrl+C
# ==============================================================================

import cv2
import time
import sys
import os
import threading
from collections import deque

try:
    from networktables import NetworkTables
    NT_AVAILABLE = True
except ImportError:
    NT_AVAILABLE = False

from detector import BallDetector

# ==============================================================================
# CONFIGURATION
# ==============================================================================

CAMERA_FPS = 30

WIDE_SENSOR_ID  = 0
WIDE_WIDTH      = 1280
WIDE_HEIGHT     = 720

ZOOM_SENSOR_ID  = 1
ZOOM_WIDTH      = 1280
ZOOM_HEIGHT     = 720

MODEL_PATH           = "best.pt"
CONFIDENCE_THRESHOLD = 0.4

BALL_DIAMETER_INCHES = 9.5
FOCAL_LENGTH_PX      = 700

SHOW_DISPLAY    = True
DISPLAY_FPS     = True
WIDE_BOX_COLOR  = (0, 255, 0)      # Green
ZOOM_BOX_COLOR  = (0, 255, 255)    # Yellow

ENABLE_NETWORKTABLES = False
ROBOT_IP             = "10.0.0.2"
NT_TABLE_NAME        = "Vision"

TRAINING_IMAGES_DIR  = "training_images"


# ==============================================================================
# HELPERS
# ==============================================================================

def make_pipeline(sensor_id, width, height, fps):
    return (
        f"nvarguscamerasrc sensor-id={sensor_id} ! "
        f"video/x-raw(memory:NVMM), width={width}, height={height}, "
        f"framerate={fps}/1 ! "
        "nvvidconv ! video/x-raw, format=BGRx ! "
        "videoconvert ! video/x-raw, format=BGR ! appsink drop=true"
    )


def estimate_distance(width_px):
    if width_px <= 0:
        return 0.0
    return round((BALL_DIAMETER_INCHES * FOCAL_LENGTH_PX) / width_px, 2)


def draw_overlay(frame, detections, distances, box_color, cam_label, fps):
    fh, fw = frame.shape[:2]

    # Crosshair
    cx, cy = fw // 2, fh // 2
    cv2.line(frame, (cx-20, cy), (cx+20, cy), (200, 200, 200), 1)
    cv2.line(frame, (cx, cy-20), (cx, cy+20), (200, 200, 200), 1)

    # Camera label
    cv2.putText(frame, cam_label, (10, fh-10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, box_color, 2, cv2.LINE_AA)

    # FPS
    if DISPLAY_FPS:
        cv2.putText(frame, f"FPS: {fps:.1f}", (10, 25),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2, cv2.LINE_AA)

    if not detections:
        cv2.putText(frame, "No ball detected", (10, 55),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2, cv2.LINE_AA)
        return frame

    for i, (det, dist) in enumerate(zip(detections, distances)):
        x1, y1, x2, y2 = det["bbox"]
        bx, by = det["x_center"], det["y_center"]
        color = box_color if i == 0 else (100, 100, 100)
        thick = 2 if i == 0 else 1

        cv2.rectangle(frame, (x1, y1), (x2, y2), color, thick)
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
            mw = max(cv2.getTextSize(l, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)[0][0]
                     for l in lines)
            cv2.rectangle(frame, (lx, max(ly - len(lines)*lh, 0)),
                          (lx + mw + 6, ly + 4), (0, 0, 0), -1)
            for j, line in enumerate(reversed(lines)):
                ty = ly - j * lh
                if ty > 0:
                    cv2.putText(frame, line, (lx+3, ty),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA)
    return frame


# ==============================================================================
# NETWORKTABLES
# ==============================================================================

class NTPublisher:
    def __init__(self):
        self.enabled = ENABLE_NETWORKTABLES and NT_AVAILABLE
        self.wide_table = self.zoom_table = None
        if not self.enabled:
            return
        print(f"[NT] Connecting to {ROBOT_IP}...")
        NetworkTables.initialize(server=ROBOT_IP)
        self.wide_table = NetworkTables.getTable(f"{NT_TABLE_NAME}/wide")
        self.zoom_table = NetworkTables.getTable(f"{NT_TABLE_NAME}/zoom")
        print("[NT] Vision/wide and Vision/zoom ready")

    def publish(self, table, detection, distance, fw, fh):
        if not self.enabled or table is None:
            return
        if detection:
            table.putBoolean("ball_detected",  True)
            table.putNumber("ball_x",          detection["x_center"])
            table.putNumber("ball_y",          detection["y_center"])
            table.putNumber("ball_width_px",   detection["width_px"])
            table.putNumber("ball_distance",   distance)
            table.putNumber("ball_confidence", detection["confidence"])
        else:
            table.putBoolean("ball_detected",  False)
            table.putNumber("ball_x",          -1)
            table.putNumber("ball_y",          -1)
            table.putNumber("ball_width_px",   0)
            table.putNumber("ball_distance",   -1)
            table.putNumber("ball_confidence", 0)
        table.putNumber("frame_width",  fw)
        table.putNumber("frame_height", fh)


# ==============================================================================
# CAMERA PIPELINE
# Each camera has:
#   - capture thread: grabs frames as fast as possible, keeps only latest
#   - inference thread: grabs latest frame, runs AI, updates result
# ==============================================================================

class CameraPipeline:
    def __init__(self, sensor_id, width, height, detector, nt, nt_table,
                 window_name, box_color, cam_label):
        self.sensor_id   = sensor_id
        self.width       = width
        self.height      = height
        self.detector    = detector
        self.nt          = nt
        self.nt_table    = nt_table
        self.window_name = window_name
        self.box_color   = box_color
        self.cam_label   = cam_label

        self.running     = True
        self.save_next   = False
        self.save_count  = 0

        # Latest raw frame (capture → inference)
        self.latest_frame      = None
        self.latest_frame_lock = threading.Lock()

        # Latest detection result (inference → display)
        self.latest_result      = ([], [], None)  # detections, distances, fps
        self.latest_result_lock = threading.Lock()

        self.cap_fps   = 0.0
        self.infer_fps = 0.0

    def start(self):
        self.cap_thread   = threading.Thread(target=self._capture_loop,   daemon=True)
        self.infer_thread = threading.Thread(target=self._inference_loop, daemon=True)
        self.cap_thread.start()
        self.infer_thread.start()

    def stop(self):
        self.running = False

    def _capture_loop(self):
        pipeline = make_pipeline(self.sensor_id, self.width, self.height, CAMERA_FPS)
        print(f"[{self.cam_label}] Opening camera...")
        cap = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
        if not cap.isOpened():
            print(f"[{self.cam_label}] ERROR: Could not open camera!")
            self.running = False
            return

        fw = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        fh = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        print(f"[{self.cam_label}] Camera opened at {fw}x{fh}")

        fc, t0 = 0, time.time()

        while self.running:
            ret, frame = cap.read()
            if not ret:
                print(f"[{self.cam_label}] Frame read failed")
                break

            # Always keep only the LATEST frame - never queue old frames
            with self.latest_frame_lock:
                self.latest_frame = frame

            fc += 1
            elapsed = time.time() - t0
            if elapsed >= 1.0:
                self.cap_fps = fc / elapsed
                fc, t0 = 0, time.time()

        cap.release()
        print(f"[{self.cam_label}] Capture stopped")

    def _inference_loop(self):
        fc, t0 = 0, time.time()

        while self.running:
            # Grab latest frame
            with self.latest_frame_lock:
                frame = self.latest_frame

            if frame is None:
                time.sleep(0.005)
                continue

            # Run AI
            detections = self.detector.detect(frame, CONFIDENCE_THRESHOLD)
            distances  = [estimate_distance(d["width_px"]) for d in detections]
            best       = detections[0] if detections else None
            best_dist  = distances[0]  if distances  else 0.0

            # Console
            if best:
                print(
                    f"[{self.cam_label}] "
                    f"X:{best['x_center']:4d}  "
                    f"Y:{best['y_center']:4d}  "
                    f"W:{best['width_px']:4d}px  "
                    f"Dist:{best_dist:6.1f}in  "
                    f"Conf:{best['confidence']:.0%}  "
                    f"FPS:{self.infer_fps:.1f}"
                )

            # NetworkTables
            fh, fw = frame.shape[:2]
            self.nt.publish(self.nt_table, best, best_dist, fw, fh)

            # Store result for display
            with self.latest_result_lock:
                self.latest_result = (detections, distances, frame.copy())

            fc += 1
            elapsed = time.time() - t0
            if elapsed >= 1.0:
                self.infer_fps = fc / elapsed
                fc, t0 = 0, time.time()

    def get_display_frame(self):
        with self.latest_result_lock:
            detections, distances, frame = self.latest_result
        if frame is None:
            return None

        frame = frame.copy()
        draw_overlay(frame, detections, distances,
                     self.box_color, self.cam_label, self.infer_fps)

        if self.save_next:
            os.makedirs(TRAINING_IMAGES_DIR, exist_ok=True)
            fname = os.path.join(TRAINING_IMAGES_DIR,
                                 f"{self.cam_label}_{int(time.time()*1000)}.jpg")
            # Save clean frame
            with self.latest_result_lock:
                _, _, clean = self.latest_result
            if clean is not None:
                cv2.imwrite(fname, clean)
                self.save_count += 1
                print(f"[{self.cam_label}] Saved {fname} ({self.save_count} total)")
            self.save_next = False

        return frame


# ==============================================================================
# MAIN
# ==============================================================================

def main():
    print("=" * 50)
    print("  FRC Ball Detection - Dual Camera (Zero Delay)")
    print("=" * 50 + "\n")

    os.makedirs(TRAINING_IMAGES_DIR, exist_ok=True)

    print("[Main] Loading AI model (shared between cameras)...")
    detector = BallDetector(MODEL_PATH)
    nt       = NTPublisher()

    wide = CameraPipeline(
        sensor_id=WIDE_SENSOR_ID, width=WIDE_WIDTH, height=WIDE_HEIGHT,
        detector=detector, nt=nt, nt_table=nt.wide_table,
        window_name="Wide Angle", box_color=WIDE_BOX_COLOR, cam_label="WIDE"
    )
    zoom = CameraPipeline(
        sensor_id=ZOOM_SENSOR_ID, width=ZOOM_WIDTH, height=ZOOM_HEIGHT,
        detector=detector, nt=nt, nt_table=nt.zoom_table,
        window_name="Zoom", box_color=ZOOM_BOX_COLOR, cam_label="ZOOM"
    )

    wide.start()
    zoom.start()

    print("[Main] Both cameras running.")
    print("[Main] Press 'q' to quit, 's' to save training frames.\n")

    while True:
        if SHOW_DISPLAY:
            wide_frame = wide.get_display_frame()
            zoom_frame = zoom.get_display_frame()

            if wide_frame is not None:
                cv2.imshow("Wide Angle", wide_frame)
            if zoom_frame is not None:
                cv2.imshow("Zoom", zoom_frame)

        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            print("[Main] Quit.")
            break
        elif key == ord('s'):
            wide.save_next = True
            zoom.save_next = True

        if not wide.cap_thread.is_alive() and not zoom.cap_thread.is_alive():
            print("[Main] Both cameras stopped.")
            break

        time.sleep(0.001)

    wide.stop()
    zoom.stop()
    cv2.destroyAllWindows()
    print("[Main] Done.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[Main] Interrupted.")
        sys.exit(0)
