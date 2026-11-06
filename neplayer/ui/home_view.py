"""Dashboard: hero + horizontal shelves (Continue Watching, Recently Added, ...)."""
import datetime

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Adw, Gtk

from neplayer.config import DENSITY_WIDTH
from neplayer.models.video import VideoItem, format_size
from neplayer.ui.video_card import VideoCard

SHELF_LIMIT = 24


class Shelf(Gtk.Box):
    def __init__(self, ctx, title, view_name):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.ctx = ctx
        self.add_css_class('shelf')
        head = Gtk.Box(spacing=8)
        lbl = Gtk.Label(label=title, xalign=0, hexpand=True)
        lbl.add_css_class('shelf-title')
        head.append(lbl)
        more = Gtk.Button(label='See all')
        more.add_css_class('flat')
        more.add_css_class('see-all')
        more.connect('clicked', lambda *_: ctx.navigate(view_name))
        head.append(more)
        self.append(head)

        self.row = Gtk.Box(spacing=18)
        self.row.add_css_class('shelf-row')
        self.scroller = Gtk.ScrolledWindow()
        self.scroller.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
        self.scroller.set_child(self.row)
        self.scroller.get_hadjustment().connect(
            'value-changed', lambda *_: ctx.previews.stop('scroll') if self.scroller.get_mapped() else None)
        self.append(self.scroller)
        self.cards = []

    def set_videos(self, videos, width):
        for c in self.cards:
            c.unbind()
            self.row.remove(c)
        self.cards = []
        for v in videos:
            card = VideoCard(self.ctx, width, fixed=True)
            card.bind(VideoItem(v))
            self.row.append(card)
            self.cards.append(card)
        self.set_visible(bool(videos))

    def video_list(self):
        return [c.item.data for c in self.cards if c.item is not None]


class HomeView(Gtk.ScrolledWindow):
    def __init__(self, ctx):
        super().__init__(vexpand=True, hexpand=True)
        self.ctx = ctx
        self.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.get_vadjustment().connect(
            'value-changed', lambda *_: ctx.previews.stop('scroll') if self.get_mapped() else None)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=32)
        box.add_css_class('home')

        hero = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        hero.add_css_class('hero')
        self.greeting = Gtk.Label(xalign=0)
        self.greeting.add_css_class('hero-title')
        self.stats = Gtk.Label(xalign=0)
        self.stats.add_css_class('hero-sub')
        hero.append(self.greeting)
        hero.append(self.stats)
        box.append(hero)

        self.shelves = {
            'continue': Shelf(ctx, 'Continue Watching', 'continue'),
            'recent': Shelf(ctx, 'Recently Added', 'recent'),
            'favorites': Shelf(ctx, 'Favorites', 'favorites'),
            'music': Shelf(ctx, 'Music', 'music'),
            'all': Shelf(ctx, 'All Videos', 'all'),
        }
        for s in self.shelves.values():
            box.append(s)

        self.empty = Adw.StatusPage(icon_name='folder-videos-symbolic',
                                    title='Build your video library',
                                    description='Add a folder and ENPlayer will find every video inside it, '
                                                'generate thumbnails and keep it in sync.')
        btns = Gtk.Box(spacing=12, halign=Gtk.Align.CENTER)
        add = Gtk.Button(label='Add Folder…')
        add.add_css_class('suggested-action')
        add.add_css_class('pill')
        add.set_action_name('win.add-folder')
        open_btn = Gtk.Button(label='Open a File…')
        open_btn.add_css_class('pill')
        open_btn.set_action_name('win.open-file')
        btns.append(add)
        btns.append(open_btn)
        self.empty.set_child(btns)
        self.empty.set_vexpand(True)
        box.append(self.empty)

        clamp = Adw.Clamp(maximum_size=100000)
        clamp.set_child(box)
        self.set_child(clamp)

    def refresh(self):
        db = self.ctx.db
        width = DENSITY_WIDTH.get(self.ctx.settings['grid_density'], 260)
        stats = db.library_stats()
        hour = datetime.datetime.now().hour
        greet = ('Good morning' if 5 <= hour < 12 else 'Good afternoon' if 12 <= hour < 18
                 else 'Good evening')
        self.greeting.set_label(greet)
        hours = stats['dur'] / 3600
        songs = db.count_kind('audio')
        vids = stats['n'] - songs
        what = '  ·  '.join(p for p in (f'{vids} videos' if vids else '', f'{songs} songs' if songs else '') if p)
        self.stats.set_label(f'{what}  ·  {hours:.1f} hours  ·  {format_size(stats["size"])}'
                             if stats['n'] else 'Your library is empty')
        empty = stats['n'] == 0
        self.empty.set_visible(empty)
        self.shelves['continue'].set_videos(db.query_videos('continue', limit=SHELF_LIMIT), width)
        self.shelves['recent'].set_videos(
            [v for v in db.query_videos('recent', sort='recent', limit=SHELF_LIMIT * 2) if not v['error']][:SHELF_LIMIT],
            width)
        self.shelves['favorites'].set_videos(db.query_videos('favorites', limit=SHELF_LIMIT), width)
        self.shelves['music'].set_videos(db.query_videos('music', sort='artist', limit=SHELF_LIMIT), width)
        self.shelves['all'].set_videos(
            [v for v in db.query_videos('all', sort=self.ctx.settings['sort'], limit=SHELF_LIMIT * 2)
             if not v['error']][:SHELF_LIMIT], width)
        if empty:
            for s in self.shelves.values():
                s.set_visible(False)

    def playlist_for(self, card):
        for s in self.shelves.values():
            if card in s.cards:
                return s.video_list()
        return None
