#!/bin/bash
# Build script for Email Classifier
# Handles slow networks and provides build options

set -e

echo "╔════════════════════════════════════════════════════════════╗"
echo "║        Email Classifier - Docker Build Script             ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""
echo "This script will build the email classifier using PyTorch CPU-only"
echo "to minimize download size (~140MB vs 670MB for CUDA version)"
echo ""

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Error: Docker is not running"
    exit 1
fi

# Ask user which Dockerfile to use
echo "Choose build method:"
echo "  1) Standard (recommended) - Single pip install"
echo "  2) Layered - Better for slow networks, installs packages separately"
echo ""
read -p "Enter choice [1]: " choice
choice=${choice:-1}

if [ "$choice" = "2" ]; then
    DOCKERFILE="Dockerfile.layered"
    echo "Using layered build approach..."
else
    DOCKERFILE="Dockerfile"
    echo "Using standard build approach..."
fi

echo ""
echo "Building image with $DOCKERFILE..."
echo ""

# Build with progress
docker build -f "$DOCKERFILE" -t email-classifier . 

if [ $? -eq 0 ]; then
    echo ""
    echo "╔════════════════════════════════════════════════════════════╗"
    echo "║                   ✅ Build Successful!                     ║"
    echo "╚════════════════════════════════════════════════════════════╝"
    echo ""
    echo "Image size:"
    docker images email-classifier --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}"
    echo ""
    echo "Next steps:"
    echo "  1. Configure .env file with your IMAP credentials"
    echo "  2. Run: docker-compose up -d"
    echo "  3. Access dashboard at http://localhost:8080"
    echo ""
else
    echo ""
    echo "╔════════════════════════════════════════════════════════════╗"
    echo "║                   ❌ Build Failed                          ║"
    echo "╚════════════════════════════════════════════════════════════╝"
    echo ""
    echo "Troubleshooting tips:"
    echo "  1. Check your internet connection"
    echo "  2. Try the layered build: ./build.sh and choose option 2"
    echo "  3. Increase Docker timeout in Docker Desktop settings"
    echo "  4. If behind a proxy, configure Docker proxy settings"
    echo ""
    exit 1
fi
