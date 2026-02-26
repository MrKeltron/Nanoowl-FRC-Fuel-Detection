# ==============================================================================
# config.py - CHANGE SETTINGS HERE
# This is the only file you should need to edit between PC and Jetson Orin Nano
# ==============================================================================

# --- CAMERA SETTINGS ---
# Set to 0 for first USB webcam, 1 for second USB cam, etc.
# On Jetson with CSI camera, set USE_CSI_CAMERA = True instead
CAMERA_INDEX = 0
USE_CSI_CAMERA = False          # Set to True on Jetson if using CSI camera
CAMERA_WIDTH = 640
CAMERA_HEIGHT = 480
CAMERA_FPS = 60

# CSI camera pipeline (only used if USE_CSI_CAMERA = True)
# You shouldn't need to change this on the Jetson
CSI_PIPELINE = (
    "nvarguscamerasrc ! "
    "video/x-raw(memory:NVMM), width=1280, height=720, framerate=30/1 ! "
    "nvvidconv ! video/x-raw, format=BGRx ! "
    "videoconvert ! video/x-raw, format=BGR ! appsink"
)

# --- MODEL SETTINGS ---
# 'yolov8n.pt' = nano (fastest, less accurate) - good for Jetson
# 'yolov8s.pt' = small (good balance)
# 'yolov8m.pt' = medium (more accurate, slower)
MODEL_PATH = "yolov8n.pt"

# COCO class ID for sports ball = 32
# If you fine-tune your own model later, set this to 0 (first class)
TARGET_CLASS_ID = 0
TARGET_CLASS_NAME = "person"

# Minimum confidence to count as a detection (0.0 - 1.0)
CONFIDENCE_THRESHOLD = 0.4

# --- DEVICE SETTINGS ---
# 'auto'  = automatically picks best available (cuda > cpu)
# 'cuda'  = force GPU (NVIDIA on Jetson, ROCm on AMD Linux)
# 'cpu'   = force CPU (safe fallback, works everywhere)
DEVICE = "auto"

# --- BALL REAL-WORLD SIZE (for distance calculation) ---
# Measure your actual ball diameter and set it here
BALL_DIAMETER_INCHES = 9.5      # FRC 2024 NOTE game piece ~9.5 inches
FOCAL_LENGTH_PX = 700           # Calibrate this! See README for instructions

# --- NETWORKTABLES SETTINGS ---
ENABLE_NETWORKTABLES = True
ROBOT_IP = "10.0.0.2"          # Change to your roboRIO IP or team number format e.g. "10.TE.AM.2"
NT_TABLE_NAME = "Vision"

# --- DISPLAY SETTINGS ---
SHOW_DISPLAY = True             # Set to False on Jetson if running headless
DISPLAY_FPS = True
BOX_COLOR = (0, 255, 255)       # Yellow box in BGR
TEXT_COLOR = (0, 0, 0)
