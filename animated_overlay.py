#!/usr/bin/env python3.14
"""
Animiertes Overlay für KI-Diktierung

Zeigt live, was am Mikrofon ankommt - keine Sinus-Schleife:
- Strahlenkranz: Spektrum in 28 Baendern, links/rechts gespiegelt, tiefe
  Frequenzen unten, Zischlaute oben. Mit fallenden Spitzenmarken.
- Ring in der Mitte: die echte Wellenform der letzten 64 ms.
- Mitte: Aufnahmezeit. Rand: Countdown bis zum Auto-Stopp, sobald es still ist.
- Nach der Aufnahme: Verarbeiten-Zustand, bis der Text in der Zwischenablage ist.

Die Daten schreibt der Daemon aus dem Audio-Callback in LIVE_FILE
(siehe LivePegel in dictation-simple.py).
"""

import os
import sys
import math
import mmap

# Setze Display-Variablen BEVOR GTK importiert wird
if 'DISPLAY' not in os.environ:
    os.environ['DISPLAY'] = ':0'
if 'WAYLAND_DISPLAY' not in os.environ:
    os.environ['WAYLAND_DISPLAY'] = 'wayland-0'
if 'XDG_RUNTIME_DIR' not in os.environ:
    os.environ['XDG_RUNTIME_DIR'] = f'/run/user/{os.getuid()}'

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib
import cairo
import numpy as np


STATE_FILE = f"/tmp/dictation-state-{os.getenv('USER')}"
LIVE_FILE = os.path.join(os.environ['XDG_RUNTIME_DIR'], "ai-dictation-live.f32")
LIVE_HEADER = 8
PHASE_KALIBRIEREN = 0
PHASE_AUFNAHME = 1
PHASE_VERARBEITEN = 2

GROESSE = 220
KALIBRIERZEIT = 0.5      # wie NOISE_CALIBRATION_TIME im Daemon
EINBLENDEN = 0.18        # Sekunden
AUSBLENDEN = 0.25        # stop_overlay() wartet bis zu 1 s
VERALTET_NACH = 0.25     # so lange ohne neuen Frame gilt der Stream als stumm

# Anzeige-Dynamik. Die Mikrofone liegen um Groessenordnungen auseinander (DMIC
# um 0.003, USB-Mikro deutlich hoeher), eine feste Skala zeigt bei einem von
# beiden nichts. Deshalb wird je Band das Grundrauschen in dB mitgefuehrt und nur
# angezeigt, was darueber liegt. Nebeneffekt: Lueftergrummeln in den tiefen
# Baendern wird herausgerechnet, Sprache leuchtet ueber das ganze Spektrum.
DYNAMIK_DB = 26.0               # so weit ueber dem Rauschen ist ein Balken voll
RAUSCHEN_ABSTAND_DB = 6.0       # Rauschen selbst soll nicht flackern
RAUSCHEN_ANSTIEG_DB_S = 2.0     # langsam nach oben, sonst frisst Dauerreden sich selbst auf
# Nach unten zuegig, aber nicht sofort: sonst klebt die Schaetzung an den
# Minima, und die tiefen Baender (nur 1-2 FFT-Bins, +-5 dB Streuung) flackern.
RAUSCHEN_ABFALL_RATE = 3.0      # (1/s)

ANSTIEG = 30.0           # Balken: schnelles Ansprechen (1/s)
ABFALL = 7.0             # Balken: weiches Zurueckfallen (1/s)
SPITZE_HALTEN = 0.35     # Sekunden, bevor die Spitzenmarke faellt
SPITZE_FALL = 1.6        # Fallbeschleunigung der Spitzenmarke (Anteil/s^2)
WELLE_RAUSCHABSTAND = 20.0  # Rauschen fuellt so nur ~1/6 der Ringhoehe

# Farbverlauf von leise nach laut: Violett -> Magenta -> Rosa -> fast Weiss
FARBEN = [
    (0.00, (0.42, 0.26, 0.96)),
    (0.55, (0.82, 0.30, 0.98)),
    (0.85, (1.00, 0.42, 0.72)),
    (1.00, (1.00, 0.88, 0.96)),
]
WARNFARBE = (1.00, 0.62, 0.22)   # Countdown bis zum Auto-Stopp


def farbe(t):
    """Interpoliert den Farbverlauf an der Stelle t (0..1)."""
    t = min(max(t, 0.0), 1.0)
    for (t0, c0), (t1, c1) in zip(FARBEN, FARBEN[1:]):
        if t <= t1:
            f = (t - t0) / (t1 - t0)
            return tuple(a + (b - a) * f for a, b in zip(c0, c1))
    return FARBEN[-1][1]


def mischen(a, b, f):
    return tuple(x + (y - x) * f for x, y in zip(a, b))


def annaehern(aktuell, ziel, rate, dt):
    """Exponentielle Glaettung, unabhaengig von der Bildrate."""
    return aktuell + (ziel - aktuell) * (1.0 - math.exp(-rate * dt))


class LiveQuelle:
    """Liest den Pegel-Puffer des Daemons. lesen() gibt None, solange er fehlt."""

    def __init__(self):
        self._mm = None
        self._zaehler = None
        self._zaehler_zeit = 0.0

    def lesen(self, jetzt):
        if self._mm is None:
            try:
                with open(LIVE_FILE, "rb") as f:
                    self._mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
            except (OSError, ValueError):
                return None

        werte = np.frombuffer(self._mm, dtype=np.float32).copy()
        anz_baender = int(werte[6])
        anz_welle = int(werte[7])
        if anz_baender <= 0 or len(werte) < LIVE_HEADER + anz_baender + anz_welle:
            return None

        if werte[0] != self._zaehler:
            self._zaehler = werte[0]
            self._zaehler_zeit = jetzt

        b0 = LIVE_HEADER
        w0 = b0 + anz_baender
        return {
            'frisch': jetzt - self._zaehler_zeit < VERALTET_NACH,
            'phase': int(werte[1]),
            'pegel': float(werte[2]),
            'stille': float(werte[4]),
            'zeit': float(werte[5]),
            'baender': werte[b0:w0],
            'welle': werte[w0:w0 + anz_welle],
        }


class RauschFolger:
    """Fuehrt das Grundrauschen in dB mit und normiert darauf (0..1)."""

    def __init__(self):
        self.rauschen = None

    def normieren(self, linear, dt):
        db = 20.0 * np.log10(np.maximum(linear, 1e-9))
        if self.rauschen is None:
            self.rauschen = db.copy()
        runter = self.rauschen + (db - self.rauschen) * (1.0 - math.exp(-RAUSCHEN_ABFALL_RATE * dt))
        rauf = self.rauschen + RAUSCHEN_ANSTIEG_DB_S * dt
        self.rauschen = np.where(db < self.rauschen, runter, np.minimum(rauf, db))
        return np.clip((db - self.rauschen - RAUSCHEN_ABSTAND_DB) / DYNAMIK_DB, 0.0, 1.0)


class VoiceWaveOverlay(Gtk.Window):
    """Rundes Overlay, das die Live-Audiodaten des Daemons zeichnet."""

    def __init__(self):
        super().__init__()

        # Window-Setup
        self.set_decorated(False)
        self.set_app_paintable(True)
        self.set_keep_above(True)
        self.set_accept_focus(False)
        self.set_type_hint(Gdk.WindowTypeHint.NOTIFICATION)

        # Transparenz
        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        if visual:
            self.set_visual(visual)

        self.set_default_size(GROESSE, GROESSE)
        self.set_position(Gtk.WindowPosition.NONE)

        # Position rechts unten
        self.connect('realize', self.on_realize)

        # Datenquelle und Anzeigezustand
        self.quelle = LiveQuelle()
        self.band_rauschen = RauschFolger()
        self.pegel_rauschen = RauschFolger()
        self.baender = None          # angezeigte Balkenhoehen 0..1
        self.spitzen = None          # Spitzenmarken 0..1
        self.spitzen_halt = None     # Restzeit, bevor die Marke faellt
        self.spitzen_tempo = None
        self.welle = None            # angezeigte Wellenform, -1..1
        self.welle_ref = 1e-3        # Bezugsamplitude der Wellenform (AGC)
        self.pegel = 0.0
        self.stille = 0.0
        self.aufnahmezeit = 0.0
        self.kalibriert = 0.0        # 0..1, Ring baut sich waehrend der Kalibrierung auf
        self.verarbeiten = 0.0       # 0..1, Ueberblendung in den Verarbeiten-Zustand
        self.sichtbar = 0.0          # 0..1, Ein-/Ausblenden
        self.ausblenden = False
        self.ausblenden_seit = None
        self.uhr = 0.0
        self.letzter_frame = None

        self.connect('draw', self.on_draw)
        # Bildtakt der Anzeige statt fester 16-ms-Uhr: synchron zum Monitor
        self.add_tick_callback(self.on_tick)

        # Prüfe ob Recording noch läuft
        GLib.timeout_add(50, self.check_recording)

        self.show_all()

    def on_realize(self, widget):
        """Positioniere Fenster rechts unten (unter Wayland entscheidet Mutter)."""
        screen = widget.get_screen()
        monitor = screen.get_monitor_at_window(screen.get_active_window() or screen.get_root_window())
        geometry = screen.get_monitor_geometry(monitor)

        x = geometry.x + geometry.width - GROESSE - 20
        y = geometry.y + geometry.height - GROESSE - 20

        self.move(x, y)

        # Leere Eingabe-Region: Klicks gehen durch das Overlay hindurch an das
        # Fenster darunter, statt im transparenten Rand haengen zu bleiben.
        self.input_shape_combine_region(cairo.Region())

    # ─── Zustand ────────────────────────────────────────────────────────────

    def on_tick(self, widget, frame_clock):
        jetzt = frame_clock.get_frame_time() / 1e6
        dt = 1 / 60 if self.letzter_frame is None else min(jetzt - self.letzter_frame, 0.1)
        self.letzter_frame = jetzt
        self.uhr += dt

        self.aktualisieren(jetzt, dt)

        if self.ausblenden:
            self.sichtbar = max(0.0, self.sichtbar - dt / AUSBLENDEN)
            if self.sichtbar <= 0.0:
                Gtk.main_quit()
                return False
        else:
            self.sichtbar = min(1.0, self.sichtbar + dt / EINBLENDEN)

        self.queue_draw()
        return True

    def aktualisieren(self, jetzt, dt):
        daten = self.quelle.lesen(jetzt)
        phase = daten['phase'] if daten else PHASE_KALIBRIEREN
        live = daten is not None and daten['frisch'] and phase != PHASE_VERARBEITEN

        self.verarbeiten = annaehern(
            self.verarbeiten, 1.0 if phase == PHASE_VERARBEITEN else 0.0, 6.0, dt
        )
        if daten is None:
            return

        anz = len(daten['baender'])
        if self.baender is None or len(self.baender) != anz:
            self.baender = np.zeros(anz)
            self.spitzen = np.zeros(anz)
            self.spitzen_halt = np.zeros(anz)
            self.spitzen_tempo = np.zeros(anz)
            self.welle = np.zeros(len(daten['welle']))

        if phase == PHASE_KALIBRIEREN:
            self.kalibriert = min(1.0, daten['zeit'] / KALIBRIERZEIT)
        else:
            self.kalibriert = 1.0
        if phase != PHASE_VERARBEITEN:
            self.aufnahmezeit = daten['zeit']

        # Balken: schnell rauf, weich runter. Ohne frische Daten (Stream
        # haengt, Aufnahme vorbei) fallen sie auf null statt einzufrieren.
        if live:
            ziel = self.band_rauschen.normieren(daten['baender'], dt)
            pegel_ziel = float(self.pegel_rauschen.normieren(np.array([daten['pegel']]), dt)[0])
        else:
            ziel = np.zeros(anz)
            pegel_ziel = 0.0
        rate = np.where(ziel > self.baender, ANSTIEG, ABFALL)
        self.baender += (ziel - self.baender) * (1.0 - np.exp(-rate * dt))
        self.pegel = annaehern(self.pegel, pegel_ziel, ANSTIEG if pegel_ziel > self.pegel else ABFALL, dt)

        # Spitzenmarken: springen mit, halten kurz, fallen dann beschleunigt
        hoeher = self.baender >= self.spitzen
        self.spitzen = np.where(hoeher, self.baender, self.spitzen)
        self.spitzen_halt = np.where(hoeher, SPITZE_HALTEN, self.spitzen_halt - dt)
        self.spitzen_tempo = np.where(hoeher | (self.spitzen_halt > 0), 0.0, self.spitzen_tempo + SPITZE_FALL * dt)
        self.spitzen = np.maximum(self.baender, self.spitzen - self.spitzen_tempo * dt)

        # Wellenform mit eigener Aussteuerung: Bezug ist die juengste Spitze,
        # die langsam zerfaellt. Untergrenze ist das Rauschen, damit Stille als
        # feines Zittern erscheint und nicht auf volle Hoehe aufgeblasen wird.
        if live:
            roh = daten['welle']
            spitze = float(np.abs(roh).max()) if len(roh) else 0.0
            rauschen_lin = 10 ** (float(self.pegel_rauschen.rauschen[0]) / 20.0) if self.pegel_rauschen.rauschen is not None else 1e-4
            self.welle_ref = max(spitze, self.welle_ref * math.exp(-1.5 * dt), rauschen_lin * WELLE_RAUSCHABSTAND, 1e-6)
            ziel_welle = np.clip(roh / self.welle_ref, -1.0, 1.0)
        else:
            ziel_welle = np.zeros_like(self.welle)
        self.welle += (ziel_welle - self.welle) * (1.0 - math.exp(-40.0 * dt))

        self.stille = annaehern(self.stille, daten['stille'] if phase == PHASE_AUFNAHME else 0.0, 12.0, dt)

    def check_recording(self):
        """Prüfe ob Aufnahme noch läuft - wenn nicht, ausblenden."""
        if not os.path.exists(STATE_FILE):
            # State-File gelöscht = fertig
            if not self.ausblenden:
                self.ausblenden = True
                self.ausblenden_seit = self.uhr
            # Ohne Bildtakt (Fenster verdeckt/minimiert) kaeme on_tick nie ans
            # Ende des Ausblendens - dann hier beenden.
            elif self.uhr - self.ausblenden_seit > AUSBLENDEN + 0.3 or self.letzter_frame is None:
                Gtk.main_quit()
                return False
        return True

    # ─── Zeichnen ───────────────────────────────────────────────────────────

    def on_draw(self, widget, cr):
        width = widget.get_allocated_width()
        height = widget.get_allocated_height()

        # Transparenter Hintergrund
        cr.set_source_rgba(0, 0, 0, 0)
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)

        if self.sichtbar <= 0.0:
            return False

        # Ein-/Ausblenden: weich skalieren und als Ganzes transparent machen
        weich = 1.0 - (1.0 - self.sichtbar) ** 3
        cr.push_group()
        cr.translate(width / 2, height / 2)
        cr.scale(0.86 + 0.14 * weich, 0.86 + 0.14 * weich)
        radius = min(width, height) / 2 - 8

        self.zeichne_scheibe(cr, radius)
        self.zeichne_rand(cr, radius)
        self.zeichne_kranz(cr, radius)
        self.zeichne_welle(cr, radius)
        self.zeichne_mitte(cr, radius)

        cr.pop_group_to_source()
        cr.paint_with_alpha(weich)
        return False

    def zeichne_scheibe(self, cr, r):
        # Aeusserer Schein, der mit der Lautstaerke aufleuchtet
        schein = 0.10 + 0.35 * self.pegel * (1.0 - self.verarbeiten)
        c = farbe(0.3 + 0.6 * self.pegel)
        verlauf = cairo.RadialGradient(0, 0, r * 0.85, 0, 0, r + 8)
        verlauf.add_color_stop_rgba(0, *c, schein)
        verlauf.add_color_stop_rgba(1, *c, 0.0)
        cr.arc(0, 0, r + 8, 0, 2 * math.pi)
        cr.set_source(verlauf)
        cr.fill()

        # Dunkle Scheibe
        verlauf = cairo.RadialGradient(0, -r * 0.3, r * 0.1, 0, 0, r)
        verlauf.add_color_stop_rgba(0, 0.11, 0.07, 0.20, 0.95)
        verlauf.add_color_stop_rgba(1, 0.03, 0.02, 0.07, 0.95)
        cr.arc(0, 0, r, 0, 2 * math.pi)
        cr.set_source(verlauf)
        cr.fill()

        cr.arc(0, 0, r - 0.5, 0, 2 * math.pi)
        cr.set_source_rgba(0.65, 0.45, 1.0, 0.22)
        cr.set_line_width(1)
        cr.stroke()

    def zeichne_rand(self, cr, r):
        """Rand: baut sich beim Kalibrieren auf, zeigt dann den Auto-Stopp-Countdown."""
        ring_r = r - 4
        cr.set_line_cap(cairo.LINE_CAP_ROUND)

        if self.verarbeiten > 0.01:
            # Verarbeiten: zwei Kometen laufen um den Rand
            for versatz in (0.0, math.pi):
                kopf = self.uhr * 4.2 + versatz
                for i in range(14):
                    a = kopf - i * 0.07
                    cr.arc(0, 0, ring_r, a - 0.07, a)
                    cr.set_source_rgba(*farbe(0.75), self.verarbeiten * (1 - i / 14) * 0.9)
                    cr.set_line_width(3 * (1 - i / 20))
                    cr.stroke()

        start = -math.pi / 2
        if self.kalibriert < 1.0:
            laenge = self.kalibriert
            c = farbe(0.2)
            alpha = 0.55
        else:
            # Erst ab spuerbarer Stille anzeigen, sonst flackert der Ring
            # zwischen zwei Woertern.
            sichtbar = min(max((self.stille - 0.12) / 0.15, 0.0), 1.0)
            laenge = 1.0 - self.stille
            c = mischen(farbe(0.25), WARNFARBE, min(self.stille * 1.4, 1.0))
            alpha = 0.18 + 0.7 * sichtbar
        alpha *= 1.0 - self.verarbeiten
        if laenge > 0.002 and alpha > 0.01:
            cr.arc(0, 0, ring_r, start, start + 2 * math.pi * laenge)
            cr.set_source_rgba(*c, alpha)
            cr.set_line_width(2.5)
            cr.stroke()

    def zeichne_kranz(self, cr, r):
        """Spektrum als Strahlenkranz, gespiegelt: tief unten, hoch oben."""
        if self.baender is None:
            return
        anz = len(self.baender)
        innen = r * 0.47
        laenge = r * 0.37
        zusammen = 1.0 - self.verarbeiten
        cr.set_line_cap(cairo.LINE_CAP_ROUND)

        for i in range(anz):
            h = float(self.baender[i]) * zusammen
            p = float(self.spitzen[i]) * zusammen
            anteil = (i + 0.5) / anz
            c = farbe(0.15 + 0.85 * h)
            for winkel in (math.pi / 2 - anteil * math.pi, math.pi / 2 + anteil * math.pi):
                dx, dy = math.cos(winkel), math.sin(winkel)
                aussen = innen + r * 0.025 + h * laenge

                # Schein, dann scharfer Strahl darueber
                cr.move_to(dx * innen, dy * innen)
                cr.line_to(dx * aussen, dy * aussen)
                cr.set_source_rgba(*c, 0.10 + 0.25 * h)
                cr.set_line_width(7)
                cr.stroke_preserve()
                cr.set_source_rgba(*c, 0.45 + 0.55 * h)
                cr.set_line_width(2.6)
                cr.stroke()

                if p > 0.04:
                    pr = innen + r * 0.025 + p * laenge + 4.5
                    cr.arc(dx * pr, dy * pr, 1.3, 0, 2 * math.pi)
                    cr.set_source_rgba(*farbe(0.6 + 0.4 * p), 0.35 + 0.6 * p)
                    cr.fill()

    def zeichne_welle(self, cr, r):
        """Die echte Wellenform als Ring um die Mitte."""
        basis = r * 0.31
        if self.welle is None or len(self.welle) < 2:
            welle = np.zeros(64)
        else:
            welle = self.welle

        anz = len(welle)
        # Enden auslaufen lassen, damit sich der Ring ohne Naht schliesst
        rand = np.minimum(np.arange(anz), np.arange(anz)[::-1]) / (anz * 0.08)
        welle = welle * np.minimum(rand, 1.0)

        zusammen = 1.0 - self.verarbeiten
        # Verarbeiten: der Ring atmet ruhig, statt auszuschlagen
        atmen = 1.0 + 0.05 * math.sin(self.uhr * 3.0) * self.verarbeiten
        amplitude = r * 0.11 * zusammen
        drehung = self.uhr * 0.35
        winkel = drehung + np.linspace(0, 2 * math.pi, anz, endpoint=False)
        radien = basis * atmen + welle * amplitude
        xs = np.cos(winkel) * radien
        ys = np.sin(winkel) * radien

        cr.move_to(xs[0], ys[0])
        for x, y in zip(xs[1:], ys[1:]):
            cr.line_to(x, y)
        cr.close_path()

        c = farbe(0.35 + 0.65 * self.pegel)
        fuellung = cairo.RadialGradient(0, 0, 0, 0, 0, basis * 1.3)
        fuellung.add_color_stop_rgba(0, *c, 0.05 + 0.30 * self.pegel)
        fuellung.add_color_stop_rgba(1, *c, 0.0)
        cr.set_source(fuellung)
        cr.fill_preserve()

        cr.set_line_join(cairo.LINE_JOIN_ROUND)
        cr.set_source_rgba(*c, 0.18)
        cr.set_line_width(6)
        cr.stroke_preserve()
        cr.set_source_rgba(*c, 0.75 + 0.25 * self.pegel)
        cr.set_line_width(1.8)
        cr.stroke()

    def zeichne_mitte(self, cr, r):
        """Aufnahmezeit, beim Verarbeiten ein Kreisel."""
        if self.verarbeiten < 0.95:
            minuten, sekunden = divmod(int(self.aufnahmezeit), 60)
            text = f"{minuten}:{sekunden:02d}"
            cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
            cr.set_font_size(r * 0.15)
            ausmass = cr.text_extents(text)
            cr.move_to(-ausmass.x_advance / 2, ausmass.height / 2)
            cr.set_source_rgba(1.0, 0.95, 1.0, (0.55 + 0.4 * self.pegel) * (1.0 - self.verarbeiten))
            cr.show_text(text)

        if self.verarbeiten > 0.05:
            cr.set_line_cap(cairo.LINE_CAP_ROUND)
            for i in range(3):
                a = self.uhr * (2.6 + i * 0.9) + i * 2.1
                kr = r * (0.12 + 0.045 * i)
                cr.arc(0, 0, kr, a, a + 1.6)
                cr.set_source_rgba(*farbe(0.4 + 0.25 * i), 0.85 * self.verarbeiten)
                cr.set_line_width(2.2)
                cr.stroke()


def main():
    """Hauptfunktion."""
    # Prüfe ob State-File existiert
    if not os.path.exists(STATE_FILE):
        print("State-File nicht gefunden, beende...")
        sys.exit(0)

    overlay = VoiceWaveOverlay()
    Gtk.main()


if __name__ == "__main__":
    main()
