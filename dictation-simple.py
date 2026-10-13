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


def _ensure_cuda_libs():
    """Macht die per pip installierten NVIDIA-Bibliotheken fuer CTranslate2 auffindbar.

    libcudnn/libcublas liegen in den pip-Paketen (nvidia-cudnn-cu12 usw.) und damit
    ausserhalb des ldconfig-Pfads. Der dynamische Linker liest LD_LIBRARY_PATH nur
    beim Prozessstart, deshalb wird der Pfad gesetzt und der Prozess einmalig ersetzt.
    Ohne das faellt CTranslate2 auf die CPU zurueck.
    """
    if os.environ.get("DICTATION_CUDA_PATH_SET"):
        return

    import site

    bases = list(site.getsitepackages())
    user_site = site.getusersitepackages()
    if user_site not in bases:
        bases.append(user_site)

    lib_dirs = []
    for base in bases:
        for package in ("cudnn", "cublas", "cuda_runtime"):
            lib_dir = os.path.join(base, "nvidia", package, "lib")
            if os.path.isdir(lib_dir) and lib_dir not in lib_dirs:
                lib_dirs.append(lib_dir)

    os.environ["DICTATION_CUDA_PATH_SET"] = "1"
    if not lib_dirs:
        return

    existing = os.environ.get("LD_LIBRARY_PATH", "")
    os.environ["LD_LIBRARY_PATH"] = os.pathsep.join(
        lib_dirs + ([existing] if existing else [])
    )
    os.environ["PYTHONUNBUFFERED"] = "1"
    os.execv(sys.executable, [sys.executable] + sys.argv)


_ensure_cuda_libs()

import sounddevice as sd
import numpy as np

# ─── Transkription: Cohere Transcribe, KEIN Whisper ──────────────────────────
#
# Whisper ist hier ausdruecklich nicht gewuenscht;
# `faster_whisper` wird nicht mehr importiert und es gibt bewusst keine
# Whisper-Rueckfallebene. Wenn Cohere nicht laedt, soll das auffallen und nicht
# stillschweigend durch Whisper ersetzt werden.
#
# Modell: cohere-transcribe-03-2026, ein 2B-Modell mit conformer-basiertem
# Encoder-Decoder, Audio rein und Text raus, 14 Sprachen inklusive Deutsch.
# Es liegt vollstaendig lokal, der Ordner enthaelt `model.safetensors` (3,9 G)
# und den eigenen Modellcode (modeling_cohere_asr.py und drei weitere).
#
# WARUM trust_remote_code NOETIG IST: transformers 4.57.1 kennt die Klasse
# `CohereAsrForConditionalGeneration` noch nicht eingebaut (geprueft:
# hasattr(transformers, ...) == False). Das Modell bringt sie per `auto_map`
# selbst mit, und die wird beim Laden ausgefuehrt. Der Code wurde vor der
# Umstellung durchgesehen: nur librosa/numpy/soundfile/torch, keine Netz-,
# Prozess- oder Dateizugriffe ausser dem Vokabular-Speichern des Tokenizers.
# Wird der Ordner je ersetzt, gehoert diese Durchsicht wiederholt.
#
# `librosa` ist eine Abhaengigkeit des Modellcodes und wurde dafuer nachgezogen
# (--user, Version 1.0.0). Ohne sie schlaegt bereits der Import fehl.
#
# bfloat16 UND NICHT float16 - das ist der entscheidende Punkt. Der Modellcode
# maskiert Aufmerksamkeitswerte mit hart kodierten -1e9
# (modeling_cohere_asr.py, Zeilen 326, 839, 850). float16 reicht nur bis
# +-65504, eine Milliarde passt dort nicht hinein, und das Laden gelingt noch,
# die Transkription scheitert dann aber mit
#   "value cannot be converted to type c10::Half without overflow"
# Genau in diese Falle laeuft auch das offizielle Beispiel im Modell-Steckbrief.
# bfloat16 hat denselben Wertebereich wie float32 (bis ~3,4e38) bei halber
# Genauigkeit der Mantisse, damit passt -1e9 und der Speicherbedarf bleibt bei
# rund 4 G. GPUs ab Ampere (Compute Capability 8.0) rechnen bfloat16 in Hardware.
#
# float32 auf der GPU ist auf 8-G-Karten KEINE Option: 2B Parameter waeren
# rund 8 G. Die CPU-Ebene ist nur eine Notloesung, auf ihr ist das
# Modell sehr langsam - aber immer noch besser als keine Diktierfunktion.
COHERE_MODEL_PATH = str(Path.home() / ".cache" / "cohere-transcribe")
TRANSCRIBE_LANGUAGE = "de"
# Stuecke je GPU-Durchlauf. transcribe() zerlegt in <=35-s-Stuecke; 300 s sind
# also bis zu 9 Stuecke. Der Vorgabewert des Modells (128) wuerde alle auf
# einmal rechnen - neben den 3,7 G Gewichten bleibt auf einer 8-G-Karte dafuer zu wenig.
TRANSCRIBE_BATCH_SIZE = 4
MODEL_CANDIDATES = [
    ("cuda", "bfloat16"),
    ("cpu", "float32"),
]
# Die CPU-Ebene braucht rund 8 G Arbeitsspeicher und rechnet minutenlang. Ist
# die GPU nur voruebergehend belegt, kann sie ein System mit knappem RAM per
# vollem Swap zum Stehen bringen. Deshalb: bei GPU-Speichermangel NIE auf die CPU
# ausweichen (beim naechsten Diktat wird die GPU erneut versucht), und die
# CPU-Ebene nur nehmen, wenn so viel Speicher wirklich frei ist.
CPU_FALLBACK_MIN_AVAILABLE_GB = 12

# Konfiguration
SAMPLE_RATE = 16000
MAX_RECORDING_TIME = 300  # 5 Minuten Maximum
PAUSE_THRESHOLD = 5.0  # Automatischer Stopp nach 5 Sekunden Pause
SILENCE_THRESHOLD = 0.02  # Obergrenze fuer die Stille-Schwelle (laute Mikrofone)

# Pegel-Aufbereitung. Manche internen Laptop-Mikrofone (DMIC) liefern einen
# konstanten Gleichspannungsanteil (gemessen ca. -0.23) und einen sehr leisen Nutzpegel. Ohne
# DC-Abzug misst jede Pegelmessung nur den Offset, und ohne Normalisierung
# bekommt das Modell ein Signal um -50 dBFS.
NOISE_CALIBRATION_TIME = 0.5  # Sekunden zur Messung des Grundrauschens
SILENCE_FACTOR = 3.0  # Stille = unterhalb des X-fachen Grundrauschens
SILENCE_FLOOR = 0.002  # Untergrenze, damit leise Mikros nicht endlos laufen
TARGET_PEAK = 0.8  # Ziel-Aussteuerung vor der Transkription
MIN_SIGNAL_LEVEL = 1e-4  # Darunter gilt die Aufnahme als leer
SETTLE_TIME = 0.3  # Einschwing-Transiente des DMIC am Anfang verwerfen
LEVEL_PERCENTILE = 99.5  # Bezugsgroesse fuer die Aussteuerung (statt Peak)
MAX_GAIN = 150.0  # Deckel, damit Stille nicht zu erfundenem Text wird

STATE_FILE = f"/tmp/dictation-state-{os.getenv('USER')}"
OSD_FILE = f"/tmp/dictation-osd-{os.getenv('USER')}"

# ─── Transkriptions-Dienst fuer andere lokale Programme ──────────────────────
#
# Das Modell belegt rund 4,7 G VRAM und bleibt nach dem ersten Diktat geladen.
# Eine zweite Kopie in einem anderen Programm passt nicht auf eine 8-G-Karte.
# Deshalb bietet der Daemon das bereits geladene Modell ueber einen Unix-Socket
# an: der Client legt Audio als float32-Rohdatei (16 kHz, mono) ab und schickt
# die Abschnitte, der Daemon transkribiert sie stapelweise.
#
# Diktieren hat Vorrang: zwischen zwei Stapeln wird geprueft, ob ein Diktat auf
# das Modell wartet - es wartet also hoechstens einen Stapel lang (~1-2 s GPU).
# Auf der CPU werden fremde Auftraege abgelehnt: dort waere ein Video minuten-
# bis stundenlang und mit ~8 G RAM beschaeftigt (siehe CPU_FALLBACK_...).
ASR_SOCKET = os.path.join(
    os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}", "ai-dictation-asr.sock"
)
ASR_SERVICE_BATCH = 4
asr_lock = threading.Lock()          # schuetzt asr_model/asr_processor
diktat_wartet = threading.Event()    # gesetzt, solange ein Diktat aufs Modell wartet

# Globale Variablen
recording = False
stop_recording_flag = False
last_trigger_time = 0
overlay_process = None
asr_model = None
asr_processor = None


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
    """Laedt Cohere Transcribe. Kein Whisper, auch nicht als Rueckfallebene."""
    global asr_model, asr_processor

    if asr_model is not None:
        return True

    if not os.path.isdir(COHERE_MODEL_PATH):
        print(f"[FEHLER] Modellordner fehlt: {COHERE_MODEL_PATH}")
        return False

    # Erst hier importieren, nicht beim Start des Daemons: transformers und torch
    # brauchen mehrere Sekunden und belegen Speicher. Der Daemon soll auf den
    # Hotkey reagieren koennen, bevor je transkribiert wurde.
    try:
        import torch
        from transformers import AutoProcessor, AutoModelForSpeechSeq2Seq
    except Exception as e:
        print(f"[FEHLER] transformers/torch nicht nutzbar: {e}")
        return False

    for device, dtype_name in MODEL_CANDIDATES:
        if device == "cuda" and not torch.cuda.is_available():
            print("[WARN] CUDA nicht verfuegbar, ueberspringe GPU")
            continue
        if device == "cpu":
            available_gb = mem_available_gb()
            if available_gb < CPU_FALLBACK_MIN_AVAILABLE_GB:
                print(
                    f"[FEHLER] CPU-Ebene uebersprungen: nur {available_gb:.1f} G frei, "
                    f"noetig {CPU_FALLBACK_MIN_AVAILABLE_GB} G"
                )
                continue
        try:
            print(f"[INFO] Lade Cohere Transcribe ({device}, {dtype_name})...")
            if asr_processor is None:
                asr_processor = AutoProcessor.from_pretrained(
                    COHERE_MODEL_PATH, trust_remote_code=True
                )
            modell = AutoModelForSpeechSeq2Seq.from_pretrained(
                COHERE_MODEL_PATH,
                trust_remote_code=True,
                dtype=getattr(torch, dtype_name),
            )
            asr_model = modell.to(device).eval()
            print(f"[INFO] Cohere Transcribe geladen ({device}, {dtype_name})")
            return True
        except Exception as e:
            print(f"[WARN] Cohere auf {device} nicht nutzbar: {e}")
            # Halb geladene Gewichte auf der GPU wieder freigeben, sonst steht
            # der VRAM dem naechsten Versuch nicht zur Verfuegung.
            asr_model = None
            if device == "cuda":
                try:
                    torch.cuda.empty_cache()
                except Exception:
                    pass
                # Volle GPU ist ein voruebergehender Zustand (anderer Prozess
                # haelt VRAM) - kein Grund, den Rechner mit der CPU-Ebene zu
                # ersticken. Abbrechen, beim naechsten Diktat neu versuchen.
                if isinstance(e, torch.cuda.OutOfMemoryError):
                    print("[FEHLER] GPU-Speicher belegt - keine CPU-Ebene, naechstes Diktat versucht es erneut")
                    show_notification("Diktierung: Grafikspeicher belegt", urgency="critical")
                    return False

    print("[FEHLER] Konnte Cohere Transcribe nicht laden")
    return False


def mem_available_gb():
    """Liest MemAvailable aus /proc/meminfo (in G)."""
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) / (1024 * 1024)
    except OSError:
        pass
    return 0.0


def has_default_source():
    """Prueft, ob PipeWire eine Default-Aufnahmequelle kennt."""
    try:
        result = subprocess.run(
            ["pw-metadata", "-n", "default"],
            capture_output=True, text=True, timeout=5
        )
        return "default.audio.source" in result.stdout
    except Exception as e:
        print(f"[DEBUG] Konnte Default-Quelle nicht pruefen: {e}")
        return True  # Im Zweifel weitermachen und den Stream versuchen


def recover_audio_input():
    """Repariert eine fehlende Aufnahmequelle durch WirePlumber-Neustart.

    Auf manchen AMD-Laptops (ACP-Audio) registriert sich die DMIC-Karte teils erst
    Minuten nach WirePlumber. Die HDA-Karte wird dann ohne UCM angelegt und
    verliert das Profil mit den internen Mikrofonen - es bleibt nur die leere
    Klinkenbuchse, also gar keine Default-Quelle. Ein Neustart laesst
    WirePlumber neu proben, diesmal mit vorhandener DMIC-Karte.
    """
    print("[INFO] Keine Aufnahmequelle - starte WirePlumber neu")
    try:
        subprocess.run(
            ["systemctl", "--user", "restart", "wireplumber"],
            capture_output=True, timeout=15, check=True
        )
    except Exception as e:
        print(f"[FEHLER] WirePlumber-Neustart fehlgeschlagen: {e}")
        return False

    # WirePlumber braucht einen Moment, bis die Karten neu geprobt sind
    for _ in range(20):
        time.sleep(0.5)
        if has_default_source():
            print("[INFO] Aufnahmequelle wiederhergestellt")
            return True

    print("[FEHLER] Auch nach Neustart keine Aufnahmequelle")
    return False


def open_input_stream(callback):
    """Oeffnet den Aufnahme-Stream, mit einem Reparaturversuch bei Fehlern."""
    def _open():
        return sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype='float32',
            callback=callback
        )

    if not has_default_source():
        recover_audio_input()

    try:
        return _open()
    except Exception as e:
        # Typisch: PaErrorCode -9999 / ALSA -2, wenn das 'default'-PCM die
        # Default-Quelle nicht aufloesen kann.
        print(f"[FEHLER] Mikrofon nicht verfuegbar: {e}")
        if not recover_audio_input():
            raise
        return _open()


def record_audio():
    """Nimmt Audio auf bis manuell gestoppt oder 8s Pause erkannt.

    Oeffnet den Stream in einem eigenen Hintergrund-Thread. Mit manchen
    USB-Mikrofonen kann stream.close() beim Beenden 15-20s dauern oder
    ganz haengen bleiben - PortAudio/ALSA-Teardown, keine Python-Exception,
    reproduzierbar bei praktisch jedem Stopp. Lief das synchron im Aufrufer
    (process_dictation), blieb dessen globales recording-Flag bis zum
    naechsten Dienst-Neustart auf True stehen, und der Hotkey tat nichts
    mehr ausser "Stoppe Aufnahme manuell" zu loggen. Die Aufnahme ist mit
    dem letzten Callback vollstaendig; der Thread schliesst den Stream
    danach unabhaengig weiter und blockiert niemanden mehr.
    """
    global stop_recording_flag

    audio_data = []
    total_frames = 0
    max_frames = int(MAX_RECORDING_TIME * SAMPLE_RATE)
    stop_recording_flag = False

    # Pause-Erkennung
    silence_frames = 0
    max_silence_frames = int(PAUSE_THRESHOLD * SAMPLE_RATE)
    auto_stopped = False

    # Adaptive Stille-Schwelle: das Grundrauschen wird zu Beginn gemessen,
    # statt eine feste Schwelle zu raten. Das interne DMIC liegt bei ~0.003,
    # ein USB-Mikrofon deutlich hoeher - eine feste Schwelle passt nie zu beiden.
    calibration_frames = int(NOISE_CALIBRATION_TIME * SAMPLE_RATE)
    calibration_levels = []
    silence_threshold = None

    def audio_callback(indata, frames, time_info, status):
        nonlocal total_frames, silence_frames, auto_stopped, silence_threshold

        if stop_recording_flag:
            raise sd.CallbackStop()

        audio_data.append(indata.copy())
        total_frames += frames

        # Pegel ohne Gleichspannungsanteil messen. Das DMIC liefert einen
        # konstanten Offset von ca. -0.23; ohne Abzug misst man nur den.
        block = indata[:, 0] if indata.ndim > 1 else indata
        audio_level = float(np.abs(block - block.mean()).mean())

        if total_frames < calibration_frames:
            calibration_levels.append(audio_level)
            return  # Waehrend der Kalibrierung nicht auf Stille pruefen

        if silence_threshold is None:
            # 25. Perzentil ist robust gegen den Einschwing-Transienten am
            # Anfang und gegen sofort einsetzendes Sprechen.
            noise_floor = float(np.percentile(calibration_levels, 25)) if calibration_levels else 0.0
            silence_threshold = min(
                max(noise_floor * SILENCE_FACTOR, SILENCE_FLOOR),
                SILENCE_THRESHOLD
            )
            print(f"[DEBUG] Grundrauschen {noise_floor:.5f} -> Stille-Schwelle {silence_threshold:.5f}")

        if audio_level < silence_threshold:
            silence_frames += frames
            if silence_frames >= max_silence_frames:
                auto_stopped = True
                print(f"[DEBUG] Auto-Stopp nach {PAUSE_THRESHOLD}s Pause")
                raise sd.CallbackStop()
        else:
            silence_frames = 0  # Reset bei Sprache

        if total_frames >= max_frames:
            raise sd.CallbackStop()

    capture_done = threading.Event()

    def capture_worker():
        try:
            stream = open_input_stream(audio_callback)
            stream.start()
        except Exception as e:
            print(f"[FEHLER] Aufnahme-Stream konnte nicht geoeffnet werden: {e}")
            capture_done.set()
            return

        try:
            # stream.active statt total_frames pruefen: nach CallbackStop
            # kommen keine Callbacks mehr, total_frames waechst nicht weiter
            # und die Schleife wuerde sonst endlos drehen.
            while stream.active and not stop_recording_flag:
                sd.sleep(100)
        except sd.CallbackStop:
            pass
        finally:
            # Ab hier ist audio_data vollstaendig - der Aufrufer muss nicht
            # auf den (potenziell haengenden) Stream-Abbau unten warten.
            capture_done.set()

        try:
            stream.stop()
            stream.close()
        except Exception as e:
            print(f"[DEBUG] Stream-Abbau-Fehler (ignoriert): {e}")

    threading.Thread(target=capture_worker, daemon=True).start()

    # Der Hang sitzt nicht immer beim Schliessen - manchmal haengt schon
    # open_input_stream()/stream.start() nativ, bevor der Worker ueberhaupt
    # die Polling-Schleife erreicht und stop_recording_flag das erste Mal
    # sieht. Ohne Frist wuerde recording in process_dictation() dann trotz
    # Fix auf Dauer True bleiben. Die Frist laeuft erst NACHDEM ein Stop
    # angefordert wurde, damit legitime lange Aufnahmen (bis
    # MAX_RECORDING_TIME) nicht abgeschnitten werden.
    GRACE_AFTER_STOP = 2.0
    stop_requested_at = None
    while not capture_done.is_set():
        if stop_recording_flag and stop_requested_at is None:
            stop_requested_at = time.monotonic()
        if (
            stop_requested_at is not None
            and time.monotonic() - stop_requested_at > GRACE_AFTER_STOP
        ):
            print("[FEHLER] Aufnahme-Stream reagiert nicht auf Stop - gebe auf")
            break
        capture_done.wait(timeout=0.1)

    if audio_data:
        result = np.concatenate(audio_data, axis=0).flatten()
        return result, auto_stopped
    return None, False


def prepare_audio(audio_np):
    """Entfernt den Gleichspannungsanteil und steuert das Signal aus.

    Das Modell erwartet ein um Null zentriertes Signal. Das interne DMIC liefert
    einen Offset von ca. -0.23 bei einem Nutzpegel um 0.003 - ohne Aufbereitung
    besteht die Aufnahme fast nur aus Offset.
    """
    # Die ersten Millisekunden enthalten den Einschwing-Transienten des DMIC
    # (gemessen ~15x lauter als das Nutzsignal). Er wuerde jede Aussteuerung
    # verfaelschen, deshalb faellt er weg - aber nur, wenn genug uebrig bleibt.
    settle_samples = int(SETTLE_TIME * SAMPLE_RATE)
    if len(audio_np) > settle_samples * 2:
        audio_np = audio_np[settle_samples:]

    audio_np = audio_np - audio_np.mean()

    # Hohes Perzentil statt Maximum: einzelne Ausreisser (Tastenklick,
    # Restspitzen) bestimmen sonst den Gain und druecken die Sprache weg.
    level = float(np.percentile(np.abs(audio_np), LEVEL_PERCENTILE))
    if level < MIN_SIGNAL_LEVEL:
        print(f"[DEBUG] Signal zu schwach (Pegel {level:.6f}) - nicht normalisiert")
        return audio_np

    gain = min(TARGET_PEAK / level, MAX_GAIN)
    print(f"[DEBUG] Pegel {level:.5f} -> Verstaerkung {gain:.1f}x")

    # Clipping nach der Verstaerkung: die obersten 0.5% werden begrenzt,
    # das ist hoerbar unkritisch und verhindert Ueberlauf.
    return np.clip(audio_np * gain, -1.0, 1.0)


def transcribe_audio(audio_np):
    """Transkribiert Audio mit Cohere Transcribe."""
    global asr_model, asr_processor

    if audio_np is None or len(audio_np) == 0:
        return ""

    # Vorrang vor dem Transkriptions-Dienst: das Event haelt ihn vor dem
    # naechsten Stapel an, das Lock wartet hoechstens den laufenden ab.
    diktat_wartet.set()
    with asr_lock:
        diktat_wartet.clear()
        return _transcribe_audio_locked(audio_np)


def _transcribe_audio_locked(audio_np):
    """Wie transcribe_audio, Aufrufer haelt asr_lock."""
    # Lade Modell falls nicht geladen
    if asr_model is None:
        if not load_model():
            return ""

    try:
        duration = len(audio_np) / SAMPLE_RATE
        print(f"[INFO] Transkribiere {duration:.1f}s Audio...")

        audio_np = prepare_audio(audio_np)

        # transcribe() des Modells und NICHT processor() + generate() von Hand.
        # Der Handweg hatte zwei Fehler, die lange Diktate zerlegt haben:
        #
        # 1. Keine Zerlegung. Der Feature-Extractor rechnet die ganze Aufnahme
        #    am Stueck, das Modell ist aber auf hoechstens 35 s ausgelegt
        #    (config.json: max_audio_clip_s). Darueber hoert der Dekoder
        #    mittendrin auf oder wiederholt den letzten Satz in Schleife.
        #    transcribe() schneidet an der leisesten Stelle kurz vor 35 s
        #    (split_audio_chunks_energy) und fuegt die Texte wieder zusammen.
        # 2. Keine Sprache. processor(language="de") verschluckt das Argument
        #    still in **kwargs - die Sprachmarke <|de|> steckt nur im
        #    Text-Prompt aus build_prompt(). Ohne ihn hat das Modell geraten
        #    und ist mitten im Satz ins Englische gekippt.
        #
        # Nebenbei faellt die "'NoneType' object has no attribute 'new_ones'"-
        # Falle weg (transformers 4.57): transcribe() gibt einen Prompt mit und
        # baut decoder_attention_mask daraus selbst, statt None zu uebergeben.
        texts = asr_model.transcribe(
            processor=asr_processor,
            language=TRANSCRIBE_LANGUAGE,
            audio_arrays=[np.asarray(audio_np, dtype=np.float32)],
            sample_rates=[SAMPLE_RATE],
            batch_size=TRANSCRIBE_BATCH_SIZE,
        )
        text = (texts[0] if texts else "").strip()

        if text:
            print(f"[INFO] Transkribiert: {text[:100]}{'...' if len(text) > 100 else ''}")
        else:
            print("[INFO] Kein Text erkannt")

        return text

    except Exception as e:
        print(f"[FEHLER] Transkriptionsfehler: {e}")
        return ""


def _asr_geraet():
    try:
        return str(next(asr_model.parameters()).device.type)
    except Exception:
        return "unbekannt"


def _asr_auftrag(anfrage, senden):
    """Fuehrt einen Auftrag des Transkriptions-Dienstes aus (siehe ASR_SOCKET)."""
    aktion = anfrage.get("aktion")
    if aktion == "status":
        senden({"ok": True, "modell_geladen": asr_model is not None,
                "geraet": _asr_geraet() if asr_model is not None else None})
        return
    if aktion != "transkribieren":
        senden({"ok": False, "fehler": f"unbekannte Aktion {aktion!r}"})
        return

    pfad = Path(str(anfrage.get("audio", "")))
    try:
        st = pfad.stat()
    except OSError as e:
        senden({"ok": False, "fehler": f"Audio nicht lesbar: {e}"})
        return
    if pfad.suffix != ".f32" or not pfad.is_file() or st.st_uid != os.getuid():
        senden({"ok": False, "fehler": "Audio muss eine eigene .f32-Datei sein"})
        return
    rate = int(anfrage.get("rate", SAMPLE_RATE))
    sprache = str(anfrage.get("sprache", TRANSCRIBE_LANGUAGE))
    abschnitte = [(int(a), int(n)) for a, n in anfrage.get("abschnitte", [])]
    audio = np.memmap(pfad, dtype=np.float32, mode="r")

    with asr_lock:
        if asr_model is None and not load_model():
            senden({"ok": False, "fehler": "Modell nicht ladbar (GPU-Speicher belegt?)"})
            return
        if _asr_geraet() != "cuda" and not anfrage.get("cpu_erlaubt"):
            senden({"ok": False, "fehler": "Modell laeuft auf der CPU - Auftrag abgelehnt"})
            return

    texte = []
    for i in range(0, len(abschnitte), ASR_SERVICE_BATCH):
        while diktat_wartet.is_set():
            time.sleep(0.05)
        stapel = [np.array(audio[a:a + n], dtype=np.float32) for a, n in abschnitte[i:i + ASR_SERVICE_BATCH]]
        with asr_lock:
            if asr_model is None:
                senden({"ok": False, "fehler": "Modell waehrend des Auftrags entladen"})
                return
            ergebnis = asr_model.transcribe(
                processor=asr_processor, language=sprache, audio_arrays=stapel,
                sample_rates=[rate] * len(stapel), batch_size=ASR_SERVICE_BATCH,
            )
        texte.extend((t or "").strip() for t in ergebnis)
        senden({"fortschritt": len(texte), "gesamt": len(abschnitte)})
    senden({"ok": True, "texte": texte})


def asr_dienst():
    """Unix-Socket-Server, ein Auftrag nach dem anderen. Laeuft als Daemon-Thread."""
    import json
    import socket

    try:
        os.unlink(ASR_SOCKET)
    except FileNotFoundError:
        pass
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    alte_maske = os.umask(0o177)          # Socket nur fuer den eigenen Benutzer
    try:
        server.bind(ASR_SOCKET)
    finally:
        os.umask(alte_maske)
    server.listen(2)
    print(f"[INFO] Transkriptions-Dienst bereit: {ASR_SOCKET}")

    while True:
        verbindung, _ = server.accept()
        with verbindung, verbindung.makefile("rwb") as datei:
            def senden(obj):
                datei.write((json.dumps(obj, ensure_ascii=False) + "\n").encode())
                datei.flush()
            try:
                zeile = datei.readline()
                if zeile:
                    _asr_auftrag(json.loads(zeile), senden)
            except (BrokenPipeError, ConnectionResetError):
                print("[WARN] Transkriptions-Dienst: Client hat die Verbindung getrennt")
            except Exception as e:
                print(f"[FEHLER] Transkriptions-Dienst: {e}")
                try:
                    senden({"ok": False, "fehler": str(e)[:300]})
                except OSError:
                    pass


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
    threading.Thread(target=asr_dienst, daemon=True, name="asr-dienst").start()
    monitor_trigger_file()


if __name__ == "__main__":
    main()
