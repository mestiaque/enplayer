"""Thumbnail cache maintenance."""
import logging
import shutil
from pathlib import Path

log = logging.getLogger(__name__)


def thumbs_dir(cache_dir):
    return Path(cache_dir) / 'thumbnails'


def cache_size(cache_dir):
    total = 0
    d = thumbs_dir(cache_dir)
    if d.exists():
        for p in d.rglob('*'):
            try:
                if p.is_file():
                    total += p.stat().st_size
            except OSError:
                pass
    return total


def clear_cache(cache_dir):
    d = thumbs_dir(cache_dir)
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)


def prune(cache_dir, limit_bytes, keep=()):
    """Delete least-recently-used thumbnails until under limit. Returns removed paths."""
    d = thumbs_dir(cache_dir)
    if not d.exists():
        return []
    files = []
    total = 0
    for p in d.rglob('*.webp'):
        try:
            st = p.stat()
        except OSError:
            continue
        files.append((st.st_atime, st.st_size, p))
        total += st.st_size
    if total <= limit_bytes:
        return []
    keep = set(keep)
    removed = []
    for _atime, size, p in sorted(files):
        if total <= limit_bytes * 0.9:
            break
        if str(p) in keep:
            continue
        p.unlink(missing_ok=True)
        total -= size
        removed.append(str(p))
    return removed


def free_space(path):
    try:
        return shutil.disk_usage(path).free
    except OSError:
        return None
