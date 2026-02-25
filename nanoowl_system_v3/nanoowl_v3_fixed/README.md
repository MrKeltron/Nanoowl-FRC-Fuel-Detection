# NanoOWL Vision System v3.0 - Fixed

Ultra-low latency vision system with Raspberry Pi 3 + Jetson Orin Nano.

## Architecture

- **Raspberry Pi 3**: Ultra-lightweight MJPEG forwarding (zero image processing)
- **Jetson Orin Nano**: All heavy processing (camera capture → GPU detection → MJPEG encoding)
- **Direct Ethernet**: Pi (192.168.50.1) ↔ Jetson (192.168.50.2)
- **Result**: ~90ms latency, stable 30 FPS

## Quick Start

### 1. Deploy to Jetson (from Pi)

```bash
cd ~/nanoowl_system_v3.0
chmod +x deploy_to_jetson.sh
./deploy_to_jetson.sh
```

### 2. Start Jetson Workers

```bash
ssh jetson@192.168.50.2
cd ~/nanoowl_system_v3.0
./launch.sh
```

### 3. Start Pi Controller

```bash
cd ~/nanoowl_system_v3.0
python3 controller.py
```

### 4. Access Web UI

Open browser to: `http://192.168.50.1:7860`

## File Structure

```
nanoowl_system_v3.0/
├── controller.py          # GUI with dual logs (run on Pi)
├── pi_server.py          # Lightweight MJPEG server (run on Pi)
├── deploy_to_jetson.sh   # Deployment script
├── jetson/
│   ├── camera_worker.py     # Raw camera stream (port 9001)
│   ├── detection_worker.py  # NanoOWL detection (port 9000)
│   └── launch.sh            # Start all workers
└── logs/                 # Log files
```

## Troubleshooting

### No Logs Showing in GUI

1. Check SSH connection:
   ```bash
   ssh jetson@192.168.50.2
   ```

2. Verify paramiko is installed:
   ```bash
   pip3 install paramiko
   ```

3. Check Jetson SSH service:
   ```bash
   ssh jetson@192.168.50.2 "sudo systemctl status ssh"
   ```

### Cameras Not Working

1. Check if workers are running:
   ```bash
   ssh jetson@192.168.50.2 "ps aux | grep python"
   ```

2. Check worker logs:
   ```bash
   ssh jetson@192.168.50.2 "tail -f ~/nanoowl_system_v3.0/logs/camera_worker.log"
   ```

3. Test camera on Jetson:
   ```bash
   ssh jetson@192.168.50.2
   gst-launch-1.0 nvarguscamerasrc ! nvvidconv ! xvimagesink
   ```

### No Detections

1. Check if NanoOWL is installed:
   ```bash
   ssh jetson@192.168.50.2 "python3 -c 'from nanoowl.owl_predictor import OwlPredictor; print(OK)'"
   ```

2. Check detection worker logs:
   ```bash
   ssh jetson@192.168.50.2 "tail -f ~/nanoowl_system_v3.0/logs/detection_worker.log"
   ```

### "Connection Refused" Error (Most Common!)

This error means the Pi can reach the Jetson, but the camera/detection workers aren't running.

**The fix: Start Jetson workers FIRST!**

```bash
# SSH to Jetson
ssh jetson@192.168.50.2

# Start workers
cd ~/nanoowl_system_v3.0
./launch.sh
```

Then refresh the web UI or restart the Pi server.

**To verify workers are running:**
```bash
ssh jetson@192.168.50.2 "netstat -tlnp | grep python"
```
You should see ports 9000, 9001, 9002 listening.

### Connection Issues

1. Verify network:
   ```bash
   ping 192.168.50.2
   ```

2. Check ports:
   ```bash
   ssh jetson@192.168.50.2 "netstat -tlnp | grep python"
   ```

### SCP "No such file" Errors

The deployment script handles this automatically by creating the directory first:
```bash
./deploy_to_jetson.sh
```

## Network Configuration

### Static IP Setup (if needed)

On Pi (`/etc/dhcpcd.conf`):
```
interface eth0
static ip_address=192.168.50.1/24
```

On Jetson (`/etc/netplan/01-netcfg.yaml`):
```yaml
network:
  version: 2
  ethernets:
    eth0:
      addresses:
        - 192.168.50.2/24
```

## Performance Tuning

### Jetson MAX Power Mode

```bash
sudo nvpmodel -m 0
sudo jetson_clocks
```

### Check GPU Usage

```bash
tegrastats
```

## Ports

| Port | Service | Description |
|------|---------|-------------|
| 7860 | Web UI | Main web interface on Pi |
| 9000 | Detection | Annotated camera feed from Jetson |
| 9001 | Camera | Raw camera feed from Jetson |
| 9002 | Reserved | Future use |

## License

MIT License - Kelton Chelbian (ninjaneers)
