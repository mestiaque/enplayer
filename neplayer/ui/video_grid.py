"""Virtualized responsive grid of video cards (Gtk.GridView)."""
import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Adw, Gio, Gtk

from neplayer.config import DENSITY_WIDTH
from neplayer.models.video import VideoItem
from neplayer.ui.video_card import VideoCard


def count_label(items):
    """'12 videos', '8 songs' or '12 videos · 8 songs'."""
    songs = sum(1 for v in items if v.get('media_kind') == 'audio')
    vids = len(items) - songs
    parts = []
    if vids or not songs:
        parts.append(f'{vids} video{"s" if vids != 1 else ""}')
    if songs:
        parts.append(f'{songs} song{"s" if songs != 1 else ""}')
    return '  ·  '.join(parts)


class VideoGrid(Gtk.Box):
    def __init__(self, ctx):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.ctx = ctx
        self.card_width = DENSITY_WIDTH.get(ctx.settings['grid_density'], 260)
        self.store = Gio.ListStore(item_type=VideoItem)

        factory = Gtk.SignalListItemFactory()
        factory.connect('setup', self._setup)
        factory.connect('bind', self._bind)
        factory.connect('unbind', self._unbind)

        self.grid = Gtk.GridView(model=Gtk.NoSelection(model=self.store), factory=factory)
        self.grid.set_max_columns(12)
        self.grid.set_min_columns(1)
        self.grid.add_css_class('video-grid')

        self.scroller = Gtk.ScrolledWindow(vexpand=True, hexpand=True)
        self.scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.scroller.set_child(self.grid)
        self.scroller.get_vadjustment().connect(
            'value-changed', lambda *_: ctx.previews.stop('scroll') if self.scroller.get_mapped() else None)

        self.header = Gtk.Box(spacing=12)
        self.header.add_css_class('page-header')
        self.title = Gtk.Label(xalign=0)
        self.title.add_css_class('page-title')
        self.count = Gtk.Label(xalign=0, hexpand=True)
        self.count.add_css_class('page-count')
        self.header.append(self.title)
        self.header.append(self.count)
        self.chips = Gtk.Box(spacing=6)
        self.header.append(self.chips)

        self.empty = Adw.StatusPage()
        self.empty.add_css_class('compact-status')
        self.stack = Gtk.Stack(vexpand=True)
        self.stack.add_named(self.scroller, 'grid')
        self.stack.add_named(self.empty, 'empty')

        self.append(self.header)
        self.append(self.stack)

    def _setup(self, _f, list_item):
        card = VideoCard(self.ctx, self.card_width)
        list_item.set_child(card)

    def _bind(self, _f, list_item):
        card = list_item.get_child()
        card.set_size_request(self.card_width, -1)
        card.bind(list_item.get_item())

    def _unbind(self, _f, list_item):
        list_item.get_child().unbind()

    def set_density(self, density):
        self.card_width = DENSITY_WIDTH.get(density, 260)
        # Re-create rows so new widths apply.
        items = [self.store.get_item(i) for i in range(self.store.get_n_items())]
        self.store.remove_all()
        self.store.splice(0, 0, items)

    def set_videos(self, videos, title, empty_title='Nothing here', empty_desc='',
                   empty_icon='video-x-generic-symbolic', keep_scroll=False):
        adj = self.scroller.get_vadjustment()
        pos = adj.get_value() if keep_scroll else 0
        self.title.set_label(title)
        self.count.set_label(count_label(videos))
        old_ids = [self.store.get_item(i).id for i in range(self.store.get_n_items())]
        new_ids = [v['id'] for v in videos]
        if keep_scroll and old_ids == new_ids:
            # Same items: update in place so nothing flickers.
            for i, v in enumerate(videos):
                item = self.store.get_item(i)
                item.data.update(v)
            from neplayer.ui.video_card import cards_for
            for v in videos:
                for c in cards_for(v['id']):
                    c.refresh()
        else:
            self.store.splice(0, self.store.get_n_items(), [VideoItem(v) for v in videos])
            if keep_scroll:
                from gi.repository import GLib
                GLib.idle_add(lambda: (adj.set_value(min(pos, adj.get_upper())), False)[1])
            else:
                adj.set_value(0)
        if videos:
            self.stack.set_visible_child_name('grid')
        else:
            self.empty.set_title(empty_title)
            self.empty.set_description(empty_desc)
            self.empty.set_icon_name(empty_icon)
            self.stack.set_visible_child_name('empty')

    def video_list(self):
        return [self.store.get_item(i).data for i in range(self.store.get_n_items())]

    def set_chips(self, labels):
        child = self.chips.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            self.chips.remove(child)
            child = nxt
        for text, on_clear in labels:
            b = Gtk.Button()
            box = Gtk.Box(spacing=4)
            box.append(Gtk.Label(label=text))
            box.append(Gtk.Image.new_from_icon_name('window-close-symbolic'))
            b.set_child(box)
            b.add_css_class('chip')
            b.connect('clicked', lambda _b, cb=on_clear: cb())
            self.chips.append(b)
