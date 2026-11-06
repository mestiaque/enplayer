"""Full embedded mpv player with auto-hiding overlay controls."""
import logging
import os
import time
from pathlib import Path

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Gdk', '4.0')
from gi.repository import Gdk, Gio, GLib, GObject, Gtk

import mpv

from neplayer.models.video import format_duration, resolution_label
from neplayer.player import shortcuts
from neplayer.player.mpv_widget import MpvGLArea
from neplayer.player.playback_manager import PlaybackManager
from neplayer.config import AUDIO_EXTENSIONS
from neplayer.core import thumbnail
import threading
from neplayer.visualizer.view import VisualizerView
from neplayer.visualizer.panel import VisualizerPanel

log = logging.getLogger(__name__)

HIDE_DELAY_MS = 2600
SAVE_INTERVAL_S = 5
SPEEDS = [0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 3.0]


def _icon_button(icon, tooltip, cb=None, css=('flat', 'player-btn')):
    b = Gtk.Button(icon_name=icon, tooltip_text=tooltip)
    for c in css:
        b.add_css_class(c)
    if cb:
        b.connect('clicked', lambda *_: cb())
    return b


class PlayerView(Gtk.Overlay):
    __gsignals__ = {
        'close-requested': (GObject.SignalFlags.RUN_FIRST, None, ()),
        'fullscreen-toggle': (GObject.SignalFlags.RUN_FIRST, None, ()),
        'escape': (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        self.settings = ctx.settings
        self.manager = PlaybackManager(ctx.db, ctx.settings)
        self.add_css_class('player')
        self.set_focusable(True)

        self._duration = 0.0
        self._position = 0.0
        self._paused = False
        self._seeking_drag = False
        self._last_save = 0.0
        self._hide_src = None
        self._osd_src = None
        self._click_src = None
        self._next_src = None
        self._next_countdown = 0
        self._tracks = []
        self._active = False
        self._loaded_path = None
        self._eof_handled = False
        self._pending_start = 0.0

        self.area = MpvGLArea(
            hwdec=self.settings['hwdec'], keep_open='yes', volume_max='130',
            volume=str(self.settings['volume']), sub_auto='fuzzy', audio_file_auto='fuzzy',
            osd_level='0', ytdl='no', hr_seek='yes', cache='yes', demuxer_max_bytes='150MiB',
            screenshot_directory=str(Path(GLib.get_user_special_dir(
                GLib.UserDirectory.DIRECTORY_PICTURES) or Path.home()) / 'Screenshots'),
            screenshot_format='png', sub_font_size='46', sub_border_size='2.6',
            sub_shadow_offset='1', sub_color='#FFFFFFFF', sub_border_color='#E6000000',
        )
        self.mpv = self.area.mpv
        self.set_child(self.area)
        self.apply_theme()
        self._is_audio = False
        self.cover_path = None
        self._build_now_playing()

        for prop in ('time-pos', 'duration', 'pause', 'volume', 'mute', 'track-list',
                     'eof-reached', 'speed', 'paused-for-cache', 'seeking', 'sub-visibility'):
            self.mpv.observe_property(prop, self._mpv_prop)
        self.mpv.register_event_callback(self._mpv_event)

        self._build_top_bar()
        self._build_bottom_bar()
        self._build_center()
        self._build_next_card()
        self._build_actions()
        self.connect('realize', self._watch_window_focus)
        self.settings.connect('changed', lambda _s, k: self._apply_viz_state()
                              if k in ('viz_enabled', 'viz_background') and self._active else None)

        motion = Gtk.EventControllerMotion()
        motion.connect('motion', self._on_motion)
        self.add_controller(motion)

        click = Gtk.GestureClick(button=Gdk.BUTTON_PRIMARY)
        click.connect('pressed', self._on_video_click)
        self.area.add_controller(click)
        rclick = Gtk.GestureClick(button=Gdk.BUTTON_SECONDARY)
        rclick.connect('pressed', lambda *_: self.toggle_pause())
        self.area.add_controller(rclick)

        scroll = Gtk.EventControllerScroll(flags=Gtk.EventControllerScrollFlags.VERTICAL)
        scroll.connect('scroll', self._on_scroll)
        self.area.add_controller(scroll)

    # Colour mpv paints around the video (letterbox), per theme.
    LETTERBOX = {'dark': '#000000', 'light': '#ececf1', 'glass': '#0e0c18'}

    def apply_theme(self):
        try:
            self.mpv['background'] = self.LETTERBOX.get(self.settings['theme'], '#000000')
        except Exception:
            log.debug('mpv background colour not supported', exc_info=True)
        self.area.queue_render()

    # =================================================================== UI
    def _build_top_bar(self):
        bar = Gtk.Box(spacing=10)
        bar.add_css_class('player-top')
        back = _icon_button('go-previous-symbolic', 'Back to library (Esc)', self.close)
        back.add_css_class('circular')
        bar.append(back)
        titles = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER, hexpand=True)
        self.title_lbl = Gtk.Label(xalign=0, ellipsize=3)
        self.title_lbl.add_css_class('player-title')
        self.sub_lbl = Gtk.Label(xalign=0, ellipsize=3)
        self.sub_lbl.add_css_class('player-subtitle')
        titles.append(self.title_lbl)
        titles.append(self.sub_lbl)
        bar.append(titles)
        self.fav_btn = Gtk.ToggleButton(icon_name='non-starred-symbolic', tooltip_text='Favorite')
        self.fav_btn.add_css_class('flat')
        self.fav_btn.add_css_class('player-btn')
        self._fav_handler = self.fav_btn.connect('toggled', self._on_fav)
        bar.append(self.fav_btn)
        self.shot_btn = _icon_button('camera-photo-symbolic', 'Screenshot (Ctrl+S)', self.screenshot)
        bar.append(self.shot_btn)
        self.viz_btn = Gtk.ToggleButton(icon_name='nep-visualizer-symbolic', tooltip_text='Visualizer (V)')
        self.viz_btn.add_css_class('flat')
        self.viz_btn.add_css_class('player-btn')
        self.viz_btn.set_active(bool(self.settings['viz_enabled']))
        self.viz_btn.connect('toggled', lambda b: self.settings.set('viz_enabled', b.get_active()))
        bar.append(self.viz_btn)
        self.viz_menu = Gtk.MenuButton(icon_name='nep-sliders-symbolic', tooltip_text='Visualizer settings')
        self.viz_menu.add_css_class('flat')
        self.viz_menu.add_css_class('player-btn')
        bar.append(self.viz_menu)
        bar.append(_icon_button('dialog-information-symbolic', 'Statistics (I)',
                                lambda: self._do('stats', None)))
        close = _icon_button('window-close-symbolic', 'Close player (Esc)', self.close)
        close.add_css_class('player-close')
        bar.append(close)
        self.top = Gtk.Revealer(transition_type=Gtk.RevealerTransitionType.CROSSFADE,
                                transition_duration=220, reveal_child=True, valign=Gtk.Align.START)
        self.top.set_child(bar)
        self.add_overlay(self.top)

    def _build_bottom_bar(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.add_css_class('player-controls')

        seek_row = Gtk.Box(spacing=12)
        self.pos_lbl = Gtk.Label(label='0:00')
        self.pos_lbl.add_css_class('time-label')
        self.seek = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL, hexpand=True)
        self.seek.set_range(0, 1)
        self.seek.set_draw_value(False)
        self.seek.add_css_class('seek-bar')
        self.seek.connect('change-value', self._on_seek_change)
        drag = Gtk.GestureClick()
        drag.connect('pressed', lambda *_: setattr(self, '_seeking_drag', True))
        drag.connect('released', self._on_seek_release)
        drag.connect('stopped', lambda *_: setattr(self, '_seeking_drag', False))
        self.seek.add_controller(drag)
        seek_hover = Gtk.EventControllerMotion()
        seek_hover.connect('motion', self._on_seek_hover)
        self.seek.add_controller(seek_hover)
        self.seek.set_has_tooltip(True)
        self.dur_lbl = Gtk.Label(label='0:00')
        self.dur_lbl.add_css_class('time-label')
        seek_row.append(self.pos_lbl)
        seek_row.append(self.seek)
        seek_row.append(self.dur_lbl)
        box.append(seek_row)

        row = Gtk.Box(spacing=4)
        self.prev_btn = _icon_button('media-skip-backward-symbolic', 'Previous (P)', self.prev)
        self.back_btn = _icon_button('media-seek-backward-symbolic', 'Back 10 s (J)',
                                     lambda: self.seek_relative(-10))
        self.play_btn = _icon_button('media-playback-pause-symbolic', 'Play / Pause (Space)',
                                     self.toggle_pause, css=('player-btn', 'play-btn', 'circular'))
        self.fwd_btn = _icon_button('media-seek-forward-symbolic', 'Forward 10 s (L)',
                                    lambda: self.seek_relative(10))
        self.next_btn = _icon_button('media-skip-forward-symbolic', 'Next (N)', self.next)
        for b in (self.prev_btn, self.back_btn, self.play_btn, self.fwd_btn, self.next_btn):
            row.append(b)
        # Music controls (shown for audio)
        self.shuffle_btn = Gtk.ToggleButton(icon_name='media-playlist-shuffle-symbolic', tooltip_text='Shuffle')
        self.shuffle_btn.add_css_class('flat')
        self.shuffle_btn.add_css_class('player-btn')
        self.shuffle_btn.set_active(bool(self.settings['shuffle']))
        self.shuffle_btn.connect('toggled', self._on_shuffle)
        self.repeat_btn = _icon_button('media-playlist-repeat-symbolic', 'Repeat', self._cycle_repeat)
        row.append(self.shuffle_btn)
        row.append(self.repeat_btn)
        self._update_repeat_btn()

        self.mute_btn = _icon_button('audio-volume-high-symbolic', 'Mute (M)', self.toggle_mute)
        row.append(self.mute_btn)
        self.vol = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL)
        self.vol.set_range(0, 130)
        self.vol.set_draw_value(False)
        self.vol.set_size_request(110, -1)
        self.vol.add_mark(100, Gtk.PositionType.BOTTOM, None)
        self.vol.add_css_class('volume-bar')
        self.vol.connect('change-value', lambda _s, _sc, v: self._set_volume(v) or False)
        row.append(self.vol)

        self.status_lbl = Gtk.Label(hexpand=True, xalign=0)
        self.status_lbl.add_css_class('player-status')
        row.append(self.status_lbl)

        self.speed_btn = Gtk.MenuButton(label='1×', tooltip_text='Playback speed')
        self.speed_btn.add_css_class('flat')
        self.speed_btn.add_css_class('player-btn')
        self.speed_btn.add_css_class('speed-btn')
        speed_menu = Gio.Menu()
        for s in SPEEDS:
            speed_menu.append('Normal' if s == 1 else f'{s:g}×', f'player.speed(\'{s}\')')
        self.speed_btn.set_menu_model(speed_menu)
        row.append(self.speed_btn)

        self.sub_btn = Gtk.MenuButton(icon_name='media-view-subtitles-symbolic',
                                      tooltip_text='Subtitles (S)')
        self.sub_btn.add_css_class('flat')
        self.sub_btn.add_css_class('player-btn')
        row.append(self.sub_btn)
        self.audio_btn = Gtk.MenuButton(icon_name='audio-x-generic-symbolic',
                                        tooltip_text='Audio track (A)')
        self.audio_btn.add_css_class('flat')
        self.audio_btn.add_css_class('player-btn')
        row.append(self.audio_btn)
        self.fs_btn = _icon_button('view-fullscreen-symbolic', 'Fullscreen (F)',
                                   lambda: self.emit('fullscreen-toggle'))
        row.append(self.fs_btn)
        box.append(row)

        hover = Gtk.EventControllerMotion()
        hover.connect('enter', lambda *_: setattr(self, '_over_controls', True))
        hover.connect('leave', lambda *_: setattr(self, '_over_controls', False))
        box.add_controller(hover)
        self._over_controls = False

        self.bottom = Gtk.Revealer(transition_type=Gtk.RevealerTransitionType.CROSSFADE,
                                   transition_duration=220, reveal_child=True, valign=Gtk.Align.END)
        self.bottom.set_child(box)
        self.add_overlay(self.bottom)

    def _build_center(self):
        self.osd = Gtk.Label()
        self.osd.add_css_class('osd-message')
        self.osd_rev = Gtk.Revealer(transition_type=Gtk.RevealerTransitionType.CROSSFADE,
                                    transition_duration=150, halign=Gtk.Align.CENTER,
                                    valign=Gtk.Align.START, can_target=False)
        self.osd_rev.set_margin_top(90)
        self.osd_rev.set_child(self.osd)
        self.add_overlay(self.osd_rev)

        self.flash = Gtk.Image(pixel_size=44)
        self.flash.add_css_class('center-flash')
        self.flash_rev = Gtk.Revealer(transition_type=Gtk.RevealerTransitionType.CROSSFADE,
                                      transition_duration=250, halign=Gtk.Align.CENTER,
                                      valign=Gtk.Align.CENTER, can_target=False)
        self.flash_rev.set_child(self.flash)
        self.add_overlay(self.flash_rev)

        self.spinner = Gtk.Spinner(halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER,
                                   width_request=48, height_request=48, can_target=False)
        self.spinner.set_visible(False)
        self.add_overlay(self.spinner)

        self.error_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8,
                                 halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER)
        self.error_box.add_css_class('player-error')
        icon = Gtk.Image.new_from_icon_name('dialog-warning-symbolic')
        icon.set_pixel_size(48)
        self.error_title = Gtk.Label()
        self.error_title.add_css_class('title-3')
        self.error_desc = Gtk.Label(wrap=True, max_width_chars=60, justify=Gtk.Justification.CENTER)
        self.error_desc.add_css_class('dim-label')
        self.error_box.append(icon)
        self.error_box.append(self.error_title)
        self.error_box.append(self.error_desc)
        self.error_box.set_visible(False)
        self.add_overlay(self.error_box)

    def _build_next_card(self):
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        card.add_css_class('up-next')
        self.next_hdr = Gtk.Label(xalign=0)
        self.next_hdr.add_css_class('caption-heading')
        self.next_title = Gtk.Label(xalign=0, ellipsize=3, max_width_chars=32)
        self.next_title.add_css_class('heading')
        btns = Gtk.Box(spacing=8)
        play = Gtk.Button(label='Play now')
        play.add_css_class('suggested-action')
        play.connect('clicked', lambda *_: (self._cancel_next(), self.next()))
        cancel = Gtk.Button(label='Cancel')
        cancel.connect('clicked', lambda *_: self._cancel_next())
        btns.append(play)
        btns.append(cancel)
        card.append(self.next_hdr)
        card.append(self.next_title)
        card.append(btns)
        self.next_rev = Gtk.Revealer(transition_type=Gtk.RevealerTransitionType.SLIDE_LEFT,
                                     halign=Gtk.Align.END, valign=Gtk.Align.END)
        self.next_rev.set_margin_end(28)
        self.next_rev.set_margin_bottom(130)
        self.next_rev.set_child(card)
        self.add_overlay(self.next_rev)

    def _build_actions(self):
        group = Gio.SimpleActionGroup()
        speed = Gio.SimpleAction.new_stateful('speed', GLib.VariantType('s'), GLib.Variant('s', '1.0'))
        speed.connect('activate', lambda a, v: self._set_speed(float(v.get_string())))
        group.add_action(speed)
        sid = Gio.SimpleAction.new_stateful('sid', GLib.VariantType('s'), GLib.Variant('s', 'no'))
        sid.connect('activate', lambda a, v: self._set_track('sid', v.get_string()))
        group.add_action(sid)
        aid = Gio.SimpleAction.new_stateful('aid', GLib.VariantType('s'), GLib.Variant('s', 'auto'))
        aid.connect('activate', lambda a, v: self._set_track('aid', v.get_string()))
        group.add_action(aid)
        load_sub = Gio.SimpleAction.new('load-sub', None)
        load_sub.connect('activate', lambda *_: self._load_external_sub())
        group.add_action(load_sub)
        self.actions = group
        self.insert_action_group('player', group)

    # ============================================================ playback
    # ============================================================ music
    def _build_now_playing(self):
        """Cover art, title and artist shown instead of the (empty) video for audio files."""
        self.np = Gtk.Overlay(visible=False, can_target=False)
        self.np.add_css_class('now-playing')
        self.np_bg = Gtk.Picture(can_shrink=True, keep_aspect_ratio=False)
        self.np_bg.add_css_class('np-bg')
        self.np.set_child(self.np_bg)
        self.np_scrim = Gtk.Box()
        self.np_scrim.add_css_class('np-scrim')
        self.np.add_overlay(self.np_scrim)
        self._pos_mono = time.monotonic()
        self.viz = VisualizerView(self.settings, self.viz_clock)
        self.viz.connect('preset-changed', lambda _v, name: self.show_osd(name) if self._is_audio else None)
        self.np.add_overlay(self.viz)
        center = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6,
                         halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER)
        center.add_css_class('np-center')
        self.np_cover = Gtk.Picture(can_shrink=True, keep_aspect_ratio=True)
        self.np_cover.set_size_request(300, 300)
        self.np_cover.set_overflow(Gtk.Overflow.HIDDEN)
        self.np_cover.add_css_class('np-cover')
        self.np_title = Gtk.Label(ellipsize=3, max_width_chars=48, justify=Gtk.Justification.CENTER)
        self.np_title.add_css_class('np-title')
        self.np_artist = Gtk.Label(ellipsize=3, max_width_chars=60)
        self.np_artist.add_css_class('np-artist')
        self.np_album = Gtk.Label(ellipsize=3, max_width_chars=60)
        self.np_album.add_css_class('np-album')
        for w in (self.np_cover, self.np_title, self.np_artist, self.np_album):
            center.append(w)
        self.np_center = center
        self.np.add_overlay(center)
        self.add_overlay(self.np)

    @staticmethod
    def is_audio_item(v):
        return v.get('media_kind') == 'audio' or \
            os.path.splitext(v.get('file_path', ''))[1].lower().lstrip('.') in AUDIO_EXTENSIONS

    @property
    def is_audio(self):
        return self._is_audio

    @property
    def is_active(self):
        return self._active

    @property
    def paused(self):
        return self._paused

    @property
    def position(self):
        return self._position

    @property
    def duration(self):
        return self._duration

    # ------------------------------------------------------- visualizer
    def viz_clock(self):
        """(playing, seconds) for the visualizer, interpolated between mpv time updates."""
        playing = self._active and self._is_audio and not self._paused
        t = self._position
        if playing:
            t += min(0.5, time.monotonic() - self._pos_mono) * float(self.settings['playback_speed'] or 1.0)
        return playing, t

    def _watch_window_focus(self, *_):
        root = self.get_root()
        if root is not None:
            root.connect('notify::is-active', self._on_window_active)

    def _on_window_active(self, win, _p):
        # Popovers are separate surfaces: close them when the user switches to another app,
        # otherwise they can stay floating above other windows. Opening a popover itself makes
        # the window inactive for a moment on X11, so only act if it *stays* inactive.
        if win.is_active():
            return

        def still_inactive():
            if not win.is_active():
                for b in (self.viz_menu, self.speed_btn, self.sub_btn, self.audio_btn):
                    if b.get_popover() is not None and b.get_popover().get_visible():
                        b.popdown()
            return False
        GLib.timeout_add(400, still_inactive)

    def _apply_viz_state(self):
        if self.viz_menu.get_popover() is None:
            panel = VisualizerPanel(self.viz)
            # While the panel is open the controls must stay visible (its parent is the top bar),
            # and when it closes the normal auto-hide resumes.
            panel.connect('show', lambda *_: self.show_controls(force=True))
            panel.connect('closed', lambda *_: self.show_controls())
            self.viz_menu.set_popover(panel)
        on = self._is_audio and bool(self.settings['viz_enabled'])
        self.viz.set_visible(on)
        self.np_center.set_visible(self._is_audio and not on)
        self.np_scrim.set_visible(not on or self.settings['viz_background'] == 'cover')
        self.viz_btn.set_visible(self._is_audio)
        self.viz_menu.set_visible(self._is_audio and on)
        if self.viz_btn.get_active() != bool(self.settings['viz_enabled']):
            self.viz_btn.set_active(bool(self.settings['viz_enabled']))
        if on:
            self._schedule_hide()

    def _set_audio_mode(self, v):
        audio = self.is_audio_item(v)
        self._is_audio = audio
        self.np.set_visible(audio)
        for w in (self.shot_btn, self.sub_btn, self.back_btn, self.fwd_btn):
            w.set_visible(not audio)
        self.shuffle_btn.set_visible(audio)
        self.repeat_btn.set_visible(audio)
        (self.add_css_class if audio else self.remove_css_class)('audio-mode')
        if not audio:
            self.cover_path = None
            self.viz.stop()
            self._apply_viz_state()
            return
        self.viz.set_track(v['file_path'])
        self._apply_viz_state()
        self.np_title.set_label(v.get('title') or os.path.basename(v['file_path']))
        self.np_artist.set_label(v.get('artist') or 'Unknown artist')
        album = ' · '.join(str(x) for x in (v.get('album'), v.get('year') or None) if x)
        self.np_album.set_label(album)
        self.np_album.set_visible(bool(album))
        self.cover_path = None  # until this song's art is ready
        self.np_cover.set_paintable(None)
        self.np_bg.set_paintable(None)
        path, mtime = v['file_path'], v.get('file_mtime') or 0
        seed = f"{v.get('album') or ''}{v.get('artist') or ''}" or os.path.basename(path)

        def work():
            try:
                cover, bg = thumbnail.cover_art(path, mtime, self.settings['cache_dir'], seed)
            except Exception:
                log.exception('cover art failed for %s', path)
                return
            GLib.idle_add(apply, cover, bg, priority=GLib.PRIORITY_DEFAULT)

        def apply(cover, bg):
            if self.manager.current is not None and self.manager.current.get('file_path') == path:
                self.cover_path = cover
                self.viz.set_cover(cover)
                try:  # fixed display size; the file is larger for sharpness on HiDPI
                    from gi.repository import GdkPixbuf
                    scale = max(1, self.get_scale_factor())
                    pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(cover, 340 * scale, 340 * scale, True)
                    self.np_cover.set_pixbuf(pb)
                    self.np_cover.set_size_request(340, 340)
                except Exception:
                    self.np_cover.set_filename(cover)
                self.np_bg.set_filename(bg)
            return False
        threading.Thread(target=work, daemon=True, name='cover-art').start()

    def _on_shuffle(self, btn):
        self.settings.set('shuffle', btn.get_active())
        self.manager.reshuffle()
        self.prev_btn.set_sensitive(self.manager.has_prev())
        self.next_btn.set_sensitive(self.manager.has_next())
        self.show_osd('Shuffle on' if btn.get_active() else 'Shuffle off')

    def _cycle_repeat(self):
        nxt = {'off': 'all', 'all': 'one', 'one': 'off'}[self.manager.repeat]
        self.settings.set('repeat', nxt)
        self._update_repeat_btn()
        self.prev_btn.set_sensitive(self.manager.has_prev())
        self.next_btn.set_sensitive(self.manager.has_next())
        self.show_osd({'off': 'Repeat off', 'all': 'Repeat all', 'one': 'Repeat one'}[nxt])

    def _update_repeat_btn(self):
        mode = self.manager.repeat
        self.repeat_btn.set_icon_name('media-playlist-repeat-song-symbolic' if mode == 'one'
                                      else 'media-playlist-repeat-symbolic')
        self.repeat_btn.set_tooltip_text({'off': 'Repeat: off', 'all': 'Repeat: all', 'one': 'Repeat: one'}[mode])
        (self.repeat_btn.add_css_class if mode != 'off' else self.repeat_btn.remove_css_class)('toggle-on')

    def play(self, video, playlist=None, from_start=False):
        self._cancel_next()
        if self._active and self.manager.current is not None:
            self._save_position()
        self.manager.set_playlist(playlist or [video], video)
        self._load_current(from_start=from_start)

    def _load_current(self, from_start=False):
        v = self.manager.current
        if v is None:
            return
        if v.get('id') is None and 'duration' not in v:
            # Opened from outside the library (Open With / sibling files): read tags now.
            from neplayer.core.library import probe_single
            meta = probe_single(v['file_path'])
            if meta:
                v.update({k: val for k, val in meta.items() if val is not None})
        self._active = True
        self._eof_handled = False
        self._duration = float(v.get('duration') or 0)
        self._position = 0.0
        self.error_box.set_visible(False)
        self.title_lbl.set_label(v.get('title') or os.path.basename(v['file_path']))
        self._set_audio_mode(v)
        self._update_subtitle_line(v)
        self._update_fav(v)
        self.prev_btn.set_sensitive(self.manager.has_prev())
        self.next_btn.set_sensitive(self.manager.has_next())
        self.seek.set_value(0)
        self.pos_lbl.set_label('0:00')
        self.dur_lbl.set_label(format_duration(self._duration) if self._duration else '--:--')
        self._tracks = []
        self._rebuild_track_menus()

        if not os.path.exists(v['file_path']):
            self._show_error('File not found',
                             f'{v["file_path"]}\nThe file was moved, deleted, or its drive is disconnected.')
            return

        start = 0.0 if from_start else self.manager.resume_position(v)
        self._pending_start = start
        opts = {}
        if start:
            opts['start'] = f'{start:.2f}'
        if self._is_audio:
            opts['vid'] = 'no'  # don't decode embedded cover art as a video track
        slang, alang = self.settings['subtitle_lang'], self.settings['audio_lang']
        try:
            self.mpv['slang'] = slang
            self.mpv['alang'] = alang
            self.mpv['sid'] = 'auto' if slang else 'no'
            self.mpv['hwdec'] = self.settings['hwdec']
            self.mpv['pause'] = False
            self.mpv['speed'] = float(self.settings['playback_speed'])
        except Exception:
            log.debug('could not set mpv option', exc_info=True)
        self._loaded_path = v['file_path']
        self.spinner.set_visible(True)
        self.spinner.start()
        load = lambda: self.mpv.command('loadfile', v['file_path'], 'replace',  # noqa: E731
                                        ','.join(f'{k}={x}' for k, x in opts.items()))
        if self.area.is_ready:
            load()
        else:
            hid = []

            def on_ready(*_):
                self.area.disconnect(hid[0])
                if self._loaded_path == v['file_path']:
                    load()
            hid.append(self.area.connect('ready', on_ready))
        if start:
            self.show_osd(f'Resumed at {format_duration(start)}  ·  Home to start over', 3500)
        self.show_controls()
        self.grab_focus()

    def _update_subtitle_line(self, v):
        bits = []
        n = len(self.manager.playlist)
        if self.is_audio_item(v):
            bits = [x for x in (v.get('artist'), v.get('album')) if x]
            if v.get('audio_codec'):
                bits.append(v['audio_codec'].upper())
            if n > 1:
                bits.append(f'{self.manager.position_in_order + 1} of {n}')
            self.sub_lbl.set_label('  ·  '.join(bits) or os.path.dirname(v['file_path']))
            return
        res = resolution_label(v.get('width'), v.get('height'))
        if res:
            bits.append(res)
        if v.get('video_codec'):
            bits.append(v['video_codec'].upper())
        if v.get('audio_codec'):
            bits.append(v['audio_codec'].upper())
        if v.get('fps'):
            bits.append(f'{v["fps"]:g} fps')
        n = len(self.manager.playlist)
        if n > 1:
            bits.append(f'{self.manager.position_in_order + 1} of {n}')
        self.sub_lbl.set_label('  ·  '.join(bits) or os.path.dirname(v['file_path']))

    def _update_fav(self, v):
        self.fav_btn.set_visible(v.get('id') is not None)
        self.fav_btn.handler_block(self._fav_handler)
        fresh = self.ctx.db.get_video(v['id']) if v.get('id') else None
        fav = bool(fresh and fresh['favorite'])
        self.fav_btn.set_active(fav)
        self.fav_btn.set_icon_name('starred-symbolic' if fav else 'non-starred-symbolic')
        self.fav_btn.handler_unblock(self._fav_handler)

    def _on_fav(self, btn):
        v = self.manager.current
        if v and v.get('id') is not None:
            self.ctx.library.set_favorite(v['id'], btn.get_active())
            btn.set_icon_name('starred-symbolic' if btn.get_active() else 'non-starred-symbolic')
            self.show_osd('Added to Favorites' if btn.get_active() else 'Removed from Favorites')

    def stop(self):
        """Save state and stop playback (player hidden)."""
        self._cancel_next()
        if self._active:
            self._save_position()
        self._active = False
        self._loaded_path = None
        self._is_audio = False
        self.viz.stop()
        try:
            self.mpv.command('stop')
        except Exception:
            pass
        self.spinner.stop()
        self.spinner.set_visible(False)
        self._show_cursor(True)

    def close(self):
        self.emit('close-requested')

    def shutdown(self):
        self.stop()
        self.area.shutdown()

    def _save_position(self):
        v = self.manager.current
        pos = self._position
        if v is not None and pos:
            self.manager.save(v, pos, self._duration)
        self._last_save = time.monotonic()

    def toggle_pause(self):
        if self.manager.current is None:
            return
        if self._eof_handled or self._position >= self._duration - 0.3 > 0:
            self.mpv.command('seek', 0, 'absolute')
            self.mpv['pause'] = False
            self._cancel_next()
            return
        self.mpv['pause'] = not self._paused
        self._flash('media-playback-start-symbolic' if self._paused
                    else 'media-playback-pause-symbolic')
        self.show_controls()

    def seek_relative(self, secs):
        try:
            self.mpv.command('seek', secs, 'relative+exact')
        except Exception:
            return
        self._flash('media-seek-forward-symbolic' if secs > 0 else 'media-seek-backward-symbolic')
        target = max(0, min(self._duration or 1e9, self._position + secs))
        self.show_osd(f'{"+" if secs > 0 else "−"}{abs(secs)} s   {format_duration(target)}')
        self.show_controls()

    def next(self):
        self._cancel_next()
        if self.manager.has_next():
            self._save_position()
            self.manager.go(1)
            self._load_current()

    def prev(self):
        self._cancel_next()
        if self._position > 5:
            self.mpv.command('seek', 0, 'absolute')
            return
        if self.manager.has_prev():
            self._save_position()
            self.manager.go(-1)
            self._load_current()

    def toggle_mute(self):
        self.mpv['mute'] = not self.mpv.mute
        self.show_osd('Muted' if self.mpv.mute else f'Volume {int(self.mpv.volume)}%')

    def _set_volume(self, v):
        v = max(0, min(130, round(v)))
        self.mpv['volume'] = v
        if self.mpv.mute and v > 0:
            self.mpv['mute'] = False
        self.settings.set('volume', int(v))

    def change_volume(self, delta):
        self._set_volume((self.mpv.volume or 0) + delta)
        self.show_osd(f'Volume {int(self.mpv.volume)}%')
        self.show_controls()

    def _set_speed(self, s):
        s = max(0.25, min(4.0, round(s, 2)))
        self.mpv['speed'] = s
        self.show_osd(f'Speed {s:g}×')

    def _set_track(self, kind, value):
        try:
            self.mpv[kind] = value if value in ('no', 'auto') else int(value)
        except Exception:
            log.debug('track switch failed', exc_info=True)
        name = 'Subtitles' if kind == 'sid' else 'Audio'
        if value == 'no':
            self.show_osd(f'{name} off')
        else:
            t = next((t for t in self._tracks if str(t.get('id')) == value
                      and t.get('type') == ('sub' if kind == 'sid' else 'audio')), None)
            if t:
                self.show_osd(f'{name}: {self._track_label(t)}')

    def cycle(self, kind):
        typ = 'sub' if kind == 'sid' else 'audio'
        ids = [str(t['id']) for t in self._tracks if t.get('type') == typ]
        if not ids:
            self.show_osd('No subtitles' if kind == 'sid' else 'No other audio tracks')
            return
        cur = self.actions.lookup_action(kind).get_state().get_string()
        options = (['no'] + ids) if kind == 'sid' else ids
        nxt = options[(options.index(cur) + 1) % len(options)] if cur in options else options[0]
        self._set_track(kind, nxt)

    def screenshot(self):
        try:
            d = self.mpv['screenshot-directory']
            os.makedirs(d, exist_ok=True)
            self.mpv.command('screenshot', 'video')
            self.show_osd(f'Screenshot saved to {d}')
        except Exception as e:
            self.show_osd(f'Screenshot failed: {e}')

    def _load_external_sub(self):
        dlg = Gtk.FileChooserNative(title='Load Subtitle File', transient_for=self.get_root(),
                                    action=Gtk.FileChooserAction.OPEN)
        f = Gtk.FileFilter()
        f.set_name('Subtitles')
        for ext in ('srt', 'ass', 'ssa', 'vtt', 'sub', 'idx'):
            f.add_pattern(f'*.{ext}')
            f.add_pattern(f'*.{ext.upper()}')
        dlg.add_filter(f)
        cur = self.manager.current
        if cur:
            dlg.set_current_folder(Gio.File.new_for_path(os.path.dirname(cur['file_path'])))

        def resp(d, r):
            if r == Gtk.ResponseType.ACCEPT:
                path = d.get_file().get_path()
                try:
                    self.mpv.command('sub-add', path, 'select')
                    self.show_osd(f'Loaded {os.path.basename(path)}')
                except Exception:
                    self.show_osd('Could not load subtitle file')
            d.destroy()
        dlg.connect('response', resp)
        dlg.show()
        self._sub_dialog = dlg

    # ===================================================== mpv callbacks
    def _mpv_prop(self, name, value):
        GLib.idle_add(self._on_prop, name, value, priority=GLib.PRIORITY_DEFAULT)

    def _mpv_event(self, event):
        try:
            eid = event.event_id.value
            if eid == mpv.MpvEventID.END_FILE:
                d = event.data
                if d.reason == mpv.MpvEventEndFile.ERROR:
                    GLib.idle_add(self._on_load_error, d.error, priority=GLib.PRIORITY_DEFAULT)
            elif eid == mpv.MpvEventID.FILE_LOADED:
                GLib.idle_add(self._on_file_loaded, priority=GLib.PRIORITY_DEFAULT)
        except Exception:
            log.debug('event handling failed', exc_info=True)

    def _on_file_loaded(self):
        self.spinner.stop()
        self.spinner.set_visible(False)
        return False

    def _on_load_error(self, code):
        self.spinner.stop()
        self.spinner.set_visible(False)
        if not self._active:
            return False
        reasons = {-13: 'Unrecognized file format', -14: 'No playable audio or video stream',
                   -16: 'Unsupported codec or corrupted data', -17: 'Unsupported codec or format'}
        self._show_error('This video can’t be played',
                         reasons.get(code, 'The file is damaged or uses an unsupported format') +
                         f'\n{self.manager.current["file_path"] if self.manager.current else ""}')
        return False

    def _show_error(self, title, desc):
        self.spinner.stop()
        self.spinner.set_visible(False)
        self.error_title.set_label(title)
        self.error_desc.set_label(desc)
        self.error_box.set_visible(True)
        self.show_controls(force=True)

    def _on_prop(self, name, value):
        if name == 'time-pos':
            if value is None:
                return False
            self._position = float(value)
            self._pos_mono = time.monotonic()
            if not self._seeking_drag:
                self.seek.set_value(self._position)
            self.pos_lbl.set_label(format_duration(self._position))
            if self._duration:
                remaining = self._duration - self._position
                self.dur_lbl.set_tooltip_text(f'−{format_duration(remaining)} remaining')
            if self._active and time.monotonic() - self._last_save > SAVE_INTERVAL_S:
                self._save_position()
        elif name == 'duration':
            if value:
                self._duration = float(value)
                self.seek.set_range(0, self._duration)
                self.dur_lbl.set_label(format_duration(self._duration))
        elif name == 'pause':
            self._paused = bool(value)
            self.play_btn.set_icon_name('media-playback-start-symbolic' if self._paused
                                        else 'media-playback-pause-symbolic')
            if self._paused:
                self.show_controls(force=True)
                if self._active:
                    self._save_position()
            else:
                self._schedule_hide()
        elif name in ('volume', 'mute'):
            vol = self.mpv.volume or 0
            muted = bool(self.mpv.mute)
            self.vol.set_value(vol)
            icon = ('audio-volume-muted-symbolic' if muted or vol == 0 else
                    'audio-volume-low-symbolic' if vol < 34 else
                    'audio-volume-medium-symbolic' if vol < 67 else 'audio-volume-high-symbolic')
            self.mute_btn.set_icon_name(icon)
        elif name == 'speed':
            if value:
                self.speed_btn.set_label(f'{value:g}×')
                self.actions.lookup_action('speed').set_state(GLib.Variant('s', f'{float(value)}'))
        elif name == 'track-list':
            self._tracks = list(value or [])
            self._rebuild_track_menus()
        elif name == 'paused-for-cache':
            buffering = bool(value)
            self.spinner.set_visible(buffering)
            if buffering:
                self.spinner.start()
            else:
                self.spinner.stop()
        elif name == 'eof-reached':
            if value and self._active and not self._eof_handled:
                self._eof_handled = True
                self._on_eof()
        return False

    def _on_eof(self):
        v = self.manager.current
        if v is not None and v.get('id') is not None:
            self.manager.save(v, self._duration or self._position, self._duration)
        if self._is_audio:
            if self.manager.repeat == 'one':
                self.mpv.command('seek', 0, 'absolute')
                self.mpv['pause'] = False
                self._eof_handled = False
            elif self.manager.has_next():
                self.next()  # albums play back to back, no countdown
            return
        self.show_controls(force=True)
        if self.settings['autoplay_next'] and self.manager.has_next():
            self._next_countdown = 5
            nxt = self.manager.peek_next()
            self.next_title.set_label(nxt.get('title') or os.path.basename(nxt['file_path']))
            self.next_hdr.set_label(f'UP NEXT IN {self._next_countdown}')
            self.next_rev.set_reveal_child(True)
            self._next_src = GLib.timeout_add(1000, self._tick_next)

    def _tick_next(self):
        self._next_countdown -= 1
        if self._next_countdown <= 0:
            self._next_src = None
            self.next_rev.set_reveal_child(False)
            self.next()
            return False
        self.next_hdr.set_label(f'UP NEXT IN {self._next_countdown}')
        return True

    def _cancel_next(self):
        if self._next_src is not None:
            GLib.source_remove(self._next_src)
            self._next_src = None
        self.next_rev.set_reveal_child(False)

    # ======================================================== track menus
    @staticmethod
    def _track_label(t):
        parts = []
        if t.get('title'):
            parts.append(t['title'])
        if t.get('lang'):
            parts.append(t['lang'].upper() if len(t['lang']) <= 3 else t['lang'])
        if t.get('codec'):
            parts.append(t['codec'])
        if t.get('demux-channel-count'):
            ch = t['demux-channel-count']
            parts.append({1: 'mono', 2: 'stereo', 6: '5.1', 8: '7.1'}.get(ch, f'{ch}ch'))
        if t.get('external'):
            parts.append('external')
        return ' · '.join(parts) or f'Track {t.get("id")}'

    def _rebuild_track_menus(self):
        subs = [t for t in self._tracks if t.get('type') == 'sub']
        auds = [t for t in self._tracks if t.get('type') == 'audio']

        sm = Gio.Menu()
        sec = Gio.Menu()
        sec.append('Off', "player.sid('no')")
        for t in subs:
            sec.append(self._track_label(t), f"player.sid('{t['id']}')")
        sm.append_section(None, sec)
        sec2 = Gio.Menu()
        sec2.append('Load Subtitle File…', 'player.load-sub')
        sm.append_section(None, sec2)
        self.sub_btn.set_menu_model(sm)
        sel_sub = next((str(t['id']) for t in subs if t.get('selected')), 'no')
        self.actions.lookup_action('sid').set_state(GLib.Variant('s', sel_sub))
        if subs:
            self.sub_btn.add_css_class('has-tracks')
        else:
            self.sub_btn.remove_css_class('has-tracks')

        am = Gio.Menu()
        for t in auds:
            am.append(self._track_label(t), f"player.aid('{t['id']}')")
        if not auds:
            am.append('No audio', None)
        self.audio_btn.set_menu_model(am)
        self.audio_btn.set_sensitive(len(auds) > 0)
        sel_aud = next((str(t['id']) for t in auds if t.get('selected')), 'no')
        self.actions.lookup_action('aid').set_state(GLib.Variant('s', sel_aud))

    # ======================================================= interaction
    def _on_seek_change(self, _scale, _scroll, value):
        if self._duration:
            value = max(0, min(self._duration, value))
            try:
                self.mpv.command('seek', value, 'absolute' if self._seeking_drag else 'absolute+exact')
            except Exception:
                pass
            self.pos_lbl.set_label(format_duration(value))
            self._cancel_next()
            self._eof_handled = False
        self.show_controls()
        return False

    def _on_seek_release(self, *_):
        self._seeking_drag = False
        try:
            self.mpv.command('seek', self.seek.get_value(), 'absolute+exact')
        except Exception:
            pass

    def _on_seek_hover(self, _ctrl, x, _y):
        w = self.seek.get_width()
        if w > 0 and self._duration:
            # Gtk.Scale has ~ slider padding; approximate with full width.
            frac = max(0.0, min(1.0, x / w))
            self.seek.set_tooltip_text(format_duration(frac * self._duration))

    def _on_video_click(self, gesture, n_press, _x, _y):
        if n_press == 2:
            if self._click_src is not None:
                GLib.source_remove(self._click_src)
                self._click_src = None
            self.emit('fullscreen-toggle')
        elif n_press == 1:
            if self._click_src is not None:
                GLib.source_remove(self._click_src)
            self._click_src = GLib.timeout_add(230, self._single_click)

    def _single_click(self):
        self._click_src = None
        self.toggle_pause()
        return False

    def _on_scroll(self, _ctrl, _dx, dy):
        self.change_volume(-5 if dy > 0 else 5)
        return True

    def handle_key(self, keyval, state):
        if self._is_audio and not state & (Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.ALT_MASK):
            K = Gdk
            if keyval in (K.KEY_v, K.KEY_V):
                self.settings.set('viz_enabled', not self.settings['viz_enabled'])
                self.show_osd('Visualizer on' if self.settings['viz_enabled'] else 'Visualizer off')
                return True
            if self.settings['viz_enabled'] and keyval in (K.KEY_comma, K.KEY_period):
                self.viz.step_preset(-1 if keyval == K.KEY_comma else 1)
                return True
            if self.settings['viz_enabled'] and keyval in (K.KEY_r, K.KEY_R):
                self.viz.random_preset()
                return True
        hit = shortcuts.lookup(keyval, state)
        if hit is None:
            return False
        self._do(*hit)
        return True

    def _do(self, action, arg):
        if action == 'toggle-pause':
            self.toggle_pause()
        elif action == 'seek':
            self.seek_relative(arg)
        elif action == 'seek-percent':
            if self._duration:
                self.mpv.command('seek', arg, 'absolute-percent')
                self.show_osd(f'{arg}%  ·  {format_duration(self._duration * arg / 100)}')
        elif action == 'volume':
            self.change_volume(arg)
        elif action == 'fullscreen':
            self.emit('fullscreen-toggle')
        elif action == 'mute':
            self.toggle_mute()
        elif action == 'escape':
            self.emit('escape')
        elif action == 'cycle-sub':
            self.cycle('sid')
        elif action == 'cycle-audio':
            self.cycle('aid')
        elif action == 'speed':
            self._set_speed((self.mpv.speed or 1) + arg)
        elif action == 'speed-reset':
            self._set_speed(1.0)
        elif action == 'next':
            self.next()
        elif action == 'prev':
            self.prev()
        elif action == 'restart':
            self.mpv.command('seek', 0, 'absolute')
            self.show_osd('Restarted')
        elif action == 'frame-step':
            self.mpv.command('frame-step' if arg > 0 else 'frame-back-step')
            self.show_osd('Next frame' if arg > 0 else 'Previous frame')
        elif action == 'stats':
            try:
                self.mpv.command('script-binding', 'stats/display-stats-toggle')
            except Exception:
                self.show_osd('Statistics are unavailable')
        elif action == 'screenshot':
            self.screenshot()
        elif action == 'toggle-sub-visibility':
            vis = not self.mpv['sub-visibility']
            self.mpv['sub-visibility'] = vis
            self.show_osd('Subtitles shown' if vis else 'Subtitles hidden')

    # ============================================================ chrome
    def show_osd(self, text, ms=1300):
        self.osd.set_label(text)
        self.osd_rev.set_reveal_child(True)
        if self._osd_src is not None:
            GLib.source_remove(self._osd_src)
        self._osd_src = GLib.timeout_add(ms, self._hide_osd)

    def _hide_osd(self):
        self._osd_src = None
        self.osd_rev.set_reveal_child(False)
        return False

    def _flash(self, icon):
        self.flash.set_from_icon_name(icon)
        self.flash_rev.set_reveal_child(True)
        GLib.timeout_add(380, lambda: self.flash_rev.set_reveal_child(False) or False)

    def _on_motion(self, _ctrl, x, y):
        last = getattr(self, '_last_xy', None)
        if last is not None and abs(last[0] - x) < 2 and abs(last[1] - y) < 2:
            return
        self._last_xy = (x, y)
        self.show_controls()

    def _set_sub_pos(self, controls_visible):
        # Keep subtitles clear of the control bar while it is shown.
        h = max(1, self.get_height())
        pos = 100 - min(30, int(130 * 100 / h)) if controls_visible else 100
        try:
            if self.mpv['sub-pos'] != pos:
                self.mpv['sub-pos'] = pos
        except Exception:
            pass

    def show_controls(self, force=False):
        self.top.set_reveal_child(True)
        self.bottom.set_reveal_child(True)
        self._set_sub_pos(True)
        self._show_cursor(True)
        if force:
            if self._hide_src is not None:
                GLib.source_remove(self._hide_src)
                self._hide_src = None
            return
        self._schedule_hide()

    def _schedule_hide(self):
        if self._hide_src is not None:
            GLib.source_remove(self._hide_src)
        self._hide_src = GLib.timeout_add(HIDE_DELAY_MS, self._auto_hide)

    def _auto_hide(self):
        self._hide_src = None
        popover_open = any(b.get_popover() is not None and b.get_popover().get_visible()
                           for b in (self.speed_btn, self.sub_btn, self.audio_btn, self.viz_menu))
        if ((self._is_audio and not self.settings['viz_enabled']) or self._paused or self._over_controls or popover_open or self.error_box.get_visible()
                or self._seeking_drag or not self._active):
            self._schedule_hide()
            return False
        self.top.set_reveal_child(False)
        self.bottom.set_reveal_child(False)
        self._set_sub_pos(False)
        self._show_cursor(False)
        return False

    def _show_cursor(self, show):
        self.set_cursor(None if show else Gdk.Cursor.new_from_name('none'))

    def set_fullscreen_state(self, fs):
        self.fs_btn.set_icon_name('view-restore-symbolic' if fs else 'view-fullscreen-symbolic')
        self.fs_btn.set_tooltip_text('Exit fullscreen (F)' if fs else 'Fullscreen (F)')
