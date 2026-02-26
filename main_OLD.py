# ==============================================================================
# main.py - Ball Detection System
# FRC Yellow Ball Detection using YOLOv8
#
# Runs on:  Windows PC (CPU or AMD GPU via ROCm on Linux)
#           Jetson Orin Nano (CUDA via TensorRT-accelerated PyTorch)
#
# To run:   python main.py
# To quit:  Press 'q' in the display window, or Ctrl+C in terminal
# ==============================================================================

import cv2
import time
import sys

import config
from camera import get_camera
from detector import BallDetector
from distance import estimate_distance
from display import draw_detections, draw_fps, draw_no_detection
from networktables_publisher import NTPublisher


def main():
    print("=" * 50)
    print("  FRC Ball Detection System")
    print("=" * 50)

    # --- Initialize modules ---
    cap = get_camera(config)
    detector = BallDetector(config)
    nt = NTPublisher(config)

    frame_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    # FPS tracking
    fps = 0.0
    frame_count = 0
    fps_timer = time.time()

    print("\n[Main] Running. Press 'q' to quit.\n")

    while True:
        ret, frame = cap.read()
        if not ret:
            print("[Main] ERROR: Failed to read frame from camera.")
            break

        # --- Run detection ---
        detections = detector.detect(frame)

        # --- Calculate distances for each detection ---
        distances = [estimate_distance(d["width_px"], config) for d in detections]

        # --- Get best detection (highest confidence) ---
        best = detections[0] if detections else None
        best_dist = distances[0] if distances else 0.0

        # --- Print to console ---
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

        # --- Publish to NetworkTables ---
        nt.publish(best, best_dist, frame_w, frame_h)

        # --- Draw and display ---
        if config.SHOW_DISPLAY:
            draw_detections(frame, detections, distances, config)

            if config.DISPLAY_FPS:
                draw_fps(frame, fps)

            if not best:
                draw_no_detection(frame)

            cv2.imshow("Ball Detection", frame)

            if cv2.waitKey(1) & 0xFF == ord('q'):
                print("[Main] Quit requested.")
                break

        # --- FPS calculation ---
        frame_count += 1
        elapsed = time.time() - fps_timer
        if elapsed >= 0.5:
            fps = frame_count / elapsed
            frame_count = 0
            fps_timer = time.time()

    # --- Cleanup ---
    print("[Main] Shutting down...")
    cap.release()
    if config.SHOW_DISPLAY:
        cv2.destroyAllWindows()
    print("[Main] Done.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[Main] Interrupted by user.")
        sys.exit(0)
