#!/bin/bash
# Test-Script um den Hotkey manuell zu triggern

echo "🧪 KI-Diktierung Hotkey-Test"
echo "============================="
echo ""
echo "Dieser Test simuliert das Drücken von Shift + Strg + Leertaste"
echo ""

# Prüfe ob Daemon läuft
if ! pgrep -f "dictation-simple.py" > /dev/null; then
    echo "❌ Diktier-Daemon läuft NICHT!"
    echo ""
    echo "Bitte zuerst starten:"
    echo "  ~/.local/share/ai-dictation/start-dictation.sh"
    echo ""
    exit 1
fi

echo "✓ Diktier-Daemon läuft (PID: $(pgrep -f dictation-simple.py))"
echo ""

# Trigger 1: Aufnahme starten
echo "→ Trigger 1: Starte Aufnahme..."
touch /tmp/dictation-trigger-$USER
sleep 3

# Prüfe ob Overlay läuft
if pgrep -f "animated_overlay.py" > /dev/null; then
    echo "✓ Overlay läuft! Aufnahme aktiv."
else
    echo "❌ Overlay läuft NICHT. Prüfe Logs:"
    echo "  tail -20 /tmp/dictation-daemon.log"
    exit 1
fi

echo ""
echo "Warte 3 Sekunden..."
sleep 3
echo ""

# Trigger 2: Aufnahme stoppen
echo "→ Trigger 2: Stoppe Aufnahme..."
touch /tmp/dictation-trigger-$USER
sleep 3

# Prüfe ob Overlay gestoppt
if ! pgrep -f "animated_overlay.py" > /dev/null; then
    echo "✓ Overlay gestoppt! Aufnahme beendet."
else
    echo "⚠️  Overlay läuft noch..."
fi

echo ""
echo "✓ Test abgeschlossen!"
echo ""
echo "Prüfe die letzten Zeilen im Log:"
echo "----------------------------------------"
tail -15 /tmp/dictation-daemon.log
echo "----------------------------------------"
echo ""
echo "Falls alles funktioniert:"
echo "  Drücke Shift + Strg + Leertaste zum Diktieren!"
echo ""
