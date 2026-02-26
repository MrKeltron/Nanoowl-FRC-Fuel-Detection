# FRC Ball Detection System
### YOLOv8 | OpenCV | NetworkTables

Detects a yellow sports ball in real time, reports X/Y position and pixel width,
estimates distance, and sends everything to the roboRIO over NetworkTables.

---

## File Structure

```
ball_detection/
├── main.py                     ← Run this
├── config.py                   ← THE ONLY FILE YOU EDIT between PC and Jetson
├── camera.py                   ← USB + CSI camera handling
├── detector.py                 ← YOLOv8 inference
├── distance.py                 ← Distance from pixel width
├── display.py                  ← On-screen overlays
├── networktables_publisher.py  ← Sends data to roboRIO
└── requirements.txt
```

---

## Setup on Windows PC

```bash
pip install -r requirements.txt
python main.py
```

That's it. It will download yolov8n.pt automatically on first run (~6MB).

---

## Setup on Jetson Orin Nano

1. Install PyTorch for Jetson (use NVIDIA's wheel, NOT pip's default):
   https://forums.developer.nvidia.com/t/pytorch-for-jetson/72048

2. Then install the rest:
```bash
pip install ultralytics opencv-python pynetworktables
```

3. Copy the entire `ball_detection/` folder to the Jetson.

4. In `config.py`, make these changes:
```python
USE_CSI_CAMERA = True       # if using CSI camera, otherwise leave False
MODEL_PATH = "yolov8n.pt"   # keep nano model for speed
DEVICE = "cuda"             # Jetson has CUDA, force it
SHOW_DISPLAY = False        # set False if running headless (no monitor)
ROBOT_IP = "10.TE.AM.2"    # set your actual roboRIO IP
```

5. Run it:
```bash
python main.py
```

---

## Calibrating Distance

The distance estimate uses the pinhole camera formula:
```
distance = (real_ball_diameter * focal_length) / pixel_width
```

To calibrate `FOCAL_LENGTH_PX` in config.py:
1. Place the ball exactly **24 inches** from the camera
2. Run the program and note the `Width:` value printed in the console
3. Calculate: `FOCAL_LENGTH_PX = width_px * 24`
4. Update the value in config.py

---

## NetworkTables Keys (table: "Vision")

| Key              | Type    | Description                        |
|------------------|---------|------------------------------------|
| ball_detected    | boolean | True if ball is in frame           |
| ball_x           | number  | X center in pixels from left       |
| ball_y           | number  | Y center in pixels from top        |
| ball_width_px    | number  | Bounding box width in pixels       |
| ball_distance    | number  | Estimated distance in inches       |
| ball_confidence  | number  | Detection confidence (0.0 - 1.0)   |
| frame_width      | number  | Camera frame width in pixels       |
| frame_height     | number  | Camera frame height in pixels      |

---

## Fine-tuning the Model Later

When you want to train on your specific yellow ball:
1. Collect ~100-200 images of your ball in various conditions
2. Label them using Roboflow (free): https://roboflow.com
3. Train: `yolo train data=your_data.yaml model=yolov8n.pt epochs=50`
4. Update `MODEL_PATH` in config.py to your new model
5. Set `TARGET_CLASS_ID = 0` (your custom model's first class)
