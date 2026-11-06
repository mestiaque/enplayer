"""Navigation sidebar (same layout as Lumen: brand, LIBRARY and FOLDERS sections)."""
import os

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Adw, GObject, Gtk
from neplayer.config import APP_ID, APP_NAME

LIBRARY = [
    ('home', 'Home', 'go-home-symbolic'),
    ('all', 'All Videos', 'view-grid-symbolic'),
    ('music', 'Music', 'audio-x-generic-symbolic'),
    ('recent', 'Recently Added', 'document-open-recent-symbolic'),
    ('continue', 'Continue Watching', 'media-playback-start-symbolic'),
    ('favorites', 'Favorites', 'non-starred-symbolic'),
]


class Sidebar(Gtk.Box):
    """Emits `navigate` with a view key: 'home', 'all', …, 'folders', or 'folder:<id>'."""

    __gsignals__ = {'navigate': (GObject.SignalFlags.RUN_FIRST, None, (str,))}

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.add_css_class('ff-sidebar')
        self.set_size_request(232, -1)

        header = Adw.HeaderBar(show_end_title_buttons=False)
        header.add_css_class('flat')
        brand = Gtk.Box(spacing=8)
        logo = Gtk.Image.new_from_icon_name(APP_ID)
        logo.set_pixel_size(24)
        logo.add_css_class('brand-logo')
        name = Gtk.Label(label=APP_NAME)
        name.add_css_class('brand-name')
        brand.append(logo)
        brand.append(name)
        header.pack_start(brand)
        header.set_title_widget(Gtk.Box())
        self.append(header)

        self.list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        self.list.add_css_class('navigation-sidebar')
        self.list.set_header_func(self._header_func)
        self.list.connect('row-selected', self._on_selected)
        scroller = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True)
        scroller.set_child(self.list)
        self.append(scroller)

        self._rows = {}
        self.counts = {}
        self._folder_rows = []
        for i, (key, label, icon) in enumerate(LIBRARY):
            self._add_row(key, label, icon, section='Library' if i == 0 else None)
        self._add_row('folders', 'All folders', 'folder-open-symbolic', section='Folders')
        self._suppress = False

    # ------------------------------------------------------------------ rows
    def _add_row(self, key, label, icon, section=None, tooltip=None):
        row = Gtk.ListBoxRow()
        row.key = key
        row.section = section
        box = Gtk.Box(spacing=10)
        img = Gtk.Image.new_from_icon_name(icon)
        img.add_css_class('nav-icon')
        box.append(img)
        box.append(Gtk.Label(label=label, xalign=0, hexpand=True, ellipsize=3))
        cnt = Gtk.Label()
        cnt.add_css_class('nav-count')
        box.append(cnt)
        self.counts[key] = cnt
        row.set_child(box)
        if tooltip:
            row.set_tooltip_text(tooltip)
        self.list.append(row)
        self._rows[key] = row
        return row

    def _header_func(self, row, _before):
        title = getattr(row, 'section', None)
        if not title:
            if row.get_header() is not None:
                row.set_header(None)
            return
        if row.get_header() is not None:
            return
        head = Gtk.Box(spacing=4)
        head.add_css_class('nav-section')
        head.append(Gtk.Label(label=title.upper(), xalign=0, hexpand=True))
        if title == 'Folders':
            add = Gtk.Button(icon_name='list-add-symbolic', tooltip_text='Add folder (Ctrl+N)')
            add.add_css_class('flat')
            add.add_css_class('nav-section-btn')
            add.set_action_name('win.add-folder')
            head.append(add)
        row.set_header(head)

    def set_folders(self, folders):
        """Library folders listed under FOLDERS (like Lumen's pinned folders)."""
        current = self._selected_key()
        for row in self._folder_rows:
            self.list.remove(row)
            self._rows.pop(row.key, None)
            self.counts.pop(row.key, None)
        self._folder_rows = []
        for f in folders:
            name = f.get('name') or os.path.basename((f.get('path') or '').rstrip('/')) or f.get('path', '')
            row = self._add_row(f'folder:{f["id"]}', name, 'folder-symbolic', tooltip=f.get('path'))
            cnt = f.get('video_count')
            self.counts[row.key].set_label(str(cnt) if cnt else '')
            self._folder_rows.append(row)
        if current:
            self.select(current)

    # ------------------------------------------------------------- selection
    def _selected_key(self):
        return getattr(self.list.get_selected_row(), 'key', None)

    def _on_selected(self, _lb, row):
        if row is not None and not self._suppress:
            self.emit('navigate', row.key)

    def select(self, key):
        self._suppress = True
        row = self._rows.get(key)
        if row is None:
            self.list.unselect_all()
        else:
            self.list.select_row(row)
        self._suppress = False

    def set_counts(self, counts):
        for k in ('all', 'music', 'recent', 'continue', 'favorites'):
            lbl = self.counts.get(k)
            if lbl is not None:
                n = counts.get(k)
                lbl.set_label(str(n) if n else '')
