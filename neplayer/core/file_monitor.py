"""Watches library folders with Gio.FileMonitor and requests debounced rescans.

inotify monitors are per-directory, so every subdirectory gets its own
monitor (capped to avoid exhausting inotify watches on huge trees).
"""
import logging
import os

import gi

gi.require_version('Gtk', '4.0')
from gi.repository import Gio, GLib

log = logging.getLogger(__name__)

MAX_WATCHES_PER_FOLDER = 2000
DEBOUNCE_MS = 2500


class FolderMonitor:
    def __init__(self, on_change):
        self._on_change = on_change  # callback(folder_id)
        self._monitors = {}  # folder_id -> list[Gio.FileMonitor]
        self._pending = {}   # folder_id -> source id
        self._mount_monitor = Gio.VolumeMonitor.get()
        self._mount_monitor.connect('mount-added', self._on_mounts_changed)
        self._mount_monitor.connect('mount-removed', self._on_mounts_changed)
        self._folders = {}

    def watch(self, folder):
        self.unwatch(folder['id'])
        self._folders[folder['id']] = folder
        root = folder['path']
        if not os.path.isdir(root):
            return
        mons = []
        dirs = [root]
        if folder.get('include_subdirs', 1):
            for cur, subdirs, _files in os.walk(root, onerror=lambda e: None):
                subdirs[:] = [s for s in subdirs if not s.startswith('.')]
                for s in subdirs:
                    dirs.append(os.path.join(cur, s))
                if len(dirs) >= MAX_WATCHES_PER_FOLDER:
                    log.info('Watch limit reached for %s', root)
                    break
        for d in dirs[:MAX_WATCHES_PER_FOLDER]:
            try:
                m = Gio.File.new_for_path(d).monitor_directory(Gio.FileMonitorFlags.WATCH_MOVES, None)
            except GLib.Error as e:
                log.debug('Cannot monitor %s: %s', d, e.message)
                continue
            m.connect('changed', self._on_changed, folder['id'])
            mons.append(m)
        self._monitors[folder['id']] = mons

    def unwatch(self, folder_id):
        for m in self._monitors.pop(folder_id, []):
            m.cancel()
        src = self._pending.pop(folder_id, None)
        if src:
            GLib.source_remove(src)
        self._folders.pop(folder_id, None)

    def unwatch_all(self):
        for fid in list(self._monitors):
            self.unwatch(fid)

    def _on_changed(self, _mon, file, _other, event, folder_id):
        if event in (Gio.FileMonitorEvent.CHANGES_DONE_HINT, Gio.FileMonitorEvent.DELETED,
                     Gio.FileMonitorEvent.CREATED, Gio.FileMonitorEvent.MOVED_IN,
                     Gio.FileMonitorEvent.MOVED_OUT, Gio.FileMonitorEvent.RENAMED):
            name = file.get_basename() or ''
            if name.startswith('.') or name.endswith(('.part', '.crdownload', '.tmp')):
                return
            self._schedule(folder_id)

    def _schedule(self, folder_id):
        src = self._pending.pop(folder_id, None)
        if src:
            GLib.source_remove(src)
        self._pending[folder_id] = GLib.timeout_add(DEBOUNCE_MS, self._fire, folder_id)

    def _fire(self, folder_id):
        self._pending.pop(folder_id, None)
        self._on_change(folder_id)
        return False

    def _on_mounts_changed(self, *_args):
        # A drive came or went: rescan every folder so availability is updated.
        for fid in list(self._folders):
            self._schedule(fid)
