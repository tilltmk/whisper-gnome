#!/usr/bin/env python3.14
"""
KI-Diktierung (Audio-Aufnahme ohne Transkription)
Wird per Hotkey-Daemon getriggert
"""

import os
import sys
import time
import subprocess
import threading
from pathlib import Path

import sounddevice as sd
import numpy as np
from faster_whisper import WhisperModel

# Konfiguration
SAMPLE_RATE = 16000
MAX_RECORDING_TIME = 300  # 5 Minuten Maximum
PAUSE_THRESHOLD = 5.0  # Automatischer Stopp nach 5 Sekunden Pause
SILENCE_THRESHOLD = 0.02  # Audio-Level unter dem als Stille gilt
STATE_FILE = f"/tmp/dictation-state-{os.getenv('USER')}"
OSD_FILE = f"/tmp/dictation-osd-{os.getenv('USER')}"

# Globale Variablen
recording = False
stop_recording_flag = False
last_trigger_time = 0
overlay_process = None
whisper_model = None


def play_sound(sound_type="start"):
    """Spielt Systemsound ab."""
    sounds = {
        "start": "/usr/share/sounds/freedesktop/stereo/service-login.oga",
        "stop": "/usr/share/sounds/freedesktop/stereo/service-logout.oga",
        "success": "/usr/share/sounds/freedesktop/stereo/audio-volume-change.oga",  # Sehr sanft
        "error": "/usr/share/sounds/freedesktop/stereo/dialog-error.oga"
    }
    sound_file = sounds.get(sound_type, sounds["start"])

    try:
        # Spiele Sound im Hintergrund ohne Shell
        # Start-Sound schneller abspielen (1.5x Geschwindigkeit)
        if sound_type == "start":
            subprocess.Popen(
                ["paplay", "--rate=24000", sound_file],  # 16000 * 1.5 = 24000
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        elif sound_type == "success":
            # Success-Sound sehr leise abspielen (50% Volumen)
            subprocess.Popen(
                ["paplay", "--volume=32768", sound_file],  # 50% von 65536
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        else:
            subprocess.Popen(
                ["paplay", sound_file],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
    except Exception as e:
        print(f"[DEBUG] Sound-Fehler ({sound_type}): {e}")


def start_overlay():
    """Startet das animierte Overlay."""
    global overlay_process

    if overlay_process is not None:
        return  # Overlay läuft bereits

    try:
        script_dir = Path(__file__).parent
        overlay_script = script_dir / "animated_overlay.py"

        # Erstelle State-File BEVOR Overlay gestartet wird
        Path(STATE_FILE).touch()

        # Starte Overlay als Subprocess
        overlay_process = subprocess.Popen(
            ["python3.14", str(overlay_script)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        print("[DEBUG] Overlay gestartet")
    except Exception as e:
        print(f"[DEBUG] Overlay-Fehler: {e}")


def stop_overlay():
    """Stoppt das animierte Overlay."""
    global overlay_process

    try:
        # Lösche State-File → Overlay beendet sich automatisch
        if os.path.exists(STATE_FILE):
            os.remove(STATE_FILE)

        # Warte kurz auf sauberes Beenden
        if overlay_process is not None:
            try:
                overlay_process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                overlay_process.terminate()
            overlay_process = None

        print("[DEBUG] Overlay gestoppt")
    except Exception as e:
        print(f"[DEBUG] Overlay-Stopp-Fehler: {e}")




def load_model():
    """Lädt das Whisper-Modell."""
    global whisper_model

    if whisper_model is not None:
        return True

    try:
        print("[INFO] Lade Whisper-Modell...")
        # Verwende medium-Modell für guten Kompromiss zwischen Qualität und Geschwindigkeit
        # device="cpu" für Stabilität (CUDNN-Bibliothek fehlt/inkompatibel)
        whisper_model = WhisperModel("medium", device="cpu", compute_type="int8")
        print("[INFO] Whisper-Modell geladen (medium, CPU, int8)")
        return True
    except Exception as e:
        print(f"[FEHLER] Konnte Whisper-Modell nicht laden: {e}")
        return False


def record_audio():
    """Nimmt Audio auf bis manuell gestoppt oder 8s Pause erkannt."""
    global stop_recording_flag

    audio_data = []
    total_frames = 0
    max_frames = int(MAX_RECORDING_TIME * SAMPLE_RATE)
    stop_recording_flag = False

    # Pause-Erkennung
    silence_frames = 0
    max_silence_frames = int(PAUSE_THRESHOLD * SAMPLE_RATE)
    auto_stopped = False

    def audio_callback(indata, frames, time_info, status):
        nonlocal total_frames, silence_frames, auto_stopped

        if stop_recording_flag:
            raise sd.CallbackStop()

        audio_data.append(indata.copy())
        total_frames += frames

        # Prüfe auf Stille (8 Sekunden Pause)
        audio_level = np.abs(indata).mean()
        if audio_level < SILENCE_THRESHOLD:
            silence_frames += frames
            if silence_frames >= max_silence_frames:
                auto_stopped = True
                print(f"[DEBUG] Auto-Stopp nach {PAUSE_THRESHOLD}s Pause")
                raise sd.CallbackStop()
        else:
            silence_frames = 0  # Reset bei Sprache

        if total_frames >= max_frames:
            raise sd.CallbackStop()

    try:
        with sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype='float32',
            callback=audio_callback
        ):
            while total_frames < max_frames and not stop_recording_flag:
                sd.sleep(100)
    except sd.CallbackStop:
        pass

    if audio_data:
        result = np.concatenate(audio_data, axis=0).flatten()
        return result, auto_stopped
    return None, False


def transcribe_audio(audio_np):
    """Transkribiert Audio mit Whisper."""
    global whisper_model

    if audio_np is None or len(audio_np) == 0:
        return ""

    # Lade Modell falls nicht geladen
    if whisper_model is None:
        if not load_model():
            return ""

    try:
        duration = len(audio_np) / SAMPLE_RATE
        print(f"[INFO] Transkribiere {duration:.1f}s Audio...")

        # Transkribiere mit faster-whisper
        # language="de" für Deutsch, beam_size=5 für gute Qualität
        segments, info = whisper_model.transcribe(
            audio_np,
            language="de",
            beam_size=5,
            vad_filter=False  # VAD deaktiviert (benötigt onnxruntime)
        )

        # Sammle alle Segmente
        text_parts = []
        for segment in segments:
            text_parts.append(segment.text.strip())

        text = " ".join(text_parts).strip()

        if text:
            print(f"[INFO] Transkribiert: {text[:100]}{'...' if len(text) > 100 else ''}")
        else:
            print("[INFO] Kein Text erkannt")

        return text

    except Exception as e:
        print(f"[FEHLER] Transkriptionsfehler: {e}")
        return ""


def show_notification(message, timeout=1500, urgency="normal", icon="audio-input-microphone"):
    """Zeigt Notification mit konfigurierbarem Icon und Urgency."""
    # Benachrichtigungen deaktiviert - zu störend
    return


def type_text(text):
    """Kopiert Text in Zwischenablage."""
    if not text:
        return False

    try:
        # Kopiere Text in Zwischenablage mit --paste-once
        # Dies beendet den Prozess sauber nach dem ersten Einfügen
        process = subprocess.Popen(
            ["wl-copy", "--paste-once"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        stdout, stderr = process.communicate(input=text.encode('utf-8'), timeout=5)

        if process.returncode != 0:
            print(f"[DEBUG] wl-copy Fehler (Code {process.returncode}): {stderr.decode() if stderr else 'unbekannt'}")
            return False

        print(f"[DEBUG] Text in Zwischenablage kopiert")
        return True
    except subprocess.TimeoutExpired:
        print(f"[DEBUG] Timeout beim Kopieren in Zwischenablage")
        process.kill()
        return False
    except Exception as e:
        print(f"[DEBUG] Fehler beim Kopieren: {e}")
        return False


def process_dictation():
    """Kompletter Diktier-Workflow - Toggle-basiert."""
    global recording, stop_recording_flag

    if recording:
        # Toggle: Stoppe aktive Aufnahme
        print("→ Stoppe Aufnahme manuell")
        stop_recording_flag = True
        return

    recording = True

    try:
        # 1. Starte Aufnahme mit Overlay
        print("[DEBUG] Starte Aufnahme...")
        start_overlay()  # Zeige animiertes Overlay
        play_sound("start")
        show_notification("🔴 AUFNAHME LÄUFT\nShift+Strg+Space zum Stoppen\nAuto-Stopp nach 5s Pause", timeout=1500, urgency="critical", icon="media-record")

        audio_np, auto_stopped = record_audio()

        # 3. Aufnahme beendet - Stoppe Overlay
        stop_overlay()
        play_sound("stop")

        # Setze Recording-Flag zurück
        recording = False
        stop_recording_flag = False

        if audio_np is None or len(audio_np) < SAMPLE_RATE * 0.5:
            show_notification("⚠️ Aufnahme zu kurz", timeout=1500, urgency="normal", icon="dialog-warning")
            play_sound("error")
            return

        # 4. Transkribiere
        print("[DEBUG] Transkribiere...")
        text = transcribe_audio(audio_np)

        if not text:
            print("[DEBUG] Kein Text erkannt!")
            show_notification("❌ Kein Text erkannt", timeout=1500, urgency="normal", icon="dialog-error")
            play_sound("error")
            return

        # 5. Kopiere Text in Zwischenablage
        print(f"[DEBUG] Text transkribiert: {text[:100]}{'...' if len(text) > 100 else ''}")
        if type_text(text):
            play_sound("success")
        else:
            print("[DEBUG] Fehler beim Kopieren!")
            show_notification("❌ Fehler beim Kopieren", timeout=1500, urgency="normal", icon="dialog-error")
            play_sound("error")

    except Exception as e:
        print(f"Fehler: {e}")
        show_notification(f"❌ Fehler: {e}", timeout=2000, urgency="critical", icon="dialog-error")
        play_sound("error")
        stop_overlay()  # Sicherstellen dass Overlay geschlossen wird
    finally:
        recording = False
        stop_recording_flag = False


def monitor_trigger_file():
    """Überwacht Trigger-Datei."""
    global last_trigger_time

    print("🎙️ KI-Diktierung Daemon gestartet")
    print("Hotkey: Shift + Strg + Leertaste (via GNOME Shortcut)")
    print("Beenden: Strg+C\n")

    # Trigger-File für IPC (wird von trigger-dictation.sh erstellt/gelöscht)
    trigger_file = f"/tmp/dictation-trigger-{os.getenv('USER')}"

    # Initialisiere wenn nicht existiert
    if not os.path.exists(trigger_file):
        Path(trigger_file).touch()

    last_mtime = os.path.getmtime(trigger_file)

    while True:
        try:
            # Prüfe ob Trigger-File existiert
            if not os.path.exists(trigger_file):
                # Wurde gelöscht, erstelle neu
                Path(trigger_file).touch()
                last_mtime = os.path.getmtime(trigger_file)
                time.sleep(0.05)
                continue

            # Prüfe ob Datei modifiziert wurde
            current_mtime = os.path.getmtime(trigger_file)

            if current_mtime > last_mtime:
                current_time = time.time()
                time_diff = current_time - last_trigger_time

                if time_diff < 1.0:
                    # Zu schnell - ignoriere (Mehrfach-Trigger vermeiden)
                    print(f"→ Ignoriere zu schnellen Trigger ({time_diff:.2f}s)")
                else:
                    # Trigger Diktierung
                    print(f"\n✓ Shortcut-Trigger erkannt!")
                    last_trigger_time = current_time

                    # Starte in separatem Thread
                    thread = threading.Thread(target=process_dictation, daemon=True)
                    thread.start()

                last_mtime = current_mtime

            time.sleep(0.05)

        except KeyboardInterrupt:
            print("\n\n✓ Daemon beendet")
            stop_overlay()  # Cleanup
            break
        except Exception as e:
            print(f"Fehler: {e}")
            time.sleep(1)


def main():
    """Hauptfunktion."""
    monitor_trigger_file()


if __name__ == "__main__":
    main()
