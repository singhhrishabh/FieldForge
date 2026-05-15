#!/usr/bin/env bash
# FieldForge — Start llama.cpp Server for Gemma 4
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODEL_PATH="${MODEL_PATH:-$HOME/models/gemma-4-E4B-it-Q4_K_M.gguf}"
CTX_LENGTH="${CTX_LENGTH:-8192}"
GPU_LAYERS="${GPU_LAYERS:-35}"
PORT="${PORT:-8080}"

GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

# Find llama-server binary
find_server() {
    if command -v llama-server &>/dev/null; then echo "llama-server"; return; fi
    if [ -f "/opt/homebrew/bin/llama-server" ]; then echo "/opt/homebrew/bin/llama-server"; return; fi
    if [ -f "/usr/local/bin/llama-server" ]; then echo "/usr/local/bin/llama-server"; return; fi
    if [ -f "$SCRIPT_DIR/llama.cpp/build/bin/llama-server" ]; then
        echo "$SCRIPT_DIR/llama.cpp/build/bin/llama-server"; return
    fi
    echo ""
}

SERVER_BIN=$(find_server)
if [ -z "$SERVER_BIN" ]; then
    echo -e "${RED}llama-server not found. Run ./setup.sh first.${NC}"; exit 1
fi

# Check if already running
if curl -s "http://localhost:$PORT/health" &>/dev/null; then
    echo -e "${GREEN}${BOLD}llama.cpp server already running on port $PORT${NC}"; exit 0
fi

# Check model exists
if [ ! -f "$MODEL_PATH" ]; then
    echo -e "${RED}Model not found: $MODEL_PATH${NC}"
    echo -e "Run ${CYAN}./setup.sh${NC} to download the model."; exit 1
fi

echo -e "${CYAN}${BOLD}Starting llama.cpp server...${NC}"
echo -e "  Model:   $(basename "$MODEL_PATH")"
echo -e "  Context: $CTX_LENGTH tokens"
echo -e "  GPU:     $GPU_LAYERS layers"
echo -e "  Port:    $PORT"

# Check for mmproj model
MMPROJ_PATH="$HOME/models/gemma-4-E4B-it-mmproj.gguf"
MMPROJ_ARG=""
if [ -f "$MMPROJ_PATH" ]; then
    echo -e "  Vision:  $(basename "$MMPROJ_PATH")"
    MMPROJ_ARG="--mmproj $MMPROJ_PATH"
fi

# Start server in background
"$SERVER_BIN" \
    -m "$MODEL_PATH" \
    $MMPROJ_ARG \
    -c "$CTX_LENGTH" \
    -ngl "$GPU_LAYERS" \
    --port "$PORT" \
    --host 0.0.0.0 \
    2>&1 | tee "$SCRIPT_DIR/output/llama_server.log" &

SERVER_PID=$!
echo "  PID:     $SERVER_PID"

# Wait for server to be ready (poll /health)
echo -ne "  Waiting for server..."
for i in $(seq 1 60); do
    if curl -s "http://localhost:$PORT/health" | grep -q "ok" 2>/dev/null; then
        echo -e "\r  ${GREEN}✓ Server ready!${NC}                    "
        echo ""
        echo -e "${GREEN}${BOLD}╔═══════════════════════════════════════════╗${NC}"
        echo -e "${GREEN}${BOLD}║  Gemma 4 E4B — ONLINE via llama.cpp      ║${NC}"
        echo -e "${GREEN}${BOLD}║  Endpoint: http://localhost:$PORT          ║${NC}"
        echo -e "${GREEN}${BOLD}║  Mode:     OFFLINE (no internet needed)   ║${NC}"
        echo -e "${GREEN}${BOLD}╚═══════════════════════════════════════════╝${NC}"
        exit 0
    fi
    echo -ne "."
    sleep 2
done

echo -e "\r  ${RED}✗ Server failed to start in 120s${NC}"
echo "  Check logs: $SCRIPT_DIR/output/llama_server.log"
kill $SERVER_PID 2>/dev/null
exit 1
