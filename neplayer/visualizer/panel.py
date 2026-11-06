"""Visualizer controls (popover): preset, look and performance settings."""
import gi

gi.require_version('Gtk', '4.0')
from gi.repository import Gtk

from neplayer.visualizer.view import BACKGROUNDS, DEFAULTS, THEME_NAMES


class VisualizerPanel(Gtk.Popover):
    def __init__(self, view):
        super().__init__()
        self.add_css_class('viz-panel')
        self.view = view
        self.settings = view.settings
        self._widgets = {}

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.add_css_class('viz-panel-box')
        title = Gtk.Label(label='Visualizer', xalign=0)
        title.add_css_class('viz-panel-title')
        box.append(title)

        # Preset picker + prev / random / next
        row = Gtk.Box(spacing=6)
        names = [p.name for p in view.presets]
        self.preset_dd = Gtk.DropDown.new_from_strings(names)
        self.preset_dd.set_hexpand(True)
        self.preset_dd.set_enable_search(True)
        self.preset_dd.connect('notify::selected', self._on_preset)
        for icon, tip, cb in (('go-previous-symbolic', 'Previous preset (,)', lambda: view.step_preset(-1)),
                              ('nep-random-symbolic', 'Random preset (R)', view.random_preset),
                              ('go-next-symbolic', 'Next preset (.)', lambda: view.step_preset(1))):
            b = Gtk.Button(icon_name=icon, tooltip_text=tip)
            b.add_css_class('flat')
            b.connect('clicked', lambda _b, cb=cb: cb())
            if icon == 'go-previous-symbolic':
                row.append(b)
                row.append(self.preset_dd)
            else:
                row.append(b)
        box.append(row)

        grid = Gtk.Grid(column_spacing=12, row_spacing=6)
        r = 0
        for key, label, lo, hi in (('viz_speed', 'Animation speed', 0.2, 2.5), ('viz_sensitivity', 'Sensitivity', 0.3, 3.0),
                                   ('viz_bass', 'Bass response', 0.5, 2.0), ('viz_density', 'Particle density', 0.0, 1.0),
                                   ('viz_glow', 'Glow intensity', 0.3, 2.5), ('viz_brightness', 'Brightness', 0.5, 1.6)):
            grid.attach(self._label(label), 0, r, 1, 1)
            sc = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, lo, hi, 0.05)
            sc.set_draw_value(False)
            sc.set_size_request(180, -1)
            sc.set_hexpand(True)
            sc.set_value(float(self.settings.get(key, DEFAULTS[key])))
            sc.connect('value-changed', lambda w, k=key: self.settings.set(k, round(w.get_value(), 2)))
            self._widgets[key] = sc
            grid.attach(sc, 1, r, 1, 1)
            r += 1
        for key, label, options in (('viz_theme', 'Colours', THEME_NAMES),
                                    ('viz_background', 'Background', BACKGROUNDS),
                                    ('viz_fft', 'FFT size', [(1024, '1024 (fastest)'), (2048, '2048'), (4096, '4096 (finest)')]),
                                    ('viz_quality', 'Performance', [('high', 'High · 60 fps'), ('balanced', 'Balanced · 30 fps'),
                                                                    ('low', 'Low power · 24 fps')])):
            grid.attach(self._label(label), 0, r, 1, 1)
            dd = Gtk.DropDown.new_from_strings([o[1] for o in options])
            cur = self.settings.get(key, DEFAULTS[key])
            for i, (val, _l) in enumerate(options):
                if val == cur:
                    dd.set_selected(i)
            dd.connect('notify::selected', lambda d, _p, k=key, o=options: self.settings.set(k, o[d.get_selected()][0]))
            self._widgets[key] = (dd, options)
            grid.attach(dd, 1, r, 1, 1)
            r += 1
        grid.attach(self._label('Reduce motion'), 0, r, 1, 1)
        sw = Gtk.Switch(halign=Gtk.Align.START, active=bool(self.settings.get('viz_reduced_motion', False)))
        sw.connect('notify::active', lambda w, _p: self.settings.set('viz_reduced_motion', w.get_active()))
        self._widgets['viz_reduced_motion'] = sw
        grid.attach(sw, 1, r, 1, 1)
        box.append(grid)

        reset = Gtk.Button(label='Reset to defaults')
        reset.connect('clicked', lambda *_: self.reset())
        box.append(reset)
        self.set_child(box)
        self._sync_preset()
        self.settings.connect('changed', lambda _s, k: self._sync_preset() if k == 'viz_preset' else None)

    @staticmethod
    def _label(text):
        lbl = Gtk.Label(label=text, xalign=0)
        lbl.add_css_class('viz-label')
        return lbl

    def _sync_preset(self):
        ids = [p.id for p in self.view.presets]
        pid = self.view.preset.id
        if pid in ids and self.preset_dd.get_selected() != ids.index(pid):
            self.preset_dd.set_selected(ids.index(pid))

    def _on_preset(self, dd, _p):
        i = dd.get_selected()
        if 0 <= i < len(self.view.presets):
            self.settings.set('viz_preset', self.view.presets[i].id)

    def reset(self):
        for key, val in DEFAULTS.items():
            self.settings.set(key, val)
            w = self._widgets.get(key)
            if isinstance(w, Gtk.Scale):
                w.set_value(float(val))
            elif isinstance(w, Gtk.Switch):
                w.set_active(bool(val))
            elif isinstance(w, tuple):
                dd, options = w
                for i, (v, _l) in enumerate(options):
                    if v == val:
                        dd.set_selected(i)
        self._sync_preset()
