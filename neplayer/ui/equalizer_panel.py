"""Equalizer popover: on/off, presets, response curve, preamp + 10 band sliders, enhancements."""
import math

import gi

gi.require_version('Gtk', '4.0')
from gi.repository import Gdk, GLib, Gtk

from neplayer.player import equalizer as eq

_CURVE_DB = 13.0          # vertical range of the graph (±)
_F_LO, _F_HI = 20.0, 20000.0


def _rgba(widget, name, fallback):
    ok, c = widget.get_style_context().lookup_color(name)
    if ok:
        return c
    c = Gdk.RGBA()
    c.parse(fallback)
    return c


class ResponseCurve(Gtk.DrawingArea):
    """Live frequency-response graph of the current EQ."""

    def __init__(self):
        super().__init__()
        self.add_css_class('eq-curve')
        self.set_content_height(104)
        self.set_hexpand(True)
        self.gains, self.preamp, self.active = list(eq.FLAT), 0.0, True
        self._freqs = [_F_LO * (_F_HI / _F_LO) ** (i / 199) for i in range(200)]
        self.set_draw_func(self._draw)

    def update(self, gains, preamp, active):
        self.gains, self.preamp, self.active = list(gains), float(preamp), active
        self.queue_draw()

    @staticmethod
    def _x(f, w):
        return w * math.log(f / _F_LO) / math.log(_F_HI / _F_LO)

    @staticmethod
    def _y(db, h):
        db = max(-_CURVE_DB, min(_CURVE_DB, db))
        return h / 2 - db / _CURVE_DB * (h / 2 - 6)

    def _draw(self, _area, cr, w, h):
        fg = self.get_style_context().get_color()
        accent = _rgba(self, 'ff_accent', '#3b82f6')
        # grid: 0 dB line, ±6/±12 dB, and the band centres
        cr.set_line_width(1)
        for db in (-12, -6, 6, 12):
            cr.set_source_rgba(fg.red, fg.green, fg.blue, 0.07)
            y = round(self._y(db, h)) + 0.5
            cr.move_to(0, y)
            cr.line_to(w, y)
            cr.stroke()
        for f in eq.BANDS:
            cr.set_source_rgba(fg.red, fg.green, fg.blue, 0.05)
            x = round(self._x(f, w)) + 0.5
            cr.move_to(x, 0)
            cr.line_to(x, h)
            cr.stroke()
        cr.set_source_rgba(fg.red, fg.green, fg.blue, 0.22)
        y0 = round(self._y(0, h)) + 0.5
        cr.move_to(0, y0)
        cr.line_to(w, y0)
        cr.stroke()
        # dB scale
        cr.set_font_size(9)
        cr.set_source_rgba(fg.red, fg.green, fg.blue, 0.45)
        for db in (12, 6, -6, -12):
            cr.move_to(4, self._y(db, h) - 2)
            cr.show_text(f'{db:+d}')

        gains = self.gains if self.active else list(eq.FLAT)
        pre = self.preamp if self.active else 0.0
        resp = eq.response_db(gains, pre, self._freqs)
        pts = [(self._x(f, w), self._y(db, h)) for f, db in zip(self._freqs, resp)]
        a = 1.0 if self.active else 0.35
        # filled area between the curve and 0 dB
        cr.move_to(pts[0][0], y0)
        for x, y in pts:
            cr.line_to(x, y)
        cr.line_to(pts[-1][0], y0)
        cr.close_path()
        cr.set_source_rgba(accent.red, accent.green, accent.blue, 0.18 * a)
        cr.fill()
        cr.set_line_width(2.2)
        cr.set_line_join(1)  # round
        cr.move_to(*pts[0])
        for x, y in pts[1:]:
            cr.line_to(x, y)
        cr.set_source_rgba(accent.red, accent.green, accent.blue, a)
        cr.stroke()
        # band handles
        for f, g in zip(eq.BANDS, gains):
            x = self._x(f, w)
            y = self._y(eq.response_db(gains, pre, [f])[0], h)
            cr.arc(x, y, 3, 0, 2 * math.pi)
            cr.set_source_rgba(accent.red, accent.green, accent.blue, a)
            cr.fill()


class _Band(Gtk.Box):
    """One vertical slider with its dB readout above and frequency below."""

    def __init__(self, label, lo, hi, on_change, css=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.add_css_class('eq-band')
        if css:
            self.add_css_class(css)
        self.value_lbl = Gtk.Label(label='0')
        self.value_lbl.add_css_class('eq-value')
        self.scale = Gtk.Scale.new_with_range(Gtk.Orientation.VERTICAL, lo, hi, 0.5)
        self.scale.set_inverted(True)            # up = boost
        self.scale.set_draw_value(False)
        self.scale.set_has_origin(False)
        self.scale.set_vexpand(True)
        self.scale.set_size_request(-1, 150)
        self.scale.set_halign(Gtk.Align.CENTER)
        self.scale.set_tooltip_text('Double-click to reset')
        self._on_change = on_change
        self._handler = self.scale.connect('value-changed', self._changed)
        dbl = Gtk.GestureClick()
        dbl.connect('pressed', lambda _g, n, _x, _y: n == 2 and self.scale.set_value(0))
        self.scale.add_controller(dbl)
        freq = Gtk.Label(label=label)
        freq.add_css_class('eq-freq')
        self.append(self.value_lbl)
        self.append(self.scale)
        self.append(freq)

    def _changed(self, scale):
        v = round(scale.get_value() * 2) / 2
        self._show(v)
        self._on_change(v)

    def _show(self, v):
        self.value_lbl.set_label('0' if v == 0 else f'{v:+g}')

    def set_value(self, v):
        """Set without notifying (sync from settings)."""
        self.scale.handler_block(self._handler)
        self.scale.set_value(v)
        self.scale.handler_unblock(self._handler)
        self._show(v)


class EqualizerPanel(Gtk.Popover):
    def __init__(self, settings):
        super().__init__()
        self.add_css_class('eq-panel')
        self.settings = settings
        self._syncing = False

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.add_css_class('eq-panel-box')

        # header: title + on/off
        head = Gtk.Box(spacing=8)
        title = Gtk.Label(label='Equalizer', xalign=0, hexpand=True)
        title.add_css_class('eq-title')
        head.append(title)
        self.switch = Gtk.Switch(valign=Gtk.Align.CENTER, tooltip_text='Equalizer on / off (E opens this panel)')
        self.switch.connect('notify::active', lambda s, _p: self._set('eq_enabled', s.get_active()))
        head.append(self.switch)
        box.append(head)

        # presets row
        row = Gtk.Box(spacing=6)
        self.preset_dd = Gtk.DropDown.new_from_strings([])
        self.preset_dd.set_hexpand(True)
        self.preset_dd.set_tooltip_text('Preset')
        self._preset_handler = self.preset_dd.connect('notify::selected', self._on_preset)
        row.append(self.preset_dd)
        self.save_btn = Gtk.Button(icon_name='list-add-symbolic', tooltip_text='Save as a new preset')
        self.save_btn.connect('clicked', lambda *_: self._show_save(True))
        self.del_btn = Gtk.Button(icon_name='list-remove-symbolic', tooltip_text='Delete this preset')
        self.del_btn.connect('clicked', self._delete_preset)
        self.reset_btn = Gtk.Button(icon_name='edit-undo-symbolic', tooltip_text='Reset to flat')
        self.reset_btn.connect('clicked', self._reset)
        for b in (self.save_btn, self.del_btn, self.reset_btn):
            b.add_css_class('flat')
            row.append(b)
        box.append(row)

        # inline "save preset" row
        save_row = Gtk.Box(spacing=6)
        self.name_entry = Gtk.Entry(placeholder_text='Preset name', hexpand=True)
        self.name_entry.connect('activate', self._save_preset)
        self.name_entry.connect('changed', lambda e: self.confirm_btn.set_sensitive(bool(e.get_text().strip())))
        self.confirm_btn = Gtk.Button(label='Save')
        self.confirm_btn.add_css_class('suggested-action')
        self.confirm_btn.connect('clicked', self._save_preset)
        cancel = Gtk.Button(label='Cancel')
        cancel.connect('clicked', lambda *_: self._show_save(False))
        save_row.append(self.name_entry)
        save_row.append(cancel)
        save_row.append(self.confirm_btn)
        self.save_rev = Gtk.Revealer(transition_type=Gtk.RevealerTransitionType.SLIDE_DOWN)
        self.save_rev.set_child(save_row)
        box.append(self.save_rev)

        self.curve = ResponseCurve()
        box.append(self.curve)

        # sliders: preamp | 10 bands
        self.controls = Gtk.Box(spacing=2)
        self.controls.add_css_class('eq-sliders')
        self.preamp = _Band('Pre', eq.PREAMP_MIN, eq.PREAMP_MAX,
                            lambda v: self._set('eq_preamp', float(v)), css='eq-preamp')
        self.preamp.set_tooltip_text('Preamp: lower it if heavy boosts sound harsh')
        self.controls.append(self.preamp)
        sep = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        sep.add_css_class('eq-sep')
        self.controls.append(sep)
        self.bands = []
        for i, lbl in enumerate(eq.BAND_LABELS):
            b = _Band(lbl, -eq.GAIN_MAX, eq.GAIN_MAX, lambda v, i=i: self._set_band(i, v))
            b.set_hexpand(True)
            self.bands.append(b)
            self.controls.append(b)
        box.append(self.controls)

        # enhancements
        enh = Gtk.Box(spacing=6, homogeneous=True)
        self.toggles = {}
        for name, key, tip in eq.ENHANCEMENTS:
            t = Gtk.ToggleButton(label=name, tooltip_text=tip)
            t.add_css_class('eq-chip')
            t.connect('toggled', lambda b, k=key: self._set(k, b.get_active()))
            self.toggles[key] = t
            enh.append(t)
        self.enh_box = enh
        box.append(enh)

        self.set_child(box)
        self.sync()
        self._sig = settings.connect('changed', lambda _s, k: k in eq.KEYS and self.sync())
        self.connect('closed', lambda *_: self._show_save(False))

    # ------------------------------------------------------------ state
    def _set(self, key, value):
        if not self._syncing:
            self.settings.set(key, value)

    def _set_band(self, i, v):
        if self._syncing:
            return
        gains = eq.clean_gains(self.settings['eq_gains'])
        gains[i] = v
        self.settings.set('eq_gains', gains)
        self.settings.set('eq_preset', eq.preset_for(gains, self.settings['eq_user_presets']))
        if not self.settings['eq_enabled']:   # touching a slider means "I want EQ"
            self.settings.set('eq_enabled', True)

    def _preset_names(self):
        names = list(eq.PRESETS) + sorted(self.settings['eq_user_presets'])
        if self.settings['eq_preset'] == eq.CUSTOM:
            names.append(eq.CUSTOM)
        return names

    def sync(self):
        """Refresh every control from the settings."""
        s = self.settings
        self._syncing = True
        try:
            on = bool(s['eq_enabled'])
            self.switch.set_active(on)
            gains = eq.clean_gains(s['eq_gains'])
            for b, g in zip(self.bands, gains):
                b.set_value(g)
            self.preamp.set_value(float(s['eq_preamp']))
            for key, t in self.toggles.items():
                t.set_active(bool(s[key]))
            names = self._preset_names()
            self.preset_dd.handler_block(self._preset_handler)
            self.preset_dd.set_model(Gtk.StringList.new(names))
            cur = s['eq_preset'] if s['eq_preset'] in names else eq.preset_for(gains, s['eq_user_presets'])
            self.preset_dd.set_selected(names.index(cur) if cur in names else 0)
            self.preset_dd.handler_unblock(self._preset_handler)
            self.del_btn.set_sensitive(cur in s['eq_user_presets'])
            for w in (self.controls, self.preset_dd, self.enh_box):
                w.set_opacity(1.0 if on else 0.55)
            self.curve.update(gains, s['eq_preamp'], on)
        finally:
            self._syncing = False

    def _on_preset(self, dd, _p):
        if self._syncing:
            return
        item = dd.get_selected_item()
        name = item.get_string() if item is not None else 'Flat'
        values = eq.PRESETS.get(name) or self.settings['eq_user_presets'].get(name)
        if values is None:          # "Custom" re-selected: nothing to load
            return
        self.settings.set('eq_gains', eq.clean_gains(values))
        self.settings.set('eq_preset', name)
        self.settings.set('eq_enabled', True)

    def _reset(self, *_):
        self.settings.set('eq_gains', list(eq.FLAT))
        self.settings.set('eq_preamp', 0.0)
        self.settings.set('eq_preset', 'Flat')

    def _show_save(self, show):
        self.save_rev.set_reveal_child(show)
        if show:
            cur = self.settings['eq_preset']
            self.name_entry.set_text('' if cur in eq.PRESETS or cur == eq.CUSTOM else cur)
            self.confirm_btn.set_sensitive(bool(self.name_entry.get_text().strip()))
            GLib.idle_add(lambda: self.name_entry.grab_focus() and False)

    def _save_preset(self, *_):
        name = self.name_entry.get_text().strip()[:32]
        if not name:
            return
        if name in eq.PRESETS or name == eq.CUSTOM:
            name += ' (mine)'
        user = dict(self.settings['eq_user_presets'])
        user[name] = eq.clean_gains(self.settings['eq_gains'])
        self.settings.set('eq_user_presets', user)
        self.settings.set('eq_preset', name)
        self._show_save(False)

    def _delete_preset(self, *_):
        name = self.settings['eq_preset']
        user = dict(self.settings['eq_user_presets'])
        if user.pop(name, None) is None:
            return
        self.settings.set('eq_user_presets', user)
        self.settings.set('eq_preset', eq.preset_for(self.settings['eq_gains'], user))
