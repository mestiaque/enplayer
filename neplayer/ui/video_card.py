"""Video card: thumbnail, badges, hover preview slot, title and metadata."""
import os
import weakref
from collections import defaultdict

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Gdk', '4.0')
from gi.repository import Gdk, Gio, GLib, Gtk

from neplayer.core.thumbnail import NO_ART_SUFFIX
from neplayer.models.video import (file_format, format_duration, format_size,
                                    resolution_label)

_registry = defaultdict(weakref.WeakSet)  # video id -> cards currently showing it


class Ratio16x9(Gtk.Widget):
    """Single-child container whose height is always 9/16 of its width."""
    __gtype_name__ = 'NeplayerRatio16x9'

    def __init__(self, child, min_width=160, nat_width=260):
        super().__init__()
        self._child = child
        self._min_width = min_width
        self._nat_width = max(min_width, nat_width)
        child.set_parent(self)

    def do_get_request_mode(self):
        return Gtk.SizeRequestMode.HEIGHT_FOR_WIDTH

    def do_measure(self, orientation, for_size):
        if orientation == Gtk.Orientation.HORIZONTAL:
            return self._min_width, self._nat_width, -1, -1
        width = for_size if for_size > 0 else self._nat_width
        h = round(width * 9 / 16)
        return h, h, -1, -1

    def do_size_allocate(self, width, height, baseline):
        self._child.allocate(width, height, baseline, None)

    def do_dispose(self):
        if self._child is not None:
            self._child.unparent()
            self._child = None


def cards_for(video_id):
    return list(_registry.get(video_id, ()))


class VideoCard(Gtk.Box):
    """A card that can be bound/rebound to different VideoItems (GridView recycling)."""

    def __init__(self, ctx, width=260, fixed=False):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.ctx = ctx  # AppContext: library, previews, actions
        self.item = None
        self._bound_id = None
        self._thumb_path = None
        self.add_css_class('video-card')
        self.set_size_request(width, -1)

        self.overlay = Gtk.Overlay()
        self.frame = Ratio16x9(self.overlay, min_width=width if fixed else 160, nat_width=width)
        self.frame.add_css_class('thumb-frame')
        self.frame.set_overflow(Gtk.Overflow.HIDDEN)

        self.placeholder = Gtk.Image.new_from_icon_name('video-x-generic-symbolic')
        self.placeholder.set_pixel_size(42)
        self.placeholder.add_css_class('thumb-placeholder')
        self.picture = Gtk.Picture()
        self.picture.set_can_shrink(True)
        self.picture.set_keep_aspect_ratio(True)
        self.picture.add_css_class('thumb')
        stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE, transition_duration=180)
        stack.add_named(self.placeholder, 'placeholder')
        stack.add_named(self.picture, 'picture')
        # Songs without cover art: a music icon styled by the active theme.
        song_icon = Gtk.Image.new_from_icon_name('audio-x-generic-symbolic')
        song_icon.set_pixel_size(30)
        song_icon.add_css_class('song-art-icon')
        song_icon.set_halign(Gtk.Align.CENTER)
        song_icon.set_valign(Gtk.Align.CENTER)
        song_art = Gtk.Box()
        song_art.add_css_class('song-art')
        song_art.append(song_icon)
        song_icon.set_hexpand(True)
        stack.add_named(song_art, 'song-art')
        self.thumb_stack = stack
        self.overlay.set_child(stack)

        # Preview attaches here, above the thumbnail but below badges.
        self.preview_slot = Gtk.Box()
        self.preview_slot.set_can_target(False)
        self.preview_slot.add_css_class('preview-slot')
        self.overlay.add_overlay(self.preview_slot)

        self.res_badge = self._badge('res', Gtk.Align.START, Gtk.Align.START)
        self.dur_badge = self._badge('dur', Gtk.Align.END, Gtk.Align.END)
        self.error_badge = self._badge('error', Gtk.Align.START, Gtk.Align.END)
        self.error_badge.set_tooltip_text('This file could not be read')

        self.fav_btn = Gtk.ToggleButton()
        self.fav_btn.set_icon_name('non-starred-symbolic')
        self.fav_btn.add_css_class('fav-button')
        self.fav_btn.add_css_class('circular')
        self.fav_btn.set_halign(Gtk.Align.END)
        self.fav_btn.set_valign(Gtk.Align.START)
        self.fav_btn.set_tooltip_text('Favorite')
        self._fav_handler = self.fav_btn.connect('toggled', self._on_fav_toggled)
        self.overlay.add_overlay(self.fav_btn)

        self.play_icon = Gtk.Image.new_from_icon_name('media-playback-start-symbolic')
        self.play_icon.set_pixel_size(28)
        self.play_icon.add_css_class('play-hint')
        self.play_icon.set_halign(Gtk.Align.CENTER)
        self.play_icon.set_valign(Gtk.Align.CENTER)
        self.play_icon.set_can_target(False)
        self.overlay.add_overlay(self.play_icon)

        self.progress = Gtk.ProgressBar()
        self.progress.add_css_class('resume-bar')
        self.progress.set_valign(Gtk.Align.END)
        self.progress.set_can_target(False)
        self.overlay.add_overlay(self.progress)

        self.append(self.frame)

        self.title = Gtk.Label(xalign=0, lines=2, wrap=True, ellipsize=3)
        self.title.set_wrap_mode(2)  # WORD_CHAR
        self.title.add_css_class('card-title')
        self.meta = Gtk.Label(xalign=0, ellipsize=3)
        self.meta.add_css_class('card-meta')
        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        text.set_margin_start(2)
        text.set_margin_end(2)
        text.append(self.title)
        text.append(self.meta)
        self.append(text)

        motion = Gtk.EventControllerMotion()
        motion.connect('enter', self._on_enter)
        motion.connect('leave', self._on_leave)
        self.frame.add_controller(motion)

        click = Gtk.GestureClick(button=0)
        click.connect('released', self._on_click)
        self.add_controller(click)

        self._menu = None
        self.set_cursor(Gdk.Cursor.new_from_name('pointer'))
        self.connect('unmap', lambda *_: self.ctx.previews.card_unbound(self))

    def _badge(self, kind, halign, valign):
        lbl = Gtk.Label()
        lbl.add_css_class('badge')
        lbl.add_css_class(kind)
        lbl.set_halign(halign)
        lbl.set_valign(valign)
        lbl.set_can_target(kind == 'error')
        self.overlay.add_overlay(lbl)
        return lbl

    # --- binding ---------------------------------------------------------
    def bind(self, item):
        if self.item is not None:
            self.unbind()
        self.item = item
        self._bound_id = item.id
        _registry[item.id].add(self)
        self.refresh()

    def unbind(self):
        self.ctx.previews.card_unbound(self)
        if self._bound_id is not None:
            _registry[self._bound_id].discard(self)
            if not _registry[self._bound_id]:
                _registry.pop(self._bound_id, None)
        self.item = None
        self._bound_id = None
        self._thumb_path = None

    def refresh(self, data=None):
        if data is not None and self.item is not None:
            self.item.data.update(data)
        if self.item is None:
            return
        v = self.item.data
        self.title.set_label(v['title'])
        self.set_tooltip_text(v['file_path'])
        self.placeholder.set_from_icon_name('audio-x-generic-symbolic' if v.get('media_kind') == 'audio'
                                            else 'video-x-generic-symbolic')
        audio = v.get('media_kind') == 'audio'
        if audio:
            parts = [v.get('artist') or 'Unknown artist', v.get('album')]
        else:
            parts = [file_format(v['file_path'])]
            if v.get('width'):
                parts.append(f'{v["width"]}×{v["height"]}')
            parts.append(format_size(v.get('file_size')))
        self.meta.set_label('  ·  '.join(p for p in parts if p))

        res = file_format(v['file_path']) if audio else resolution_label(v.get('width'), v.get('height'))
        self.res_badge.set_label(res)
        self.res_badge.set_visible(bool(res))
        self.res_badge.remove_css_class('uhd')
        if res == '4K':
            self.res_badge.add_css_class('uhd')
        self.dur_badge.set_label(format_duration(v.get('duration')))
        self.dur_badge.set_visible(bool(v.get('duration')))
        self.error_badge.set_label('Unreadable')
        self.error_badge.set_visible(bool(v.get('error')))

        self.fav_btn.handler_block(self._fav_handler)
        self.fav_btn.set_active(bool(v.get('favorite')))
        self.fav_btn.handler_unblock(self._fav_handler)
        self.fav_btn.set_icon_name('starred-symbolic' if v.get('favorite') else 'non-starred-symbolic')
        if v.get('favorite'):
            self.add_css_class('is-favorite')
        else:
            self.remove_css_class('is-favorite')

        pos, dur = v.get('position') or 0, v.get('duration') or 0
        show_prog = dur > 0 and pos > 5 and not v.get('completed')
        self.progress.set_visible(show_prog)
        if show_prog:
            self.progress.set_fraction(min(1.0, pos / dur))
        self._load_thumbnail()

    def _load_thumbnail(self):
        v = self.item.data
        path = v.get('thumbnail_path')
        if path and path == self._thumb_path and self.thumb_stack.get_visible_child_name() == 'picture':
            return
        self._thumb_path = path
        if path and path.endswith(NO_ART_SUFFIX):
            self.thumb_stack.set_visible_child_name('song-art')
            return
        if not path:
            self.thumb_stack.set_visible_child_name('placeholder')
            self.ctx.library.request_thumbnail(v, visible=True)
            return
        tex = self.ctx.library.textures.get(path)
        if tex is not None:
            self.picture.set_paintable(tex)
            self.thumb_stack.set_visible_child_name('picture')
            return
        self.thumb_stack.set_visible_child_name('placeholder')
        vid = v['id']

        def done(texture):
            if self.item is None or self.item.id != vid or self._thumb_path != path:
                return
            if texture is None:
                # Cache file pruned or corrupt: regenerate.
                v['thumbnail_path'] = None
                self._thumb_path = None
                self.ctx.library.request_thumbnail(v, visible=True)
                return
            self.picture.set_paintable(texture)
            self.thumb_stack.set_visible_child_name('picture')
        self.ctx.library.textures.load(path, done)

    # --- preview ---------------------------------------------------------
    def attach_preview(self, area):
        if area.get_parent() is not None:
            area.unparent()
        self.preview_slot.append(area)
        self.add_css_class('previewing')

    def detach_preview(self, area):
        if area.get_parent() is self.preview_slot:
            self.preview_slot.remove(area)
        self.remove_css_class('previewing')

    def on_preview_started(self):
        self.add_css_class('preview-live')

    def _on_enter(self, *_):
        self.add_css_class('hover')
        if self.item is None or self.item.data.get('media_kind') != 'audio':  # no video to preview
            self.ctx.previews.hover_enter(self)

    def _on_leave(self, *_):
        self.remove_css_class('hover')
        self.remove_css_class('preview-live')
        self.ctx.previews.hover_leave(self)

    # --- interaction -----------------------------------------------------
    def _on_click(self, gesture, n_press, x, y):
        if self.item is None:
            return
        button = gesture.get_current_button()
        if button == Gdk.BUTTON_SECONDARY:
            self._show_menu(x, y)
            return
        if button == Gdk.BUTTON_PRIMARY:
            # Ignore clicks that landed on the favorite button.
            picked = self.pick(x, y, Gtk.PickFlags.DEFAULT)
            while picked is not None and picked is not self:
                if picked is self.fav_btn:
                    return
                picked = picked.get_parent()
            self.ctx.previews.stop('click')
            self.ctx.play(self.item.data, self)

    def _on_fav_toggled(self, btn):
        if self.item is not None:
            self.ctx.library.set_favorite(self.item.id, btn.get_active())

    def _show_menu(self, x, y):
        v = self.item.data
        group = Gio.SimpleActionGroup()

        def add(name, cb):
            a = Gio.SimpleAction.new(name, None)
            a.connect('activate', lambda *_: cb())
            group.add_action(a)
        add('play', lambda: self.ctx.play(v, self))
        add('play-start', lambda: self.ctx.play(v, self, from_start=True))
        add('favorite', lambda: self.ctx.library.set_favorite(v['id'], not v.get('favorite')))
        add('open-folder', lambda: self._open_folder(v['file_path']))
        add('copy-path', lambda: self.get_clipboard().set(v['file_path']))
        add('clear-progress', lambda: self.ctx.clear_progress(v['id']))
        add('info', lambda: self.ctx.show_info(v))
        self.insert_action_group('card', group)

        menu = Gio.Menu()
        s1 = Gio.Menu()
        s1.append('Play', 'card.play')
        if (v.get('position') or 0) > 5:
            s1.append('Play from Beginning', 'card.play-start')
        s1.append('Remove from Favorites' if v.get('favorite') else 'Add to Favorites', 'card.favorite')
        menu.append_section(None, s1)
        s2 = Gio.Menu()
        s2.append('Open Containing Folder', 'card.open-folder')
        s2.append('Copy File Path', 'card.copy-path')
        if (v.get('position') or 0) > 0:
            s2.append('Clear Watch Progress', 'card.clear-progress')
        menu.append_section(None, s2)
        s3 = Gio.Menu()
        s3.append('Properties', 'card.info')
        menu.append_section(None, s3)

        if self._menu is not None:
            self._menu.unparent()
        self._menu = Gtk.PopoverMenu.new_from_model(menu)
        self._menu.set_parent(self)
        self._menu.set_has_arrow(False)
        rect = Gdk.Rectangle()
        rect.x, rect.y, rect.width, rect.height = int(x), int(y), 1, 1
        self._menu.set_pointing_to(rect)
        self._menu.popup()

    def _open_folder(self, path):
        if os.name == 'nt':
            import subprocess
            subprocess.Popen(['explorer', '/select,', os.path.normpath(path)])
            return
        uri = GLib.filename_to_uri(os.path.dirname(path), None)
        try:
            # Ask the file manager to highlight the file; fall back to opening the folder.
            bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
            bus.call_sync('org.freedesktop.FileManager1', '/org/freedesktop/FileManager1',
                          'org.freedesktop.FileManager1', 'ShowItems',
                          GLib.Variant('(ass)', ([GLib.filename_to_uri(path, None)], '')),
                          None, Gio.DBusCallFlags.NONE, 2000, None)
        except Exception:
            Gtk.show_uri(self.get_root(), uri, Gdk.CURRENT_TIME)
