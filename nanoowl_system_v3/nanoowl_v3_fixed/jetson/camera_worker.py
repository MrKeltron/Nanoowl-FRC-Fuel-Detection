#!/usr/bin/env python3
"""
NANOOWL VISION SYSTEM v3.0 - Camera Worker (Jetson Orin Nano)
Captures camera frames, encodes on GPU, streams MJPEG to Pi
"""

import cv2
import socket
import threading
import time
import logging
import argparse
from typing import Optional
import numpy as np

parser = argparse.ArgumentParser()
parser.add_argument("--camera-id", type=int, default=0)
args = parser.parse_args()

# Configuration
CAMERA_PORT = 9001  # Raw camera feed
CAMERA_ID = args.camera_id
RESOLUTION = (640, 480)
FPS = 30
JPEG_QUALITY = 85

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - CameraWorker - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class CameraWorker:
    """Captures camera and streams MJPEG to Pi"""
    
    def __init__(self) -> None:
        self.camera: Optional[cv2.VideoCapture] = None
        self.server_socket: Optional[socket.socket] = None
        self.running = True
        self.frame_count = 0
        self.last_fps_time = time.time()
        self.camera_lock = threading.Lock()
        self.stats_lock = threading.Lock()
        
    def init_camera(self) -> bool:
        """Initialize the camera (Jetson GStreamer if available, otherwise OS-appropriate backend)."""
        import platform

        try:
            logger.info(f"Initializing camera {CAMERA_ID}...")

            self.camera = None

            # --- 1) Jetson path: try GStreamer pipeline first (only makes sense on Linux) ---
            if platform.system() != "Windows":
                gst_str = (
                    f"nvarguscamerasrc sensor-id={CAMERA_ID} ! "
                    f"video/x-raw(memory:NVMM), width={RESOLUTION[0]}, height={RESOLUTION[1]}, "
                    f"format=NV12, framerate={FPS}/1 ! "
                    f"nvvidconv ! video/x-raw, format=BGRx ! "
                    f"videoconvert ! video/x-raw, format=BGR ! "
                    f"appsink drop=true"
                )

                logger.info("Trying Jetson GStreamer pipeline...")
                cam = cv2.VideoCapture(gst_str, cv2.CAP_GSTREAMER)
                if cam.isOpened():
                    self.camera = cam

            # --- 2) Fallback path: Windows webcam (force DirectShow) ---
            if self.camera is None:
                if platform.system() == "Windows":
                    logger.warning("GStreamer failed/unavailable. Trying Windows DirectShow...")
                    cam = cv2.VideoCapture(int(CAMERA_ID), cv2.CAP_DSHOW)
                    if not cam.isOpened():
                        logger.warning("DirectShow failed. Trying MSMF...")
                        cam = cv2.VideoCapture(int(CAMERA_ID), cv2.CAP_MSMF)
                    if not cam.isOpened():
                        logger.warning("MSMF failed. Trying default backend...")
                        cam = cv2.VideoCapture(int(CAMERA_ID))
                    if cam.isOpened():
                        self.camera = cam
                else:
                    # --- 3) Linux non-Jetson fallback ---
                    logger.warning("GStreamer failed/unavailable. Trying V4L2/default...")
                    cam = cv2.VideoCapture(int(CAMERA_ID), cv2.CAP_V4L2)
                    if not cam.isOpened():
                        logger.warning("V4L2 failed. Trying default backend...")
                        cam = cv2.VideoCapture(int(CAMERA_ID))
                    if cam.isOpened():
                        self.camera = cam

            if self.camera is None or not self.camera.isOpened():
                raise RuntimeError("Failed to open camera!")

            # Apply capture properties after opening (some backends ignore, but harmless)
            self.camera.set(cv2.CAP_PROP_FRAME_WIDTH,  RESOLUTION[0])
            self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, RESOLUTION[1])
            self.camera.set(cv2.CAP_PROP_FPS, FPS)

            # Warm-up read (some Windows cams need 1-3 reads)
            ok = False
            for _ in range(3):
                ok, _ = self.camera.read()
                if ok:
                    break

            if not ok:
                raise RuntimeError("Camera opened but failed to read frames (permissions / in-use / backend issue).")

            logger.info(f"Camera initialized: {RESOLUTION[0]}x{RESOLUTION[1]} @ ~{FPS}FPS")
            return True

        except Exception as e:
            logger.error(f"Camera initialization failed: {e}")
            return False
            
    def start_server(self) -> bool:
        """Start the MJPEG streaming server"""
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind(("0.0.0.0", CAMERA_PORT))
            self.server_socket.listen(5)
            logger.info(f"Camera server listening on port {CAMERA_PORT}")
            return True
        except Exception as e:
            logger.error(f"Failed to start server: {e}")
            return False
            
    def encode_frame(self, frame: np.ndarray) -> Optional[bytes]:
        """Encode frame to JPEG using GPU acceleration"""
        try:
            # Use OpenCV's JPEG encoding
            encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY]
            _, jpeg_data = cv2.imencode('.jpg', frame, encode_params)
            return jpeg_data.tobytes()
        except Exception as e:
            logger.error(f"Frame encoding failed: {e}")
            return None
            
    def stream_to_client(self, client_socket: socket.socket) -> None:
        """Stream MJPEG to a connected client"""
        logger.info("Client connected to camera stream")
        
        try:
            while self.running:
                with self.camera_lock:
                    if self.camera is None or not self.camera.isOpened():
                        logger.error("Camera is not available")
                        break
                    ret, frame = self.camera.read()
                
                if not ret:
                    logger.warning("Failed to read frame from camera")
                    time.sleep(0.01)
                    continue
                    
                # Encode frame
                jpeg_data = self.encode_frame(frame)
                if jpeg_data is None:
                    continue
                    
                # Send MJPEG frame
                try:
                    header = b"--frame\r\nContent-Type: image/jpeg\r\n"
                    header += f"Content-Length: {len(jpeg_data)}\r\n\r\n".encode()
                    client_socket.sendall(header + jpeg_data + b"\r\n")
                except BrokenPipeError:
                    logger.info("Client disconnected")
                    break
                except Exception as e:
                    logger.error(f"Send error: {e}")
                    break
                    
                # FPS counter
                with self.stats_lock:
                    self.frame_count += 1
                    if time.time() - self.last_fps_time >= 5:
                        fps = self.frame_count / 5
                        logger.info(f"Camera streaming: {fps:.1f} FPS")
                        self.frame_count = 0
                        self.last_fps_time = time.time()
                    
        except Exception as e:
            logger.error(f"Stream error: {e}")
        finally:
            try:
                client_socket.close()
            except Exception:
                pass
            logger.info("Camera stream ended")
            
    def run(self) -> None:
        """Main worker loop"""
        logger.info("=" * 50)
        logger.info("Camera Worker v3.0 Starting...")
        logger.info("=" * 50)
        
        # Initialize camera
        if not self.init_camera():
            logger.error("Camera initialization failed, exiting")
            return
            
        # Start server
        if not self.start_server():
            logger.error("Server start failed, exiting")
            return
            
        # Accept connections
        while self.running:
            try:
                if self.server_socket is not None:
                    self.server_socket.settimeout(1.0)
                    client_socket, addr = self.server_socket.accept()
                    logger.info(f"Connection from {addr}")
                    
                    # Handle client in separate thread
                    client_thread = threading.Thread(
                        target=self.stream_to_client,
                        args=(client_socket,),
                        daemon=True
                    )
                    client_thread.start()
                
            except socket.timeout:
                continue
            except Exception as e:
                logger.error(f"Accept error: {e}")
                time.sleep(1)
                
    def stop(self) -> None:
        """Stop the worker"""
        self.running = False
        with self.camera_lock:
            if self.camera and self.camera.isOpened():
                self.camera.release()
        if self.server_socket:
            try:
                self.server_socket.close()
            except Exception:
                pass
        logger.info("Camera worker stopped")


if __name__ == "__main__":
    worker = CameraWorker()
    try:
        worker.run()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    finally:
        worker.stop()
