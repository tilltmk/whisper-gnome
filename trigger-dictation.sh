#!/bin/bash
# Trigger-Script für Diktierung (wird vom GNOME-Shortcut aufgerufen)

TRIGGER_FILE="/tmp/dictation-trigger-$USER"

# Prüfe ob Daemon läuft, starte ihn falls nötig
if ! systemctl --user is-active --quiet ai-dictation.service; then
    systemctl --user start ai-dictation.service
    sleep 0.5
fi

# Toggle-Trigger: Touch Trigger-File
touch "$TRIGGER_FILE"

exit 0
