#!/bin/bash
set -e

# Build script for hermes-agent and hermes-web-ui
# This script builds the base image first, then the web-ui on top of it

IMAGE_NAME=${1:-hermes-agent}
WEB_UI_IMAGE_NAME=${2:-hermes-web-ui}

echo "=== Building hermes-agent base image ==="
docker build -f Dockerfile -t ${IMAGE_NAME}:latest .

if [ -d "../hermes-web-ui" ]; then
    echo ""
    echo "=== Building hermes-web-ui image on top of ${IMAGE_NAME}:latest ==="
    cd ../hermes-web-ui
    docker build -f Dockerfile --build-arg BASE_IMAGE=${IMAGE_NAME}:latest -t ${WEB_UI_IMAGE_NAME}:latest .
    echo ""
    echo "=== Build complete ==="
    echo "  hermes-agent:  docker run -it ${IMAGE_NAME}:latest"
    echo "  hermes-web-ui: docker run -p 6060:6060 -it ${WEB_UI_IMAGE_NAME}:latest"
else
    echo "hermes-web-ui directory not found, skipping web-ui build"
fi

echo ""
echo "=== Done ==="