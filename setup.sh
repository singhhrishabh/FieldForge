#!/usr/bin/env bash
# FieldForge — Full Environment Setup
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODEL_DIR="$SCRIPT_DIR/models"
LLAMA_DIR="$SCRIPT_DIR/llama.cpp"
MODEL_DIR="$HOME/models"
MODEL_NAME="gemma-4-E4B-it-Q4_K_M.gguf"
MMPROJ_NAME="gemma-4-E4B-it-mmproj.gguf"

log_step() { echo -e "\n${BLUE}${BOLD}[STEP]${NC} $1"; }
log_ok()   { echo -e "  ${GREEN}✓${NC} $1"; }
log_warn() { echo -e "  ${YELLOW}⚠${NC} $1"; }
log_err()  { echo -e "  ${RED}✗${NC} $1"; }
log_info() { echo -e "  ${CYAN}→${NC} $1"; }

detect_os() {
    case "$(uname -s)" in
        Linux*)  echo "linux";;
        Darwin*) echo "macos";;
        *)       echo "unknown";;
    esac
}

install_python_deps() {
    log_step "Installing Python dependencies..."
    if ! command -v python3 &>/dev/null; then
        log_err "Python 3 not found. Please install Python 3.11+."; exit 1
    fi
    log_info "Python version: $(python3 --version)"
    pip3 install -r "$SCRIPT_DIR/requirements.txt" --quiet 2>/dev/null
    log_ok "Python packages installed"
}

install_gcc_arm() {
    log_step "Checking ARM cross-compiler..."
    if command -v arm-none-eabi-gcc &>/dev/null; then
        log_ok "Already installed: $(arm-none-eabi-gcc --version | head -1)"; return 0
    fi
    local OS=$(detect_os)
    case "$OS" in
        macos)
            log_info "Installing via Homebrew..."
            brew install --cask gcc-arm-embedded 2>/dev/null || brew install arm-none-eabi-gcc 2>/dev/null || {
                log_warn "Auto-install failed. Download from: https://developer.arm.com/downloads/-/gnu-rm"
            };;
        linux)
            if command -v apt-get &>/dev/null; then
                sudo apt-get update -qq && sudo apt-get install -y -qq gcc-arm-none-eabi binutils-arm-none-eabi libnewlib-arm-none-eabi
            elif command -v pkg &>/dev/null; then
                log_warn "On Termux, ARM GCC may need manual setup."
            fi;;
    esac
    command -v arm-none-eabi-gcc &>/dev/null && log_ok "ARM GCC installed" || log_warn "ARM GCC not found in PATH"
}

install_llama_cpp() {
    log_step "Setting up llama.cpp..."
    if command -v llama-server &>/dev/null || [ -f "/opt/homebrew/bin/llama-server" ] || [ -f "/usr/local/bin/llama-server" ]; then
        log_ok "llama-server already installed"; return 0
    fi
    if [ -f "$LLAMA_DIR/build/bin/llama-server" ]; then
        log_ok "llama.cpp already built"; return 0
    fi
    local OS=$(detect_os)
    if [ "$OS" = "macos" ] && command -v brew &>/dev/null; then
        log_info "Installing via Homebrew..."
        brew install llama.cpp 2>/dev/null && { log_ok "Installed via Homebrew"; return 0; }
    fi
    log_info "Building from source..."
    [ ! -d "$LLAMA_DIR" ] && git clone --depth 1 https://github.com/ggerganov/llama.cpp "$LLAMA_DIR"
    cd "$LLAMA_DIR" && mkdir -p build && cd build
    if [ "$OS" = "macos" ]; then cmake .. -DGGML_METAL=ON; else cmake ..; fi
    cmake --build . --config Release -j$(nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo 4)
    [ -f "$LLAMA_DIR/build/bin/llama-server" ] && log_ok "Built successfully" || log_err "Build failed"
    cd "$SCRIPT_DIR"
}

download_model() {
    log_step "Checking Gemma 4 E4B models..."
    mkdir -p "$MODEL_DIR"
    
    # Download main model
    if [ -f "$MODEL_DIR/$MODEL_NAME" ]; then
        log_ok "Main model present: $(du -h "$MODEL_DIR/$MODEL_NAME" | cut -f1)"
    else
        log_info "Downloading Gemma 4 E4B Q4_K_M..."
        local HF_URL="https://huggingface.co/unsloth/gemma-4-E4B-it-GGUF/resolve/main/$MODEL_NAME"
        if command -v huggingface-cli &>/dev/null; then
            huggingface-cli download "unsloth/gemma-4-E4B-it-GGUF" "$MODEL_NAME" --local-dir "$MODEL_DIR"
        elif command -v curl &>/dev/null; then
            curl -L -C - --progress-bar -o "$MODEL_DIR/$MODEL_NAME" "$HF_URL"
        elif command -v wget &>/dev/null; then
            wget -c --progress=bar:force -O "$MODEL_DIR/$MODEL_NAME" "$HF_URL"
        else
            log_err "No download tool found. Download manually: $HF_URL"; return 1
        fi
        [ -f "$MODEL_DIR/$MODEL_NAME" ] && log_ok "Main model downloaded" || log_err "Main model download failed"
    fi

    # Download mmproj model
    if [ -f "$MODEL_DIR/$MMPROJ_NAME" ]; then
        log_ok "Vision model present: $(du -h "$MODEL_DIR/$MMPROJ_NAME" | cut -f1)"
    else
        log_info "Downloading Gemma 4 E4B Vision Adapter (mmproj)..."
        local MMPROJ_URL="https://huggingface.co/unsloth/gemma-4-E4B-it-GGUF/resolve/main/$MMPROJ_NAME"
        if command -v huggingface-cli &>/dev/null; then
            huggingface-cli download "unsloth/gemma-4-E4B-it-GGUF" "$MMPROJ_NAME" --local-dir "$MODEL_DIR"
        elif command -v curl &>/dev/null; then
            curl -L -C - --progress-bar -o "$MODEL_DIR/$MMPROJ_NAME" "$MMPROJ_URL"
        elif command -v wget &>/dev/null; then
            wget -c --progress=bar:force -O "$MODEL_DIR/$MMPROJ_NAME" "$MMPROJ_URL"
        fi
        [ -f "$MODEL_DIR/$MMPROJ_NAME" ] && log_ok "Vision model downloaded" || log_err "Vision model download failed"
    fi
}

install_qemu() {
    log_step "Checking QEMU ARM simulator..."
    if command -v qemu-system-arm &>/dev/null; then
        log_ok "Already installed: $(qemu-system-arm --version | head -1)"; return 0
    fi
    local OS=$(detect_os)
    case "$OS" in
        macos) brew install qemu 2>/dev/null;;
        linux) command -v apt-get &>/dev/null && sudo apt-get install -y -qq qemu-system-arm;;
    esac
    command -v qemu-system-arm &>/dev/null && log_ok "QEMU installed" || log_warn "QEMU not installed (simulator will be skipped)"
}

verify_setup() {
    log_step "Final verification..."
    python3 -c "import click, rich, pydantic, cv2, PIL, numpy" 2>/dev/null && log_ok "Python packages OK" || log_warn "Some packages missing"
    command -v arm-none-eabi-gcc &>/dev/null || [ -f "/opt/homebrew/bin/arm-none-eabi-gcc" ] && log_ok "ARM GCC OK" || log_warn "ARM GCC missing"
    (command -v llama-server &>/dev/null || [ -f "/opt/homebrew/bin/llama-server" ] || [ -f "/usr/local/bin/llama-server" ] || [ -f "$LLAMA_DIR/build/bin/llama-server" ]) && log_ok "llama.cpp OK" || log_warn "llama.cpp missing"
    [ -f "$MODEL_DIR/$MODEL_NAME" ] && log_ok "Gemma 4 model OK" || log_warn "Model missing"
    command -v qemu-system-arm &>/dev/null && log_ok "QEMU OK" || log_warn "QEMU missing"
    echo -e "\n${GREEN}${BOLD}Setup complete!${NC} Run ${CYAN}./start_server.sh${NC} then ${CYAN}python -m ui.cli demo${NC}"
}

echo -e "${CYAN}${BOLD}FieldForge — Environment Setup${NC}"
mkdir -p "$SCRIPT_DIR"/{output,models,demo/sample_outputs}
install_python_deps
install_gcc_arm
install_llama_cpp
download_model
install_qemu
verify_setup
