"""Real-time hover previews played straight from the original file.

One shared MpvGLArea (one mpv core) exists for the whole app. When the
pointer rests on a card for `preview_delay_ms`, the widget is re-parented
into that card and plays a muted, looping segment of the real video. Only
one preview can ever be active; leaving the card, scrolling, opening the
player or the card being recycled all stop it.
"""
import logging

import gi

gi.require_version('Gtk', '4.0')
from gi.repository import GLib

from neplayer.player.mpv_widget import MpvGLArea

log = logging.getLogger(__name__)


class PreviewManager:
    def __init__(self, settings):
        self.settings = settings
        self._area = None
        self._failed = False
        self._timer = None
        self._pending_card = None
        self.active_card = None
        self._ready_handler = None
        self._suspended = False
        self.starts = 0  # for diagnostics/tests
        self.last_stop_reason = None

    # --- public API used by cards ----------------------------------------
    def hover_enter(self, card):
        if not self.settings['preview_enabled'] or self._failed or self._suspended:
            return
        if card is self.active_card or card is self._pending_card:
            return
        self._cancel_timer()
        self._pending_card = card
        self._timer = GLib.timeout_add(max(50, int(self.settings['preview_delay_ms'])),
                                       self._on_timer)

    def hover_leave(self, card):
        if card is self._pending_card:
            self._cancel_timer()
        if card is self.active_card:
            self.stop('leave')

    def card_unbound(self, card):
        self.hover_leave(card)

    def suspend(self, suspended=True):
        """Disable previews while the full player is visible."""
        self._suspended = suspended
        if suspended:
            self._cancel_timer()
            self.stop('suspend')

    def stop(self, reason='stop'):
        if self.active_card is not None or self._pending_card is not None:
            log.debug('preview stop: %s', reason)
            self.last_stop_reason = reason
        self._cancel_timer()
        card = self.active_card
        self.active_card = None
        if self._area is None:
            return
        try:
            self._area.mpv.command('stop')
        except Exception:
            log.debug('preview stop failed', exc_info=True)
        if self._ready_handler is not None:
            self._area.disconnect(self._ready_handler)
            self._ready_handler = None
        if card is not None:
            card.detach_preview(self._area)
        elif self._area.get_parent() is not None:
            self._area.unparent()

    def shutdown(self):
        self.stop()
        if self._area is not None:
            self._area.shutdown()
            self._area = None

    # --- internals -------------------------------------------------------
    def _cancel_timer(self):
        if self._timer is not None:
            GLib.source_remove(self._timer)
            self._timer = None
        self._pending_card = None

    def _ensure_area(self):
        if self._area is not None:
            return self._area
        try:
            vol = int(self.settings['preview_volume'])
            opts = dict(
                hwdec=self.settings['hwdec'],
                mute='yes' if vol <= 0 else 'no',
                volume=str(max(0, vol)),
                loop_file='inf',
                cache='yes',
                demuxer_max_bytes='8MiB',
                demuxer_readahead_secs='4',
                vd_lavc_threads='2',
                sub_auto='no',
                sid='no',
                hr_seek='no',
                video_sync='audio',
            )
            if vol <= 0:
                opts['aid'] = 'no'  # don't even decode audio when muted
            self._area = MpvGLArea(**opts)
            self._area.add_css_class('preview-surface')
            self._area.connect('first-frame', self._on_first_frame)
            self._area.set_can_target(False)
        except Exception:
            log.exception('Preview engine unavailable; falling back to static thumbnails')
            self._failed = True
            return None
        return self._area

    def _on_timer(self):
        self._timer = None
        card = self._pending_card
        self._pending_card = None
        if card is None or not card.get_mapped() or card.item is None:
            return False
        video = card.item.data
        if video.get('missing') or video.get('error'):
            return False
        area = self._ensure_area()
        if area is None:
            return False
        self.stop()
        self.active_card = card
        # Not 0: GTK skips drawing fully transparent widgets, so mpv would never
        # render a frame. 1% is invisible over the thumbnail but still renders.
        area.set_opacity(0.01)
        card.attach_preview(area)
        if area.is_ready:
            self._load(video)
        else:
            self._ready_handler = area.connect('ready', self._on_ready, video)
        return False

    def _on_ready(self, area, video):
        area.disconnect(self._ready_handler)
        self._ready_handler = None
        if self.active_card is not None and self.active_card.item is not None \
                and self.active_card.item.data['id'] == video['id']:
            self._load(video)

    def _load(self, video):
        dur = float(video.get('duration') or 0)
        seg = max(2, int(self.settings['preview_duration_s']))
        if dur > seg * 3:
            start = dur * 0.25
        elif dur > seg:
            start = (dur - seg) / 2
        else:
            start = 0
        end = min(dur, start + seg) if dur else start + seg
        opts = {'start': f'{start:.2f}'}
        if dur > seg:
            opts['ab-loop-a'] = f'{start:.2f}'
            opts['ab-loop-b'] = f'{end:.2f}'
        max_h = int(self.settings['preview_max_height'])
        if max_h > 0 and (video.get('height') or 0) > max_h * 1.5:
            # Reduce GPU upload cost for big sources; decode cost is unchanged.
            opts['vf'] = f'scale=-2:{max_h}'
        self._area.expect_first_frame()
        try:
            self._area.mpv.command('loadfile', video['file_path'], 'replace',
                                   ','.join(f'{k}={v}' for k, v in opts.items()))
            self.starts += 1
        except Exception:
            log.exception('Preview failed to load %s', video['file_path'])
            self.stop()

    def _on_first_frame(self, area):
        if self.active_card is not None and area.get_parent() is not None:
            area.set_opacity(1)
            self.active_card.on_preview_started()
