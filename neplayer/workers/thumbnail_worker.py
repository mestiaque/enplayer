"""Background thumbnail generation queue with priorities and de-duplication."""
import heapq
import itertools
import logging
import os
import threading

import gi

gi.require_version('Gtk', '4.0')
from gi.repository import GLib

from neplayer.core import thumbnail

log = logging.getLogger(__name__)

PRIO_VISIBLE = 0
PRIO_BACKGROUND = 10


class ThumbnailWorker:
    def __init__(self, db, get_cache_dir, on_done, threads=2):
        self._db = db
        self._get_cache_dir = get_cache_dir
        self._on_done = on_done  # called on GTK thread: (video_id, path_or_None)
        self._heap = []
        self._queued = {}  # video_id -> priority
        self._running = set()
        self._counter = itertools.count()
        self._cv = threading.Condition()
        self._stop = False
        self._threads = [threading.Thread(target=self._run, name=f'thumb-{i}', daemon=True)
                         for i in range(threads)]
        for t in self._threads:
            t.start()

    def request(self, video, priority=PRIO_BACKGROUND):
        vid = video['id']
        with self._cv:
            if vid in self._running:
                return
            cur = self._queued.get(vid)
            if cur is not None and cur <= priority:
                return
            self._queued[vid] = priority
            heapq.heappush(self._heap, (priority, next(self._counter), vid,
                                        video['file_path'], video.get('duration') or 0,
                                        video.get('file_mtime') or 0))
            self._cv.notify()

    def pending(self):
        with self._cv:
            return len(self._queued) + len(self._running)

    def clear(self):
        with self._cv:
            self._heap.clear()
            self._queued.clear()

    def stop(self):
        with self._cv:
            self._stop = True
            self._cv.notify_all()

    def _run(self):
        if hasattr(os, 'nice'):  # not available on Windows
            try:
                os.nice(5)  # keep the UI and playback smooth
            except OSError:
                pass
        while True:
            with self._cv:
                item = None
                while item is None and not self._stop:
                    while self._heap:
                        entry = heapq.heappop(self._heap)
                        if self._queued.get(entry[2]) == entry[0]:  # skip stale entries
                            item = entry
                            break
                    if item is None:
                        self._cv.wait()
                if self._stop:
                    return
                _prio, _, vid, path, dur, mtime = item
                del self._queued[vid]
                self._running.add(vid)
            result = None
            try:
                out = thumbnail.thumb_path(self._get_cache_dir(), path, mtime)
                if out.exists() and out.stat().st_size > 0:
                    result = str(out)
                else:
                    result = thumbnail.generate(path, dur, out)
                self._db.set_thumbnail(vid, result)
            except Exception as e:  # one bad file must never stop the queue
                log.info('Thumbnail failed for %s: %s', path, e)
                result = None
            finally:
                with self._cv:
                    self._running.discard(vid)
            GLib.idle_add(self._on_done, vid, result)
