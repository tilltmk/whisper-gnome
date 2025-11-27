# 🎙️ KI-Diktierung - Quickstart

## ✨ Features

- **Faster-Whisper Large-v3** - Bestes deutsches Sprachmodell
- **Animiertes Overlay** - Lila radiale Wellen während Aufnahme
- **Toggle-Funktion** - Gleicher Hotkey zum Starten & Stoppen
- **GPU-beschleunigt** - Nutzt eine NVIDIA-GPU mit CUDA
- **GNOME-Integration** - Native Keyboard Shortcuts
- **Keine Auto-Pause** - Du kontrollierst wann gestoppt wird

## 🚀 Ersteinrichtung (EINMALIG!)

### Schritt 1: GNOME Shortcut konfigurieren

```bash
~/.local/share/ai-dictation/setup-gnome-shortcut.sh
```

Das Script versucht automatisch einen Shortcut zu erstellen.

**Falls nicht automatisch geklappt:**
1. Öffne GNOME Einstellungen (`gnome-control-center`)
2. Gehe zu **Tastatur** → **Tastenkombinationen anzeigen und anpassen**
3. Scrolle nach unten zu **"Eigene Tastenkombinationen"**
4. Klicke auf **"+"**
5. Gib ein:
   - **Name**: `KI-Diktierung`
   - **Befehl**: `~/.local/share/ai-dictation/trigger-dictation.sh`
6. Klicke auf **"Tastenkombination festlegen"**
7. Drücke: **Beide Shift-Tasten + Space gleichzeitig**
   - Falls nicht erkannt: Nutze alternative Kombination (z.B. `Super+D`)

### Schritt 2: Daemon starten

```bash
~/.local/share/ai-dictation/start-dictation.sh
```

Das Script:
- Prüft ob Shortcut konfiguriert ist
- Startet den Diktier-Daemon
- Lädt beim ersten Start das large-v3 Modell (~3GB Download)

### Schritt 3: Testen!

Drücke deine konfigurierte Tastenkombination:
- ✅ Overlay sollte erscheinen (lila Wellen rechts unten)
- ✅ Sound sollte abgespielt werden
- ✅ Notification sollte "🔴 AUFNAHME LÄUFT" anzeigen

## 🎯 Nutzung

### Diktieren

1. **Drücke Hotkey** (z.B. beide Shift + Space)
   - 🟣 **Animiertes Overlay erscheint** mit pulsierenden Wellen
   - 🔊 **Bestätigungs-Sound**
   - 📢 **Notification**: "🔴 AUFNAHME LÄUFT"

2. **Sprich deinen Text** (Deutsch)
   - Das Overlay pulsiert während du sprichst
   - **Keine Angst vor Pausen** - wird NICHT automatisch gestoppt
   - Nur 5-Minuten-Maximum

3. **Drücke Hotkey nochmal** zum Stoppen
   - 🔴 **Overlay verschwindet**
   - 🔊 **Stop-Sound**
   - 📢 **Notification**: "⏹️ Aufnahme gestoppt - Transkribiere..."

4. **Warte kurz** - KI transkribiert (dauert je nach Länge 2-10 Sekunden)
   - Mit large-v3 Modell sehr genaue deutsche Erkennung

5. **Text einfügen**
   - Drücke `Strg+V` - Text ist in Zwischenablage!
   - Notification zeigt erkannten Text

### Autostart beim Login

Damit der Daemon automatisch beim Login startet:

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

## 🎨 Das Overlay

### 🟣 Lila (Pulsierende Wellen)
**"Aufnahme läuft"** - Das ist der Moment wo du sprichst
- 30 radiale Balken pulsieren rhythmisch
- Animiert mit 60 FPS
- Positioniert rechts unten
- Verschwindet automatisch beim Stoppen

## ⚙️ Konfiguration

Datei: `~/.local/share/ai-dictation/dictation-simple.py`

```python
# Zeile 19-23:
SAMPLE_RATE = 16000
MAX_RECORDING_TIME = 300          # 5 Minuten Maximum
MODEL_NAME = "large-v3"           # Whisper-Modell
DEVICE = "cuda"                   # GPU-Beschleunigung
COMPUTE_TYPE = "float16"          # für NVIDIA-GPUs mit Tensor-Cores
```

Nach Änderungen Daemon neu starten:
```bash
pkill -f dictation-simple.py
~/.local/share/ai-dictation/start-dictation.sh
```

### Modell-Optionen

- `tiny` - Schnellst, niedrigste Qualität (~40 MB)
- `base` - Schnell, okay Qualität (~75 MB)
- `small` - Gut, etwas langsamer (~250 MB)
- `medium` - Sehr gut, moderat (~770 MB)
- **`large-v3`** - **Beste Qualität** (~3 GB) **← Aktuell**

## 🐛 Troubleshooting

### "Hotkey reagiert nicht"

**Prüfe Shortcut:**
```bash
gsettings get org.gnome.settings-daemon.plugins.media-keys custom-keybindings
```

Falls leer: Führe `setup-gnome-shortcut.sh` nochmal aus

**Alternative**: Konfiguriere manuell in GNOME Einstellungen

### "Overlay erscheint nicht"

**Teste manuell:**
```bash
touch /tmp/dictation-state-$USER
~/.local/share/ai-dictation/venv/bin/python3 ~/.local/share/ai-dictation/animated_overlay.py
```

Falls Fehler: GTK3 nicht verfügbar (sollte auf GNOME vorhanden sein)

**Prüfe Logs:**
```bash
tail -f /tmp/dictation-daemon.log
```

### "Daemon startet nicht"

**Prüfe ob läuft:**
```bash
pgrep -af dictation-simple.py
```

**Starte manuell im Vordergrund:**
```bash
~/.local/share/ai-dictation/venv/bin/python3 ~/.local/share/ai-dictation/dictation-simple.py
```

Das zeigt Fehler direkt an.

### "Schlechte Erkennungsqualität"

1. **Näher am Mikrofon sprechen**
2. **Hintergrundgeräusche reduzieren**
3. **Deutlich sprechen, nicht zu schnell**
4. Modell ist schon `large-v3` (beste Qualität)

### "GPU wird nicht genutzt"

**Prüfe CUDA:**
```bash
nvidia-smi
```

Falls nicht verfügbar: In `dictation-simple.py` Zeile 22 ändern:
```python
DEVICE = "cpu"  # Nutzt CPU statt GPU
```

## 📊 Systemressourcen

- **Festplatte**: ~5 GB (large-v3 Modell + Dependencies)
- **RAM (Leerlauf)**: ~50 MB
- **RAM (Aufnahme/Transkription)**: ~4-6 GB
- **GPU-VRAM**: ~3 GB (large-v3 float16)
- **CPU (Leerlauf)**: ~0%
- **CPU (Transkription mit GPU)**: ~20-40%

## ❌ Deinstallation

```bash
# Daemon stoppen
pkill -f dictation-simple.py

# Autostart entfernen
rm ~/.config/autostart/ai-dictation.desktop

# Dateien löschen
rm -rf ~/.local/share/ai-dictation

# Cache leeren (optional)
rm -rf ~/.cache/whisper
```

GNOME Shortcut manuell entfernen in GNOME Einstellungen → Tastatur

---

**Viel Erfolg! 🚀**

Bei Problemen:
- Logs: `tail -f /tmp/dictation-daemon.log`
- Test-Script: `~/.local/share/ai-dictation/test-installation.sh`
- README: Ausführliche Dokumentation
