"""Adw.Application: wires services together and owns the main window."""
import logging
import os
import time
from pathlib import Path

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
gi.require_version('Gdk', '4.0')
from gi.repository import Adw, Gdk, Gio, GLib, Gtk

from neplayer.config import APP_ID, APP_NAME, DB_PATH, IS_WINDOWS, LOG_PATH, RESOURCES_DIR
from neplayer.core.database import Database
from neplayer.core.library import LibraryService
from neplayer.core.settings import Settings

log = logging.getLogger(__name__)


class NeplayerApp(Adw.Application):
    def __init__(self):
        flags = Gio.ApplicationFlags.HANDLES_OPEN
        if IS_WINDOWS:
            # No session bus on Windows: run as a plain single process.
            flags |= Gio.ApplicationFlags.NON_UNIQUE
        super().__init__(application_id=APP_ID, flags=flags)
        GLib.set_application_name(APP_NAME)
        self.db = None
        self.settings = None
        self.library = None
        self.window = None
        self._pending_open = []

    def do_startup(self):
        Adw.Application.do_startup(self)
        self.db = self._open_database()
        if self.db is None:
            return
        self.settings = Settings(self.db)
        self.library = LibraryService(self.db, self.settings)
        self.apply_theme()
        self._load_css()
        icon_theme = Gtk.IconTheme.get_for_display(Gdk.Display.get_default())
        icon_theme.add_search_path(str(RESOURCES_DIR / 'icons'))
        self._use_lucide_icons()
        Gtk.Window.set_default_icon_name(APP_ID)

        quit_action = Gio.SimpleAction.new('quit', None)
        quit_action.connect('activate', lambda *_: self._quit())
        self.add_action(quit_action)
        self.set_accels_for_action('app.quit', ['<Control>q'])

    def _open_database(self):
        try:
            return Database(DB_PATH)
        except Exception:
            log.exception('Database failed to open; moving it aside and starting fresh')
        # Never let a damaged or incompatible database stop the app from opening:
        # keep it as a backup and create a new one.
        stamp = time.strftime('%Y%m%d-%H%M%S')
        try:
            for suffix in ('', '-wal', '-shm'):
                src = Path(str(DB_PATH) + suffix)
                if src.exists():
                    src.rename(Path(f'{DB_PATH}.broken-{stamp}{suffix}'))
            self._db_reset_note = f'Your previous library database could not be read and was saved as ' \
                                  f'{DB_PATH.name}.broken-{stamp}. Starting with a fresh library.'
            return Database(DB_PATH)
        except Exception as e:
            log.exception('Fresh database failed too')
            self._fatal(f'Could not open the library database:\n{DB_PATH}\n\n{e}')
            return None

    def _use_lucide_icons(self):
        """Bundled 'NEPLAYER' icon theme: Lucide icons (same set as Lumen), falls back to Adwaita."""
        settings = Gtk.Settings.get_default()
        if settings is not None and settings.get_property('gtk-icon-theme-name') != 'NEPLAYER':
            settings.set_property('gtk-icon-theme-name', 'NEPLAYER')

    def apply_theme(self):
        """Dark / Light / Glass. Forces the libadwaita scheme (PREFER_LIGHT would
        follow a dark system style) and reloads the stylesheet in place."""
        theme = self.settings['theme']
        sm = Adw.StyleManager.get_default()
        sm.set_color_scheme(Adw.ColorScheme.FORCE_LIGHT if theme == 'light' else Adw.ColorScheme.FORCE_DARK)
        if getattr(self, '_css_provider', None) is not None:
            self._load_css()

    def _accent_css(self, theme):
        from neplayer.config import ACCENTS
        a = self.settings['accent'] if self.settings['accent'] in ACCENTS else ACCENTS[0]
        text = f'shade({a}, 0.82)' if theme == 'light' else f'shade({a}, 1.3)'
        dots = ''.join(f'.accent-dot-{i} {{ background-color: {c}; }}\n' for i, c in enumerate(ACCENTS))
        return (f'@define-color ff_accent {a};\n@define-color ff_accent_hot shade({a}, 1.3);\n'
                f'@define-color accent_bg_color {a};\n@define-color accent_fg_color #ffffff;\n'
                f'@define-color accent_color {text};\n{dots}')

    def _load_css(self):
        styles = RESOURCES_DIR / 'styles'
        theme = self.settings['theme']
        # Palette first (named colours), then base rules, then theme-specific rules.
        css = (styles / f'themes/{theme}.colors.css').read_text(encoding='utf-8') + self._accent_css(theme) + \
            ''.join((styles / f).read_text(encoding='utf-8') for f in ('style.css', f'themes/{theme}.css'))
        display = Gdk.Display.get_default()
        if getattr(self, '_css_provider', None) is not None:
            Gtk.StyleContext.remove_provider_for_display(display, self._css_provider)
        provider = Gtk.CssProvider()
        provider.load_from_data(css.encode('utf-8'))
        Gtk.StyleContext.add_provider_for_display(display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self._css_provider = provider

    def _ensure_window(self):
        if self.window is None:
            from neplayer.ui.main_window import MainWindow
            self.window = MainWindow(self, self.db, self.settings, self.library)
            self.window.connect('close-request', self._on_window_close)
            GLib.idle_add(self._start_library)
        return self.window

    def _start_library(self):
        self.library.start()
        return False

    def do_activate(self):
        if self.db is None:
            return
        try:
            self._ensure_window().present()
        except Exception as e:
            # A half-built window would keep a windowless process alive; tell the
            # user what happened and exit cleanly instead.
            log.exception('Main window failed to open')
            if self.window is not None:
                self.window.destroy()
                self.window = None
            self._fatal(f'The main window failed to open:\n\n{e}\n\nDetails are in {LOG_PATH}')
            return
        note = getattr(self, '_db_reset_note', None)
        if note:
            self._db_reset_note = None
            self.window.toast(note, timeout=10)

    def do_open(self, files, _n, _hint):
        if self.db is None:
            return
        win = self._ensure_window()
        win.present()
        paths = [f.get_path() for f in files if f.get_path()]
        for p in paths:
            if os.path.isdir(p):
                win.library.add_folder(p)
        vids = [p for p in paths if os.path.isfile(p)]
        if vids:
            GLib.idle_add(lambda: win.play_path(vids[0]) and False)

    def _on_window_close(self, *_):
        self.library.shutdown()
        return False

    def _quit(self):
        if self.window is not None:
            self.window.close()
        self.quit()

    def _fatal(self, text):
        dlg = Gtk.MessageDialog(modal=True, message_type=Gtk.MessageType.ERROR,
                                buttons=Gtk.ButtonsType.CLOSE, text='ENPlayer cannot start')
        dlg.set_property('secondary-text', text)
        dlg.set_application(self)
        dlg.connect('response', lambda *_: self.quit())
        dlg.present()
