# KI-Diktierung mit Faster-Whisper (Deutsch)

Lokale Spracherkennung mit Faster-Whisper Large-v3, optimiert für deine RTX 4060 GPU.

## Features

- **100% lokal** - Keine Cloud, alle Daten bleiben auf deinem System
- **GPU-beschleunigt** - Nutzt deine RTX 4060 mit CUDA
- **Large-v3 Modell** - Bestes Modell für deutsche Spracherkennung
- **Animiertes Overlay** - Lila radiale Wellen während der Aufnahme
- **GNOME-Integration** - Nativ über GNOME Keyboard Shortcuts
- **Toggle-Steuerung** - Gleiche Taste zum Starten und Stoppen
- **Keine Auto-Pause** - Du kontrollierst wann die Aufnahme endet

## Installation

Das System ist bereits installiert in:
- Python-Umgebung: `~/.local/share/ai-dictation/venv/`
- Whisper-Modell: `large-v3` (wird beim ersten Start heruntergeladen, ~3GB)

## Einrichtung

### 1. GNOME Shortcut konfigurieren

```bash
~/.local/share/ai-dictation/setup-gnome-shortcut.sh
```

Das Script versucht automatisch einen GNOME Shortcut zu erstellen.

**Falls automatische Konfiguration nicht klappt:**
1. Öffne GNOME Einstellungen → Tastatur
2. Scrolle zu "Eigene Tastenkombinationen"
3. Klicke auf "+"
4. Name: `KI-Diktierung`
5. Befehl: `~/.local/share/ai-dictation/trigger-dictation.sh`
6. Tastenkombination: Drücke beide Shift-Tasten + Space gleichzeitig

**Alternative Tastenkombinationen** (falls beide Shift nicht funktioniert):
- `Super+D`
- `Ctrl+Alt+Space`
- `Super+Space`

### 2. Daemon starten

```bash
~/.local/share/ai-dictation/start-dictation.sh
```

Der Daemon:
- Lädt das large-v3 Modell beim Start (~3GB Download beim ersten Mal)
- Läuft permanent im Hintergrund
- Wartet auf Hotkey-Trigger

## Nutzung

### Diktieren

1. **Start**: Drücke deine konfigurierte Tastenkombination (z.B. beide Shift + Space)
   - Sound wird abgespielt
   - Animiertes lila Overlay erscheint rechts unten
   - Notification: "🔴 AUFNAHME LÄUFT"

2. **Sprechen**: Sprich deinen Text (Deutsch)
   - Keine Angst vor Pausen - kein automatisches Stoppen
   - Overlay zeigt Animation während Aufnahme

3. **Stoppen**: Drücke dieselbe Tastenkombination nochmal
   - Overlay verschwindet
   - Notification: "⏹️ Aufnahme gestoppt - Transkribiere..."

4. **Einfügen**: Text ist in Zwischenablage
   - Drücke `Strg+V` zum Einfügen
   - Notification zeigt erkannten Text an

### Automatischer Start beim Login

Wenn du den Daemon automatisch beim Login starten möchtest:

```bash
mkdir -p ~/.config/autostart
cat > ~/.config/autostart/ai-dictation.desktop << 'EOF'
[Desktop Entry]
Type=Application
Name=KI-Diktierung (Faster-Whisper)
Exec=~/.local/share/ai-dictation/start-dictation.sh
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
EOF
```

## Konfiguration

Die Einstellungen können in `~/.local/share/ai-dictation/dictation-simple.py` angepasst werden:

```python
SAMPLE_RATE = 16000               # Audio-Samplerate
MAX_RECORDING_TIME = 300          # Max. 5 Minuten
MODEL_NAME = "large-v3"           # Whisper-Modell
DEVICE = "cuda"                   # GPU-Beschleunigung
COMPUTE_TYPE = "float16"          # Optimiert für RTX 4060
```

### Andere Whisper-Modelle

Verfügbare Modelle (aufsteigend nach Qualität/Größe):
- `tiny` - Schnellstes, niedrigste Qualität (~40MB)
- `base` - Schnell, okay Qualität (~75MB)
- `small` - Gut, etwas langsamer (~250MB)
- `medium` - Sehr gut, moderat (~770MB)
- **`large-v3`** - **Standard** - Beste Qualität (~3GB)

Zum Ändern: Zeile 21 in `dictation-simple.py` anpassen und Daemon neu starten.

## Troubleshooting

### Hotkey funktioniert nicht

**Problem**: Tastenkombination wird nicht erkannt.

**Lösung**:
1. Prüfe ob GNOME Shortcut konfiguriert ist:
   ```bash
   gsettings get org.gnome.settings-daemon.plugins.media-keys custom-keybindings
   ```

2. Falls nicht: Führe `setup-gnome-shortcut.sh` aus oder konfiguriere manuell (siehe Einrichtung)

3. Falls "beide Shift + Space" nicht funktioniert: Nutze alternative Tastenkombination

### Overlay erscheint nicht

**Problem**: Kein animiertes Fenster bei Aufnahme.

**Lösung**:
1. Prüfe ob GTK3 verfügbar:
   ```bash
   python3 -c "import gi; gi.require_version('Gtk', '3.0'); from gi.repository import Gtk"
   ```

2. Prüfe Daemon-Logs:
   ```bash
   tail -f /tmp/dictation-daemon.log
   ```

3. Teste Overlay manuell:
   ```bash
   touch /tmp/dictation-state-$USER
   ~/.local/share/ai-dictation/venv/bin/python3 ~/.local/share/ai-dictation/animated_overlay.py
   ```

### Kein Ton / Audio-Aufnahme funktioniert nicht

Prüfe ob PulseAudio/PipeWire läuft:
```bash
pactl info
```

Mikrofon testen:
```bash
arecord -d 5 test.wav && aplay test.wav
```

### GPU nicht erkannt

Prüfe CUDA-Installation:
```bash
nvidia-smi
```

Falls CUDA nicht verfügbar, ändere in `dictation-simple.py` Zeile 22:
```python
DEVICE = "cpu"  # Nutzt CPU statt GPU
```

### Schlechte Erkennungsqualität

- **Näher am Mikrofon sprechen**
- **Hintergrundgeräusche reduzieren**
- **Deutlich und nicht zu schnell sprechen**
- Modell ist bereits `large-v3` (beste Qualität)

### Daemon läuft nicht

Prüfe Status:
```bash
pgrep -af dictation-simple.py
```

Starte manuell im Vordergrund:
```bash
~/.local/share/ai-dictation/venv/bin/python3 ~/.local/share/ai-dictation/dictation-simple.py
```

Logs anzeigen:
```bash
tail -f /tmp/dictation-daemon.log
```

## Systemressourcen

- **Festplatte**: ~5 GB (large-v3 Modell + Dependencies)
- **RAM (Leerlauf)**: ~50 MB (Daemon)
- **RAM (Transkription)**: ~4-6 GB (Modell geladen)
- **GPU-VRAM**: ~3 GB (large-v3 mit float16)
- **CPU (Leerlauf)**: ~0%
- **CPU (Transkription mit GPU)**: ~20-40%

## Deinstallation

```bash
# Daemon stoppen
pkill -f dictation-simple.py

# Autostart entfernen (falls konfiguriert)
rm ~/.config/autostart/ai-dictation.desktop

# GNOME Shortcut entfernen (manuell via GNOME Einstellungen)

# Alle Dateien löschen
rm -rf ~/.local/share/ai-dictation

# Cache leeren (optional)
rm -rf ~/.cache/whisper
```

## Entwickelt mit

- **Faster-Whisper** - Optimierte Speech-to-Text Engine (CTranslate2)
- **PyTorch** - Machine Learning Framework
- **CUDA** - GPU-Beschleunigung (NVIDIA)
- **GTK3** - Animiertes Overlay
- **GNOME** - Keyboard Shortcuts Integration
- **sounddevice** - Audio-Aufnahme
- **wl-copy** - Wayland Clipboard

## Lizenz & Datenschutz

- **100% lokal** - Keine Datenübertragung an externe Server
- **Open Source** - Basiert auf OpenAI Whisper (MIT Lizenz)
- **Privatsphäre** - Alle Aufnahmen werden nur temporär im RAM gehalten

---

**Status**: Installiert und konfiguriert ✓
**GPU**: NVIDIA RTX 4060 Max-Q ✓
**Modell**: Faster-Whisper Large-v3 ✓
**Sprache**: Deutsch ✓
**Hotkey**: GNOME Shortcut (konfigurierbar) ✓
**Overlay**: Animierte lila Wellen ✓
