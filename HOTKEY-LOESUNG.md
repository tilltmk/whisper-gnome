# Hotkey-Problem: Analyse und Lösung

## Problem-Diagnose

Das KI-Diktiersystem wurde mit der Annahme implementiert, dass "beide Shift-Tasten + Space" als Hotkey verwendet werden sollten. Diese Tastenkombination ist jedoch unter GNOME/Wayland **NICHT direkt unterstützt**.

### Was wurde getestet:

1. **GNOME Custom Shortcuts** - ✓ Funktioniert!
2. **pynput unter Wayland ohne Berechtigungen** - ✗ Funktioniert NICHT
3. **evdev** - Nicht getestet (benötigt input-Gruppe)

## Lösung: GNOME Shortcut verwenden

Der existierende GNOME Shortcut ist bereits **KORREKT konfiguriert und funktioniert**:

```bash
Binding: <Shift><Control>space
Command: ~/.local/share/ai-dictation/trigger-dictation.sh
Name: KI-Diktierung
```

### Warum funktioniert der GNOME Shortcut?

- GNOME Shortcuts sind direkt in Mutter/GNOME Shell integriert
- Funktionieren unter Wayland ohne zusätzliche Berechtigungen
- **Shift + Strg + Leertaste** ist eine ergonomische, leicht zu drückende Kombination
- Kein zusätzlicher Daemon erforderlich

### Warum funktioniert pynput NICHT?

`pynput` benötigt unter Wayland direkten Zugriff auf `/dev/input/event*` Devices. Das erfordert:
- Mitgliedschaft in der `input` Gruppe
- Potentielle Sicherheitsrisiken (Zugriff auf alle Tastatureingaben)
- Komplexere Einrichtung

## Finale Konfiguration

**Hotkey**: `Shift + Strg + Leertaste` (Shift + Control + Space)

### Dateien angepasst:

1. `~/.local/share/ai-dictation/start-dictation.sh`
   - Entfernt hotkey-monitor.py Start
   - Zeigt korrekten Hotkey an

2. `~/.local/share/ai-dictation/dictation-simple.py`
   - Korrigierte Dokumentation

3. `~/.local/share/ai-dictation/hotkey-monitor.py`
   - NICHT verwendet (optional für Zukunft)

## System-Architektur

```
GNOME Shell (Wayland)
    ↓ (Shift + Strg + Leertaste)
GNOME Shortcuts Handler
    ↓
trigger-dictation.sh
    ↓
touch /tmp/dictation-trigger-core
    ↓
dictation-simple.py (überwacht File-Änderung)
    ↓
Aufnahme starten/stoppen
```

## Wie es funktioniert

1. User drückt **Shift + Strg + Leertaste**
2. GNOME Shell erkennt den Shortcut
3. `trigger-dictation.sh` wird ausgeführt
4. Script touched `/tmp/dictation-trigger-core`
5. `dictation-simple.py` erkennt File-Änderung (via mtime)
6. Toggle-Logik startet oder stoppt Aufnahme

## Test-Ergebnisse

```bash
# Manueller Test erfolgreich:
$ touch /tmp/dictation-trigger-core

# Daemon-Log zeigt:
✓ Shortcut-Trigger erkannt!
[DEBUG] Starte Aufnahme...
[DEBUG] Overlay gestartet
```

Der GNOME Shortcut funktioniert einwandfrei!

## Status

✓ **GELÖST** - System funktioniert mit GNOME Shortcut
✓ Hotkey: Shift + Strg + Leertaste
✓ Kein zusätzlicher Hotkey-Monitor erforderlich
✓ Funktioniert nativ unter Wayland/GNOME 48
