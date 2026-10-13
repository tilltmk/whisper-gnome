# Quickstart

Lokale Diktierung mit **Cohere Transcribe** (2B, Deutsch und 13 weitere Sprachen) –
41 Minuten Audio in 21 Sekunden, Wortfehlerrate 0,8 % (Messung siehe README).

## Einrichten

```bash
pip install --user -r ~/.local/share/ai-dictation/requirements.txt
hf download CohereLabs/cohere-transcribe-03-2026 --local-dir ~/.cache/cohere-transcribe
systemctl --user enable --now ai-dictation.service     # Unit-Datei: siehe README
~/.local/share/ai-dictation/setup-gnome-shortcut.sh
```

Falls das Shortcut-Skript nicht klappt: GNOME Einstellungen → Tastatur →
Eigene Tastenkombinationen → „+“, Befehl `~/.local/share/ai-dictation/trigger-dictation.sh`,
Kürzel z. B. Shift + Strg + Leertaste.

## Diktieren

1. Kürzel drücken – Overlay erscheint
2. Sprechen
3. Kürzel erneut drücken oder 5 Sekunden schweigen
4. `Strg+V`

## Wenn etwas hakt

```bash
journalctl --user -u ai-dictation -f
~/.local/share/ai-dictation/test-installation.sh
```
