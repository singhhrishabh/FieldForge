#!/usr/bin/env bash
# FieldForge — Start llama.cpp Server with Gemma 4 Multimodal
# Usage: ./start_server.sh
# chmod +x start_server.sh
set -euo pipefail

# ─── Paths (expand ~ explicitly) ──────────────────────────────
MODEL_PATH="${MODEL_PATH:-$HOME/models/gemma-4-E4B-it-Q4_K_M.gguf}"
MMPROJ_PATH="${MMPROJ_PATH:-$HOME/models/mmproj-BF16.gguf}"
PORT="${PORT:-8080}"
HOST="${HOST:-127.0.0.1}"
CTX_SIZE="${CTX_SIZE:-8192}"
GPU_LAYERS="${GPU_LAYERS:-99}"
LOG_FILE="/tmp/llama_server.log"
PID_FILE="/tmp/llama_server.pid"

GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'
YELLOW='\033[1;33m'; BOLD='\033[1m'; NC='\033[0m'

# ─── Find llama-server binary ─────────────────────────────────
find_server() {
    if command -v llama-server &>/dev/null; then echo "llama-server"; return; fi
    if [ -f "/opt/homebrew/bin/llama-server" ]; then echo "/opt/homebrew/bin/llama-server"; return; fi
    if [ -f "/usr/local/bin/llama-server" ]; then echo "/usr/local/bin/llama-server"; return; fi
    local SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    if [ -f "$SCRIPT_DIR/llama.cpp/build/bin/llama-server" ]; then
        echo "$SCRIPT_DIR/llama.cpp/build/bin/llama-server"; return
    fi
    echo ""
}

SERVER_BIN=$(find_server)
if [ -z "$SERVER_BIN" ]; then
    echo -e "${RED}✗ llama-server not found.${NC}"
    echo "  Install: brew install llama.cpp"
    exit 1
fi
echo -e "  Binary:  ${CYAN}$SERVER_BIN${NC}"

# ─── Check model files exist ──────────────────────────────────
if [ ! -f "$MODEL_PATH" ]; then
    echo -e "${RED}✗ Model not found: $MODEL_PATH${NC}"
    echo "  Download: huggingface-cli download unsloth/gemma-4-E4B-it-GGUF --include 'gemma-4-E4B-it-Q4_K_M.gguf' --local-dir ~/models"
    exit 1
fi

if [ ! -f "$MMPROJ_PATH" ]; then
    echo -e "${RED}✗ Vision model (mmproj) not found: $MMPROJ_PATH${NC}"
    echo "  Download: huggingface-cli download unsloth/gemma-4-E4B-it-GGUF --include 'mmproj-BF16.gguf' --local-dir ~/models"
    exit 1
fi

# ─── Check if already running ─────────────────────────────────
if curl -sf "http://$HOST:$PORT/health" &>/dev/null; then
    echo -e "${GREEN}${BOLD}✓ Server already running on port $PORT${NC}"
    exit 0
fi

# ─── Kill stale process if PID file exists ─────────────────────
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE" 2>/dev/null || true)
    if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
        echo -e "${YELLOW}  Stopping stale server (PID $OLD_PID)...${NC}"
        kill "$OLD_PID" 2>/dev/null || true
        sleep 2
    fi
    rm -f "$PID_FILE"
fi

# ─── Start server ─────────────────────────────────────────────
echo -e "${CYAN}${BOLD}Starting llama.cpp server...${NC}"
echo -e "  Model:   $(basename "$MODEL_PATH")"
echo -e "  Vision:  $(basename "$MMPROJ_PATH")"
echo -e "  Context: $CTX_SIZE tokens"
echo -e "  GPU:     $GPU_LAYERS layers"
echo -e "  Port:    $PORT"

nohup "$SERVER_BIN" \
    -m "$MODEL_PATH" \
    --mmproj "$MMPROJ_PATH" \
    --port "$PORT" \
    --host "$HOST" \
    -ngl "$GPU_LAYERS" \
    --ctx-size "$CTX_SIZE" \
    --temp 1.0 \
    --top-p 0.95 \
    --top-k 64 \
    --chat-template-kwargs '{"enable_thinking":false}' \
    > "$LOG_FILE" 2>&1 &

SERVER_PID=$!
echo "$SERVER_PID" > "$PID_FILE"
echo -e "  PID:     $SERVER_PID"
echo -e "  Log:     $LOG_FILE"

# ─── Wait for server to be ready ──────────────────────────────
echo -ne "  Waiting for server..."
for i in $(seq 1 60); do
    if curl -sf "http://$HOST:$PORT/health" &>/dev/null; then
        echo -e "\r  ${GREEN}✓ Server ready!${NC}                    "
        echo ""
        echo -e "${GREEN}${BOLD}╔═══════════════════════════════════════════════╗${NC}"
        echo -e "${GREEN}${BOLD}║  ✅ FIELDFORGE SERVER READY                  ║${NC}"
        echo -e "${GREEN}${BOLD}║  Model:    Gemma 4 E4B (multimodal)          ║${NC}"
        echo -e "${GREEN}${BOLD}║  Vision:   mmproj-BF16.gguf ✓               ║${NC}"
        echo -e "${GREEN}${BOLD}║  Endpoint: http://$HOST:$PORT              ║${NC}"
        echo -e "${GREEN}${BOLD}║  Network:  OFFLINE CAPABLE ✓                ║${NC}"
        echo -e "${GREEN}${BOLD}╚═══════════════════════════════════════════════╝${NC}"
        exit 0
    fi

    # Check if process died
    if ! kill -0 "$SERVER_PID" 2>/dev/null; then
        echo -e "\r  ${RED}✗ Server process died.${NC}                    "
        echo -e "  Check logs: ${CYAN}cat $LOG_FILE${NC}"
        tail -5 "$LOG_FILE" 2>/dev/null
        rm -f "$PID_FILE"
        exit 1
    fi

    echo -ne "."
    sleep 2
done

echo -e "\r  ${RED}✗ Server timed out after 120s.${NC}                    "
echo -e "  Check logs: ${CYAN}cat $LOG_FILE${NC}"
tail -10 "$LOG_FILE" 2>/dev/null
kill "$SERVER_PID" 2>/dev/null || true
rm -f "$PID_FILE"
exit 1
