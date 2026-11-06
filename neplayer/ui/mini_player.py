"""Mini player: keeps music playing while you browse the library."""
import gi

gi.require_version('Gtk', '4.0')
from gi.repository import GLib, Gtk

from neplayer.models.video import format_duration


class MiniPlayer(Gtk.Revealer):
    """Bottom bar shown in the library while a song plays in the background.

    It reads the state of the (hidden) PlayerView, so there is a single mpv
    instance and a single playlist.
    """

    def __init__(self, player, on_open, on_close):
        super().__init__(transition_type=Gtk.RevealerTransitionType.SLIDE_UP, transition_duration=200,
                         reveal_child=False)
        self.player = player
        self._on_open = on_open
        self._on_close = on_close
        self._timer = None
        self._shown_path = None
        self._shown_cover = None

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        outer.add_css_class('mini-player')
        self.progress = Gtk.ProgressBar()
        self.progress.add_css_class('mini-progress')
        outer.append(self.progress)

        row = Gtk.Box(spacing=12)
        row.add_css_class('mini-row')
        self.cover = Gtk.Picture(can_shrink=True, keep_aspect_ratio=True)
        self.cover.set_size_request(44, 44)
        self.cover.set_overflow(Gtk.Overflow.HIDDEN)
        self.cover.add_css_class('mini-cover')
        labels = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER, hexpand=True)
        self.title = Gtk.Label(xalign=0, ellipsize=3)
        self.title.add_css_class('mini-title')
        self.artist = Gtk.Label(xalign=0, ellipsize=3)
        self.artist.add_css_class('mini-artist')
        labels.append(self.title)
        labels.append(self.artist)
        info = Gtk.Box(spacing=12, hexpand=True)
        info.append(self.cover)
        info.append(labels)
        info.set_tooltip_text('Open the player')
        click = Gtk.GestureClick()
        click.connect('released', lambda *_: self._on_open())
        info.add_controller(click)
        row.append(info)

        self.time = Gtk.Label()
        self.time.add_css_class('mini-time')
        row.append(self.time)

        def btn(icon, tip, cb, extra=None):
            b = Gtk.Button(icon_name=icon, tooltip_text=tip, valign=Gtk.Align.CENTER)
            b.add_css_class('flat')
            b.add_css_class('hb-btn')
            if extra:
                b.add_css_class(extra)
            b.connect('clicked', lambda *_: cb())
            row.append(b)
            return b

        self.prev_btn = btn('media-skip-backward-symbolic', 'Previous', player.prev)
        self.play_btn = btn('media-playback-pause-symbolic', 'Play / Pause', player.toggle_pause, 'mini-play')
        self.next_btn = btn('media-skip-forward-symbolic', 'Next', player.next)
        btn('window-close-symbolic', 'Stop', self._close)
        outer.append(row)
        self.set_child(outer)

    # ------------------------------------------------------------------
    def show(self):
        self.set_reveal_child(True)
        self._update()
        if self._timer is None:
            self._timer = GLib.timeout_add(400, self._update)

    def hide(self):
        self.set_reveal_child(False)
        if self._timer is not None:
            GLib.source_remove(self._timer)
            self._timer = None

    def _close(self):
        self.hide()
        self._on_close()

    def _update(self):
        p = self.player
        v = p.manager.current
        if not p.is_active or v is None or not p.is_audio:
            self.hide()
            return False
        if v['file_path'] != self._shown_path:
            self._shown_path = v['file_path']
            self.title.set_label(v.get('title') or '')
            self.artist.set_label(' · '.join(x for x in (v.get('artist') or 'Unknown artist', v.get('album')) if x))
        if p.cover_path != self._shown_cover:  # art loads asynchronously per song
            self._shown_cover = p.cover_path
            if p.cover_path:
                self.cover.set_filename(p.cover_path)
            else:
                self.cover.set_paintable(None)
        self.play_btn.set_icon_name('media-playback-start-symbolic' if p.paused else 'media-playback-pause-symbolic')
        self.prev_btn.set_sensitive(True)
        self.next_btn.set_sensitive(p.manager.has_next())
        dur = p.duration or 0
        self.progress.set_fraction(min(1.0, p.position / dur) if dur else 0.0)
        self.time.set_label(f'{format_duration(p.position)} / {format_duration(dur)}' if dur else '')
        return True
