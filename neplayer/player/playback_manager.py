"""Playlist, resume points and watch-history bookkeeping for the full player."""
import logging
import os
import random

log = logging.getLogger(__name__)

COMPLETE_FRACTION = 0.95
MIN_RESUME = 5.0


class PlaybackManager:
    def __init__(self, db, settings):
        self.db = db
        self.settings = settings
        self.playlist = []
        self._order = []   # playback order (indices into playlist); shuffled when shuffle is on
        self._pos = -1     # position in _order

    # --- playlist ----------------------------------------------------------
    @property
    def index(self):
        return self._order[self._pos] if 0 <= self._pos < len(self._order) else -1

    @property
    def position_in_order(self):
        return self._pos

    @property
    def current(self):
        i = self.index
        return self.playlist[i] if 0 <= i < len(self.playlist) else None

    def set_playlist(self, videos, current):
        self.playlist = [v for v in videos if not v.get('missing')] or [current]
        ids = [v.get('id') for v in self.playlist]
        if current.get('id') in ids and current.get('id') is not None:
            idx = ids.index(current['id'])
        else:
            paths = [v['file_path'] for v in self.playlist]
            if current['file_path'] in paths:
                idx = paths.index(current['file_path'])
            else:
                self.playlist = [current]
                idx = 0
        self._build_order(idx)

    def _build_order(self, current_idx):
        n = len(self.playlist)
        if self.settings['shuffle'] and n > 1:
            rest = [i for i in range(n) if i != current_idx]
            random.shuffle(rest)
            self._order = [current_idx] + rest
            self._pos = 0
        else:
            self._order = list(range(n))
            self._pos = current_idx

    def reshuffle(self):
        """Apply a changed shuffle setting without interrupting the current item."""
        if self.playlist:
            self._build_order(self.index)

    # --- navigation ----------------------------------------------------------
    @property
    def repeat(self):
        return self.settings['repeat'] if self.settings['repeat'] in ('off', 'all', 'one') else 'off'

    def _step(self, delta):
        new = self._pos + delta
        n = len(self._order)
        if 0 <= new < n:
            return new
        if self.repeat == 'all' and n > 1:
            return new % n
        return None

    def has_next(self):
        return self._step(1) is not None

    def has_prev(self):
        return self._step(-1) is not None

    def peek_next(self):
        p = self._step(1)
        return self.playlist[self._order[p]] if p is not None else None

    def go(self, delta):
        p = self._step(delta)
        if p is None:
            return None
        self._pos = p
        return self.current

    def resume_position(self, video):
        """Seconds to start at, or 0."""
        if not self.settings['resume_playback'] or video.get('id') is None:
            return 0.0
        if video.get('media_kind') == 'audio':  # songs always start from the beginning
            return 0.0
        fresh = self.db.get_video(video['id'])
        if not fresh:
            return 0.0
        pos, dur = fresh.get('position') or 0, fresh.get('duration') or 0
        if fresh.get('completed') or pos < MIN_RESUME:
            return 0.0
        if dur and pos > dur - 10:
            return 0.0
        return float(pos)

    def save(self, video, position, duration):
        if video is None or video.get('id') is None or position is None:
            return
        if not self.settings['keep_history']:  # Privacy: don't record what was watched
            return
        completed = bool(duration) and position >= duration * COMPLETE_FRACTION
        try:
            self.db.save_position(video['id'], 0.0 if completed else float(position), completed)
        except Exception:
            log.exception('Could not save playback position')

    @staticmethod
    def exists(video):
        return os.path.exists(video['file_path'])
