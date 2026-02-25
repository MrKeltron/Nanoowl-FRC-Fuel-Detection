#!/bin/bash
#
# NANOOWL VISION SYSTEM v3.0 - Deployment Script
# Transfers jetson/ folder from Pi to Jetson via SCP with password authentication
#

set -e

# Configuration - EDIT THESE VARIABLES
JETSON_IP="192.168.50.2"
JETSON_USER="jetson"
JETSON_PASSWORD="jetson"  # <-- CHANGE THIS TO YOUR JETSON PASSWORD
JETSON_DIR="~/nanoowl_system_v3.0"
LOCAL_JETSON_DIR="./jetson"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}  NanoOWL v3.0 - Deploy to Jetson${NC}"
echo -e "${GREEN}============================================${NC}"
echo ""

# Check if local jetson directory exists
if [ ! -d "$LOCAL_JETSON_DIR" ]; then
    echo -e "${RED}ERROR: Local jetson/ directory not found!${NC}"
    echo -e "${YELLOW}Make sure you're running this from the nanoowl_system_v3.0 directory${NC}"
    exit 1
fi

# Check if Jetson is reachable
echo -e "${BLUE}[1/4] Checking Jetson connectivity...${NC}"
if ping -c 1 -W 2 "$JETSON_IP" &> /dev/null; then
    echo -e "${GREEN}  Jetson is reachable at $JETSON_IP${NC}"
else
    echo -e "${RED}ERROR: Cannot reach Jetson at $JETSON_IP${NC}"
    echo -e "${YELLOW}Please check:${NC}"
    echo -e "  - Ethernet cable is connected between Pi and Jetson"
    echo -e "  - Jetson is powered on"
    echo -e "  - IP addresses are configured correctly"
    exit 1
fi

# Function to run SSH command with password
run_ssh() {
    local cmd="$1"
    if command -v sshpass &> /dev/null; then
        sshpass -p "$JETSON_PASSWORD" ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null "$JETSON_USER@$JETSON_IP" "$cmd"
    else
        # Fallback: use SSH_ASKPASS
        SSH_ASKPASS_REQUIRE=force SSH_ASKPASS="/bin/sh -c 'echo $JETSON_PASSWORD'" ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null "$JETSON_USER@$JETSON_IP" "$cmd"
    fi
}

# Function to run SCP with password
run_scp() {
    local src="$1"
    local dest="$2"
    if command -v sshpass &> /dev/null; then
        sshpass -p "$JETSON_PASSWORD" scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -r "$src" "$dest"
    else
        # Fallback: use SSH_ASKPASS
        SSH_ASKPASS_REQUIRE=force SSH_ASKPASS="/bin/sh -c 'echo $JETSON_PASSWORD'" scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -r "$src" "$dest"
    fi
}

# Install sshpass if not available
if ! command -v sshpass &> /dev/null; then
    echo -e "${YELLOW}sshpass not found, attempting to install...${NC}"
    sudo apt-get update && sudo apt-get install -y sshpass 2>/dev/null || {
        echo -e "${YELLOW}Could not install sshpass, trying alternative method...${NC}"
    }
fi

# Create destination directory on Jetson
echo -e "${BLUE}[2/4] Creating destination directory on Jetson...${NC}"
if run_ssh "mkdir -p $JETSON_DIR/logs"; then
    echo -e "${GREEN}  Directory created: $JETSON_DIR${NC}"
else
    echo -e "${RED}ERROR: Failed to create directory on Jetson${NC}"
    echo -e "${YELLOW}Check your JETSON_PASSWORD in this script${NC}"
    exit 1
fi

# Transfer files
echo -e "${BLUE}[3/4] Transferring files to Jetson...${NC}"
echo -e "${YELLOW}  Files to transfer:${NC}"
ls -la "$LOCAL_JETSON_DIR/"

echo ""
if run_scp "$LOCAL_JETSON_DIR"/* "$JETSON_USER@$JETSON_IP:$JETSON_DIR/"; then
    echo -e "${GREEN}  Files transferred successfully!${NC}"
else
    echo -e "${RED}ERROR: SCP transfer failed${NC}"
    echo -e "${YELLOW}Check your JETSON_PASSWORD in this script${NC}"
    exit 1
fi

# Make scripts executable
echo -e "${BLUE}[4/4] Setting permissions...${NC}"
if run_ssh "chmod +x $JETSON_DIR/launch.sh"; then
    echo -e "${GREEN}  Permissions set${NC}"
else
    echo -e "${YELLOW}Warning: Could not set execute permission${NC}"
fi

echo ""
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}  Deployment Complete!${NC}"
echo -e "${GREEN}============================================${NC}"
echo ""
echo -e "${BLUE}Files deployed to:${NC} $JETSON_USER@$JETSON_IP:$JETSON_DIR"
echo ""
echo -e "${YELLOW}To start the workers on Jetson, run:${NC}"
echo -e "  ssh $JETSON_USER@$JETSON_IP"
echo -e "  cd $JETSON_DIR"
echo -e "  ./launch.sh"
echo ""
echo -e "${YELLOW}Or start remotely with password:${NC}"
echo -e "  sshpass -p '$JETSON_PASSWORD' ssh $JETSON_USER@$JETSON_IP 'cd $JETSON_DIR && ./launch.sh'"
echo ""

# Verify deployment
echo -e "${BLUE}Verifying deployment...${NC}"
run_ssh "ls -la $JETSON_DIR/"
