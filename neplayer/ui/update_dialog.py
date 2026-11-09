"""'A new version is available' dialog: release notes, download progress, install, restart."""
import threading

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Adw, GLib, Gtk

from neplayer.config import APP_NAME, VERSION
from neplayer.core import updater


class UpdateDialog(Adw.Window):
    def __init__(self, parent, update, cache_dir):
        super().__init__(transient_for=parent, modal=True, title='Update available',
                         default_width=460, resizable=False)
        self.add_css_class('update-dialog')
        self.parent_win = parent
        self.update = update
        self.cache_dir = cache_dir
        self.kind = updater.install_kind()
        self._cancel = False
        self._busy = False

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.add_css_class('update-box')
        head = Gtk.Box(spacing=14)
        logo = Gtk.Image.new_from_icon_name(parent.get_application().get_application_id())
        logo.set_pixel_size(56)
        head.append(logo)
        t = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER)
        title = Gtk.Label(label=f'{APP_NAME} {update.version} is available', xalign=0)
        title.add_css_class('about-name')
        sub = Gtk.Label(label=f'You have version {VERSION}.', xalign=0)
        sub.add_css_class('set-hint')
        t.append(title)
        t.append(sub)
        head.append(t)
        box.append(head)

        if update.notes:
            notes = Gtk.Label(label=update.notes, xalign=0, yalign=0, wrap=True, selectable=True)
            notes.add_css_class('update-notes')
            sc = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, min_content_height=60,
                                    max_content_height=220, propagate_natural_height=True)
            sc.set_child(notes)
            box.append(sc)

        self.status = Gtk.Label(xalign=0, wrap=True)
        self.status.add_css_class('set-hint')
        self.progress = Gtk.ProgressBar(visible=False)
        box.append(self.progress)
        box.append(self.status)

        buttons = Gtk.Box(spacing=8, halign=Gtk.Align.END)
        self.later = Gtk.Button(label='Later')
        self.later.connect('clicked', lambda *_: self._on_later())
        self.go = Gtk.Button(label='Update now' if update.installable else 'OK')
        self.go.add_css_class('suggested-action')
        self._go_id = self.go.connect('clicked', lambda *_: self._on_go())
        if update.installable:
            buttons.append(self.later)
        buttons.append(self.go)
        box.append(buttons)
        if update.installable:
            self.status.set_label('The update downloads and installs in place; your library and settings are kept.'
                                  + (' Ubuntu asks for your password.' if self.kind == 'deb' else ''))
        else:
            self.status.set_label('This copy runs from the source code, so it cannot update itself. '
                                  'Copies installed from the ENPlayer .deb or Windows installer update in place.')
        self.set_content(box)
        self.connect('close-request', self._on_close_request)

    # ------------------------------------------------------------------
    def _on_close_request(self, *_):
        if self._busy:
            self._cancel = True
        return False

    def _on_later(self):
        self._cancel = True
        self.close()

    def _on_go(self):
        if not self.update.installable:
            self.close()
            return
        self._busy = True
        self.go.set_sensitive(False)
        self.progress.set_visible(True)
        self.status.set_label('Downloading…')
        threading.Thread(target=self._work, daemon=True, name='update').start()

    def _work(self):
        def progress(done, total):
            GLib.idle_add(self._on_progress, done, total, priority=GLib.PRIORITY_DEFAULT)
        try:
            path = updater.download(self.update, self.cache_dir / 'updates', progress, lambda: self._cancel)
            GLib.idle_add(self._set_status, 'Installing…' + (' Enter your password if asked.' if self.kind == 'deb' else ''),
                          priority=GLib.PRIORITY_DEFAULT)
            updater.install(path, self.kind)
        except updater.UpdateError as e:
            GLib.idle_add(self._on_failed, str(e), priority=GLib.PRIORITY_DEFAULT)
            return
        GLib.idle_add(self._on_installed, priority=GLib.PRIORITY_DEFAULT)

    def _on_progress(self, done, total):
        if total:
            self.progress.set_fraction(min(1.0, done / total))
            self.status.set_label(f'Downloading… {done / 1e6:.1f} of {total / 1e6:.1f} MB')
        else:
            self.progress.pulse()
        return False

    def _set_status(self, text):
        self.progress.pulse()
        self.status.set_label(text)
        return False

    def _on_failed(self, msg):
        self._busy = False
        self.progress.set_visible(False)
        self.status.set_label(msg)
        self.go.set_label('Try again')
        self.go.set_sensitive(True)
        return False

    def _on_installed(self):
        self._busy = False
        self.progress.set_fraction(1.0)
        app = self.parent_win.get_application()
        if self.kind == 'windows':
            self.status.set_label('Installing… ENPlayer will restart by itself.')
            GLib.timeout_add(600, lambda: app.quit() or False)
            return False
        self.status.set_label(f'{APP_NAME} {self.update.version} is installed. Restart to use it.')
        self.later.set_label('Restart later')
        self.go.set_label('Restart now')
        self.go.set_sensitive(True)
        self.go.disconnect(self._go_id)
        self.go.connect('clicked', lambda *_: (updater.restart(), app.quit()))
        return False
