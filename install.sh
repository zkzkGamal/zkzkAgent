#!/bin/bash

# zkzkAgent Installation Script
# This script automates the setup of zkzkAgent on Linux.

set -e

# Colors for terminal output
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🚀 Starting zkzkAgent Installation...${NC}"

# 1. OS Validation
if [[ "$OSTYPE" != "linux-gnu"* ]]; then
    echo -e "${RED}❌ Error: This script is only supported on Linux.${NC}"
    exit 1
fi

# 2. Update System and Install System Dependencies
echo -e "${BLUE}📦 Installing system dependencies (requires sudo)...${NC}"
sudo apt update
sudo apt install -y python3-pip python3-venv ffmpeg portaudio19-dev network-manager curl libportaudio2

# 3. Virtual Environment Setup
echo -e "${BLUE}🐍 Setting up Python virtual environment...${NC}"
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo -e "${GREEN}✅ Virtual environment created.${NC}"
else
    echo -e "${BLUE}ℹ️ Virtual environment already exists.${NC}"
fi

# 4. Install Python Requirements
echo -e "${BLUE}🛠️ Installing Python packages...${NC}"
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 5. Ollama Setup
echo -e "${BLUE}🤖 Checking Ollama and model setup...${NC}"
if ! command -v ollama &> /dev/null; then
    echo -e "${BLUE}📥 Ollama not found. Installing Ollama...${NC}"
    curl -fsSL https://ollama.com/install.sh | sh
else
    echo -e "${GREEN}✅ Ollama is already installed.${NC}"
fi

# Start Ollama service if not running (systemd check)
if systemctl is-active --quiet ollama; then
    echo -e "${GREEN}✅ Ollama service is running.${NC}"
else
    echo -e "${BLUE}🔄 Starting Ollama service...${NC}"
    sudo systemctl start ollama || echo -e "${RED}⚠️ Could not start Ollama automatically. Please ensure it is running.${NC}"
fi

# Pull the default model
echo -e "${BLUE}📥 Pulling Qwen-VL model (this may take a while)...${NC}"
ollama pull qwen3-vl:4b-instruct-q4_K_M

echo -e "${GREEN}✨ Installation Complete!${NC}"
echo -e "${BLUE}--------------------------------------------------${NC}"
echo -e "To start the agent, run:"
echo -e "  ${GREEN}source venv/bin/activate${NC}"
echo -e "  ${GREEN}python3 main.py${NC}"
echo -e "${BLUE}--------------------------------------------------${NC}"
