#!/bin/bash
#
# NANOOWL VISION SYSTEM v3.0 - Diagnostic Script
# Helps troubleshoot common issues
#

# Configuration - EDIT THIS
JETSON_IP="192.168.50.2"
JETSON_USER="jetson"
JETSON_PASSWORD="jetson"  # <-- CHANGE THIS TO YOUR JETSON PASSWORD

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# Function to run SSH command with password (if sshpass available)
run_ssh() {
    local cmd="$1"
    if command -v sshpass &> /dev/null; then
        sshpass -p "$JETSON_PASSWORD" ssh -o ConnectTimeout=3 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null "$JETSON_USER@$JETSON_IP" "$cmd" 2>/dev/null
    else
        ssh -o ConnectTimeout=3 -o BatchMode=yes "$JETSON_USER@$JETSON_IP" "$cmd" 2>/dev/null
    fi
}

echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}  NanoOWL v3.0 - Diagnostic Tool${NC}"
echo -e "${GREEN}============================================${NC}"
echo ""

# Function to print section header
section() {
    echo ""
    echo -e "${BLUE}>>> $1${NC}"
    echo "----------------------------------------"
}

# Check if running on Pi
section "System Information"
echo "Hostname: $(hostname)"
echo "Date: $(date)"
echo "Uptime: $(uptime -p 2>/dev/null || uptime)"

# Network diagnostics
section "Network Configuration"
echo "IP Addresses:"
ip addr show 2>/dev/null | grep "inet " || ifconfig 2>/dev/null | grep "inet "

echo ""
echo "Route to Jetson:"
ip route get $JETSON_IP 2>/dev/null || echo "  Cannot determine route"

# Ping test
section "Connectivity Tests"
echo -n "Ping Jetson ($JETSON_IP): "
if ping -c 1 -W 2 "$JETSON_IP" &> /dev/null; then
    echo -e "${GREEN}OK${NC}"
    ping -c 1 "$JETSON_IP" | grep "time="
else
    echo -e "${RED}FAILED${NC}"
fi

# SSH test
echo -n "SSH to Jetson: "
if run_ssh "echo OK" | grep -q "OK"; then
    echo -e "${GREEN}OK${NC}"
else
    echo -e "${RED}FAILED${NC} (check JETSON_PASSWORD in this script)"
fi

# Check running processes
section "Local Processes (Pi)"
echo "Python processes:"
ps aux | grep python | grep -v grep || echo "  No Python processes running"

echo ""
echo "Listening ports:"
netstat -tlnp 2>/dev/null | grep -E "(python|7860|900)" || ss -tlnp 2>/dev/null | grep -E "(python|7860|900)" || echo "  No relevant ports found"

# Check Jetson processes (if reachable)
section "Remote Processes (Jetson)"
if run_ssh "echo OK" | grep -q "OK"; then
    echo "Python processes on Jetson:"
    run_ssh "ps aux | grep python | grep -v grep" || echo "  No Python processes"
    
    echo ""
    echo "Listening ports on Jetson:"
    run_ssh "netstat -tlnp 2>/dev/null | grep python || ss -tlnp 2>/dev/null | grep python" || echo "  No Python ports"
else
    echo -e "${YELLOW}Cannot connect to Jetson${NC}"
fi

# Check log files
section "Log Files"
if [ -d "logs" ]; then
    echo "Log directory exists"
    ls -la logs/
    
    echo ""
    echo "Recent errors (if any):"
    for log in logs/*.log; do
        if [ -f "$log" ]; then
            echo "--- $log ---"
            tail -n 5 "$log" 2>/dev/null
        fi
    done
else
    echo -e "${YELLOW}No logs directory found${NC}"
fi

# Check file structure
section "File Structure"
echo "Checking required files:"
files=("controller.py" "pi_server.py" "jetson/camera_worker.py" "jetson/detection_worker.py" "jetson/launch.sh")
for file in "${files[@]}"; do
    if [ -f "$file" ]; then
        echo -e "  ${GREEN}✓${NC} $file"
    else
        echo -e "  ${RED}✗${NC} $file (MISSING)"
    fi
done

# Check Jetson file structure (if reachable)
section "Jetson File Structure"
if run_ssh "echo OK" | grep -q "OK"; then
    echo "Checking files on Jetson:"
    run_ssh "
        for file in ~/nanoowl_system_v3.0/camera_worker.py ~/nanoowl_system_v3.0/detection_worker.py ~/nanoowl_system_v3.0/launch.sh; do
            if [ -f \"\$file\" ]; then
                echo \"  ✓ \$file\"
            else
                echo \"  ✗ \$file (MISSING)\"
            fi
        done
    "
else
    echo -e "${YELLOW}Cannot connect to Jetson${NC}"
fi

# Hardware info
section "Hardware Information"
echo "CPU: $(cat /proc/cpuinfo | grep "model name" | head -1 | cut -d: -f2 | xargs)"
echo "Memory: $(free -h | grep Mem | awk '{print $2}')"
echo "Disk: $(df -h . | tail -1 | awk '{print $3 "/" $2 " (" $5 " used)"}')"

# Temperature (if available)
if [ -f /sys/class/thermal/thermal_zone0/temp ]; then
    temp=$(cat /sys/class/thermal/thermal_zone0/temp)
    temp_c=$((temp / 1000))
    echo "Temperature: ${temp_c}°C"
fi

# Jetson hardware info (if reachable)
section "Jetson Hardware Information"
if run_ssh "echo OK" | grep -q "OK"; then
    echo "Jetson Info:"
    run_ssh "
        if command -v jetson_release &> /dev/null; then
            jetson_release
        else
            echo 'JetPack: Unknown'
        fi
        echo 'CUDA: '
        nvcc --version 2>/dev/null | grep release || echo '  Not found'
    "
    
    echo ""
    echo "Jetson Power Mode:"
    run_ssh "sudo nvpmodel -q 2>/dev/null | grep 'NV Power Mode' || echo '  Unknown'"
    
    echo ""
    echo "Jetson tegrastats (last reading):"
    run_ssh "tegrastats --interval 1000 | head -1" 2>/dev/null || echo "  tegrastats not available"
else
    echo -e "${YELLOW}Cannot connect to Jetson${NC}"
fi

# Check for common errors in logs
section "Log Analysis"
if [ -f "logs/pi_server.log" ]; then
    echo "Checking for common errors:"
    
    CONNECTION_REFUSED=$(grep -c "Connection refused" logs/pi_server.log 2>/dev/null || echo "0")
    if [ "$CONNECTION_REFUSED" -gt 0 ]; then
        echo -e "  ${RED}Found 'Connection refused' errors ($CONNECTION_REFUSED times)${NC}"
        echo -e "  ${YELLOW}This means Jetson workers are NOT running!${NC}"
        echo ""
        echo "  To fix:"
        echo "    ssh $JETSON_USER@$JETSON_IP"
        echo "    cd ~/nanoowl_system_v3.0"
        echo "    ./launch.sh"
    else
        echo -e "  ${GREEN}No 'Connection refused' errors found${NC}"
    fi
else
    echo -e "${YELLOW}No pi_server.log found${NC}"
fi

# Summary
section "Summary"
echo "Common issues and solutions:"
echo ""
echo "1. Connection Refused (most common):"
echo "   - Jetson workers not running"
echo "   - Fix: ssh $JETSON_USER@$JETSON_IP 'cd ~/nanoowl_system_v3.0 && ./launch.sh'"
echo ""
echo "2. No logs in GUI:"
echo "   - Check SSH connection: ssh $JETSON_USER@$JETSON_IP"
echo "   - Install paramiko: pip3 install paramiko"
echo ""
echo "3. Cameras not working:"
echo "   - Check workers: ssh $JETSON_USER@$JETSON_IP 'ps aux | grep python'"
echo "   - Check logs: ssh $JETSON_USER@$JETSON_IP 'tail ~/nanoowl_system_v3.0/logs/camera_worker.log'"
echo ""
echo "4. No detections:"
echo "   - Check NanoOWL install: ssh $JETSON_USER@$JETSON_IP 'python3 -c \"from nanoowl.owl_predictor import OwlPredictor\"'"
echo "   - Check detection logs: ssh $JETSON_USER@$JETSON_IP 'tail ~/nanoowl_system_v3.0/logs/detection_worker.log'"
echo ""
echo "4. SCP errors:"
echo "   - Run: ./deploy_to_jetson.sh"
echo ""

echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}  Diagnostic Complete${NC}"
echo -e "${GREEN}============================================${NC}"
