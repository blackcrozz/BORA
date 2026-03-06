#!/bin/bash
# ============================================================
#  BORA AI Video Editor — Auto Installer (macOS / Linux)
# ============================================================
#
#  USAGE:  Open Terminal, navigate to the project folder, and run:
#
#      chmod +x install.sh
#      ./install.sh
#
#  This script will:
#    1. Check if Python 3.10+ is installed
#    2. Install FFmpeg (if missing)
#    3. Create a virtual environment
#    4. Install all Python packages (Whisper, Argos Translate)
#    5. Download a default Whisper model
#    6. Verify everything works
#
# ============================================================

set -e  # Stop on any error

# --- Colors for pretty output ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
NC='\033[0m' # No Color

echo ""
echo -e "${PURPLE}╔══════════════════════════════════════════════════╗${NC}"
echo -e "${PURPLE}║                                                  ║${NC}"
echo -e "${PURPLE}║     ⚡ BORA AI Video Editor — Installer ⚡       ║${NC}"
echo -e "${PURPLE}║                                                  ║${NC}"
echo -e "${PURPLE}╚══════════════════════════════════════════════════╝${NC}"
echo ""

# Track what was installed
INSTALLED=()
WARNINGS=()

# ------------------------------------------------------------------
# STEP 1: Check Operating System
# ------------------------------------------------------------------
echo -e "${BLUE}[1/6]${NC} Detecting operating system..."

OS="unknown"
if [[ "$OSTYPE" == "darwin"* ]]; then
    OS="macos"
    echo -e "  ${GREEN}✓${NC} macOS detected"
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    OS="linux"
    echo -e "  ${GREEN}✓${NC} Linux detected"
else
    echo -e "  ${RED}✗${NC} Unsupported OS: $OSTYPE"
    echo "  This script supports macOS and Linux."
    echo "  For Windows, use install.bat instead."
    exit 1
fi

# ------------------------------------------------------------------
# STEP 2: Check / Install Python 3.10+
# ------------------------------------------------------------------
echo ""
echo -e "${BLUE}[2/6]${NC} Checking Python..."

PYTHON_CMD=""

# Try python3 first, then python
for cmd in python3 python; do
    if command -v $cmd &> /dev/null; then
        version=$($cmd --version 2>&1 | grep -oE '[0-9]+\.[0-9]+')
        major=$(echo $version | cut -d. -f1)
        minor=$(echo $version | cut -d. -f2)
        if [ "$major" -ge 3 ] && [ "$minor" -ge 10 ]; then
            PYTHON_CMD=$cmd
            echo -e "  ${GREEN}✓${NC} Found $cmd ($($cmd --version))"
            break
        fi
    fi
done

if [ -z "$PYTHON_CMD" ]; then
    echo -e "  ${RED}✗${NC} Python 3.10 or higher is required but not found."
    echo ""
    echo "  Please install Python first:"
    if [ "$OS" == "macos" ]; then
        echo "    → Download from: https://www.python.org/downloads/"
        echo "    → Or run: brew install python@3.12"
    else
        echo "    → sudo apt update && sudo apt install python3 python3-pip python3-venv"
    fi
    echo ""
    echo "  After installing Python, run this script again."
    exit 1
fi

# Check pip
if ! $PYTHON_CMD -m pip --version &> /dev/null; then
    echo -e "  ${YELLOW}!${NC} pip not found, installing..."
    if [ "$OS" == "linux" ]; then
        sudo apt install -y python3-pip python3-venv
    else
        $PYTHON_CMD -m ensurepip --upgrade
    fi
fi

# ------------------------------------------------------------------
# STEP 3: Check / Install FFmpeg
# ------------------------------------------------------------------
echo ""
echo -e "${BLUE}[3/6]${NC} Checking FFmpeg..."

if command -v ffmpeg &> /dev/null; then
    FFMPEG_VERSION=$(ffmpeg -version 2>&1 | head -n1)
    echo -e "  ${GREEN}✓${NC} FFmpeg is already installed ($FFMPEG_VERSION)"
else
    echo -e "  ${YELLOW}!${NC} FFmpeg not found. Installing..."

    if [ "$OS" == "macos" ]; then
        # Check for Homebrew
        if command -v brew &> /dev/null; then
            echo "  Installing via Homebrew..."
            brew install ffmpeg
            INSTALLED+=("FFmpeg (via Homebrew)")
        else
            echo -e "  ${YELLOW}!${NC} Homebrew not found. Installing Homebrew first..."
            /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
            
            # Add Homebrew to PATH for Apple Silicon
            if [[ $(uname -m) == "arm64" ]]; then
                eval "$(/opt/homebrew/bin/brew shellenv)"
            fi
            
            brew install ffmpeg
            INSTALLED+=("Homebrew" "FFmpeg")
        fi
    elif [ "$OS" == "linux" ]; then
        echo "  Installing via apt..."
        sudo apt update
        sudo apt install -y ffmpeg
        INSTALLED+=("FFmpeg (via apt)")
    fi

    # Verify
    if command -v ffmpeg &> /dev/null; then
        echo -e "  ${GREEN}✓${NC} FFmpeg installed successfully"
    else
        echo -e "  ${RED}✗${NC} FFmpeg installation failed."
        WARNINGS+=("FFmpeg could not be installed automatically. Please install it manually.")
    fi
fi

# ------------------------------------------------------------------
# STEP 4: Create Virtual Environment & Install Python Packages
# ------------------------------------------------------------------
echo ""
echo -e "${BLUE}[4/6]${NC} Setting up Python virtual environment..."

VENV_DIR="venv"

if [ -d "$VENV_DIR" ]; then
    echo -e "  ${GREEN}✓${NC} Virtual environment already exists"
else
    $PYTHON_CMD -m venv $VENV_DIR
    echo -e "  ${GREEN}✓${NC} Virtual environment created at ./$VENV_DIR/"
    INSTALLED+=("Python virtual environment")
fi

# Activate virtual environment
source $VENV_DIR/bin/activate

echo ""
echo -e "${BLUE}[5/6]${NC} Installing Python packages (this may take a few minutes)..."
echo ""

# Upgrade pip first
pip install --upgrade pip > /dev/null 2>&1

# Install packages one by one for better error reporting
PACKAGES=(
    "openai-whisper"
    "argostranslate"
)

for pkg in "${PACKAGES[@]}"; do
    echo -e "  Installing ${YELLOW}$pkg${NC}..."
    if pip install "$pkg" 2>&1 | tail -1; then
        echo -e "  ${GREEN}✓${NC} $pkg installed"
        INSTALLED+=("$pkg")
    else
        echo -e "  ${RED}✗${NC} Failed to install $pkg"
        WARNINGS+=("$pkg failed to install. Try: pip install $pkg")
    fi
    echo ""
done

# ------------------------------------------------------------------
# STEP 5: Download default Whisper model
# ------------------------------------------------------------------
echo -e "${BLUE}[6/6]${NC} Downloading Whisper model (medium)..."
echo "  This is a one-time ~1.5 GB download..."
echo ""

$PYTHON_CMD -c "
import whisper
print('  Downloading model...')
model = whisper.load_model('medium')
print('  Model loaded and cached successfully!')
" 2>&1

if [ $? -eq 0 ]; then
    echo -e "  ${GREEN}✓${NC} Whisper medium model ready"
    INSTALLED+=("Whisper medium model (~1.5 GB)")
else
    echo -e "  ${YELLOW}!${NC} Model download skipped (will download on first run)"
    WARNINGS+=("Whisper model will download automatically on first use")
fi

# ------------------------------------------------------------------
# Create a convenient run script
# ------------------------------------------------------------------
cat > run.sh << 'RUNSCRIPT'
#!/bin/bash
# Quick launcher for Bora AI Video Editor
# Usage: ./run.sh input_video.mp4 [options]
#
# Examples:
#   ./run.sh my_video.mp4
#   ./run.sh my_video.mp4 --translate es
#   ./run.sh my_video.mp4 --style tiktok --word-highlight
#   ./run.sh my_video.mp4 --clip --translate fr

source venv/bin/activate

if [ $# -eq 0 ]; then
    echo ""
    echo "⚡ BORA AI Video Editor"
    echo "========================"
    echo ""
    echo "Usage: ./run.sh <video_file> [options]"
    echo ""
    echo "Examples:"
    echo "  ./run.sh video.mp4                              # Basic captioning"
    echo "  ./run.sh video.mp4 --style tiktok               # TikTok style"
    echo "  ./run.sh video.mp4 --word-highlight              # Word-by-word highlight"
    echo "  ./run.sh video.mp4 --translate es                # Translate to Spanish"
    echo "  ./run.sh video.mp4 --clip                        # Auto-generate clips"
    echo "  ./run.sh video.mp4 --style tiktok --word-highlight --translate es --clip"
    echo ""
    echo "Caption styles: tiktok | youtube | reels | minimal | srt"
    echo ""
    echo "Languages: es (Spanish), fr (French), de (German), ja (Japanese),"
    echo "           zh (Chinese), ko (Korean), pt (Portuguese), it (Italian),"
    echo "           ar (Arabic), hi (Hindi), and 20+ more"
    echo ""
    exit 0
fi

VIDEO="$1"
shift

if [ ! -f "$VIDEO" ]; then
    echo "Error: File not found: $VIDEO"
    exit 1
fi

python main.py --input "$VIDEO" "$@"
RUNSCRIPT

chmod +x run.sh

# ------------------------------------------------------------------
# SUMMARY
# ------------------------------------------------------------------
echo ""
echo -e "${PURPLE}╔══════════════════════════════════════════════════╗${NC}"
echo -e "${PURPLE}║          ✅ Installation Complete!               ║${NC}"
echo -e "${PURPLE}╚══════════════════════════════════════════════════╝${NC}"
echo ""

if [ ${#INSTALLED[@]} -gt 0 ]; then
    echo -e "${GREEN}Installed:${NC}"
    for item in "${INSTALLED[@]}"; do
        echo -e "  ✓ $item"
    done
    echo ""
fi

if [ ${#WARNINGS[@]} -gt 0 ]; then
    echo -e "${YELLOW}Warnings:${NC}"
    for item in "${WARNINGS[@]}"; do
        echo -e "  ⚠ $item"
    done
    echo ""
fi

echo -e "${GREEN}How to use Bora:${NC}"
echo ""
echo "  1. Put your video file in this folder"
echo ""
echo "  2. Run one of these commands:"
echo ""
echo -e "     ${YELLOW}./run.sh video.mp4${NC}"
echo "       → Basic: transcribe + TikTok-style captions"
echo ""
echo -e "     ${YELLOW}./run.sh video.mp4 --word-highlight${NC}"
echo "       → Word-by-word highlighting effect"
echo ""
echo -e "     ${YELLOW}./run.sh video.mp4 --translate es${NC}"
echo "       → Add Spanish translation"
echo ""
echo -e "     ${YELLOW}./run.sh video.mp4 --clip${NC}"
echo "       → Auto-generate short clips"
echo ""
echo -e "     ${YELLOW}./run.sh video.mp4 --style tiktok --word-highlight --translate es --clip${NC}"
echo "       → Full pipeline: styled captions + translate + clips"
echo ""
echo "  3. Find your results in the ./output/ folder"
echo ""
echo -e "  Run ${YELLOW}./run.sh${NC} without arguments to see all options."
echo ""
