#!/bin/bash
# Start Piper TTS Docker container (runs at localhost:5000)
# Run once before starting an exam.

set -e
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Starting Piper TTS"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if docker ps --format "{{.Names}}" | grep -q "^piper-tts$"; then
    echo -e "${GREEN}  ✅ Piper TTS already running${NC}"
else
    if docker ps -a --format "{{.Names}}" | grep -q "^piper-tts$"; then
        echo "  Starting existing piper-tts container…"
        docker start piper-tts > /dev/null
    else
        echo "  Creating piper-tts container…"
        # Build image if it doesn't exist
        if ! docker images --format "{{.Repository}}" | grep -q "^piper-tts$"; then
            echo "  Building Piper TTS image (one-time, takes ~1 min)…"
            docker build -t piper-tts /home/dropouts/curious-frame/piper_server
        fi
        docker run -d --name piper-tts --runtime nvidia --network host \
            --restart unless-stopped piper-tts
    fi
    echo "  Waiting for Piper TTS to be ready…"
    for i in $(seq 1 15); do
        if curl -s -X POST http://localhost:5000 \
               -H "Content-Type: application/json" \
               -d '{"text":"test"}' > /dev/null 2>&1; then
            echo -e "${GREEN}  ✅ Piper TTS ready at localhost:5000${NC}"
            break
        fi
        sleep 1
        if [ "$i" -eq 15 ]; then
            echo -e "${RED}  ❌ Piper TTS not responding after 15s — check: docker logs piper-tts${NC}"
        fi
    done
fi

echo ""
echo "  To stop: docker stop piper-tts"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
