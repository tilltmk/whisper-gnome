#!/usr/bin/env python3.14
"""
Überwacht beide Shift-Tasten + Space und triggert Diktierung
Funktioniert unter Wayland mit pynput
"""
import os
import subprocess
import time
from pathlib import Path

try:
    from pynput import keyboard
    from pynput.keyboard import Key
except ImportError:
    print("ERROR: pynput nicht installiert!")
    print("Bitte installieren: pip install pynput")
    exit(1)

# Aktuell gedrückte Tasten
current_keys = set()
last_trigger_time = 0
TRIGGER_COOLDOWN = 0.5  # Mindestabstand zwischen Triggers in Sekunden

def trigger_dictation():
    """Triggert die Diktierung durch Touch des Trigger-Files."""
    global last_trigger_time

    current_time = time.time()
    time_diff = current_time - last_trigger_time

    if time_diff < TRIGGER_COOLDOWN:
        # Zu schnell - ignoriere (Mehrfach-Trigger vermeiden)
        print(f"→ Ignoriere zu schnellen Trigger ({time_diff:.2f}s)")
        return

    last_trigger_time = current_time

    try:
        # Touch Trigger-File (wie trigger-dictation.sh)
        trigger_file = f"/tmp/dictation-trigger-{os.getenv('USER')}"
        Path(trigger_file).touch()
        print("✓ Diktierung getriggert!")
    except Exception as e:
        print(f"ERROR beim Triggern: {e}")

def on_press(key):
    """Wird aufgerufen wenn Taste gedrückt wird."""
    global current_keys
    current_keys.add(key)

    # Prüfe ob beide Shift-Tasten + Space gedrückt sind
    shift_left = Key.shift_l in current_keys or Key.shift in current_keys
    shift_right = Key.shift_r in current_keys
    space = Key.space in current_keys

    if shift_left and shift_right and space:
        # Trigger Diktierung
        trigger_dictation()
        # Cleare Keys um doppelte Trigger zu vermeiden
        current_keys.clear()

def on_release(key):
    """Wird aufgerufen wenn Taste losgelassen wird."""
    try:
        current_keys.discard(key)
    except KeyError:
        pass

def main():
    """Hauptfunktion."""
    print("🎙️ Hotkey Monitor gestartet")
    print("Hotkey: Beide Shift-Tasten + Space")
    print("Platform: Wayland/GNOME")
    print("Backend: pynput")
    print("Beenden: Strg+C\n")

    try:
        # Starte Keyboard Listener
        with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
            listener.join()
    except KeyboardInterrupt:
        print("\n✓ Hotkey Monitor beendet")
    except Exception as e:
        print(f"\nERROR: {e}")
        print("\nFalls unter Wayland Probleme auftreten:")
        print("  - Prüfe ob User in 'input' Gruppe ist: groups")
        print("  - Füge User hinzu: sudo usermod -aG input $USER")
        print("  - Logout/Login erforderlich")

if __name__ == '__main__':
    main()
