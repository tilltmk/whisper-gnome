#!/bin/bash
# Prüft die Installation der KI-Diktierung (Cohere Transcribe)

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; NC='\033[0m'
PY="${PYTHON:-python3}"
MODELL="$HOME/.cache/cohere-transcribe"
fehler=0

ok()     { echo -e "${GREEN}OK${NC}${1:+ ($1)}"; }
fehlt()  { echo -e "${RED}FEHLT${NC}${1:+ ($1)}"; fehler=1; }
hinweis(){ echo -e "${YELLOW}$1${NC}"; }

echo "======================================"
echo " KI-Diktierung - Installationstest"
echo "======================================"

echo -n "Python ............................ "
V=$($PY --version 2>&1) && ok "$V" || fehlt

for m in numpy sounddevice transformers librosa soundfile; do
    printf "%-35s " "Paket $m"
    $PY -c "import $m" 2>/dev/null && ok || fehlt "pip install --user -r requirements.txt"
done

echo -n "PyTorch mit CUDA .................. "
C=$($PY -c "import torch; print(torch.cuda.is_available(), torch.version.cuda)" 2>/dev/null)
case "$C" in True*) ok "CUDA ${C#True }";; False*) hinweis "nur CPU - Diktierung sehr langsam";; *) fehlt;; esac

echo -n "bfloat16 auf der GPU .............. "
B=$($PY -c "import torch; print(torch.cuda.is_available() and torch.cuda.is_bf16_supported())" 2>/dev/null)
[ "$B" = "True" ] && ok || hinweis "nicht verfügbar"

echo -n "Cohere-Transcribe-Modell .......... "
[ -f "$MODELL/model.safetensors" ] && [ -f "$MODELL/modeling_cohere_asr.py" ] && ok "$MODELL" || fehlt "siehe README"

echo -n "wl-copy (Zwischenablage) .......... "
command -v wl-copy >/dev/null && ok || fehlt "Paket wl-clipboard"

echo -n "systemd-Dienst .................... "
if systemctl --user cat ai-dictation.service >/dev/null 2>&1; then
    ok "$(systemctl --user is-active ai-dictation.service)"
else
    hinweis "nicht eingerichtet (siehe README)"
fi

echo -n "Transkriptions-Socket ............. "
S="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/ai-dictation-asr.sock"
[ -S "$S" ] && ok "$S" || hinweis "nicht vorhanden (Daemon läuft nicht?)"

echo -n "GNOME-Shortcut .................... "
gsettings get org.gnome.settings-daemon.plugins.media-keys custom-keybindings 2>/dev/null | grep -q dictation && ok || hinweis "setup-gnome-shortcut.sh ausführen"

echo ""
[ $fehler -eq 0 ] && echo -e "${GREEN}Installation vollständig.${NC}" || echo -e "${RED}Es fehlt etwas - siehe oben.${NC}"
exit $fehler
