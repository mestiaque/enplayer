"""LibraryService: the single façade the UI talks to for library state.

Owns the scan worker, thumbnail worker, folder monitor and texture cache.
All signals are emitted on the GTK main thread.
"""
import logging
import os
import shutil

import gi

gi.require_version('Gtk', '4.0')
from gi.repository import GLib, GObject

from neplayer.core import cache, metadata
from neplayer.core.file_monitor import FolderMonitor
from neplayer.core.texture_cache import TextureCache
from neplayer.workers.scan_worker import ScanWorker
from neplayer.workers.thumbnail_worker import PRIO_BACKGROUND, PRIO_VISIBLE, ThumbnailWorker

log = logging.getLogger(__name__)


class LibraryService(GObject.Object):
    __gsignals__ = {
        'changed': (GObject.SignalFlags.RUN_FIRST, None, ()),
        'folders-changed': (GObject.SignalFlags.RUN_FIRST, None, ()),
        'video-updated': (GObject.SignalFlags.RUN_FIRST, None, (int,)),
        'thumbnail-ready': (GObject.SignalFlags.RUN_FIRST, None, (int, str)),
        'scan-status': (GObject.SignalFlags.RUN_FIRST, None, (bool, str)),
        'message': (GObject.SignalFlags.RUN_FIRST, None, (str,)),
    }

    def __init__(self, db, settings):
        super().__init__()
        self.db = db
        self.settings = settings
        self.textures = TextureCache()
        self._changed_src = None
        self._scan_errors = []
        self._scan_totals = {'added': 0, 'removed': 0, 'updated': 0}
        self.thumbs = ThumbnailWorker(db, lambda: self.settings['cache_dir'], self._on_thumb_done)
        self.scanner = ScanWorker(db, settings, self._on_scan_progress,
                                  self._on_folder_scanned, self._on_scan_idle)
        self.monitor = FolderMonitor(self._on_folder_fs_change)
        settings.connect('changed', self._on_setting_changed)

    # --- lifecycle -------------------------------------------------------
    def start(self):
        missing = [t for t in ('ffmpeg', 'ffprobe') if shutil.which(t) is None]
        if missing:
            self.emit('message', f'{" and ".join(missing)} not found — install with: '
                                 'sudo apt install ffmpeg')
        self._check_disk_space()
        folders = self.db.list_folders()
        if not self.settings['first_run_done']:
            self.settings.set('first_run_done', True)
            if not folders:
                folders = self._add_default_folder()
        if self.settings['auto_monitor']:
            for f in folders:
                if f['enabled']:
                    self.monitor.watch(f)
        if self.settings['scan_on_startup']:
            self.rescan()
        else:
            self.queue_missing_thumbnails()

    def _add_default_folder(self):
        """First launch: start with the user's Videos folder so the library isn't empty."""
        if os.environ.get('NEPLAYER_NO_DEFAULT_FOLDER'):
            return []
        videos = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_VIDEOS)
        if videos and os.path.isdir(videos) and os.path.realpath(videos) != os.path.realpath(os.path.expanduser('~')):
            self.db.add_folder(videos, self.settings['include_subdirs'])
            self.emit('message', f'Added your Videos folder ({videos}). Add more with the + button.')
            self.emit('folders-changed')
        return self.db.list_folders()

    def shutdown(self):
        self.monitor.unwatch_all()
        self.scanner.stop()
        self.thumbs.stop()
        self.textures.shutdown()

    # --- folders ---------------------------------------------------------
    def add_folder(self, path):
        path = os.path.abspath(os.path.expanduser(path))
        if not os.path.isdir(path):
            self.emit('message', f'Not a folder: {path}')
            return None
        for f in self.db.list_folders():
            if path == f['path'] or path.startswith(f['path'].rstrip('/') + '/'):
                self.emit('message', f'“{path}” is already part of your library')
                return None
        folder = self.db.add_folder(path, self.settings['include_subdirs'])
        if self.settings['auto_monitor']:
            self.monitor.watch(folder)
        self.scanner.request(folder['id'])
        self.emit('folders-changed')
        return folder

    def remove_folder(self, folder_id):
        self.monitor.unwatch(folder_id)
        thumbs = self.db.remove_folder(folder_id)
        for t in thumbs:
            try:
                os.unlink(t)
            except OSError:
                pass
        self.emit('folders-changed')
        self._emit_changed()

    def update_folder(self, folder_id, **fields):
        self.db.update_folder(folder_id, **fields)
        folder = self.db.get_folder(folder_id)
        if folder and folder['enabled'] and self.settings['auto_monitor']:
            self.monitor.watch(folder)
        else:
            self.monitor.unwatch(folder_id)
        self.emit('folders-changed')
        if 'include_subdirs' in fields or 'enabled' in fields:
            self.rescan(folder_id)
        self._emit_changed()

    def rescan(self, folder_id=None):
        ids = [folder_id] if folder_id is not None else \
            [f['id'] for f in self.db.list_folders() if f['enabled']]
        if not ids:
            return
        self._scan_errors = []
        self._scan_totals = {'added': 0, 'removed': 0, 'updated': 0}
        for fid in ids:
            self.scanner.request(fid)

    @property
    def is_scanning(self):
        return self.scanner.busy

    # --- thumbnails ------------------------------------------------------
    def request_thumbnail(self, video, visible=True):
        if video.get('missing') or video.get('error'):
            return
        self.thumbs.request(video, PRIO_VISIBLE if visible else PRIO_BACKGROUND)

    def queue_missing_thumbnails(self):
        for v in self.db.videos_without_thumbnail():
            self.thumbs.request(v, PRIO_BACKGROUND)

    def clear_cache(self):
        self.thumbs.clear()
        self.db.clear_all_thumbnails()
        cache.clear_cache(self.settings['cache_dir'])
        self.textures.invalidate()
        self._emit_changed()

    def rebuild_thumbnails(self):
        self.clear_cache()
        self.queue_missing_thumbnails()

    def _on_thumb_done(self, video_id, path):
        if path:
            self.emit('thumbnail-ready', video_id, path)
        return False

    # --- favorites -------------------------------------------------------
    def set_favorite(self, video_id, fav):
        self.db.set_favorite(video_id, fav)
        self.emit('video-updated', video_id)

    # --- scanning callbacks (GTK thread) ---------------------------------
    def _on_scan_progress(self, name, done, total):
        msg = f'Scanning {name}…' if not total else f'Scanning {name} — {done}/{total}'
        self.emit('scan-status', True, msg)
        if done and done % 25 == 0:
            self._emit_changed()
        return False

    def _on_folder_scanned(self, res):
        for k in self._scan_totals:
            self._scan_totals[k] += getattr(res, k)
        if not res.available:
            f = self.db.get_folder(res.folder_id)
            self._scan_errors.append(f'{f["name"] if f else "Folder"}: {res.error}')
        for vid in res.changed_ids:
            v = self.db.get_video(vid)
            if v and not v['thumbnail_path']:
                self.request_thumbnail(v, visible=False)
        self.emit('folders-changed')
        self._emit_changed()
        return False

    def _on_scan_idle(self):
        t = self._scan_totals
        parts = []
        if t['added']:
            parts.append(f'{t["added"]} new')
        if t['updated']:
            parts.append(f'{t["updated"]} updated')
        if t['removed']:
            parts.append(f'{t["removed"]} removed')
        msg = 'Library up to date' + (f' · {", ".join(parts)}' if parts else '')
        self.emit('scan-status', False, msg)
        for e in self._scan_errors:
            self.emit('message', e)
        self._scan_errors = []
        self._scan_totals = {'added': 0, 'removed': 0, 'updated': 0}
        self.queue_missing_thumbnails()
        self._prune_cache()
        return False

    def _on_folder_fs_change(self, folder_id):
        if self.db.get_folder(folder_id):
            self.scanner.request(folder_id)

    def _on_setting_changed(self, _s, key):
        if key == 'auto_monitor':
            if self.settings['auto_monitor']:
                for f in self.db.list_folders():
                    if f['enabled']:
                        self.monitor.watch(f)
            else:
                self.monitor.unwatch_all()
        elif key in ('extensions', 'ignore_hidden', 'music_enabled', 'audio_extensions'):
            self.rescan()

    def _emit_changed(self):
        # Coalesce bursts of changes into one UI refresh.
        if self._changed_src is None:
            self._changed_src = GLib.timeout_add(150, self._fire_changed)

    def _fire_changed(self):
        self._changed_src = None
        self.emit('changed')
        return False

    def _prune_cache(self):
        limit = int(self.settings['cache_limit_mb']) * 1024 * 1024
        removed = cache.prune(self.settings['cache_dir'], limit)
        if removed:
            log.info('Pruned %d thumbnails from cache', len(removed))

    def _check_disk_space(self):
        d = self.settings['cache_dir']
        try:
            os.makedirs(d, exist_ok=True)
        except OSError as e:
            self.emit('message', f'Cannot create cache directory: {e}')
            return
        free = cache.free_space(d)
        if free is not None and free < 200 * 1024 * 1024:
            self.emit('message', 'Low disk space: thumbnails may fail to generate')


def probe_single(path):
    """Used when opening a file that isn't in the library."""
    try:
        return metadata.probe(path)
    except Exception:
        return None
