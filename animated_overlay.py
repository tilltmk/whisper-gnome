#!/usr/bin/env python3.14
"""
Animiertes Overlay für KI-Diktierung
Kleines rundes Fenster mit lila radialen Wellen
"""

import os
import sys
import math
import time

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


STATE_FILE = f"/tmp/dictation-state-{os.getenv('USER')}"


class VoiceWaveOverlay(Gtk.Window):
    """Kleines animiertes Overlay mit lila radialen Wellen."""

    def __init__(self):
        super().__init__()

        # Window-Setup
        self.set_decorated(False)
        self.set_app_paintable(True)
        self.set_keep_above(True)
        self.set_type_hint(Gdk.WindowTypeHint.NOTIFICATION)

        # Transparenz
        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        if visual:
            self.set_visual(visual)

        # Kleines rundes Fenster
        self.set_default_size(200, 200)
        self.set_position(Gtk.WindowPosition.NONE)

        # Position rechts unten
        self.connect('realize', self.on_realize)

        # Animation
        self.phase = 0.0
        self.bars = []

        # Erstelle 30 Wellen-Balken mit individuellen Eigenschaften
        for i in range(30):
            self.bars.append({
                'height': 0.3,
                'speed': 0.1 + (i % 3) * 0.05,
                'offset': i * 0.4
            })

        # Draw-Event
        self.connect('draw', self.on_draw)

        # Animation-Timer (60 FPS)
        GLib.timeout_add(16, self.update_animation)

        # Prüfe ob Recording noch läuft
        GLib.timeout_add(100, self.check_recording)

        self.show_all()

    def on_realize(self, widget):
        """Positioniere Fenster rechts unten."""
        screen = widget.get_screen()
        monitor = screen.get_monitor_at_window(screen.get_active_window() or screen.get_root_window())
        geometry = screen.get_monitor_geometry(monitor)

        x = geometry.x + geometry.width - 220
        y = geometry.y + geometry.height - 220

        self.move(x, y)

    def on_draw(self, widget, cr):
        """Zeichne rundes Fenster mit radialen lila Wellen."""
        width = widget.get_allocated_width()
        height = widget.get_allocated_height()
        center_x = width / 2
        center_y = height / 2
        radius = min(width, height) / 2 - 10

        # Transparenter Hintergrund
        cr.set_source_rgba(0, 0, 0, 0)
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)

        # Dunkler semi-transparenter Kreis als Hintergrund
        cr.arc(center_x, center_y, radius, 0, 2 * math.pi)
        cr.set_source_rgba(0.05, 0.05, 0.1, 0.95)
        cr.fill()

        # Radiale Wellen-Balken
        bar_count = len(self.bars)
        for i, bar in enumerate(self.bars):
            angle = (2 * math.pi * i / bar_count)

            # Berechne dynamische Balkenhöhe mit Sinus-Wave
            bar_height = abs(math.sin(self.phase * bar['speed'] + bar['offset'])) * 0.6 + 0.2
            bar['height'] = bar_height

            # Start- und Endpunkt des Balkens (vom Zentrum nach außen)
            start_r = radius * 0.3
            end_r = radius * (0.5 + bar_height * 0.4)

            x1 = center_x + start_r * math.cos(angle)
            y1 = center_y + start_r * math.sin(angle)
            x2 = center_x + end_r * math.cos(angle)
            y2 = center_y + end_r * math.sin(angle)

            # Lila Farbe mit variierendem Alpha basierend auf Höhe
            alpha = 0.6 + bar['height'] * 0.4
            cr.set_source_rgba(0.6, 0.3, 0.9, alpha)  # Lila
            cr.set_line_width(3)
            cr.move_to(x1, y1)
            cr.line_to(x2, y2)
            cr.stroke()

        # Pulsierender Mittelpunkt
        pulse = math.sin(self.phase * 0.3) * 0.2 + 0.8
        cr.arc(center_x, center_y, 8 * pulse, 0, 2 * math.pi)
        cr.set_source_rgba(0.8, 0.4, 1.0, 0.9)  # Helles Lila
        cr.fill()

        return False

    def update_animation(self):
        """Aktualisiere Animation."""
        self.phase += 0.1
        self.queue_draw()
        return True

    def check_recording(self):
        """Prüfe ob Aufnahme noch läuft."""
        if not os.path.exists(STATE_FILE):
            # State-File gelöscht = Aufnahme gestoppt
            Gtk.main_quit()
            return False
        return True


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
