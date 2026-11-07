"""Main application window. Also acts as the 'context' passed to child views."""
import logging
import os
import threading
import time
from pathlib import Path

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
gi.require_version('Gdk', '4.0')
from gi.repository import Adw, Gdk, Gio, GLib, Gtk

from neplayer.config import (APP_ID, APP_NAME, COPYRIGHT_YEAR, DATA_DIR, DEVELOPER, DEVELOPER_EMAIL,
                             DEVELOPER_WEBSITE, VERSION, XWAYLAND_MARKER)
from neplayer.core.library import probe_single
from neplayer.models.video import format_duration, format_size
from neplayer.player import shortcuts
from neplayer.preview.preview_manager import PreviewManager
from neplayer.ui.folders_view import FoldersView
from neplayer.ui.home_view import HomeView
from neplayer.ui.player_view import PlayerView
from neplayer.ui.settings_view import SettingsDialog
from neplayer.ui.mini_player import MiniPlayer
from neplayer.ui.window_top import needs_xwayland, set_always_on_top
from neplayer.ui.video_grid import count_label
from neplayer.ui.sidebar import Sidebar
from neplayer.ui.toolbar import LibraryHeader
from neplayer.ui.video_card import cards_for
from neplayer.ui.video_grid import VideoGrid

log = logging.getLogger(__name__)

VIEW_TITLES = {
    'all': ('All Videos', 'No videos yet', 'Add a folder to start building your library.',
            'folder-videos-symbolic'),
    'music': ('Music', 'No music yet', 'Add a folder with audio files (MP3, FLAC, M4A, OGG, Opus, WAV…).',
              'audio-x-generic-symbolic'),
    'recent': ('Recently Added', 'Nothing new', 'Videos added in the last 30 days appear here.',
               'document-open-recent-symbolic'),
    'continue': ('Continue Watching', 'Nothing in progress',
                 'Videos you have started but not finished appear here.',
                 'media-playback-start-symbolic'),
    'favorites': ('Favorites', 'No favorites yet',
                  'Click the star on any video to add it here.', 'starred-symbolic'),
    'folder': ('Folder', 'This folder is empty', 'No videos were found in this folder.',
               'folder-symbolic'),
    'search': ('Search', 'No results', 'Try a different search or clear the filters.',
               'system-search-symbolic'),
}


class MainWindow(Adw.ApplicationWindow):
    def __init__(self, app, db, settings, library):
        super().__init__(application=app, title=APP_NAME)
        self.app = app
        self.db = db
        self.settings = settings
        self.library = library
        self.previews = PreviewManager(settings)
        self.view = 'home'
        self.folder_id = None
        self.search_text = ''
        self._return_view = 'home'
        self._search_src = None
        self.add_css_class('neplayer')
        self.set_default_size(1360, 860)
        self.set_size_request(760, 520)

        # ---------- library page
        self.sidebar = Sidebar()
        self.sidebar.connect('navigate', lambda _s, key: self._on_sidebar(key))
        self.header = LibraryHeader()
        self.header.connect('search-changed', self._on_search)
        self.header.connect('filters-changed', lambda *_: self._refresh_view())
        self._history, self._hist_i = [], -1
        self.sidebar_rev = Gtk.Revealer(transition_type=Gtk.RevealerTransitionType.SLIDE_RIGHT,
                                        reveal_child=settings['sidebar_visible'])
        self.sidebar_rev.set_child(self.sidebar)
        self.header.sidebar_btn.set_active(settings['sidebar_visible'])
        self.header.sidebar_btn.connect('toggled', lambda b: settings.set('sidebar_visible',
                                                                          b.get_active()))

        self.home = HomeView(self)
        self.grid = VideoGrid(self)
        self.folders = FoldersView(self)
        self._settings_dialog = None
        self.content = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE,
                                 transition_duration=140, vexpand=True, hexpand=True)
        self.content.add_named(self.home, 'home')
        self.content.add_named(self.grid, 'grid')
        self.content.add_named(self.folders, 'folders')
        self.content.add_css_class('ff-content')

        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        content_box.add_css_class('ff-main')
        content_box.append(self.header)
        content_box.append(self.content)
        self._mini_slot = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        content_box.append(self._mini_slot)
        content_box.append(self._build_status_bar())

        library_page = Gtk.Box()
        library_page.append(self.sidebar_rev)
        library_page.append(content_box)

        # ---------- player page
        self.player = PlayerView(self)
        self.player.connect('close-requested', lambda *_: self.close_player())
        self.player.connect('fullscreen-toggle', lambda *_: self.toggle_fullscreen())
        self.player.connect('escape', lambda *_: self._on_player_escape())
        self.mini = MiniPlayer(self.player, on_open=self.reopen_player, on_close=self.player.stop)
        self._mini_slot.append(self.mini)

        self.pages = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE,
                               transition_duration=180)
        self.pages.add_named(library_page, 'library')
        self.pages.add_named(self.player, 'player')

        self.toasts = Adw.ToastOverlay()
        self.toasts.set_child(self.pages)
        self.set_content(self.toasts)

        self._setup_actions()
        self._setup_keys()
        self._setup_dnd()

        library.connect('changed', lambda *_: self._refresh_view(keep_scroll=True))
        library.connect('folders-changed', lambda *_: self._on_folders_changed())
        library.connect('video-updated', self._on_video_updated)
        library.connect('thumbnail-ready', self._on_thumbnail_ready)
        library.connect('scan-status', lambda _l, busy, text: self._set_scan_status(busy, text))
        library.connect('message', lambda _l, text: self.toast(text, timeout=6))
        settings.connect('changed', self._on_setting_changed)
        self.connect('notify::fullscreened', self._on_fullscreen_changed)
        self.connect('notify::is-active', lambda *_: None if self.is_active() else self.previews.stop('window-inactive'))
        self.connect('close-request', self._on_close)

        start = self.settings['startup_view']
        self.navigate(start if start in ('home', 'all', 'continue', 'favorites') else 'home')
        self._update_counts()
        self._pending_update = None
        self.schedule_update_check()

    # ================================================================ ctx API
    def toast(self, text, timeout=3, button=None, action=None):
        t = Adw.Toast(title=GLib.markup_escape_text(text), timeout=timeout)
        if button and action:
            t.set_button_label(button)
            t.set_action_name(action)
        self.toasts.add_toast(t)

    # ================================================================ updates
    def schedule_update_check(self):
        """Quietly look for a new release a few seconds after every start."""
        if not self.settings['check_updates']:
            return
        GLib.timeout_add_seconds(8, lambda: self.check_updates(manual=False) and False)

    def check_updates(self, manual=True, done=None):
        """manual: report "up to date" / errors too. done(text) receives a short status line."""
        from neplayer.core import updater

        def work():
            try:
                up, err = updater.check(), None
            except updater.UpdateError as e:
                up, err = None, str(e)
            GLib.idle_add(finish, up, err, priority=GLib.PRIORITY_DEFAULT)

        def finish(up, err):
            if err is None:
                self.settings.set('last_update_check', time.time())
            self._pending_update = up
            if err:
                text = 'Could not check for updates. Are you online?'
            elif up:
                text = f'{APP_NAME} {up.version} is available'
            else:
                text = f'You have the latest version ({VERSION})'
            if done:
                done(text)
            if up and manual:
                self._show_pending_update()
            elif up:
                self.toast(text, timeout=0, button='Update', action='win.update')
            elif manual and not done:
                self.toast(text)
            return False
        threading.Thread(target=work, daemon=True, name='update-check').start()

    def _show_pending_update(self):
        up = getattr(self, '_pending_update', None)
        if up is None:
            return
        from neplayer.ui.update_dialog import UpdateDialog
        UpdateDialog(self, up, Path(self.settings['cache_dir'])).present()

    def show_settings(self, section=None):
        if self._settings_dialog is None:
            self._settings_dialog = SettingsDialog(self, self)
        self._settings_dialog.present_section(section)

    def navigate(self, view, folder_id=None, _from_history=False):
        if view == 'settings':  # settings is a popup, not a page
            self.show_settings()
            return
        if self.pages.get_visible_child_name() == 'player':
            self.close_player()
        self.previews.stop('navigate')
        self.view = view
        self.folder_id = folder_id
        self.sidebar.select(f'folder:{folder_id}' if view == 'folder' else view)
        self._update_page_title()
        if not _from_history:
            entry = (view, folder_id)
            if not self._history or self._history[self._hist_i] != entry:
                self._history = self._history[:self._hist_i + 1] + [entry]
                self._history = self._history[-100:]
                self._hist_i = len(self._history) - 1
        self._update_history_actions()
        if view == 'home' and not self._searching():
            self.home.refresh()
            self.content.set_visible_child_name('home')
        elif view == 'folders':
            self.folders.refresh()
            self.content.set_visible_child_name('folders')
        else:
            self._refresh_grid()
            self.content.set_visible_child_name('grid')

    def play(self, video, card=None, from_start=False):
        self.previews.stop('play')
        playlist = None
        if card is not None:
            playlist = self.home.playlist_for(card)
        if playlist is None and self.content.get_visible_child_name() == 'grid':
            listing = self.grid.video_list()
            if any(v['id'] == video.get('id') for v in listing):
                playlist = listing
        if video.get('missing') or not os.path.exists(video['file_path']):
            self.toast(f'File not found: {os.path.basename(video["file_path"])}', timeout=5)
            return
        self.previews.suspend(True)
        self.mini.hide()
        self.pages.set_visible_child_name('player')
        self.player.play(video, playlist, from_start=from_start)
        self.set_title(video.get('title') or APP_NAME)

    def play_path(self, path):
        path = os.path.abspath(path)
        v = self.db.get_video_by_path(path)
        if v is None:
            meta = probe_single(path) or {'file_path': path,
                                          'title': os.path.splitext(os.path.basename(path))[0]}
            meta['id'] = None
            v = meta
            # Siblings in the same folder form the playlist for external files.
            playlist = self._sibling_playlist(path) or [v]
            self.previews.suspend(True)
            self.mini.hide()
            self.pages.set_visible_child_name('player')
            self.player.play(v, playlist)
            self.set_title(v.get('title') or APP_NAME)
            return
        self.play(v)

    def _sibling_playlist(self, path):
        d = os.path.dirname(path)
        # Songs play with the other songs in the folder, videos with the videos.
        from neplayer.config import AUDIO_EXTENSIONS
        is_song = path.rsplit('.', 1)[-1].lower() in AUDIO_EXTENSIONS
        exts = set(AUDIO_EXTENSIONS) if is_song else self.settings.video_extensions
        try:
            names = sorted((n for n in os.listdir(d) if n.rsplit('.', 1)[-1].lower() in exts),
                           key=str.lower)
        except OSError:
            return None
        out = []
        for n in names:
            p = os.path.join(d, n)
            rec = self.db.get_video_by_path(p)
            out.append(rec or {'id': None, 'file_path': p, 'title': os.path.splitext(n)[0]})
        return out

    def reopen_player(self):
        """Back from the mini player to the full Now Playing screen."""
        if not self.player.is_active:
            return
        self.mini.hide()
        self.previews.suspend(True)
        self.pages.set_visible_child_name('player')
        self.player.show_controls()
        self.player.grab_focus()

    def close_player(self):
        # Music keeps playing in the mini player; videos stop.
        if self.player.is_audio and self.player.is_active:
            self.pages.set_visible_child_name('library')
            if self.is_fullscreen():
                self.unfullscreen()
            self.previews.suspend(False)
            self.set_title(APP_NAME)
            self.mini.show()
            self._refresh_view(keep_scroll=True)
            return
        self.mini.hide()
        self.player.stop()
        if self.is_fullscreen():
            self.unfullscreen()
        self.pages.set_visible_child_name('library')
        self.previews.suspend(False)
        self.set_title(APP_NAME)
        self._refresh_view(keep_scroll=True)

    def clear_progress(self, video_id):
        self.db.clear_history(video_id)
        self._on_video_updated(None, video_id)
        self._refresh_view(keep_scroll=True)

    def show_info(self, v):
        win = Adw.Window(transient_for=self, modal=True, title='Properties')
        win.set_default_size(520, 560)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        hb = Adw.HeaderBar()
        hb.set_title_widget(Adw.WindowTitle(title='Properties', subtitle=''))
        box.append(hb)
        page = Adw.PreferencesPage()
        g = Adw.PreferencesGroup(title=GLib.markup_escape_text(v['title']))
        streams = v.get('audio_streams') or '[]'
        subs = v.get('subtitle_streams') or '[]'
        try:
            import json
            streams = json.loads(streams) if isinstance(streams, str) else streams
            subs = json.loads(subs) if isinstance(subs, str) else subs
        except ValueError:
            streams, subs = [], []
        rows = [
            ('Location', v['file_path']),
            ('Size', format_size(v.get('file_size'))),
            ('Duration', format_duration(v.get('duration'))),
            ('Resolution', f'{v.get("width")} × {v.get("height")}' if v.get('width') else '—'),
            ('Frame rate', f'{v.get("fps"):g} fps' if v.get('fps') else '—'),
            ('Video codec', (v.get('video_codec') or '—').upper()),
            ('Audio codec', (v.get('audio_codec') or '—').upper()),
            ('Bitrate', f'{(v.get("bitrate") or 0) / 1000:.0f} kb/s' if v.get('bitrate') else '—'),
            ('Container', v.get('container') or '—'),
            ('Audio tracks', ', '.join(f'{s.get("language") or "und"} ({s.get("codec")})'
                                       for s in streams) or 'None'),
            ('Subtitle tracks', ', '.join(f'{s.get("language") or "und"} ({s.get("codec")})'
                                          for s in subs) or 'None'),
        ]
        if v.get('error'):
            rows.append(('Error', v['error']))
        for title, value in rows:
            r = Adw.ActionRow(title=title)
            lbl = Gtk.Label(label=str(value), selectable=True, wrap=True, xalign=1,
                            max_width_chars=40)
            lbl.add_css_class('dim-label')
            r.add_suffix(lbl)
            g.add(r)
        page.add(g)
        box.append(page)
        win.set_content(box)
        win.present()

    # ================================================================ views
    def _searching(self):
        return bool(self.search_text) or self.header.active_filter_count() > 0

    def _on_search(self, _h, text):
        self.search_text = text.strip()
        if self._search_src is not None:
            GLib.source_remove(self._search_src)
        self._search_src = GLib.timeout_add(180, self._apply_search)

    def _apply_search(self):
        self._search_src = None
        if self.view in ('folders', 'settings') and self.search_text:
            self.view = 'all'
            self.sidebar.select('all')
        self.navigate(self.view, self.folder_id)
        return False

    def _refresh_view(self, keep_scroll=False):
        if self.pages.get_visible_child_name() == 'player':
            return
        if self.view == 'home' and not self._searching():
            self.home.refresh()
            self.content.set_visible_child_name('home')
        elif self.view == 'folders':
            self.folders.refresh()
        elif self.view == 'settings':
            pass
        else:
            self._refresh_grid(keep_scroll)
            self.content.set_visible_child_name('grid')
        self._update_counts()

    def _refresh_grid(self, keep_scroll=False):
        view = self.view
        if view in ('home', 'folders', 'settings'):
            view = 'all'
        filters = dict(self.header.filters)
        videos = self.db.query_videos(view=view, search=self.search_text,
                                      sort=self.settings['sort'], filters=filters,
                                      folder_id=self.folder_id if self.view == 'folder' else None)
        key = 'search' if (self._searching() and self.view == 'home') else \
            (self.view if self.view in VIEW_TITLES else 'all')
        title, etitle, edesc, eicon = VIEW_TITLES[key]
        if self.view == 'folder' and self.folder_id is not None:
            f = self.db.get_folder(self.folder_id)
            if f:
                title = f['name']
        if self.search_text:
            title = f'Results for “{self.search_text}”' + (f' in {title}' if key != 'search' else '')
            etitle, edesc, eicon = VIEW_TITLES['search'][1:]
        elif self.header.active_filter_count():
            etitle, edesc, eicon = VIEW_TITLES['search'][1:]
        self.grid.set_videos(videos, title, etitle, edesc, eicon, keep_scroll=keep_scroll)
        self.status_count.set_label(count_label(videos))
        self.grid.set_chips([(label, lambda k=k: self.header.clear_filter(k))
                             for label, k in self.header.filter_chips()])

    # ------------------------------------------------- Lumen-style chrome
    def _go_history(self, delta):
        i = self._hist_i + delta
        if 0 <= i < len(self._history):
            self._hist_i = i
            view, folder_id = self._history[i]
            self.navigate(view, folder_id, _from_history=True)

    def _update_history_actions(self):
        for name, ok in (('go-back', self._hist_i > 0), ('go-forward', self._hist_i < len(self._history) - 1)):
            a = self.lookup_action(name)
            if a is not None:
                a.set_enabled(ok)

    def _on_sidebar(self, key):
        if key.startswith('folder:'):
            self.navigate('folder', folder_id=int(key.split(':', 1)[1]))
        else:
            self.navigate(key)

    def _build_status_bar(self):
        bar = Gtk.Box(spacing=12)
        bar.add_css_class('ff-statusbar')
        self.status_count = Gtk.Label(xalign=0)
        self.status_path = Gtk.Label(xalign=0, hexpand=True, ellipsize=3)
        self.status_path.add_css_class('dim')
        self.status_spinner = Gtk.Spinner(visible=False)
        self.status_text = Gtk.Label(xalign=1, ellipsize=3)
        for w in (self.status_count, self.status_path, self.status_spinner, self.status_text):
            bar.append(w)
        return bar

    def _set_scan_status(self, busy, text):
        self.status_spinner.set_visible(busy)
        self.status_spinner.set_spinning(busy)
        self.status_text.set_label(text or '')

    def _set_item_count(self, n):
        self.status_count.set_label(f'{n:,} video' + ('' if n == 1 else 's'))

    def _update_page_title(self):
        """Title + subtitle on the left of the header bar, like Lumen."""
        sub = ''
        if self.view == 'folder' and self.folder_id is not None:
            f = self.db.get_folder(self.folder_id) or {}
            title, sub = f.get('name') or 'Folder', f.get('path') or ''
        else:
            title = {'home': 'Home', 'folders': 'Folders'}.get(self.view) or VIEW_TITLES.get(self.view, ('Library',))[0]
        self.header.set_page(title, sub)
        self.status_path.set_label(sub)
        if self.view in ('home', 'folders'):
            try:
                n = len(self.db.query_videos('all'))
                folders = len(self.db.list_folders())
                self.status_count.set_label(f'{n:,} videos · {folders} folder' + ('' if folders == 1 else 's'))
            except Exception:
                log.exception('status count failed')

    def _update_counts(self):
        try:
            self.sidebar.set_folders(self.db.list_folders())
            self.sidebar.set_counts({
                'all': len(self.db.query_videos('all')),
                'music': self.db.count_kind('audio'),
                'continue': len(self.db.query_videos('continue')),
                'favorites': len(self.db.query_videos('favorites')),
            })
        except Exception:
            log.exception('count update failed')

    def _on_folders_changed(self):
        self.sidebar.set_folders(self.db.list_folders())
        if self.view == 'folders':
            self.folders.refresh()

    def _on_video_updated(self, _lib, video_id):
        v = self.db.get_video(video_id)
        if v is None:
            return
        for c in cards_for(video_id):
            c.refresh(v)
        if self.view == 'favorites' or self.header.filters.get('favorites'):
            self._refresh_view(keep_scroll=True)
        else:
            self._update_counts()

    def _on_thumbnail_ready(self, _lib, video_id, path):
        for c in cards_for(video_id):
            c.refresh({'thumbnail_path': path})

    def _on_setting_changed(self, _s, key):
        if key == 'grid_density':
            self.grid.set_density(self.settings['grid_density'])
            self.home.refresh()
        elif key == 'sidebar_visible':
            vis = self.settings['sidebar_visible']
            self.sidebar_rev.set_reveal_child(vis)
            if self.header.sidebar_btn.get_active() != vis:
                self.header.sidebar_btn.set_active(vis)
        elif key == 'always_on_top':
            self._apply_always_on_top(announce=True)
        elif key == 'accent':
            self.app.apply_theme()
        elif key == 'theme':
            self.app.apply_theme()
            self.header.set_theme_icon(self.settings['theme'])
            a = self.lookup_action('theme')
            if a is not None:
                a.set_state(GLib.Variant('s', self.settings['theme']))
            self.player.apply_theme()
        elif key == 'sort':
            self._refresh_view()
        elif key in ('preview_volume', 'hwdec'):
            # Preview engine picks these up when re-created.
            self.previews.shutdown()
            self.previews = PreviewManager(self.settings)

    def _apply_always_on_top(self, announce=False):
        on = self.settings['always_on_top']
        self.lookup_action('always-on-top').set_state(GLib.Variant('b', on))
        if not on or needs_xwayland(self):
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            XWAYLAND_MARKER.write_text('') if on else XWAYLAND_MARKER.unlink(missing_ok=True)
        if self.get_surface() is not None and not needs_xwayland(self):
            set_always_on_top(self, on)
        elif announce and on:
            self.toast('Restart ENPlayer to turn on Always on top', timeout=6)
        return GLib.SOURCE_REMOVE

    # ============================================================== actions
    def _setup_actions(self):
        def add(name, cb, accels=None):
            a = Gio.SimpleAction.new(name, None)
            a.connect('activate', lambda *_: cb())
            self.add_action(a)
            if accels:
                self.app.set_accels_for_action(f'win.{name}', accels)

        add('add-folder', self.choose_folder, ['<Control>n'])
        add('open-file', self.choose_file, ['<Control>o'])
        add('rescan', self._rescan, ['F5'])
        add('search', self._focus_search, ['<Control>f'])
        add('shortcuts', self.show_shortcuts, ['<Control>question', '<Control>slash'])
        add('about', self.show_about)
        add('update', self._show_pending_update)
        add('settings', self.show_settings, ['<Control>comma'])
        add('go-back', lambda: self._go_history(-1), ['<Alt>Left'])
        add('go-forward', lambda: self._go_history(1), ['<Alt>Right'])
        theme = Gio.SimpleAction.new_stateful('theme', GLib.VariantType('s'), GLib.Variant('s', self.settings['theme']))
        theme.connect('activate', lambda a, v: (a.set_state(v), self.settings.set('theme', v.get_string())))
        self.add_action(theme)
        top = Gio.SimpleAction.new_stateful('always-on-top', None,
                                            GLib.Variant('b', self.settings['always_on_top']))
        top.connect('activate', lambda a, _v: self.settings.set('always_on_top', not a.get_state().get_boolean()))
        self.add_action(top)
        self.connect('map', lambda *_: GLib.idle_add(self._apply_always_on_top))
        self.header.set_theme_icon(self.settings['theme'])
        add('toggle-sidebar', lambda: self.settings.set('sidebar_visible',
                                                       not self.settings['sidebar_visible']), ['F9'])

        sort = Gio.SimpleAction.new_stateful('sort', GLib.VariantType('s'),
                                             GLib.Variant('s', self.settings['sort']))
        sort.connect('activate', lambda a, v: (a.set_state(v), self.settings.set('sort', v.get_string())))
        self.add_action(sort)
        density = Gio.SimpleAction.new_stateful('density', GLib.VariantType('s'),
                                                GLib.Variant('s', self.settings['grid_density']))
        density.connect('activate', lambda a, v: (a.set_state(v),
                                                  self.settings.set('grid_density', v.get_string())))
        self.add_action(density)

    def _rescan(self):
        if not self.db.list_folders():
            self.toast('Add a folder first')
            return
        self.library.rescan()
        self.toast('Scanning library…')

    def _focus_search(self):
        if self.pages.get_visible_child_name() == 'player':
            return
        self.header.search.grab_focus()

    def choose_folder(self):
        dlg = Gtk.FileChooserNative(title='Add Folders to Library', transient_for=self,
                                    action=Gtk.FileChooserAction.SELECT_FOLDER,
                                    accept_label='Add')
        dlg.set_select_multiple(True)

        def resp(d, r):
            if r == Gtk.ResponseType.ACCEPT:
                files = d.get_files()
                added = 0
                for i in range(files.get_n_items()):
                    p = files.get_item(i).get_path()
                    if p and self.library.add_folder(p):
                        added += 1
                if added:
                    self.toast(f'Added {added} folder{"s" if added > 1 else ""} — scanning…')
                    if self.view == 'folders':
                        self.folders.refresh()
            d.destroy()
        dlg.connect('response', resp)
        dlg.show()
        self._dialog = dlg

    def choose_file(self):
        dlg = Gtk.FileChooserNative(title='Open Video', transient_for=self,
                                    action=Gtk.FileChooserAction.OPEN)
        f = Gtk.FileFilter()
        f.set_name('Video files')
        f.add_mime_type('video/*')
        for ext in self.settings.extensions:
            f.add_pattern(f'*.{ext}')
            f.add_pattern(f'*.{ext.upper()}')
        dlg.add_filter(f)
        all_f = Gtk.FileFilter()
        all_f.set_name('All files')
        all_f.add_pattern('*')
        dlg.add_filter(all_f)

        def resp(d, r):
            if r == Gtk.ResponseType.ACCEPT:
                p = d.get_file().get_path()
                if p:
                    self.play_path(p)
            d.destroy()
        dlg.connect('response', resp)
        dlg.show()
        self._dialog = dlg

    def show_about(self):
        about = Gtk.AboutDialog(transient_for=self, modal=True, program_name=APP_NAME,
                                version=VERSION, logo_icon_name=APP_ID,
                                comments='A fast, native video and music player for Linux.\n'
                                         'Powered by GTK, libadwaita, mpv and FFmpeg.',
                                developers=[f'{DEVELOPER} <{DEVELOPER_EMAIL}>'],
                                copyright=f'© {COPYRIGHT_YEAR} {DEVELOPER}',
                                website=DEVELOPER_WEBSITE, website_label='mestiaque.com',
                                license_type=Gtk.License.GPL_3_0)
        about.present()

    def show_shortcuts(self):
        win = Adw.Window(transient_for=self, modal=True, title='Keyboard Shortcuts')
        win.set_default_size(560, 680)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.append(Adw.HeaderBar())
        page = Adw.PreferencesPage()
        for section, items in shortcuts.HELP:
            g = Adw.PreferencesGroup(title=section)
            for keys, desc in items:
                r = Adw.ActionRow(title=desc)
                k = Gtk.Label(label=keys)
                k.add_css_class('keycap')
                r.add_suffix(k)
                g.add(r)
            page.add(g)
        box.append(page)
        win.set_content(box)
        win.present()

    # ================================================================ input
    def _setup_keys(self):
        keys = Gtk.EventControllerKey()
        keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        keys.connect('key-pressed', self._on_key)
        self.add_controller(keys)

    def _on_key(self, _ctrl, keyval, _code, state):
        if self.pages.get_visible_child_name() == 'player':
            focus = self.get_focus()
            if isinstance(focus, (Gtk.Entry, Gtk.Text)):
                return False
            return self.player.handle_key(keyval, state)
        if keyval == Gdk.KEY_Escape and self.header.search.has_focus() and self.search_text:
            self.header.search.set_text('')
            return True
        return False

    def _on_player_escape(self):
        if self.is_fullscreen():
            self.unfullscreen()
        else:
            self.close_player()

    def toggle_fullscreen(self):
        if self.is_fullscreen():
            self.unfullscreen()
        else:
            self.fullscreen()

    def _on_fullscreen_changed(self, *_):
        self.player.set_fullscreen_state(self.is_fullscreen())

    def _setup_dnd(self):
        target = Gtk.DropTarget.new(Gdk.FileList, Gdk.DragAction.COPY)
        target.connect('drop', self._on_drop)
        self.add_controller(target)

    def _on_drop(self, _t, value, _x, _y):
        files = value.get_files() if hasattr(value, 'get_files') else []
        played = False
        for f in files:
            p = f.get_path()
            if not p:
                continue
            if os.path.isdir(p):
                if self.library.add_folder(p):
                    self.toast(f'Added {os.path.basename(p)} — scanning…')
            elif not played:
                self.play_path(p)
                played = True
        return True

    def _on_close(self, *_):
        self.player.shutdown()
        self.previews.shutdown()
        return False
