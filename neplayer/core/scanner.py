"""Incremental recursive directory scanner. Runs in worker threads only."""
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from neplayer.core import metadata

log = logging.getLogger(__name__)


@dataclass
class ScanResult:
    folder_id: int
    available: bool = True
    error: str = ''
    found: int = 0
    added: int = 0
    updated: int = 0
    removed: int = 0
    failed: int = 0
    changed_ids: list = field(default_factory=list)


_WIN_HIDDEN = 0x2 | 0x4  # FILE_ATTRIBUTE_HIDDEN | FILE_ATTRIBUTE_SYSTEM


def _is_hidden(entry):
    if entry.name.startswith('.'):
        return True
    if os.name == 'nt':
        try:
            return bool(entry.stat(follow_symlinks=False).st_file_attributes & _WIN_HIDDEN)
        except (OSError, AttributeError):
            return False
    return False


# Folders that hold program code/dependencies, never anyone's videos.
SKIP_DIRS = {'node_modules', '__pycache__', 'site-packages', 'dist-packages', 'bower_components',
             '$RECYCLE.BIN', 'System Volume Information'}

# '.ts' is shared by MPEG transport streams and TypeScript source files.
_TS_EXTS = {'ts', 'mts', 'm2ts'}


def _is_mpeg_ts(path):
    """MPEG-TS packets start with 0x47 every 188 bytes (192 for M2TS/AVCHD)."""
    try:
        with open(path, 'rb') as f:
            head = f.read(400)
    except OSError:
        return False
    for start, size in ((0, 188), (4, 192)):
        if len(head) > start + size and head[start] == 0x47 and head[start + size] == 0x47:
            return True
    return False


def iter_video_files(root, extensions, recursive=True, ignore_hidden=True, cancel=None):
    """Yield (path, stat) for video files below root. Permission errors are skipped."""
    stack = [root]
    seen = set()
    while stack:
        if cancel is not None and cancel.is_set():
            return
        d = stack.pop()
        try:
            real = os.path.realpath(d)
            if real in seen:  # symlink loops
                continue
            seen.add(real)
            with os.scandir(d) as it:
                entries = list(it)
        except (PermissionError, FileNotFoundError, NotADirectoryError, OSError) as e:
            log.warning('Cannot read %s: %s', d, e)
            continue
        for e in entries:
            name = e.name
            if ignore_hidden and _is_hidden(e):
                continue
            try:
                if e.is_dir(follow_symlinks=True):
                    if recursive and name not in SKIP_DIRS:
                        stack.append(e.path)
                    continue
                ext = name.rsplit('.', 1)[-1].lower() if '.' in name else ''
                if ext in extensions and e.is_file(follow_symlinks=True):
                    if ext in _TS_EXTS and not _is_mpeg_ts(e.path):
                        continue
                    yield e.path, e.stat(follow_symlinks=True)
            except OSError:
                continue


def scan_folder(db, folder, extensions, ignore_hidden=True, cancel=None,
                progress=None, workers=4):
    """Scan one library folder and sync it into the DB.

    Only new or modified files (size/mtime changed) are probed again.
    """
    res = ScanResult(folder_id=folder['id'])
    root = folder['path']
    if not os.path.isdir(root) or not os.access(root, os.R_OK | os.X_OK):
        res.available = False
        res.error = ('Folder is not accessible (drive disconnected or permission denied)'
                     if not os.path.exists(root) else 'Permission denied')
        db.mark_folder_missing(folder['id'], True)
        db.update_folder(folder['id'], available=0)
        return res

    known = db.folder_index(folder['id'])
    seen = set()
    todo = []
    for path, st in iter_video_files(root, extensions, bool(folder.get('include_subdirs', 1)),
                                     ignore_hidden, cancel):
        res.found += 1
        seen.add(path)
        k = known.get(path)
        if k and k['file_size'] == st.st_size and abs(k['file_mtime'] - st.st_mtime) < 0.001:
            if k['missing']:
                db.set_missing([k['id']], False)
                res.changed_ids.append(k['id'])
            continue
        todo.append((path, k is not None))

    if cancel is not None and cancel.is_set():
        return res

    def work(item):
        path, _ = item
        try:
            return item, metadata.probe(path)
        except metadata.MetadataError as e:
            log.info('Probe failed for %s: %s', path, e)
            try:
                return item, metadata.fallback_meta(path, e)
            except OSError:
                return item, None
        except OSError as e:
            log.info('Cannot stat %s: %s', path, e)
            return item, None

    done = 0
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix='probe') as pool:
        for (path, is_update), meta in pool.map(work, todo):
            done += 1
            if cancel is not None and cancel.is_set():
                break
            if meta is None:
                res.failed += 1
                continue
            if meta.get('error'):
                res.failed += 1
            try:
                vid = db.upsert_video(folder['id'], meta)
            except Exception:
                log.exception('DB upsert failed for %s', path)
                continue
            res.changed_ids.append(vid)
            if is_update:
                res.updated += 1
            else:
                res.added += 1
            if progress is not None:
                progress(done, len(todo), path)

    if cancel is None or not cancel.is_set():
        gone = [v['id'] for p, v in known.items() if p not in seen]
        if gone:
            db.delete_videos(gone)
            res.removed = len(gone)
        db.update_folder(folder['id'], available=1, last_scanned_at=time.time())
    return res
