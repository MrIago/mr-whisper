#!/usr/bin/env python3
"""Widget flutuante do VoiceFlow — pill escura central com waveform animada.

Roda como processo próprio. Lê comandos do stdin (uma linha por comando):
  listening        → mostra a pill no modo "ouvindo", anima a waveform
  level <0..1>     → atualiza a amplitude da waveform (volume do mic agora)
  transcribing     → troca pro estado "transcrevendo" (spinner)
  hide             → some
  quit             → fecha o processo

Posiciona no centro-baixo do monitor que contém o ponteiro do mouse (a tela ativa).
"""
import sys
import math
import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gtk, Gdk, GLib  # noqa: E402

BARS = 13
PILL_W = 150
PILL_H = 52


class Pill(Gtk.Window):
    def __init__(self):
        super().__init__(type=Gtk.WindowType.POPUP)
        self.set_decorated(False)
        self.set_keep_above(True)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_accept_focus(False)
        self.set_app_paintable(True)
        self.set_default_size(PILL_W, PILL_H)
        self.set_resizable(False)

        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        if visual:
            self.set_visual(visual)

        self.mode = "listening"      # listening | transcribing | pasting
        self.level = 0.0             # amplitude alvo (0..1)
        self.bars = [0.08] * BARS    # alturas suavizadas por barra
        self.phase = 0.0

        self.area = Gtk.DrawingArea()
        self.area.set_size_request(PILL_W, PILL_H)
        self.area.connect("draw", self.on_draw)
        self.add(self.area)

        GLib.timeout_add(33, self.tick)  # ~30 fps

    def position(self):
        display = Gdk.Display.get_default()
        seat = display.get_default_seat()
        ptr = seat.get_pointer()
        _, px, py = ptr.get_position()
        mon = display.get_monitor_at_point(px, py)
        geo = mon.get_geometry()
        x = geo.x + (geo.width - PILL_W) // 2
        y = geo.y + int(geo.height * 0.82)  # parte de baixo, centralizado
        self.move(x, y)

    def tick(self):
        self.phase += 0.35
        # suaviza nível e gera alturas por barra (onda viva)
        for i in range(BARS):
            base = self.level
            wobble = 0.5 + 0.5 * math.sin(self.phase + i * 0.6)
            target = 0.08 + base * (0.25 + 0.75 * wobble)
            self.bars[i] += (target - self.bars[i]) * 0.4
        self.area.queue_draw()
        return True

    def on_draw(self, _widget, cr):
        w, h = self.get_allocated_width(), self.get_allocated_height()
        cr.set_operator(1)  # OVER
        cr.set_source_rgba(0, 0, 0, 0)
        cr.paint()

        # pill arredondada escura
        r = h / 2
        cr.set_source_rgba(0.10, 0.10, 0.12, 0.92)
        self._round_rect(cr, 0, 0, w, h, r)
        cr.fill()

        if self.mode == "transcribing":
            self._draw_spinner(cr, w, h)
        else:
            self._draw_waveform(cr, w, h)

    def _draw_waveform(self, cr, w, h):
        cx_pad = 18
        usable = w - cx_pad * 2
        gap = usable / BARS
        bw = gap * 0.45
        cr.set_source_rgba(0.95, 0.95, 0.97, 1.0)
        for i, lvl in enumerate(self.bars):
            bh = max(3, lvl * (h * 0.62))
            x = cx_pad + i * gap + (gap - bw) / 2
            y = (h - bh) / 2
            self._round_rect(cr, x, y, bw, bh, bw / 2)
            cr.fill()

    def _draw_spinner(self, cr, w, h):
        cx, cy = w / 2, h / 2
        rad = h * 0.22
        cr.set_line_width(3)
        for i in range(12):
            a = self.phase + i * (math.pi / 6)
            alpha = (i / 12.0)
            cr.set_source_rgba(0.95, 0.95, 0.97, alpha)
            cr.move_to(cx + math.cos(a) * rad * 0.55, cy + math.sin(a) * rad * 0.55)
            cr.line_to(cx + math.cos(a) * rad, cy + math.sin(a) * rad)
            cr.stroke()

    @staticmethod
    def _round_rect(cr, x, y, w, h, r):
        r = min(r, w / 2, h / 2)
        cr.new_sub_path()
        cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
        cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
        cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
        cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
        cr.close_path()


class App:
    def __init__(self):
        self.pill = Pill()
        self.visible = False
        GLib.io_add_watch(sys.stdin, GLib.IO_IN, self.on_stdin)

    def on_stdin(self, _src, _cond):
        # drena TODAS as linhas disponíveis — se 'transcribing' e 'pasting'
        # chegam coladas, ler só uma deixava o widget preso no estado anterior.
        line = sys.stdin.readline()
        if not line:
            Gtk.main_quit()
            return False
        while line:
            if not self._handle(line):
                return False
            # readline bloquearia se não houver mais dados; só continua se
            # houver algo já bufferizado. Saímos no fim da linha simples.
            break
        return True

    def _handle(self, line: str) -> bool:
        cmd, _, arg = line.strip().partition(" ")
        if cmd == "listening":
            self.pill.mode = "listening"
            self.pill.level = 0.0
            self.pill.position()
            self.pill.show_all()
            self.visible = True
        elif cmd == "level":
            try:
                self.pill.level = max(0.0, min(1.0, float(arg)))
            except ValueError:
                pass
        elif cmd == "transcribing":
            self.pill.mode = "transcribing"
        elif cmd == "hide":
            self.pill.hide()
            self.visible = False
        elif cmd == "quit":
            Gtk.main_quit()
            return False
        return True


if __name__ == "__main__":
    App()
    Gtk.main()
