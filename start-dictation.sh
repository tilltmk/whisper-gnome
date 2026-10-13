#!/bin/bash
# Startet den Diktier-Daemon (Cohere Transcribe) - bevorzugt als systemd-Dienst.
# Hotkey kommt über einen GNOME-Shortcut (setup-gnome-shortcut.sh).

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "🎙️ KI-Diktierung mit Cohere Transcribe"
echo "======================================"
echo "Hotkey: Shift+Strg+Leertaste (GNOME-Shortcut)"
echo ""

SHORTCUT_BINDING=$(gsettings get org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/dictation/ binding 2>/dev/null)
if [ -n "$SHORTCUT_BINDING" ]; then
    echo "✓ GNOME Shortcut konfiguriert: $SHORTCUT_BINDING"
else
    echo "⚠️  GNOME Shortcut NICHT konfiguriert - setup-gnome-shortcut.sh ausführen"
fi
echo ""

if systemctl --user cat ai-dictation.service >/dev/null 2>&1; then
    systemctl --user start ai-dictation.service
    systemctl --user --no-pager --lines=0 status ai-dictation.service | head -3
    echo "Log: journalctl --user -u ai-dictation -f"
elif pgrep -f "dictation-simple.py" > /dev/null; then
    echo "⚠️  Diktier-Daemon läuft bereits (PID $(pgrep -f dictation-simple.py))"
else
    echo "→ Kein systemd-Dienst eingerichtet (siehe README) - starte direkt"
    python3 -u "$SCRIPT_DIR/dictation-simple.py" >> /tmp/dictation-daemon.log 2>&1 &
    echo "  PID: $!   Log: /tmp/dictation-daemon.log"
fi
