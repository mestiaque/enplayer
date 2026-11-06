"""Single background thread that runs folder scans sequentially."""
import logging
import queue
import threading

import gi

gi.require_version('Gtk', '4.0')
from gi.repository import GLib

from neplayer.core import scanner

log = logging.getLogger(__name__)


class ScanWorker:
    def __init__(self, db, settings, on_progress, on_folder_done, on_idle):
        self._db = db
        self._settings = settings
        self._on_progress = on_progress        # (folder_name, done, total)
        self._on_folder_done = on_folder_done  # (ScanResult)
        self._on_idle = on_idle                # ()
        self._q = queue.Queue()
        self._pending = set()
        self._lock = threading.Lock()
        self.cancel_event = threading.Event()
        self.busy = False
        self._thread = threading.Thread(target=self._run, name='scanner', daemon=True)
        self._thread.start()

    def request(self, folder_id):
        with self._lock:
            if folder_id in self._pending:
                return
            self._pending.add(folder_id)
        self.busy = True
        self._q.put(folder_id)

    def stop(self):
        self.cancel_event.set()
        self._q.put(None)

    def _run(self):
        while True:
            fid = self._q.get()
            if fid is None:
                return
            with self._lock:
                self._pending.discard(fid)
            folder = self._db.get_folder(fid)
            if folder and folder['enabled']:
                name = folder['name']
                exts = self._settings.extensions
                hidden = self._settings['ignore_hidden']

                def progress(done, total, _path, name=name):
                    GLib.idle_add(self._on_progress, name, done, total)

                GLib.idle_add(self._on_progress, name, 0, 0)
                try:
                    res = scanner.scan_folder(self._db, folder, exts, hidden,
                                              self.cancel_event, progress)
                    GLib.idle_add(self._on_folder_done, res)
                except Exception:
                    log.exception('Scan failed for %s', folder['path'])
            if self._q.empty():
                self.busy = False
                GLib.idle_add(self._on_idle)
