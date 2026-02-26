# ==============================================================================
# camera.py - Camera abstraction layer
# Handles USB webcam (PC + Jetson) and CSI camera (Jetson only)
# ==============================================================================

import cv2
import sys


def get_camera(config):
    """
    Opens and returns a camera capture object.
    Automatically tries CSI first if configured, falls back to USB.
    """
    if config.USE_CSI_CAMERA:
        print("[Camera] Trying CSI camera pipeline...")
        cap = cv2.VideoCapture(config.CSI_PIPELINE, cv2.CAP_GSTREAMER)
        if cap.isOpened():
            print("[Camera] CSI camera opened successfully.")
            return cap
        else:
            print("[Camera] WARNING: CSI camera failed. Falling back to USB camera.")

    print(f"[Camera] Opening USB camera at index {config.CAMERA_INDEX}...")
    cap = cv2.VideoCapture(config.CAMERA_INDEX, cv2.CAP_DSHOW)

    if not cap.isOpened():
        print(f"[Camera] ERROR: Could not open camera at index {config.CAMERA_INDEX}.")
        print("[Camera] Try changing CAMERA_INDEX in config.py")
        sys.exit(1)

    # Set resolution and FPS
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, config.CAMERA_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config.CAMERA_HEIGHT)
    cap.set(cv2.CAP_PROP_FPS, config.CAMERA_FPS)

    actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    actual_fps = cap.get(cv2.CAP_PROP_FPS)
    print(f"[Camera] Opened at {actual_w}x{actual_h} @ {actual_fps:.1f} FPS")

    return cap
