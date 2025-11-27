#!/bin/bash
# Setup-Script für GNOME Keyboard Shortcut

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TRIGGER_SCRIPT="$SCRIPT_DIR/trigger-dictation.sh"

echo "🔧 GNOME Shortcut Setup für KI-Diktierung"
echo "=========================================="
echo ""

# Prüfe ob wir auf GNOME sind
if [ "$XDG_CURRENT_DESKTOP" != "GNOME" ]; then
    echo "⚠️  Warnung: Desktop ist nicht GNOME"
    echo "   Aktueller Desktop: $XDG_CURRENT_DESKTOP"
    echo ""
fi

echo "Erstelle Custom Shortcut via gsettings..."
echo ""

# Finde einen freien Slot für Custom Shortcuts
CUSTOM_SHORTCUTS=$(gsettings get org.gnome.settings-daemon.plugins.media-keys custom-keybindings)

# Wenn leer, initialisiere Array
if [ "$CUSTOM_SHORTCUTS" == "@as []" ] || [ -z "$CUSTOM_SHORTCUTS" ]; then
    NEW_PATH="/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/custom0/"
    gsettings set org.gnome.settings-daemon.plugins.media-keys custom-keybindings "['$NEW_PATH']"
else
    # Finde höchsten Index
    HIGHEST_INDEX=0
    for i in {0..99}; do
        if echo "$CUSTOM_SHORTCUTS" | grep -q "custom$i"; then
            HIGHEST_INDEX=$i
        fi
    done

    NEXT_INDEX=$((HIGHEST_INDEX + 1))
    NEW_PATH="/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/custom$NEXT_INDEX/"

    # Füge neuen Pfad hinzu
    UPDATED_SHORTCUTS=$(echo "$CUSTOM_SHORTCUTS" | sed "s/]/, '$NEW_PATH']/")
    gsettings set org.gnome.settings-daemon.plugins.media-keys custom-keybindings "$UPDATED_SHORTCUTS"
fi

# Setze Shortcut-Details
gsettings set org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:$NEW_PATH name 'KI-Diktierung'
gsettings set org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:$NEW_PATH command "$TRIGGER_SCRIPT"
gsettings set org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:$NEW_PATH binding '<Shift><Shift>space'

echo "✓ Shortcut erstellt!"
echo ""
echo "Name:    KI-Diktierung"
echo "Command: $TRIGGER_SCRIPT"
echo "Binding: Beide Shift + Space"
echo ""
echo "⚠️  WICHTIG: GNOME unterstützt '<Shift><Shift>space' möglicherweise nicht!"
echo ""
echo "Falls der Hotkey nicht funktioniert:"
echo "1. Öffne GNOME Einstellungen → Tastatur → Tastenkombinationen anzeigen und anpassen"
echo "2. Scrolle nach unten zu 'Eigene Tastenkombinationen'"
echo "3. Suche 'KI-Diktierung'"
echo "4. Klicke darauf und drücke MANUELL: Beide Shift-Tasten + Space"
echo ""
echo "Alternative Tastenkombination (falls beide Shift nicht geht):"
echo "  - Super+D"
echo "  - Ctrl+Alt+Space"
echo "  - Super+Space"
echo ""

read -p "Möchtest du die GNOME Einstellungen jetzt öffnen? [j/N] " -n 1 -r
echo
if [[ $REPLY =~ ^[Jj]$ ]]; then
    gnome-control-center keyboard &
    echo "✓ Einstellungen geöffnet - navigiere zu 'Tastenkombinationen'"
fi

echo ""
echo "Setup abgeschlossen!"
