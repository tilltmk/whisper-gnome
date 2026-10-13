# KI-Diktierung für GNOME – jetzt mit Cohere Transcribe

Lokale Spracherkennung per Tastenkürzel: sprechen, Text landet in der
Zwischenablage. Läuft komplett offline auf der eigenen NVIDIA-GPU.

> **Neu: Cohere Transcribe statt Whisper.**
> Die Diktierung nutzt jetzt [Cohere Transcribe](https://huggingface.co/CohereLabs/cohere-transcribe-03-2026)
> (`cohere-transcribe-03-2026`), ein 2-Milliarden-Parameter-Modell mit Conformer-Encoder,
> 14 Sprachen inklusive Deutsch, Apache-2.0-Lizenz. Whisper ist vollständig entfernt –
> auch nicht als Rückfallebene.

## Wie schnell?

Gemessen mit einer gemeinfreien LibriVox-Lesung (Kafka, *Die Verwandlung*, Kapitel 1,
[archive.org](https://archive.org/details/verwandlung_mw_0811_librivox)).
Das Modell war bereits geladen, bfloat16 auf einer Laptop-GPU mit 8 GB VRAM:

| Audio | Transkribiert in | Tempo |
|---|---|---|
| 10 Sekunden | 0,34 s | 29× Echtzeit |
| 1 Minute | 0,71 s | 84× Echtzeit |
| 5 Minuten | 2,81 s | 107× Echtzeit |
| **41 Minuten (ganzes Kapitel)** | **21,5 s** | **115× Echtzeit** |

**Wortfehlerrate: 0,8 %** auf 6.104 Wörtern. Verglichen wurde mit dem Originaltext
von Project Gutenberg, ohne Groß-/Kleinschreibung und Satzzeichen.

Einordnung: Das ist eine saubere, vorgelesene Aufnahme. Spontane Sprache, Hall
oder Störgeräusche ergeben höhere Fehlerraten. Ein typisches Diktat von
10–30 Sekunden ist praktisch sofort in der Zwischenablage.

## Funktionen

- **100 % lokal** – kein Audio verlässt den Rechner
- **Tastenkürzel** über GNOME (Vorgabe: Shift + Strg + Leertaste), gleiche Taste startet und stoppt
- **Automatischer Stopp** nach 5 Sekunden Stille, höchstens 5 Minuten je Aufnahme
- **Lange Diktate** werden an leisen Stellen in Stücke ≤ 35 s zerlegt (die Obergrenze des Modells)
- **Pegel-Aufbereitung** für leise oder versetzte Mikrofone (DC-Abzug, Aussteuerung)
- **Animiertes Overlay** während der Aufnahme
- **Transkriptions-Dienst** für andere lokale Programme über einen Unix-Socket (siehe unten)

## Voraussetzungen

- Linux mit GNOME (Wayland), PipeWire, `wl-copy`
- NVIDIA-GPU mit CUDA und mindestens ~5 GB freiem VRAM; bfloat16-Hardware ab Ampere empfohlen
- Python 3.14 mit den Paketen aus `requirements.txt`

## Installation

```bash
git clone https://github.com/tilltmk/whisper-gnome.git ~/.local/share/ai-dictation
pip install --user -r ~/.local/share/ai-dictation/requirements.txt

# Modell (~3,9 GB) nach ~/.cache/cohere-transcribe – das offizielle Repo erfordert
# die Annahme der Nutzungsbedingungen auf Hugging Face und ein Zugriffstoken.
hf download CohereLabs/cohere-transcribe-03-2026 --local-dir ~/.cache/cohere-transcribe
```

Das Modell bringt eigenen Modellcode mit und wird deshalb mit `trust_remote_code=True`
geladen. Wer den Modellordner austauscht, sollte diesen Code vorher durchsehen.

### Als Dienst starten

`~/.config/systemd/user/ai-dictation.service`:

```ini
[Unit]
Description=AI Dictation Daemon
After=graphical-session.target

[Service]
ExecStart=/usr/bin/python3.14 -u %h/.local/share/ai-dictation/dictation-simple.py
Restart=on-failure
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=default.target
```

```bash
systemctl --user daemon-reload
systemctl --user enable --now ai-dictation.service
~/.local/share/ai-dictation/setup-gnome-shortcut.sh
```

## Nutzung

1. Tastenkürzel drücken – Ton und Overlay zeigen die laufende Aufnahme
2. Sprechen
3. Tastenkürzel erneut drücken oder 5 Sekunden schweigen
4. `Strg+V` – der Text ist in der Zwischenablage

## Speicher und Rückfallebenen

| | |
|---|---|
| Modell auf der GPU | ~3,7 GB Gewichte (bfloat16), insgesamt ~4,7 GB VRAM |
| Modell bleibt geladen | ab dem ersten Diktat, damit jedes weitere sofort startet |
| GPU voll (anderer Prozess) | kein Ausweichen auf die CPU, das nächste Diktat versucht es erneut |
| CPU-Ebene | nur ohne CUDA **und** mit ≥ 12 GB freiem RAM (float32, ~8 GB, langsam) |

**Warum bfloat16 und nicht float16?** Der Modellcode maskiert Aufmerksamkeitswerte mit
fest kodierten `-1e9`. float16 reicht nur bis ±65.504, die Transkription bricht dann mit
`value cannot be converted to type c10::Half without overflow` ab. bfloat16 hat den
Wertebereich von float32 bei halbem Speicherbedarf.

## Transkriptions-Dienst für andere Programme

Eine zweite Kopie des Modells passt neben der Diktierung nicht auf eine 8-GB-Karte.
Der Daemon bietet die bereits geladene Instanz deshalb über einen Unix-Socket an:
`$XDG_RUNTIME_DIR/ai-dictation-asr.sock`, nur für den eigenen Benutzer lesbar (0600).

Protokoll: eine JSON-Zeile hin, JSON-Zeilen zurück.

```json
{"aktion": "transkribieren", "audio": "/pfad/eingang.f32", "rate": 16000, "sprache": "de",
 "abschnitte": [[0, 160000], [160000, 240000]]}
```

- `audio`: float32-Rohdaten, mono, 16 kHz, eigene Datei mit Endung `.f32`
- `abschnitte`: `[Offset, Länge]` in Samples, je höchstens 35 s
- Antworten: `{"fortschritt": n, "gesamt": m}` während der Arbeit, am Ende `{"ok": true, "texte": [...]}`
- `{"aktion": "status"}` liefert, ob und wo das Modell geladen ist

Diktieren hat Vorrang: Ein Diktat wartet höchstens einen Stapel (~1–2 s GPU).
Läuft das Modell auf der CPU, werden fremde Aufträge abgelehnt.

## Fehlersuche

```bash
journalctl --user -u ai-dictation -f      # Live-Log
systemctl --user restart ai-dictation      # Neustart
~/.local/share/ai-dictation/test-installation.sh
```

- **Keine Aufnahmequelle:** Auf manchen AMD-Laptops registriert sich das interne
  Mikrofon erst nach WirePlumber. Der Daemon startet WirePlumber dann selbst neu.
- **„Grafikspeicher belegt“:** Ein anderer Prozess hält den VRAM. Das nächste Diktat versucht es erneut.
- **Schlechte Erkennung:** näher ans Mikrofon, Störgeräusche reduzieren. Die Sprache ist
  in `TRANSCRIBE_LANGUAGE` festgelegt (Vorgabe `de`).

## Lizenz

- Code: siehe Repository
- Modell: Cohere Transcribe, Apache 2.0, © Cohere
