"""GPU visualizer widget: real audio analysis → GLSL preset → screen."""
import logging
import random
import time

import gi
import numpy as np

gi.require_version('Gtk', '4.0')
from gi.repository import GLib, GObject, Gtk

from neplayer.visualizer import gl as G
from neplayer.visualizer.analysis import HISTORY, N_BANDS, N_WAVE, Analyzer, PcmSource
from neplayer.visualizer.presets import load_presets

log = logging.getLogger(__name__)

VERTEX = """#version 330 core
void main() {
    vec2 p = vec2((gl_VertexID << 1) & 2, gl_VertexID & 2);   // one full-screen triangle
    gl_Position = vec4(p * 2.0 - 1.0, 0.0, 1.0);
}
"""

# Colour themes: three stops each (0..1 RGB). 'accent' and 'cover' are computed.
THEMES = {
    'neon':   ((0.0, 0.9, 1.0), (0.62, 0.2, 1.0), (1.0, 0.15, 0.6)),
    'sunset': ((1.0, 0.55, 0.15), (0.95, 0.25, 0.45), (0.45, 0.2, 0.75)),
    'ocean':  ((0.1, 0.85, 0.75), (0.15, 0.5, 0.95), (0.35, 0.2, 0.8)),
    'aurora': ((0.2, 1.0, 0.6), (0.1, 0.75, 0.85), (0.6, 0.35, 1.0)),
    'fire':   ((1.0, 0.85, 0.2), (1.0, 0.45, 0.05), (0.85, 0.05, 0.1)),
    'classic': ((0.15, 0.95, 0.25), (0.95, 0.9, 0.15), (1.0, 0.2, 0.1)),
    'mono':   ((0.85, 0.85, 0.9), (0.6, 0.6, 0.68), (1.0, 1.0, 1.0)),
}
THEME_NAMES = [('accent', 'Accent colour'), ('cover', 'From album art'), ('neon', 'Neon'), ('sunset', 'Sunset'),
               ('ocean', 'Ocean'), ('aurora', 'Aurora'), ('fire', 'Fire'), ('classic', 'Classic (green-red)'),
               ('mono', 'Monochrome')]
BACKGROUNDS = [('cover', 'Blurred album art'), ('dark', 'Dark'), ('black', 'Black'), ('gradient', 'Gradient')]
QUALITY_FPS = {'high': 60, 'balanced': 30, 'low': 24}

from neplayer.config import VIZ_DEFAULTS as DEFAULTS  # noqa: E402


def hex_rgb(h):
    h = h.lstrip('#')
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def accent_stops(hex_color):
    import colorsys
    r, g, b = hex_rgb(hex_color)
    hue, light, sat = colorsys.rgb_to_hls(r, g, b)
    return (colorsys.hls_to_rgb((hue - 0.08) % 1, min(0.7, light + 0.1), sat),
            (r, g, b),
            colorsys.hls_to_rgb((hue + 0.12) % 1, min(0.75, light + 0.15), min(1, sat * 1.1)))


def cover_stops(path):
    """Three vivid colours from album art (PIL median-cut)."""
    try:
        from PIL import Image
        import colorsys
        with Image.open(path) as im:
            q = im.convert('RGB').resize((64, 64)).quantize(colors=8)
            pal = q.getpalette()[:24]
            counts = sorted(q.getcolors(), reverse=True)
        cols = []
        for _n, idx in counts:
            r, g, b = (c / 255 for c in pal[idx * 3: idx * 3 + 3])
            h, l, s = colorsys.rgb_to_hls(r, g, b)
            cols.append(colorsys.hls_to_rgb(h, min(max(l, 0.45), 0.7), max(s, 0.55)))
        while len(cols) < 3:
            cols.append(cols[-1] if cols else (0.4, 0.6, 1.0))
        return tuple(cols[:3])
    except Exception:
        return None


class VisualizerView(Gtk.GLArea):
    """`clock()` must return (playing: bool, seconds: float) for the current track."""

    __gsignals__ = {'preset-changed': (GObject.SignalFlags.RUN_FIRST, None, (str,))}

    def __init__(self, settings, clock):
        super().__init__()
        self.settings = settings
        self.clock = clock
        self.set_auto_render(False)
        self.set_hexpand(True)
        self.set_vexpand(True)
        self.set_can_target(False)
        self.presets = load_presets()
        self._ids = [p.id for p in self.presets]
        self.analyzer = Analyzer(self._s('viz_fft'), self._s('viz_sensitivity'), self._s('viz_bass'))
        self.source = None
        self._gl = None
        self._programs = {}
        self._failed = set()
        self._vao = 0
        self._tex = None
        self._tick = None
        self._last = time.monotonic()
        self._last_draw = 0.0
        self._time = 0.0
        self._cover_colors = None
        self._cover_pixels = None      # pending album art upload (numpy uint8)
        self._cover_tex = 0
        self._cover_data = False       # CPU copy, re-uploaded if the GL context is recreated
        self.connect('realize', self._on_realize)
        self.connect('unrealize', self._on_unrealize)
        self.connect('render', self._on_render)
        self.connect('map', lambda *_: self._start())
        self.connect('unmap', lambda *_: self._stop())
        settings.connect('changed', self._on_setting)

    # ------------------------------------------------------------- settings
    def _s(self, key):
        return self.settings.get(key, DEFAULTS.get(key))

    def _on_setting(self, _s, key):
        if key == 'viz_fft':
            self.analyzer.set_fft_size(self._s('viz_fft'))
        elif key == 'viz_sensitivity':
            self.analyzer.sensitivity = float(self._s('viz_sensitivity'))
        elif key == 'viz_bass':
            self.analyzer.bass_response = float(self._s('viz_bass'))
        elif key == 'viz_preset':
            self.emit('preset-changed', self.preset.name)

    @property
    def preset(self):
        pid = self._s('viz_preset')
        for p in self.presets:
            if p.id == pid:
                return p
        return self.presets[0]

    def step_preset(self, delta):
        i = self._ids.index(self.preset.id) if self.preset.id in self._ids else 0
        self.settings.set('viz_preset', self._ids[(i + delta) % len(self._ids)])

    def random_preset(self):
        choices = [i for i in self._ids if i != self.preset.id]
        self.settings.set('viz_preset', random.choice(choices))

    # --------------------------------------------------------------- source
    def set_track(self, path, cover_path=None):
        if self.source is not None:
            self.source.close()
        self.source = PcmSource(path) if path else None
        self.set_cover(cover_path)

    def set_cover(self, cover_path):
        self._cover_colors = cover_stops(cover_path) if cover_path else None
        self._cover_pixels = self._cover_data = False  # "no cover" until the art is loaded
        if cover_path:
            try:
                from PIL import Image
                with Image.open(cover_path) as im:
                    img = im.convert('RGBA').resize((512, 512))
                    self._cover_pixels = self._cover_data = np.ascontiguousarray(
                        np.asarray(img, np.uint8)[::-1])  # GL: bottom row first
            except Exception:
                log.exception('visualizer: could not load album art')

    def stop(self):
        if self.source is not None:
            self.source.close()
            self.source = None

    # -------------------------------------------------------------- frames
    def _start(self):
        if self._tick is None:
            self._last = time.monotonic()
            self._tick = self.add_tick_callback(self._on_tick)

    def _stop(self):
        if self._tick is not None:
            self.remove_tick_callback(self._tick)
            self._tick = None

    def _on_tick(self, _widget, _clock):
        now = time.monotonic()
        fps = QUALITY_FPS.get(self._s('viz_quality'), 60)
        if now - self._last_draw < 1.0 / fps - 0.002:
            return GLib.SOURCE_CONTINUE
        dt = now - self._last
        self._last = now
        self._last_draw = now
        playing, t = self.clock()
        data = None
        if playing and self.source is not None:
            data = self.source.window(t, self.analyzer.fft_size)
        self.analyzer.analyze(data, dt, playing=playing and data is not None)
        motion = 0.35 if self._s('viz_reduced_motion') else 1.0
        self._time += dt * float(self._s('viz_speed')) * motion
        self.queue_render()
        return GLib.SOURCE_CONTINUE

    # -------------------------------------------------------------------- GL
    def _on_realize(self, _area):
        self.make_current()
        if self.get_error() is not None:
            log.warning('visualizer GL context failed: %s', self.get_error())
            return
        try:
            g = G.GL()
            vao = G.C.c_uint(0)
            g.GenVertexArrays(1, G.C.byref(vao))
            self._vao = vao.value
            self._tex = (g.float_texture(N_BANDS, 4), g.float_texture(N_WAVE, 2), g.float_texture(N_BANDS, HISTORY))
            self._gl = g
        except Exception:
            log.exception('visualizer: OpenGL unavailable')
            self._gl = None

    def _on_unrealize(self, _area):
        self._stop()
        if self._gl is not None:
            self.make_current()
            for prog in self._programs.values():
                self._gl.DeleteProgram(prog)
        self._programs.clear()
        self._gl = None
        self._cover_tex = 0
        self._cover_pixels = self._cover_data  # upload again in the next context

    def _program(self, preset):
        prog = self._programs.get(preset.id)
        if prog is None and preset.id not in self._failed:
            try:
                prog = self._gl.program(VERTEX, preset.source)
                self._programs[preset.id] = prog
            except RuntimeError as e:
                log.error('visualizer preset %s failed to compile:\n%s', preset.id, e)
                self._failed.add(preset.id)
        return prog

    def _colors(self):
        theme = self._s('viz_theme')
        if theme == 'cover' and self._cover_colors:
            return self._cover_colors
        if theme in THEMES:
            return THEMES[theme]
        return accent_stops(self.settings.get('accent', '#3b82f6'))

    def _on_render(self, _area, _ctx):
        g = self._gl
        if g is None:
            return True
        preset = self.preset
        prog = self._program(preset) or self._program(self.presets[0])
        scale = self.get_scale_factor()
        w, h = self.get_width() * scale, self.get_height() * scale
        g.Viewport(0, 0, w, h)
        g.ClearColor(0, 0, 0, 0)
        g.Clear(G.GL_COLOR_BUFFER_BIT)
        if not prog:
            return True
        f = self.analyzer.frame
        g.upload(self._tex[0], np.ascontiguousarray(np.stack([f.bands, f.bands_l, f.bands_r, f.peaks]), np.float32))
        g.upload(self._tex[1], np.ascontiguousarray(np.stack([f.wave_l, f.wave_r]), np.float32))
        g.upload(self._tex[2], np.ascontiguousarray(f.history, np.float32))
        g.UseProgram(prog)
        loc = lambda n: g.GetUniformLocation(prog, n.encode())  # noqa: E731
        for unit, (tex, name) in enumerate(zip(self._tex, ('uSpec', 'uWave', 'uHist'))):
            g.ActiveTexture(G.GL_TEXTURE0 + unit)
            g.BindTexture(G.GL_TEXTURE_2D, tex)
            g.Uniform1i(loc(name), unit)
        reduced = bool(self._s('viz_reduced_motion'))
        quality_density = {'high': 1.0, 'balanced': 0.8, 'low': 0.5}.get(self._s('viz_quality'), 1.0)
        g.Uniform2f(loc('uRes'), float(w), float(h))
        g.Uniform1f(loc('uTime'), self._time)
        for name, val in (('uBass', f.bass), ('uMid', f.mid), ('uTreble', f.treble), ('uLevel', f.level),
                          ('uBeat', 0.0 if reduced else f.beat)):
            g.Uniform1f(loc(name), float(val))
        for name, rgb in zip(('uC1', 'uC2', 'uC3'), self._colors()):
            g.Uniform3f(loc(name), *map(float, rgb))
        g.Uniform1f(loc('uGlow'), float(self._s('viz_glow')))
        g.Uniform1f(loc('uBright'), float(self._s('viz_brightness')))
        g.Uniform1f(loc('uDensity'), float(self._s('viz_density')) * quality_density)
        g.Uniform1f(loc('uMotion'), 0.35 if reduced else 1.0)
        bg = self._s('viz_background')
        g.Uniform1i(loc('uBgMode'), {'cover': 1, 'gradient': 2}.get(bg, 0))
        g.Uniform3f(loc('uBg'), *((0.0, 0.0, 0.0) if bg == 'black' else (0.045, 0.045, 0.06)))
        if self._cover_pixels is not None:          # new album art (or none) for this track
            if self._cover_tex:
                g.DeleteTextures(1, G.C.byref(G.C.c_uint(self._cover_tex)))
                self._cover_tex = 0
            if self._cover_pixels is not False:
                self._cover_tex = g.rgba_texture(512, 512, self._cover_pixels)
            self._cover_pixels = None
        g.ActiveTexture(G.GL_TEXTURE0 + 3)
        g.BindTexture(G.GL_TEXTURE_2D, self._cover_tex)
        g.Uniform1i(loc('uCover'), 3)
        g.Uniform1f(loc('uHasCover'), 1.0 if self._cover_tex else 0.0)
        g.BindVertexArray(self._vao)
        g.DrawArrays(G.GL_TRIANGLES, 0, 3)
        return True
