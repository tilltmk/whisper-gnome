#!/bin/bash
# Start-Script für KI-Diktierung mit Faster-Whisper Large-v3
# Startet Diktier-Daemon (Hotkey via GNOME Shortcut)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PYTHON="$SCRIPT_DIR/venv/bin/python3"

echo "🎙️ KI-Diktierung mit Faster-Whisper Large-v3"
echo "=============================================="
echo ""
echo "Modell: large-v3 (beste Qualität für Deutsch)"
echo "Hotkey: Shift+Strg+Leertaste"
echo "GPU: CUDA (RTX 4060)"
echo "Overlay: Animierte lila Wellen"
echo ""

# Prüfe GNOME Shortcut
SHORTCUT_BINDING=$(gsettings get org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/dictation/ binding 2>/dev/null)
if [ -n "$SHORTCUT_BINDING" ]; then
    echo "✓ GNOME Shortcut konfiguriert: $SHORTCUT_BINDING"
else
    echo "⚠️  GNOME Shortcut NICHT konfiguriert!"
    echo "  Bitte setup-gnome-shortcut.sh ausführen"
fi

echo ""
echo "Starte Daemon..."
echo ""

# Prüfe ob bereits läuft
if pgrep -f "dictation-simple.py" > /dev/null; then
    echo "⚠️  Diktier-Daemon läuft bereits"
    echo "  PID: $(pgrep -f dictation-simple.py)"
else
    # Starte Diktier-Daemon im Hintergrund
    echo "→ Starte Diktier-Daemon..."
    "$VENV_PYTHON" "$SCRIPT_DIR/dictation-simple.py" >> /tmp/dictation-daemon.log 2>&1 &
    DAEMON_PID=$!
    echo "  PID: $DAEMON_PID"
    sleep 2
fi

echo ""
echo "✓ Bereit!"
echo ""
echo "Zum Diktieren: Shift+Strg+Leertaste drücken"
echo "Zum Stoppen: Shift+Strg+Leertaste nochmal drücken"
echo "Zum Beenden: pkill -f dictation-simple.py"
echo ""
echo "Logs anzeigen: tail -f /tmp/dictation-daemon.log"
echo ""
