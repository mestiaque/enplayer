"""Settings dialog, built to match Lumen's: a title bar with a close button, a
category list on the left and flat rows on the right (title + hint on the
left, control on the right, hairline separators)."""
import os

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Adw, Gtk

from neplayer.config import ACCENTS, APP_ID, APP_NAME, COPYRIGHT_YEAR, DATA_DIR, DEFAULT_EXTENSIONS, DEVELOPER, DEVELOPER_EMAIL, DEVELOPER_WEBSITE, LOG_PATH, VERSION
from neplayer.core import cache
from neplayer.models.video import format_size

SECTIONS = ['General', 'Appearance', 'Playback', 'Hover preview', 'Library', 'Performance',
            'Privacy', 'About']
THEMES = [('dark', 'Dark'), ('light', 'Light'), ('glass', 'Glass')]


class SettingsDialog(Adw.Window):
    """Modal settings popup."""

    def __init__(self, ctx, parent):
        super().__init__(modal=True, transient_for=parent, default_width=860, default_height=620,
                         destroy_with_parent=True, hide_on_close=True)
        self.add_css_class('settings-dialog')
        self.view = SettingsView(ctx)

        title = Gtk.Label(label='Settings', xalign=0, hexpand=True)
        title.add_css_class('settings-title')
        close = Gtk.Button(icon_name='window-close-symbolic', tooltip_text='Close (Esc)', valign=Gtk.Align.CENTER)
        close.add_css_class('flat')
        close.add_css_class('circular')
        close.connect('clicked', lambda *_: self.close())
        head = Gtk.Box(spacing=8)
        head.add_css_class('settings-head')
        head.append(title)
        head.append(close)
        handle = Gtk.WindowHandle()
        handle.set_child(head)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.append(handle)
        box.append(Gtk.Separator())
        box.append(self.view)
        self.set_content(box)

        esc = Gtk.ShortcutController()
        esc.add_shortcut(Gtk.Shortcut.new(Gtk.ShortcutTrigger.parse_string('Escape'),
                                          Gtk.CallbackAction.new(lambda *_: (self.close(), True)[1])))
        self.add_controller(esc)

    def present_section(self, section=None):
        self.view.refresh()
        if section:
            self.view.show_section(section)
        self.present()


class SettingsView(Gtk.Box):
    def __init__(self, ctx):
        super().__init__(vexpand=True)
        self.ctx = ctx
        self.add_css_class('settings-page')
        self._pages = {}
        self._watchers = []  # (key, callback) to refresh controls when a setting changes elsewhere

        self.nav = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        self.nav.add_css_class('settings-nav')
        self.nav.set_size_request(184, -1)
        self.nav.connect('row-selected', self._on_nav)
        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE, transition_duration=120,
                               hexpand=True, vexpand=True)
        self.append(self.nav)
        self.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))
        self.append(self.stack)
        for name in SECTIONS:
            self._add_section(name)
        self.nav.select_row(self.nav.get_row_at_index(0))

        self._build_general()
        self._build_appearance()
        self._build_playback()
        self._build_preview()
        self._build_library()
        self._build_performance()
        self._build_privacy()
        self._build_about()
        ctx.settings.connect('changed', self._on_setting_changed)

    # ============================================================ sections
    def _build_general(self):
        p = self._pages['General']
        self._dropdown(p, 'On startup', 'What ENPlayer shows when it opens', 'startup_view',
                       [('Home', 'home'), ('All Videos', 'all'), ('Continue Watching', 'continue'),
                        ('Favorites', 'favorites')])
        self._switch(p, 'Scan on startup', 'Look for new and changed files when the app opens', 'scan_on_startup')
        self._switch(p, 'Watch folders for changes', 'Update the library when files are added, removed or renamed',
                     'auto_monitor')
        self._switch(p, 'Show sidebar', None, 'sidebar_visible')
        self._switch(p, 'Check for updates automatically', 'Looks for a new ENPlayer release on GitHub once a day',
                     'check_updates')
        upd = Gtk.Button(label='Check now', valign=Gtk.Align.CENTER)
        hint = self._row(p, 'Updates', f'You have version {VERSION}', upd)

        def check(*_):
            upd.set_sensitive(False)
            hint.set_label('Checking…')
            self.ctx.check_updates(manual=True, done=lambda text: (hint.set_label(text), upd.set_sensitive(True)))
        upd.connect('clicked', check)

    def _build_appearance(self):
        p = self._pages['Appearance']
        self._theme_cards(p)
        self._accent(p)
        self._dropdown(p, 'Thumbnail size', None, 'grid_density',
                       [('Small', 'small'), ('Medium', 'medium'), ('Large', 'large')])

    def _build_playback(self):
        p = self._pages['Playback']
        self._switch(p, 'Resume playback', 'Continue where you left off', 'resume_playback')
        self._switch(p, 'Play next video automatically', None, 'autoplay_next')
        self._spin(p, 'Default volume', 'Volume when ENPlayer starts (100 = the file\u2019s own loudness)',
                   'default_volume', 0, 130, 5)
        self._dropdown(p, 'Default speed', None, 'playback_speed',
                       [('0.5×', 0.5), ('0.75×', 0.75), ('Normal', 1.0), ('1.25×', 1.25), ('1.5×', 1.5), ('2×', 2.0)])
        self._entry(p, 'Preferred subtitle language', 'e.g. eng,ben (empty disables auto-select)', 'subtitle_lang')
        self._entry(p, 'Preferred audio language', 'e.g. eng,jpn', 'audio_lang')
        hw = [('Automatic', 'auto-safe'), ('Direct3D 11', 'd3d11va')] if os.name == 'nt' else \
            [('Automatic', 'auto-safe'), ('VA-API', 'vaapi')]
        self._dropdown(p, 'Hardware decoding', 'Takes effect for the next video', 'hwdec', hw + [('Off', 'no')])

    def _build_preview(self):
        p = self._pages['Hover preview']
        self._switch(p, 'Play preview on hover', 'Real video plays when you rest the pointer on a card',
                     'preview_enabled')
        self._spin(p, 'Hover delay', 'Milliseconds before the preview starts', 'preview_delay_ms', 100, 3000, 50)
        self._spin(p, 'Preview length', 'Seconds of video to loop', 'preview_duration_s', 2, 60, 1)
        self._spin(p, 'Preview volume', '0 keeps previews silent', 'preview_volume', 0, 100, 5)
        self._dropdown(p, 'Preview resolution', 'Downscale large videos for smoother previews', 'preview_max_height',
                       [('Original', 0), ('720p', 720), ('480p', 480), ('360p', 360)])

    def _build_library(self):
        p = self._pages['Library']
        self._switch(p, 'Include subfolders', 'Default for newly added folders', 'include_subdirs')
        self._switch(p, 'Ignore hidden folders', 'Skip files and folders starting with a dot', 'ignore_hidden')
        ext = Gtk.Entry(text=self.ctx.settings['extensions'], valign=Gtk.Align.CENTER, width_chars=26)
        ext.connect('activate', lambda e: self._set_extensions(e))
        ext.connect('notify::has-focus', lambda e, _p: None if e.has_focus() else self._set_extensions(e))
        reset = Gtk.Button(icon_name='edit-undo-symbolic', valign=Gtk.Align.CENTER, tooltip_text='Restore defaults')
        reset.add_css_class('flat')
        reset.connect('clicked', lambda *_: (ext.set_text(','.join(DEFAULT_EXTENSIONS)), self._set_extensions(ext)))
        box = Gtk.Box(spacing=4)
        box.append(ext)
        box.append(reset)
        self._row(p, 'Video formats', 'Comma-separated file extensions', box)
        self._switch(p, 'Music library', 'Also find audio files and play them with the music player',
                     'music_enabled')
        aext = Gtk.Entry(text=self.ctx.settings['audio_extensions'], width_chars=26)
        def set_audio(e):
            exts = ','.join(x.strip().lower().lstrip('.') for x in e.get_text().split(',') if x.strip())
            if exts:
                self.ctx.settings.set('audio_extensions', exts)
        aext.connect('activate', set_audio)
        aext.connect('notify::has-focus', lambda e, _p: None if e.has_focus() else set_audio(e))
        self._row(p, 'Audio formats', 'Comma-separated file extensions', aext)

    def _build_performance(self):
        p = self._pages['Performance']
        self._spin(p, 'Thumbnail cache size', 'Megabytes; least-recently used thumbnails are removed',
                   'cache_limit_mb', 50, 20000, 50)
        clear = Gtk.Button(label='Clear', valign=Gtk.Align.CENTER)
        clear.connect('clicked', lambda *_: (self.ctx.library.clear_cache(), self._update_cache_row(),
                                             self.ctx.toast('Thumbnail cache cleared')))
        rebuild = Gtk.Button(label='Rebuild', valign=Gtk.Align.CENTER)
        rebuild.connect('clicked', lambda *_: (self.ctx.library.rebuild_thumbnails(),
                                               self.ctx.toast('Rebuilding thumbnails in the background')))
        box = Gtk.Box(spacing=6)
        box.append(rebuild)
        box.append(clear)
        self.cache_hint = self._row(p, 'Thumbnail cache', '', box)
        self._update_cache_row()

    def _build_privacy(self):
        p = self._pages['Privacy']
        self._switch(p, 'Keep watch history', 'Remember what you watched and where you stopped', 'keep_history')
        hb = Gtk.Button(label='Clear history', valign=Gtk.Align.CENTER)
        hb.add_css_class('destructive-action')
        hb.connect('clicked', lambda *_: (self.ctx.db.clear_history(), self.ctx.library.emit('changed'),
                                          self.ctx.toast('Watch history cleared')))
        self._row(p, 'Watch history', 'Forget all playback positions and “Continue Watching”', hb)
        cb = Gtk.Button(label='Clear cache', valign=Gtk.Align.CENTER)
        cb.connect('clicked', lambda *_: (self.ctx.library.clear_cache(), self._update_cache_row(),
                                          self.ctx.toast('Thumbnail cache cleared')))
        self._row(p, 'Thumbnails', 'Generated previews of your videos stored on this computer', cb)
        note = Gtk.Label(wrap=True, xalign=0, label='ENPlayer works offline. It never uploads your videos, '
                         'thumbnails or watch history anywhere, and it never modifies your video files. '
                         'The only network request is the update check (General → Check for updates), '
                         'which asks GitHub for the latest version number.')
        note.add_css_class('set-note')
        p.append(note)

    def _build_about(self):
        p = self._pages['About']
        head = Gtk.Box(spacing=14)
        head.add_css_class('about-head')
        logo = Gtk.Image.new_from_icon_name(APP_ID)
        logo.set_pixel_size(64)
        head.append(logo)
        t = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER)
        name = Gtk.Label(label=f'{APP_NAME} {VERSION}', xalign=0)
        name.add_css_class('about-name')
        desc = Gtk.Label(label='A video and music player with live hover previews and an audio visualizer.', xalign=0)
        desc.add_css_class('set-hint')
        t.append(name)
        t.append(desc)
        head.append(t)
        p.append(head)
        for title, value in (('Playback engine', 'libmpv · GTK 4 · libadwaita'),
                             ('Library data', str(DATA_DIR)),
                             ('Thumbnail cache', self.ctx.settings['cache_dir']),
                             ('Log file', str(LOG_PATH))):
            v = Gtk.Label(label=value, xalign=1, selectable=True, ellipsize=1, max_width_chars=48)
            v.add_css_class('set-value')
            self._row(p, title, None, v)

        dev_title = Gtk.Label(label='DEVELOPER', xalign=0)
        dev_title.add_css_class('set-section-title')
        p.append(dev_title)
        self._row(p, 'Developed by', None, self._value(DEVELOPER))
        mail = Gtk.LinkButton(uri=f'mailto:{DEVELOPER_EMAIL}', label=DEVELOPER_EMAIL)
        mail.add_css_class('set-link')
        self._row(p, 'Contact', 'Bug reports, ideas and feedback are welcome', mail)
        web = Gtk.LinkButton(uri=DEVELOPER_WEBSITE, label=DEVELOPER_WEBSITE.split('//', 1)[-1])
        web.add_css_class('set-link')
        self._row(p, 'Website', None, web)
        self._row(p, 'Also by the developer', 'The matching image viewer', self._value('ENViewer'))
        self._row(p, 'Copyright', None, self._value(f'© {COPYRIGHT_YEAR} {DEVELOPER} · GPL-3.0'))

    @staticmethod
    def _value(text):
        v = Gtk.Label(label=text, xalign=1, selectable=True)
        v.add_css_class('set-value')
        return v

    # =========================================================== plumbing
    def _add_section(self, name):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        page.add_css_class('set-page')
        scroller = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        scroller.set_child(page)
        key = name.lower().replace(' ', '-')
        self.stack.add_named(scroller, key)
        self._pages[name] = page
        row = Gtk.ListBoxRow()
        row.key = key
        row.set_child(Gtk.Label(label=name, xalign=0))
        self.nav.append(row)

    def _row(self, page, title, subtitle, widget):
        """Lumen row: title (+ hint) on the left, control on the right."""
        row = Gtk.Box(spacing=24)
        row.add_css_class('set-row')
        labels = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True, valign=Gtk.Align.CENTER)
        t = Gtk.Label(label=title, xalign=0, wrap=True)
        t.add_css_class('set-title')
        labels.append(t)
        hint = Gtk.Label(label=subtitle or '', xalign=0, wrap=True, visible=bool(subtitle))
        hint.add_css_class('set-hint')
        labels.append(hint)
        row.append(labels)
        widget.set_valign(Gtk.Align.CENTER)
        row.append(widget)
        page.append(row)
        return hint

    def refresh(self):
        self._update_cache_row()

    def show_section(self, name):
        for i in range(len(SECTIONS)):
            row = self.nav.get_row_at_index(i)
            if row.key == name:
                self.nav.select_row(row)

    def _on_nav(self, _lb, row):
        if row is not None:
            self.stack.set_visible_child_name(row.key)

    def _on_setting_changed(self, _s, key):
        for k, cb in self._watchers:
            if k == key:
                cb()

    def _update_cache_row(self):
        d = self.ctx.settings['cache_dir']
        self.cache_hint.set_label(f'{format_size(cache.cache_size(d))} in {d}')
        self.cache_hint.set_visible(True)

    # ------------------------------------------------------------ controls
    def _switch(self, page, title, subtitle, key):
        sw = Gtk.Switch(active=bool(self.ctx.settings[key]))
        sw.connect('notify::active', lambda w, _p: self.ctx.settings.set(key, w.get_active()))
        self._watchers.append((key, lambda: sw.get_active() != bool(self.ctx.settings[key]) and
                               sw.set_active(bool(self.ctx.settings[key]))))
        self._row(page, title, subtitle, sw)

    def _spin(self, page, title, subtitle, key, lo, hi, step):
        spin = Gtk.SpinButton.new_with_range(lo, hi, step)
        spin.set_value(self.ctx.settings[key])
        spin.connect('value-changed', lambda w: self.ctx.settings.set(key, int(w.get_value())))
        self._row(page, title, subtitle, spin)

    def _dropdown(self, page, title, subtitle, key, options):
        dd = Gtk.DropDown.new_from_strings([o[0] for o in options])
        cur = self.ctx.settings[key]
        for i, (_label, val) in enumerate(options):
            if val == cur:
                dd.set_selected(i)
        dd.connect('notify::selected', lambda d, _p: self.ctx.settings.set(key, options[d.get_selected()][1]))

        def sync():
            for i, (_l, val) in enumerate(options):
                if val == self.ctx.settings[key] and dd.get_selected() != i:
                    dd.set_selected(i)
        self._watchers.append((key, sync))
        self._row(page, title, subtitle, dd)

    def _entry(self, page, title, subtitle, key):
        e = Gtk.Entry(text=self.ctx.settings[key], width_chars=14)
        e.connect('changed', lambda w: self.ctx.settings.set(key, w.get_text().strip()))
        self._row(page, title, subtitle, e)

    def _theme_cards(self, page):
        """Dark / Light / Glass as preview cards."""
        box = Gtk.Box(spacing=12)
        box.add_css_class('theme-cards')
        self._theme_btns = []
        group = None
        for key, label in THEMES:
            b = Gtk.ToggleButton()
            b.add_css_class('theme-card')
            if group is None:
                group = b
            else:
                b.set_group(group)
            inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            prev = Gtk.Box(spacing=0)
            prev.add_css_class('theme-preview')
            prev.add_css_class(f'theme-preview-{key}')
            side = Gtk.Box()
            side.add_css_class('tp-side')
            main = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, hexpand=True)
            main.add_css_class('tp-main')
            bar = Gtk.Box()
            bar.add_css_class('tp-bar')
            tiles = Gtk.Box(spacing=4)
            for _ in range(3):
                t = Gtk.Box(hexpand=True)
                t.add_css_class('tp-tile')
                tiles.append(t)
            main.append(bar)
            main.append(tiles)
            prev.append(side)
            prev.append(main)
            inner.append(prev)
            inner.append(Gtk.Label(label=label))
            b.set_child(inner)
            b.set_active(self.ctx.settings['theme'] == key)
            b.connect('toggled', lambda w, k=key: w.get_active() and self.ctx.settings.set('theme', k))
            self._theme_btns.append((b, key))
            box.append(b)

        def sync():
            for b, k in self._theme_btns:
                if b.get_active() != (k == self.ctx.settings['theme']):
                    b.set_active(k == self.ctx.settings['theme'])
        self._watchers.append(('theme', sync))
        hint = Gtk.Label(label='Applies to the library and the video player. Glass uses translucent panels '
                               'over a colour gradient.', xalign=0, wrap=True)
        hint.add_css_class('set-hint')
        wrap = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        wrap.add_css_class('set-row')
        t = Gtk.Label(label='Theme', xalign=0)
        t.add_css_class('set-title')
        wrap.append(t)
        wrap.append(box)
        wrap.append(hint)
        page.append(wrap)

    def _accent(self, page):
        box = Gtk.Box(spacing=6)
        self._accent_btns = []
        for i, c in enumerate(ACCENTS):
            b = Gtk.Button(tooltip_text=c)
            b.add_css_class('accent-dot')
            b.add_css_class(f'accent-dot-{i}')
            b.connect('clicked', lambda _b, c=c: self.ctx.settings.set('accent', c))
            box.append(b)
            self._accent_btns.append((b, c))
        self._watchers.append(('accent', self._mark_accent))
        self._mark_accent()
        self._row(page, 'Accent color', None, box)

    def _mark_accent(self):
        cur = self.ctx.settings['accent']
        for b, c in self._accent_btns:
            if c == cur:
                b.set_icon_name('object-select-symbolic')
                b.add_css_class('selected')
            else:
                b.set_child(None)
                b.remove_css_class('selected')

    def _set_extensions(self, entry):
        exts = ','.join(x.strip().lower().lstrip('.') for x in entry.get_text().split(',') if x.strip())
        if exts:
            self.ctx.settings.set('extensions', exts)


