# Use Ubuntu 24.04 as base
FROM ubuntu:24.04

# Avoid interactive prompts during apt
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Install system dependencies
# Added build-essential and libasound2-dev for python package compilation and audio support
RUN apt-get update && apt-get install -y \
    python3.12 \
    python3.12-venv \
    python3-pip \
    python3-dev \
    build-essential \
    portaudio19-dev \
    libasound2-dev \
    ffmpeg \
    network-manager \
    curl \
    git \
    libportaudio2 \
    espeak-ng \
    && rm -rf /var/lib/apt/lists/*

# Install Ollama inside the container
RUN curl -fsSL https://ollama.com/install.sh | sh

# Create app directory
WORKDIR /app

# Copy requirements first for better layer caching
COPY requirements.txt .

# Create virtual env and install Python deps
RUN python3 -m venv /app/venv \
    && /app/venv/bin/pip install --upgrade pip \
    && /app/venv/bin/pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

# Pre-pull model (optional, but requested in original file)
RUN ollama serve & sleep 5 && ollama pull qwen2:7b-instruct-q4_K_M && pkill ollama

# Expose Ollama port
EXPOSE 11434

# Use the virtual environment by default
ENV PATH="/app/venv/bin:$PATH"

# ENTRYPOINT: run main.py
ENTRYPOINT ["python3", "main.py"]