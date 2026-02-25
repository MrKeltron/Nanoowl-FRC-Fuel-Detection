#!/bin/bash
#
# NANOOWL VISION SYSTEM v3.0 - Launch Script (Jetson Orin Nano)
# Starts all workers with MAX performance mode (25W)
#

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}  NanoOWL Vision System v3.0 - Jetson${NC}"
echo -e "${GREEN}============================================${NC}"
echo ""

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Set Jetson to MAX performance mode (25W)
echo -e "${BLUE}[1/5] Setting MAX performance mode (25W)...${NC}"
sudo nvpmodel -m 0 2>/dev/null || echo -e "${YELLOW}Warning: Could not set nvpmodel${NC}"
sudo jetson_clocks 2>/dev/null || echo -e "${YELLOW}Warning: Could not run jetson_clocks${NC}"

# Check CUDA
echo -e "${BLUE}[2/5] Checking CUDA...${NC}"
if command -v nvcc &> /dev/null; then
    echo -e "${GREEN}  CUDA version: $(nvcc --version | grep release | awk '{print $5}' | cut -d',' -f1)${NC}"
else
    echo -e "${YELLOW}  Warning: nvcc not found in PATH${NC}"
fi

# Check GPU
echo -e "${BLUE}[3/5] Checking GPU...${NC}"
if command -v nvidia-smi &> /dev/null; then
    nvidia-smi --query-gpu=name,memory.total,utilization.gpu --format=csv,noheader 2>/dev/null || true
else
    echo -e "${YELLOW}  nvidia-smi not available (normal for Jetson)${NC}"
fi

# Show current power mode
echo -e "${BLUE}[4/5] Current power mode:${NC}"
sudo nvpmodel -q 2>/dev/null | grep "NV Power Mode" || echo "  Unknown"

# Kill any existing workers
echo -e "${BLUE}[5/5] Stopping any existing workers...${NC}"
pkill -f "camera_worker.py" 2>/dev/null || true
pkill -f "detection_worker.py" 2>/dev/null || true
sleep 1

echo ""
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}  Starting Workers...${NC}"
echo -e "${GREEN}============================================${NC}"
echo ""

# Create logs directory
mkdir -p logs

# Start detection worker (port 9000 - annotated feed)
echo -e "${YELLOW}Starting Detection Worker on port 9000...${NC}"
python3 detection_worker.py > logs/detection_worker.log 2>&1 &
DETECTION_PID=$!
echo -e "${GREEN}  Detection Worker PID: $DETECTION_PID${NC}"

# Wait a moment for detection worker to initialize
sleep 2

# Start camera worker (port 9001 - raw feed)
echo -e "${YELLOW}Starting Camera Worker on port 9001...${NC}"
python3 camera_worker.py > logs/camera_worker.log 2>&1 &
CAMERA_PID=$!
echo -e "${GREEN}  Camera Worker PID: $CAMERA_PID${NC}"

echo ""
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}  All Workers Started!${NC}"
echo -e "${GREEN}============================================${NC}"
echo ""
echo -e "${BLUE}Detection Worker:${NC}  http://192.168.50.2:9000 (annotated feed)"
echo -e "${BLUE}Camera Worker:${NC}     http://192.168.50.2:9001 (raw feed)"
echo ""
echo -e "${YELLOW}Logs are being written to ./logs/${NC}"
echo -e "${YELLOW}Press Ctrl+C to stop all workers${NC}"
echo ""

# Function to cleanup on exit
cleanup() {
    echo ""
    echo -e "${RED}Stopping workers...${NC}"
    kill $DETECTION_PID 2>/dev/null || true
    kill $CAMERA_PID 2>/dev/null || true
    pkill -f "camera_worker.py" 2>/dev/null || true
    pkill -f "detection_worker.py" 2>/dev/null || true
    echo -e "${GREEN}Workers stopped.${NC}"
    exit 0
}

# Set trap for cleanup
trap cleanup SIGINT SIGTERM

# Monitor workers
echo -e "${GREEN}Monitoring workers...${NC}"
while true; do
    if ! kill -0 $DETECTION_PID 2>/dev/null; then
        echo -e "${RED}ERROR: Detection Worker crashed!${NC}"
        echo -e "${YELLOW}Check logs/detection_worker.log for details${NC}"
    fi
    
    if ! kill -0 $CAMERA_PID 2>/dev/null; then
        echo -e "${RED}ERROR: Camera Worker crashed!${NC}"
        echo -e "${YELLOW}Check logs/camera_worker.log for details${NC}"
    fi
    
    # Show GPU stats every 10 seconds
    if command -v tegrastats &> /dev/null; then
        tegrastats --interval 10000 --logfile logs/tegrastats.log &
        TEGRA_PID=$!
        sleep 10
        kill $TEGRA_PID 2>/dev/null || true
    else
        sleep 5
    fi
done
