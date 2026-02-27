# FRC Ball Detection System

Portable YOLOv8 ball detection for Windows, Linux, Mac, and Jetson Orin Nano. Auto-detects and uses the best available hardware: CUDA (NVIDIA) → DirectML (AMD/Intel GPU) → CPU.

## Quick Start

### 1. Install
```bash
pip install -r requirements.txt
```

### 2. Run
```bash
python main.py
```

That's it! The system auto-detects your hardware and starts detecting.

## Output

**Console:**
```
[Detection] X: 320px  Y: 240px  Width: 85px  Distance: 112.4in  Conf: 95%  FPS: 12.5
```

**Display Window:**
- Green bounding box around ball
- Crosshair at center
- Position, distance, confidence, FPS

## Configuration

Edit the top of `main.py`:

```python
CAMERA_INDEX = 0                 # 0 = first USB webcam
CONFIDENCE_THRESHOLD = 0.4       # Detection threshold (0.0-1.0)
BALL_DIAMETER_INCHES = 9.5       # Ball size for distance
FOCAL_LENGTH_PX = 700            # Camera calibration
SHOW_DISPLAY = True              # Show video window
ENABLE_NETWORKTABLES = False     # FRC robot integration
```

## Supported Hardware

| Hardware | Status | Notes |
|----------|--------|-------|
| **NVIDIA GPU** | ✓ Auto-detected | RTX, GTX, A100, etc. - ~20-30 FPS |
| **Jetson Orin Nano** | ✓ Auto-detected | CUDA - ~15-25 FPS |
| **AMD Ryzen AI NPU** | ✓ Auto-detected | Install torch-directml for speedup |
| **Intel Arc GPU** | ✓ Auto-detected | Install torch-directml |
| **CPU** | ✓ Fallback | Works on any system - ~10 FPS |

## Calibrate Distance

1. Place ball exactly 24 inches from camera
2. Note the `Width: XXXpx` value in console
3. Set `FOCAL_LENGTH_PX = width_px * 24`

Example: if width is 85px:
```python
FOCAL_LENGTH_PX = 85 * 24  # = 2040
```

## Optional: FRC Robot Integration

To send data to your roboRIO:

1. Uncomment in `requirements.txt`:
```
pynetworktables>=2021.0.0
```

2. In `main.py`:
```python
ENABLE_NETWORKTABLES = True
ROBOT_IP = "10.0.0.2"
```

Data sent to `Vision` NetworkTable:
- ball_detected (boolean)
- ball_x, ball_y (pixels)
- ball_width_px (pixels)
- ball_distance (inches)
- ball_confidence (0.0-1.0)

## Optional: Faster GPU (Windows)

For 2-3x speedup with AMD NPU/GPU or Intel Arc:

1. Uncomment in `requirements.txt`:
```
torch-directml
```

2. Reinstall: `pip install -r requirements.txt`

## Special: Jetson Orin Nano

1. First install Jetson PyTorch:
```bash
pip install torch torchvision --index-url https://download.pytorch.org/whl/nightly/jetson/cu118
```

2. Then: `pip install -r requirements.txt`

3. For CSI camera, set in main.py:
```python
USE_CSI_CAMERA = True
SHOW_DISPLAY = False  # if running headless
```

## Controls

- `q` - Quit
- `s` - Save training image to `training_images/` folder

## Troubleshooting

**"No module named 'torch'"**
```bash
pip install -r requirements.txt
```

**"Could not open camera"**
- Try CAMERA_INDEX = 1 or 2
- On Jetson: set USE_CSI_CAMERA = True

**Low FPS**
- Reduce image size: change `imgsz=416` to `imgsz=320` in detector.py
- Enable GPU/DirectML
- Reduce CAMERA_WIDTH and CAMERA_HEIGHT

**GPU not detected?**
- Check startup message to see what was selected
- For NVIDIA: run `nvidia-smi` to verify drivers
- Verify PyTorch sees GPU: `python -c "import torch; print(torch.cuda.is_available())"`

## Files

```
.
├── main.py                              (Run this - includes everything)
├── detector.py                          (YOLOv8 with smart device detection)
├── requirements.txt                     (Dependencies)
├── README.md                            (This file)
├── runs/detect/train3/weights/best.pt   (Model file)
└── training_images/                     (Saved frames - created on first run)
```

## Train Your Own Model

1. Label images on Roboflow (free): https://roboflow.com
2. Train:
```bash
yolo detect train data=your_data.yaml model=yolov8n.pt epochs=50
```
3. Update MODEL_PATH in main.py

## Resources

- **YOLOv8**: https://docs.ultralytics.com
- **PyTorch**: https://pytorch.org
- **Jetson**: https://developer.nvidia.com/embedded/jetson-orin-nano-developer-kit
- **DirectML**: https://learn.microsoft.com/en-us/windows/ai/directml/

---

**Team 340 - NanoOwl**
