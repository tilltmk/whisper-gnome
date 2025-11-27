# KI-Diktierung - Verwendung (Vereinfachte Version)

## Funktionsweise

Das System besteht aus zwei Komponenten:

1. **dictation-simple.py** - Daemon der im Hintergrund läuft und auf Trigger wartet
2. **trigger-dictation.sh** - Script zum Auslösen der Diktierung

## Verwendung

### Methode 1: GNOME Tastenkürzel (Empfohlen)

1. Öffne **Einstellungen** → **Tastatur** → **Tastaturkürzel anzeigen und anpassen**
2. Scrolle nach unten zu **Benutzerdefinierte Tastenkombinationen**
3. Klicke auf **+** (Hinzufügen)
4. Trage ein:
   - **Name:** KI-Diktierung
   - **Befehl:** `~/.local/share/ai-dictation/trigger-dictation.sh`
   - **Tastenkombination:** Drücke `Strg+Shift+Space`

### Methode 2: Manuelles Triggern

Führe einfach das Script aus:
```bash
~/.local/share/ai-dictation/trigger-dictation.sh
```

## Feedback

Das System verwendet GNOME Notifications für Feedback:
- **"● Aufnahme läuft - Sprechen Sie jetzt"** - Aufnahme gestartet
- **"Transkribiere Audio..."** - Verarbeitung läuft
- **"Aufnahme abgebrochen"** - Wenn während Aufnahme erneut getriggert

## Audio-Feedback

Das System spielt kurze Sounds bei verschiedenen Aktionen:
- Aufnahme Start: Kurzer Beep
- Aufnahme Stop: Doppelter Beep
- Erfolg: Bestätigungston

## Logs Prüfen

```bash
# Daemon Status
tail -f /tmp/dictation-daemon.log

# Trigger Script Log
tail -f /tmp/trigger-script-debug.log
```

## Daemon neu starten

```bash
# Prozess beenden
pkill -f "dictation-simple.py"

# Trigger-Script ausführen (startet Daemon automatisch)
~/.local/share/ai-dictation/trigger-dictation.sh
```

## Technische Details

- **Whisper Modell:** medium (CPU-Modus)
- **Sprache:** Deutsch (automatische Erkennung)
- **Clipboard:** wl-copy/wl-paste (Wayland)
- **IPC:** File-based trigger (/tmp/dictation-state-core)
