#!/usr/bin/env python3
"""
NANOOWL VISION SYSTEM v3.0 - Detection Worker (Jetson Orin Nano)
Runs NanoOWL object detection, draws boxes on GPU, streams annotated frames to Pi
"""

import cv2
import socket
import threading
import time
import logging
from PIL import Image
import torch
import importlib
import inspect
from typing import Tuple, List, Dict, Any, Optional
import numpy as np

# Try to import NanoOWL dynamically to avoid static analysis errors when package is absent
nanoowl_available: bool = False
OwlPredictor: Optional[type] = None

try:
    owl_mod = importlib.import_module("nanoowl.owl_predictor")
    OwlPredictor = getattr(owl_mod, "OwlPredictor")
    nanoowl_available = True
except Exception as e:
    print(f"Warning: NanoOWL not available ({type(e).__name__}: {e}), running in demo mode")
    nanoowl_available = False

# Configuration
CAMERA_PORT = 9000  # Detection feed (annotated)
CAMERA_ID = 0
RESOLUTION = (640, 480)
FPS = 30
JPEG_QUALITY = 85
COMMAND_PORT = 9003  # control socket for prompt updates
RAW_FEED_HOST = "127.0.0.1"
RAW_FEED_PORT = 9001  # fallback: read raw MJPEG from camera_worker

# Detection settings
DEFAULT_PROMPT = "a person, a car, a dog, a cat, a bottle"
DETECTION_THRESHOLD = 0.3
NMS_THRESHOLD = 0.5

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - DetectionWorker - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DetectionWorker:
    """Runs NanoOWL detection and streams annotated frames to Pi"""
    
    def __init__(self):
        self.camera: Optional[Any] = None
        self.server_socket = None
        self.cmd_socket = None
        self.running = True
        self.frame_count = 0
        self.last_fps_time = time.time()
        self.detection_count = 0
        self.mjpeg_socket: Optional[socket.socket] = None
        self.mjpeg_buffer = b""
        
        # NanoOWL
        self.predictor = None
        # store prompt as comma-separated string too for ease
        self.prompt_text: str = DEFAULT_PROMPT
        self.prompts: List[str] = [str(s) for s in self.prompt_text.split(", ")]
        self.detection_enabled = True
        

    def init_nanoowl(self):
        """Initialize NanoOWL predictor with robust device autodetect/fallback."""
        import os
        if not nanoowl_available or OwlPredictor is None:
            logger.warning("NanoOWL not available, detection disabled")
            self.detection_enabled = False
            return False

        try:
            logger.info("Initializing NanoOWL...")

            # 1) Allow explicit override via env var
            env_device = os.environ.get("NANOOWL_DEVICE")
            candidates: List[str] = []
            if env_device:
                candidates = [env_device]
                logger.info(f"Using NANOOWL_DEVICE override: {env_device}")
            else:
                candidates = []
                # NVIDIA CUDA
                try:
                    if torch.cuda.is_available():
                        candidates.append("cuda")
                except Exception:
                    pass
                # Apple Silicon MPS
                try:
                    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                        candidates.append("mps")
                except Exception:
                    pass
                # AMD/XPU/NPUs (user may need to override)
                candidates.extend(["npu", "xpu", "cpu"])
                logger.info(f"Device candidates: {candidates}")

            last_exc = None
            for dev in candidates:
                try:
                    logger.info(f"Trying NanoOWL device='{dev}'")
                    self.predictor = OwlPredictor(device=dev)
                    logger.info(f"NanoOWL initialized successfully on device='{dev}'")
                    self.detection_enabled = True
                    logger.info(f"Detection prompt: {self.prompts}")
                    return True
                except Exception as e:
                    logger.warning(f"Device '{dev}' failed: {type(e).__name__}: {e}")
                    last_exc = e
                    self.predictor = None
                    continue

            # fallback to cpu
            try:
                logger.info("Falling back to 'cpu'")
                self.predictor = OwlPredictor(device="cpu")
                self.detection_enabled = True
                logger.info("NanoOWL initialized successfully on device='cpu'")
                logger.info(f"Detection prompt: {self.prompts}")
                return True
            except Exception as e:
                last_exc = e

            logger.error(f"NanoOWL initialization failed (all candidates exhausted): {last_exc}")
            self.detection_enabled = False
            return False

        except Exception as e:
            logger.error(f"NanoOWL initialization failed: {type(e).__name__}: {e}")
            self.detection_enabled = False
            return False
            
    def init_camera(self):
        """Initialize the camera.

        On a Jetson we try an nvarguscamerasrc GStreamer pipeline first;
        on other platforms we fall back to whatever OpenCV backend makes sense.
        """
        import platform

        try:
            logger.info(f"Initializing camera {CAMERA_ID}...")
            system = platform.system()

            if system != "Windows":
                # Jetson / Linux path: hardware‑accelerated GStreamer >> V4L2
                gst_str = (
                    f"nvarguscamerasrc sensor-id={CAMERA_ID} ! "
                    f"video/x-raw(memory:NVMM), width={RESOLUTION[0]}, height={RESOLUTION[1]}, "
                    f"format=NV12, framerate={FPS}/1 ! "
                    f"nvvidconv ! video/x-raw, format=BGRx ! "
                    f"videoconvert ! video/x-raw, format=BGR ! "
                    f"appsink drop=true"
                )
                self.camera = cv2.VideoCapture(gst_str, cv2.CAP_GSTREAMER)
                if not self.camera.isOpened():
                    logger.warning("GStreamer failed, trying default capture backend...")
                    self.camera = cv2.VideoCapture(CAMERA_ID)
            else:
                # Windows: try a sequence of backends so we can diagnose failure
                backends = [cv2.CAP_DSHOW, cv2.CAP_MSMF, cv2.CAP_VFW]
                self.camera = None
                for b in backends:
                    logger.info(f"Trying Windows backend {b} for camera {CAMERA_ID}...")
                    cap = cv2.VideoCapture(int(CAMERA_ID), b)
                    if cap.isOpened():
                        self.camera = cap
                        logger.info(f"Backend {b} opened camera")
                        break
                if self.camera is None:
                    # last‑ditch: default backend
                    self.camera = cv2.VideoCapture(int(CAMERA_ID))

            # common configuration
            camera_ok = False
            if self.camera is not None and self.camera.isOpened():
                # try applying settings where supported
                try:
                    self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, RESOLUTION[0])
                    self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, RESOLUTION[1])
                    self.camera.set(cv2.CAP_PROP_FPS, FPS)
                except Exception:
                    pass

                # warm‑up read to confirm frames are available
                ok = False
                for _ in range(3):
                    ok, _ = self.camera.read()
                    if ok:
                        camera_ok = True
                        break
                
                if not camera_ok:
                    logger.warning("Camera opened but failed to read frames (likely in use by another process)")
                    try:
                        self.camera.release()
                    except Exception:
                        pass
                    self.camera = None

            # If direct camera access failed, try MJPEG input
            if not camera_ok:
                logger.warning("Direct camera access failed, trying MJPEG input from camera_worker...")
                if self.init_mjpeg_input():
                    logger.info("Using MJPEG input for detection")
                    return True
                raise RuntimeError("Failed to open camera directly or via MJPEG input!")

            logger.info(f"Camera initialized: {RESOLUTION[0]}x{RESOLUTION[1]} @ {FPS}FPS")
            return True

        except Exception as e:
            logger.error(f"Camera initialization failed: {e}")
            # release any half‑opened capture
            try:
                if self.camera:
                    self.camera.release()
            except Exception:
                pass
            self.camera = None
            return False

    def init_mjpeg_input(self) -> bool:
        """Connect to the raw MJPEG feed as a fallback input."""
        try:
            if self.mjpeg_socket:
                try:
                    self.mjpeg_socket.close()
                except Exception:
                    pass
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            sock.connect((RAW_FEED_HOST, RAW_FEED_PORT))
            sock.settimeout(None)
            self.mjpeg_socket = sock
            self.mjpeg_buffer = b""
            return True
        except Exception as e:
            logger.error(f"Failed to connect to MJPEG input {RAW_FEED_HOST}:{RAW_FEED_PORT}: {e}")
            self.mjpeg_socket = None
            return False

    def read_mjpeg_frame(self) -> Optional[np.ndarray]:
        """Read a single JPEG frame from the MJPEG socket."""
        if self.mjpeg_socket is None:
            return None

        try:
            # Ensure we have a full header
            while b"\r\n\r\n" not in self.mjpeg_buffer:
                chunk = self.mjpeg_socket.recv(4096)
                if not chunk:
                    return None
                self.mjpeg_buffer += chunk

            header_bytes, rest = self.mjpeg_buffer.split(b"\r\n\r\n", 1)
            headers = header_bytes.decode(errors="ignore").split("\r\n")
            length = None
            for line in headers:
                if line.lower().startswith("content-length"):
                    parts = line.split(":", 1)
                    if len(parts) == 2:
                        length = int(parts[1].strip())
                        break
            if length is None:
                # If header is malformed, drop it and retry
                self.mjpeg_buffer = rest
                return None

            while len(rest) < length:
                chunk = self.mjpeg_socket.recv(4096)
                if not chunk:
                    return None
                rest += chunk

            jpeg_bytes = rest[:length]
            self.mjpeg_buffer = rest[length:]

            # Skip past the trailing boundary marker if present
            if self.mjpeg_buffer.startswith(b"\r\n"):
                self.mjpeg_buffer = self.mjpeg_buffer[2:]

            frame_array = np.frombuffer(jpeg_bytes, dtype=np.uint8)
            frame = cv2.imdecode(frame_array, cv2.IMREAD_COLOR)
            
            if frame is None:
                logger.warning("Failed to decode MJPEG frame")
                return None
                
            return frame
        except Exception as e:
            logger.error(f"MJPEG read error: {e}")
            return None

    def read_frame(self) -> Optional[np.ndarray]:
        """Read a frame from the camera or MJPEG input."""
        if self.camera is not None:
            ret, frame = self.camera.read()
            return frame if ret else None
        return self.read_mjpeg_frame()
            
    def start_server(self):
        """Start the MJPEG streaming server"""
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind(("0.0.0.0", CAMERA_PORT))
            self.server_socket.listen(5)
            logger.info(f"Detection server listening on port {CAMERA_PORT}")
            return True
        except Exception as e:
            logger.error(f"Failed to start server: {e}")
            return False
            
    def detect_objects(self, frame: np.ndarray) -> Tuple[np.ndarray, List[Dict[str, Any]]]:
        """Run NanoOWL detection on frame"""
        if not self.detection_enabled or self.predictor is None:
            # Demo mode - draw placeholder
            cv2.putText(frame, "NanoOWL: Demo Mode (not installed)", 
                       (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
            return frame, []
            
        try:
            # Convert to PIL Image
            pil_image = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))

            # Run detection
            with torch.no_grad():
                sig = inspect.signature(self.predictor.predict)
                logger.debug(f"predict signature: {sig}")
                kwargs: Dict[str, Any] = {}
                if 'image' in sig.parameters:
                    kwargs['image'] = pil_image
                if 'text' in sig.parameters:
                    kwargs['text'] = self.prompts
                if 'threshold' in sig.parameters:
                    kwargs['threshold'] = DETECTION_THRESHOLD
                if 'pad_square' in sig.parameters:
                    kwargs['pad_square'] = True
                # supply text_encodings if required; many versions accept None as optional
                if 'text_encodings' in sig.parameters:
                    kwargs['text_encodings'] = None

                # debug: list potential encoder methods
                if 'text_encodings' in sig.parameters:
                    encoder_methods = [m for m in dir(self.predictor) if 'encode' in m.lower()]
                    logger.debug(f"predictor encoder candidates: {encoder_methods}")

                output = self.predictor.predict(**kwargs)

            # Draw detections
            detections: List[Dict[str, Any]] = []
            for i, box in enumerate(output.boxes):
                score = output.scores[i].item()
                label_idx = int(output.labels[i].item())
                label_str: str = str(self.prompts[label_idx]) if label_idx < len(self.prompts) else "unknown"
                
                # Get box coordinates
                x1, y1, x2, y2 = [int(v) for v in box]
                
                # Draw rectangle
                color = (0, 255, 0)  # Green
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                
                # Draw label
                label_text = f"{label_str if label_str else 'unknown'}: {score:.2f}"
                cv2.putText(frame, label_text, (x1, y1 - 10),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
                
                detections.append({
                    "label": label_str,
                    "score": score,
                    "box": [x1, y1, x2, y2]
                })
                
            self.detection_count += len(detections)
            
            # Draw detection count
            cv2.putText(frame, f"Detections: {len(detections)}", 
                       (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            
            return frame, detections
            
        except Exception as e:
            logger.error(f"Detection error: {e}")
            cv2.putText(frame, f"Detection Error: {str(e)[:50]}", 
                       (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
            return frame, []
            
    def start_command_server(self) -> None:
        """Listen for simple JSON commands (currently: set_prompt)"""
        import json
        def loop() -> None:
            while self.running:
                try:
                    if self.cmd_socket is None:
                        time.sleep(0.5)
                        continue
                    try:
                        self.cmd_socket.settimeout(1.0)
                        conn, _ = self.cmd_socket.accept()
                    except socket.timeout:
                        continue
                    data = conn.recv(4096).decode()
                    try:
                        cmd = json.loads(data)
                        if cmd.get('cmd') == 'set_prompt':
                            text = cmd.get('text','')
                            self.prompt_text = text
                            self.prompts = [str(s) for s in text.split(', ')]
                            logger.info(f"Prompt updated to: '{text}'")
                            conn.sendall(b'OK')
                        else:
                            conn.sendall(b'UNKNOWN')
                    except Exception as e:
                        conn.sendall(str(e).encode())
                    conn.close()
                except Exception:
                    time.sleep(0.5)
        try:
            self.cmd_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.cmd_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.cmd_socket.bind(("0.0.0.0", COMMAND_PORT))
            self.cmd_socket.listen(1)
            threading.Thread(target=loop, daemon=True).start()
            logger.info(f"Command server listening on port {COMMAND_PORT}")
        except Exception as e:
            logger.error(f"Failed to start command server: {e}")

    def encode_frame(self, frame: np.ndarray) -> Optional[bytes]:
        """Encode frame to JPEG using GPU acceleration"""
        try:
            encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY]
            _, jpeg_data = cv2.imencode('.jpg', frame, encode_params)
            return jpeg_data.tobytes()
        except Exception as e:
            logger.error(f"Frame encoding failed: {e}")
            return None
            
    def stream_to_client(self, client_socket: socket.socket) -> None:
        """Stream MJPEG with detections to a connected client"""
        logger.info("Client connected to detection stream")
        bad_reads = 0
        frame_counter = 0

        try:
            while self.running:
                frame = self.read_frame()
                if frame is None:
                    bad_reads += 1
                    logger.warning(f"Failed to read frame from camera (count={bad_reads})")
                    # if we keep failing, try to re‑open camera once
                    if bad_reads >= 10:
                        logger.error("Repeated camera read failures, attempting to reinitialize camera")
                        if not self.init_camera():
                            logger.error("Camera reinitialization failed, stopping stream and worker")
                            # shut down entire worker so the pi server knows there's no feed
                            self.running = False
                            break
                        bad_reads = 0
                    time.sleep(0.01)
                    continue
                bad_reads = 0
                
                # Log frame info periodically for debugging
                frame_counter += 1
                if frame_counter == 1 or frame_counter % 30 == 0:
                    logger.info(f"Frame {frame_counter}: shape={frame.shape}, dtype={frame.dtype}, mean_pixel_value={frame.mean():.1f}")

                # Run detection and annotate
                annotated_frame, _ = self.detect_objects(frame)

                # Encode frame
                jpeg_data = self.encode_frame(annotated_frame)
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
                self.frame_count += 1
                if time.time() - self.last_fps_time >= 5:
                    fps = self.frame_count / 5
                    dps = self.detection_count / 5
                    logger.info(f"Detection streaming: {fps:.1f} FPS, {dps:.1f} detections/sec")
                    self.frame_count = 0
                    self.detection_count = 0
                    self.last_fps_time = time.time()

        finally:
            try:
                client_socket.close()
            except Exception:
                pass
            logger.info("Detection stream ended")
            
    def run(self):
        """Main worker loop"""
        logger.info("=" * 50)
        logger.info("Detection Worker v3.0 Starting...")
        logger.info("=" * 50)
        logger.info(f"Initial prompt: '{self.prompt_text}'")
        
        # Initialize NanoOWL
        self.init_nanoowl()
        
        # start command listener for prompt updates
        self.start_command_server()

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
                if self.server_socket is None:
                    logger.error("Server socket is None")
                    break
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
                
    def stop(self):
        """Stop the worker"""
        self.running = False
        if self.camera:
            self.camera.release()
        if self.server_socket:
            self.server_socket.close()
        if self.cmd_socket:
            try:
                self.cmd_socket.close()
            except:
                pass
        logger.info("Detection worker stopped")


if __name__ == "__main__":
    worker = DetectionWorker()
    try:
        worker.run()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    finally:
        worker.stop()
