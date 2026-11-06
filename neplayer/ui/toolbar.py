"""Library header bar, laid out like Lumen's toolbar."""
import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Adw, Gio, GObject, Gtk

SORT_OPTIONS = [
    ('recent', 'Recently Added'),
    ('name_asc', 'Name (A–Z)'),
    ('name_desc', 'Name (Z–A)'),
    ('duration_desc', 'Longest First'),
    ('duration_asc', 'Shortest First'),
    ('size_desc', 'Largest Files'),
    ('resolution_desc', 'Highest Resolution'),
    ('artist', 'Artist / Album'),
]

FILTERS = {
    'resolution': ('Resolution', [('', 'Any'), ('4k', '4K'), ('1080', '1080p'), ('720', '720p'),
                                  ('sd', 'SD (below 720p)')]),
    'format': ('Format', [('', 'Any')] + [(e, e.upper()) for e in
                                           ('mp4', 'mkv', 'webm', 'avi', 'mov', 'wmv', 'flv',
                                            'm4v', 'ts', 'mpg', 'mpeg', '3gp')]),
    'duration': ('Duration', [('', 'Any'), ('short', 'Under 4 min'), ('medium', '4–20 min'),
                              ('long', 'Over 20 min')]),
}


class LibraryHeader(Gtk.Box):
    __gsignals__ = {
        'search-changed': (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        'filters-changed': (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.bar = Adw.HeaderBar()
        self.bar.add_css_class('flat')
        self.append(self.bar)
        self.filters = {'resolution': '', 'format': '', 'duration': '', 'favorites': False}

        def icon_btn(icon, tip, action=None):
            b = Gtk.Button(icon_name=icon, tooltip_text=tip)
            b.add_css_class('flat')
            b.add_css_class('hb-btn')
            if action:
                b.set_action_name(action)
            return b

        # ---- left: sidebar, back, forward, page title (Lumen layout)
        self.sidebar_btn = Gtk.ToggleButton(icon_name='sidebar-show-symbolic',
                                            tooltip_text='Toggle sidebar (F9)')
        self.sidebar_btn.add_css_class('flat')
        self.sidebar_btn.add_css_class('hb-btn')
        self.bar.pack_start(self.sidebar_btn)
        self.back_btn = icon_btn('go-previous-symbolic', 'Back (Alt+←)', 'win.go-back')
        self.fwd_btn = icon_btn('go-next-symbolic', 'Forward (Alt+→)', 'win.go-forward')
        self.bar.pack_start(self.back_btn)
        self.bar.pack_start(self.fwd_btn)

        titles = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER)
        titles.add_css_class('page-titles')
        self.page_title = Gtk.Label(xalign=0, ellipsize=3)
        self.page_title.add_css_class('header-title')
        self.page_sub = Gtk.Label(xalign=0, ellipsize=3, visible=False)
        self.page_sub.add_css_class('header-subtitle')
        titles.append(self.page_title)
        titles.append(self.page_sub)
        self.bar.pack_start(titles)
        self.bar.set_title_widget(Gtk.Box())

        # ---- right side (pack_end adds right-to-left)
        more = Gio.Menu()
        sec = Gio.Menu()
        sec.append('Open File…', 'win.open-file')
        sec.append('Add Folder…', 'win.add-folder')
        sec.append('Scan Library', 'win.rescan')
        more.append_section(None, sec)
        sec = Gio.Menu()
        sec.append('Keyboard Shortcuts', 'win.shortcuts')
        sec.append('About ENPlayer', 'win.about')
        more.append_section(None, sec)

        self.bar.pack_end(icon_btn('emblem-system-symbolic', 'Settings (Ctrl+,)', 'win.settings'))
        more_btn = Gtk.MenuButton(icon_name='view-more-horizontal-symbolic', menu_model=more,
                                  tooltip_text='More')
        more_btn.add_css_class('flat')
        more_btn.add_css_class('hb-btn')
        self.bar.pack_end(more_btn)

        theme = Gio.Menu()
        theme.append('Dark', "win.theme('dark')")
        theme.append('Light', "win.theme('light')")
        theme.append('Glass', "win.theme('glass')")
        self.theme_btn = Gtk.MenuButton(menu_model=theme, tooltip_text='Theme')
        self.theme_btn.add_css_class('flat')
        self.theme_btn.add_css_class('hb-btn')
        self.bar.pack_end(self.theme_btn)
        self.bar.pack_end(icon_btn('document-open-symbolic', 'Open file (Ctrl+O)', 'win.open-file'))
        self.bar.pack_end(icon_btn('folder-open-symbolic', 'Add folder (Ctrl+N)', 'win.add-folder'))

        sep = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        sep.add_css_class('hb-sep')
        self.bar.pack_end(sep)

        self.bar.pack_end(icon_btn('view-refresh-symbolic', 'Scan library (F5)', 'win.rescan'))
        density = Gio.Menu()
        density.append('Compact', "win.density('small')")
        density.append('Comfortable', "win.density('medium')")
        density.append('Large', "win.density('large')")
        dens = Gtk.MenuButton(icon_name='view-grid-symbolic', menu_model=density, tooltip_text='Grid density')
        dens.add_css_class('flat')
        dens.add_css_class('hb-btn')
        self.bar.pack_end(dens)

        self.filter_btn = Gtk.MenuButton(icon_name='ff-filter-symbolic', tooltip_text='Filter')
        self.filter_btn.add_css_class('flat')
        self.filter_btn.add_css_class('hb-btn')
        self.filter_btn.set_popover(self._build_filter_popover())
        self.bar.pack_end(self.filter_btn)

        sort = Gio.Menu()
        for key, label in SORT_OPTIONS:
            sort.append(label, f"win.sort('{key}')")
        self.sort_btn = Gtk.MenuButton(icon_name='view-sort-descending-symbolic', menu_model=sort,
                                       tooltip_text='Sort')
        self.sort_btn.add_css_class('flat')
        self.sort_btn.add_css_class('hb-btn')
        self.bar.pack_end(self.sort_btn)

        self.search = Gtk.SearchEntry(placeholder_text='Search videos, files and folders…')
        self.search.set_size_request(280, -1)
        self.search.set_valign(Gtk.Align.CENTER)
        self.search.add_css_class('library-search')
        self.search.connect('search-changed', lambda e: self.emit('search-changed', e.get_text()))
        self.bar.pack_end(self.search)

    def set_theme_icon(self, theme):
        self.theme_btn.set_icon_name({'light': 'weather-clear-symbolic',
                                      'glass': 'weather-few-clouds-symbolic'}.get(theme, 'weather-clear-night-symbolic'))

    def set_page(self, title, subtitle=''):
        self.page_title.set_label(title)
        self.page_sub.set_label(subtitle or '')
        self.page_sub.set_visible(bool(subtitle))
        self.page_sub.set_tooltip_text(subtitle or None)

    def _build_filter_popover(self):
        pop = Gtk.Popover()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.add_css_class('filter-popover')
        title = Gtk.Label(label='Filter videos', xalign=0)
        title.add_css_class('heading')
        box.append(title)
        grid = Gtk.Grid(column_spacing=12, row_spacing=8)
        self._drops = {}
        for row, (key, (label, opts)) in enumerate(FILTERS.items()):
            lbl = Gtk.Label(label=label, xalign=0)
            lbl.add_css_class('dim-label')
            dd = Gtk.DropDown.new_from_strings([o[1] for o in opts])
            dd.set_hexpand(True)
            dd.connect('notify::selected', self._on_drop, key, opts)
            grid.attach(lbl, 0, row, 1, 1)
            grid.attach(dd, 1, row, 1, 1)
            self._drops[key] = (dd, opts)
        fav_lbl = Gtk.Label(label='Favorites only', xalign=0)
        fav_lbl.add_css_class('dim-label')
        self._fav_switch = Gtk.Switch(halign=Gtk.Align.END)
        self._fav_switch.connect('notify::active', self._on_fav)
        grid.attach(fav_lbl, 0, len(FILTERS), 1, 1)
        grid.attach(self._fav_switch, 1, len(FILTERS), 1, 1)
        box.append(grid)
        reset = Gtk.Button(label='Reset Filters')
        reset.connect('clicked', lambda *_: self.reset_filters())
        box.append(reset)
        pop.set_child(box)
        return pop

    def _on_drop(self, dd, _p, key, opts):
        self.filters[key] = opts[dd.get_selected()][0]
        self._filters_updated()

    def _on_fav(self, sw, _p):
        self.filters['favorites'] = sw.get_active()
        self._filters_updated()

    def _filters_updated(self):
        if self.active_filter_count():
            self.filter_btn.add_css_class('filter-active')
        else:
            self.filter_btn.remove_css_class('filter-active')
        self.emit('filters-changed')

    def active_filter_count(self):
        return sum(1 for v in self.filters.values() if v)

    def clear_filter(self, key):
        if key == 'favorites':
            self._fav_switch.set_active(False)
        else:
            self._drops[key][0].set_selected(0)

    def reset_filters(self):
        for key in self._drops:
            self._drops[key][0].set_selected(0)
        self._fav_switch.set_active(False)
        self.filters.update({'resolution': '', 'format': '', 'duration': '', 'favorites': False})
        self._filters_updated()

    def filter_chips(self):
        chips = []
        for key, (label, opts) in FILTERS.items():
            val = self.filters[key]
            if val:
                chips.append((dict(opts)[val], key))
        if self.filters['favorites']:
            chips.append(('Favorites', 'favorites'))
        return chips
