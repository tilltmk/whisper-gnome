#!/bin/bash
# Test-Script für KI-Diktierung Installation

echo "======================================"
echo " KI-Diktierung - Installationstest"
echo "======================================"
echo ""

# Farben
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test 1: Virtual Environment
echo -n "Test 1: Virtual Environment... "
if [ -d "$HOME/.local/share/ai-dictation/venv" ]; then
    echo -e "${GREEN}OK${NC}"
else
    echo -e "${RED}FEHLT${NC}"
    exit 1
fi

# Test 2: Python 3.13
echo -n "Test 2: Python 3.13... "
PYTHON_VERSION=$($HOME/.local/share/ai-dictation/venv/bin/python --version 2>&1)
if [[ $PYTHON_VERSION == *"3.13"* ]]; then
    echo -e "${GREEN}OK${NC} ($PYTHON_VERSION)"
else
    echo -e "${RED}FEHLER${NC} ($PYTHON_VERSION)"
fi

# Test 3: Faster-Whisper installiert
echo -n "Test 3: Faster-Whisper... "
if $HOME/.local/share/ai-dictation/venv/bin/python -c "import faster_whisper" 2>/dev/null; then
    echo -e "${GREEN}OK${NC}"
else
    echo -e "${RED}FEHLT${NC}"
    exit 1
fi

# Test 4: PyTorch + CUDA
echo -n "Test 4: PyTorch mit CUDA... "
CUDA_AVAILABLE=$($HOME/.local/share/ai-dictation/venv/bin/python -c "import torch; print(torch.cuda.is_available())" 2>/dev/null)
if [[ $CUDA_AVAILABLE == "True" ]]; then
    CUDA_VERSION=$($HOME/.local/share/ai-dictation/venv/bin/python -c "import torch; print(torch.version.cuda)" 2>/dev/null)
    echo -e "${GREEN}OK${NC} (CUDA $CUDA_VERSION)"
else
    echo -e "${YELLOW}CPU-Modus${NC} (GPU nicht verfügbar)"
fi

# Test 5: sounddevice
echo -n "Test 5: Audio-Aufnahme (sounddevice)... "
if $HOME/.local/share/ai-dictation/venv/bin/python -c "import sounddevice" 2>/dev/null; then
    echo -e "${GREEN}OK${NC}"
else
    echo -e "${RED}FEHLT${NC}"
fi

# Test 6: pynput
echo -n "Test 6: Tastatur-Events (pynput)... "
if $HOME/.local/share/ai-dictation/venv/bin/python -c "import pynput" 2>/dev/null; then
    echo -e "${GREEN}OK${NC}"
else
    echo -e "${RED}FEHLT${NC}"
fi

# Test 7: xdotool
echo -n "Test 7: Text-Eingabe (xdotool)... "
if command -v xdotool &> /dev/null; then
    echo -e "${GREEN}OK${NC}"
else
    echo -e "${RED}FEHLT${NC}"
fi

# Test 8: Autostart konfiguriert
echo -n "Test 8: Autostart-Eintrag... "
if [ -f "$HOME/.config/autostart/ai-dictation.desktop" ]; then
    echo -e "${GREEN}OK${NC}"
else
    echo -e "${YELLOW}NICHT KONFIGURIERT${NC}"
fi

# Test 9: Scripts ausführbar
echo -n "Test 9: Scripts ausführbar... "
if [ -x "$HOME/.local/share/ai-dictation/start-dictation.sh" ] && [ -x "$HOME/.local/share/ai-dictation/dictation-simple.py" ]; then
    echo -e "${GREEN}OK${NC}"
else
    echo -e "${RED}FEHLER${NC}"
fi

echo ""
echo "======================================"
echo " Zusammenfassung"
echo "======================================"
echo ""
echo "Installation: ${GREEN}Erfolgreich${NC}"
echo ""
echo "Zum Starten:"
echo "  ~/.local/share/ai-dictation/start-dictation.sh"
echo ""
echo "Hotkey: Beide Shift-Tasten + Space"
echo ""
echo "Dokumentation:"
echo "  ~/.local/share/ai-dictation/README.md"
echo ""
