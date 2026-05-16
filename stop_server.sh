#!/usr/bin/env bash
# FieldForge — Stop llama.cpp Server
# Usage: ./stop_server.sh
# chmod +x stop_server.sh
set -euo pipefail

PID_FILE="/tmp/llama_server.pid"
GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; NC='\033[0m'

if [ ! -f "$PID_FILE" ]; then
    echo -e "${YELLOW}No PID file found at $PID_FILE${NC}"
    # Try to find and kill any running llama-server
    PIDS=$(pgrep -f "llama-server" 2>/dev/null || true)
    if [ -n "$PIDS" ]; then
        echo -e "${YELLOW}Found running llama-server processes: $PIDS${NC}"
        kill $PIDS 2>/dev/null || true
        echo -e "${GREEN}✓ Killed llama-server processes${NC}"
    else
        echo -e "${GREEN}No llama-server processes running.${NC}"
    fi
    exit 0
fi

PID=$(cat "$PID_FILE")
if kill -0 "$PID" 2>/dev/null; then
    echo -e "Stopping llama-server (PID $PID)..."
    kill "$PID" 2>/dev/null
    sleep 2
    # Force kill if still running
    if kill -0 "$PID" 2>/dev/null; then
        kill -9 "$PID" 2>/dev/null || true
        sleep 1
    fi
    echo -e "${GREEN}✓ Server stopped.${NC}"
else
    echo -e "${YELLOW}Server (PID $PID) was not running.${NC}"
fi

rm -f "$PID_FILE"
