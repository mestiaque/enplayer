"""Library folder management page."""
import datetime
import os

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Adw, Gtk


def _ago(ts):
    if not ts:
        return 'never scanned'
    delta = datetime.datetime.now() - datetime.datetime.fromtimestamp(ts)
    s = delta.total_seconds()
    if s < 60:
        return 'scanned just now'
    if s < 3600:
        return f'scanned {int(s // 60)} min ago'
    if s < 86400:
        return f'scanned {int(s // 3600)} h ago'
    return f'scanned {int(s // 86400)} d ago'


class FoldersView(Gtk.ScrolledWindow):
    def __init__(self, ctx):
        super().__init__(vexpand=True)
        self.ctx = ctx
        self.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        outer.add_css_class('folders-page')

        head = Gtk.Box(spacing=12)
        title = Gtk.Label(label='Folders', xalign=0, hexpand=True)
        title.add_css_class('page-title')
        head.append(title)
        rescan = Gtk.Button(label='Rescan All')
        rescan.set_action_name('win.rescan')
        add = Gtk.Button(label='Add Folder…')
        add.add_css_class('suggested-action')
        add.set_action_name('win.add-folder')
        head.append(rescan)
        head.append(add)
        outer.append(head)

        self.list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self.list.add_css_class('boxed-list')
        outer.append(self.list)
        self.empty = Adw.StatusPage(icon_name='folder-symbolic', title='No folders yet',
                                    description='Add folders that contain your videos. '
                                                'Subfolders are included automatically.')
        self.empty.add_css_class('compact-status')
        outer.append(self.empty)

        clamp = Adw.Clamp(maximum_size=900, tightening_threshold=600)
        clamp.set_child(outer)
        self.set_child(clamp)

    def refresh(self):
        child = self.list.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            self.list.remove(child)
            child = nxt
        folders = self.ctx.db.list_folders()
        self.empty.set_visible(not folders)
        self.list.set_visible(bool(folders))
        for f in folders:
            self.list.append(self._row(f))

    def _row(self, f):
        available = os.path.isdir(f['path'])
        row = Adw.ActionRow(title=GLib_markup_escape(f['name']),
                            subtitle=GLib_markup_escape(f['path']))
        row.set_activatable(True)
        row.connect('activated', lambda *_: self.ctx.navigate('folder', folder_id=f['id']))
        icon = Gtk.Image.new_from_icon_name('folder-videos-symbolic' if available
                                            else 'drive-harddisk-symbolic')
        row.add_prefix(icon)

        info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER)
        count = Gtk.Label(label=f'{f["video_count"]} videos', xalign=1)
        count.add_css_class('heading')
        when = Gtk.Label(label=_ago(f['last_scanned_at']) if available else 'Not available',
                         xalign=1)
        when.add_css_class('caption')
        when.add_css_class('dim-label' if available else 'error')
        info.append(count)
        info.append(when)
        row.add_suffix(info)

        sub = Gtk.ToggleButton(icon_name='view-list-symbolic', valign=Gtk.Align.CENTER)
        sub.set_active(bool(f['include_subdirs']))
        sub.set_tooltip_text('Include subfolders')
        sub.add_css_class('flat')
        sub.connect('toggled', lambda b: self.ctx.library.update_folder(
            f['id'], include_subdirs=int(b.get_active())))
        row.add_suffix(sub)

        enabled = Gtk.Switch(valign=Gtk.Align.CENTER, active=bool(f['enabled']))
        enabled.set_tooltip_text('Show this folder in the library')
        enabled.connect('notify::active', lambda s, _p: self.ctx.library.update_folder(
            f['id'], enabled=int(s.get_active())))
        row.add_suffix(enabled)

        rescan = Gtk.Button(icon_name='view-refresh-symbolic', valign=Gtk.Align.CENTER)
        rescan.set_tooltip_text('Rescan folder')
        rescan.add_css_class('flat')
        rescan.connect('clicked', lambda *_: self.ctx.library.rescan(f['id']))
        row.add_suffix(rescan)

        remove = Gtk.Button(icon_name='user-trash-symbolic', valign=Gtk.Align.CENTER)
        remove.set_tooltip_text('Remove from library (files are not deleted)')
        remove.add_css_class('flat')
        remove.connect('clicked', lambda *_: self._confirm_remove(f))
        row.add_suffix(remove)
        return row

    def _confirm_remove(self, f):
        dlg = Gtk.MessageDialog(transient_for=self.get_root(), modal=True,
                                message_type=Gtk.MessageType.QUESTION,
                                buttons=Gtk.ButtonsType.NONE,
                                text=f'Remove “{f["name"]}” from the library?')
        dlg.set_property('secondary-text', 'Your video files will not be deleted. '
                                           'Thumbnails and watch history for this folder are removed.')
        dlg.add_button('Cancel', Gtk.ResponseType.CANCEL)
        btn = dlg.add_button('Remove', Gtk.ResponseType.ACCEPT)
        btn.add_css_class('destructive-action')

        def resp(d, r):
            d.destroy()
            if r == Gtk.ResponseType.ACCEPT:
                self.ctx.library.remove_folder(f['id'])
        dlg.connect('response', resp)
        dlg.present()


def GLib_markup_escape(text):
    from gi.repository import GLib
    return GLib.markup_escape_text(text)
