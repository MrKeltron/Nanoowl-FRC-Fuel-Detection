#!/bin/bash
#
# NANOOWL VISION SYSTEM v3.0 - Pi Quick Start
# Starts all Pi-side services
#

set -e

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}  NanoOWL v3.0 - Pi Quick Start${NC}"
echo -e "${GREEN}============================================${NC}"
echo ""

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Check dependencies
echo -e "${BLUE}[1/4] Checking dependencies...${NC}"

# Check Python3
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}ERROR: python3 not found${NC}"
    exit 1
fi

# Check pip packages
python3 -c "import tkinter" 2>/dev/null || {
    echo -e "${YELLOW}Installing tkinter...${NC}"
    sudo apt-get update && sudo apt-get install -y python3-tk
}

python3 -c "import paramiko" 2>/dev/null || {
    echo -e "${YELLOW}Installing paramiko...${NC}"
    pip3 install paramiko
}

# Check network
echo -e "${BLUE}[2/4] Checking network...${NC}"

# Get IP addresses
ETH_IP=$(ip addr show eth0 2>/dev/null | grep "inet " | awk '{print $2}' | cut -d/ -f1 || echo "Not configured")
WIFI_IP=$(ip addr show wlan0 2>/dev/null | grep "inet " | awk '{print $2}' | cut -d/ -f1 || echo "Not connected")

echo -e "${GREEN}  Ethernet IP: $ETH_IP${NC}"
echo -e "${GREEN}  WiFi IP: $WIFI_IP${NC}"

# Check Jetson connectivity
echo -e "${BLUE}  Checking Jetson connectivity...${NC}"
if ping -c 1 -W 2 "192.168.50.2" &> /dev/null; then
    echo -e "${GREEN}  Jetson: Reachable (192.168.50.2)${NC}"
    
    # Check if Jetson workers are running
    echo -e "${BLUE}  Checking Jetson workers...${NC}"
    WORKERS_RUNNING=true
    for port in 9000 9001 9002; do
        if timeout 2 bash -c "exec 3<>/dev/tcp/192.168.50.2/$port" 2>/dev/null; then
            echo -e "${GREEN}    Port $port: OK${NC}"
        else
            echo -e "${RED}    Port $port: NOT RUNNING${NC}"
            WORKERS_RUNNING=false
        fi
    done
    
    if [ "$WORKERS_RUNNING" = false ]; then
        echo ""
        echo -e "${RED}============================================${NC}"
        echo -e "${RED}  WARNING: Jetson workers not running!${NC}"
        echo -e "${RED}============================================${NC}"
        echo ""
        echo -e "${YELLOW}You MUST start Jetson workers first:${NC}"
        echo -e "  ssh jetson@192.168.50.2"
        echo -e "  cd ~/nanoowl_system_v3.0"
        echo -e "  ./launch.sh"
        echo ""
        echo -e "${YELLOW}Then restart this script${NC}"
        echo ""
        read -p "Press Enter to continue anyway (cameras won't work)..."
    else
        echo -e "${GREEN}  All Jetson workers are running!${NC}"
    fi
else
    echo -e "${RED}  Jetson: Not reachable${NC}"
    echo -e "${YELLOW}  Check Ethernet connection${NC}"
fi

# Kill existing processes
echo -e "${BLUE}[3/4] Stopping existing services...${NC}"
pkill -f "pi_server.py" 2>/dev/null || true
sleep 1

# Create logs directory
mkdir -p logs

# Start pi_server.py
echo -e "${BLUE}[4/4] Starting Pi Server...${NC}"
python3 pi_server.py > logs/pi_server.log 2>&1 &
PI_SERVER_PID=$!
echo -e "${GREEN}  Pi Server PID: $PI_SERVER_PID${NC}"

# Wait for server to start
sleep 2

# Check if server is running
if kill -0 $PI_SERVER_PID 2>/dev/null; then
    echo -e "${GREEN}  Pi Server is running!${NC}"
else
    echo -e "${RED}  ERROR: Pi Server failed to start${NC}"
    echo -e "${YELLOW}  Check logs/pi_server.log for details${NC}"
    exit 1
fi

echo ""
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}  Pi Services Started!${NC}"
echo -e "${GREEN}============================================${NC}"
echo ""
echo -e "${BLUE}Web UI:${NC} http://192.168.50.1:7860"
echo -e "${BLUE}Pi Server Log:${NC} tail -f logs/pi_server.log"
echo ""
echo -e "${YELLOW}To start the GUI controller, run:${NC}"
echo -e "  python3 controller.py"
echo ""

# Show log tail
echo -e "${BLUE}Pi Server log (last 10 lines):${NC}"
tail -n 10 logs/pi_server.log

echo ""
echo -e "${GREEN}Press Ctrl+C to stop${NC}"

# Keep script running
trap "echo ''; echo -e '${YELLOW}Stopping Pi Server...${NC}'; kill $PI_SERVER_PID 2>/dev/null || true; exit 0" SIGINT SIGTERM

while true; do
    if ! kill -0 $PI_SERVER_PID 2>/dev/null; then
        echo -e "${RED}WARNING: Pi Server has stopped!${NC}"
        echo -e "${YELLOW}Check logs/pi_server.log for errors${NC}"
        exit 1
    fi
    sleep 5
done
