"""One-time carry-over from the app's previous name (FrameFlow).

Moves the old data/cache folders to the new NEPLAYER locations so the user's
library, favorites, watch history and thumbnails survive the rename.
Runs before logging and the database are set up; never raises.
"""
import os
import shutil
import sqlite3
from pathlib import Path

from neplayer import config

OLD_NAME = 'frameflow'


def _old_dirs():
    if config.IS_WINDOWS:
        local = Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData' / 'Local'))
        return local / 'FrameFlow', local / 'FrameFlow' / 'Cache'
    data = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local' / 'share'))
    cache = Path(os.environ.get('XDG_CACHE_HOME', Path.home() / '.cache'))
    return data / OLD_NAME, cache / OLD_NAME


def migrate():
    """Returns a short description of what was migrated (or None)."""
    if os.environ.get('NEPLAYER_DATA_DIR') or os.environ.get('NEPLAYER_CACHE_DIR'):
        return None
    old_data, old_cache = _old_dirs()
    done = []
    try:
        if old_cache.is_dir() and not config.DEFAULT_CACHE_DIR.exists():
            config.DEFAULT_CACHE_DIR.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(old_cache), str(config.DEFAULT_CACHE_DIR))
            done.append('cache')
        if old_data.is_dir() and not config.DATA_DIR.exists():
            config.DATA_DIR.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(old_data), str(config.DATA_DIR))
            for suffix in ('', '-wal', '-shm'):
                src = config.DATA_DIR / f'{OLD_NAME}.db{suffix}'
                if src.exists():
                    src.rename(config.DATA_DIR / f'{config.DB_PATH.name}{suffix}')
            (config.DATA_DIR / f'{OLD_NAME}.log').unlink(missing_ok=True)
            done.append('library')
        if 'cache' in done and config.DB_PATH.exists():
            _rewrite_thumbnail_paths(str(old_cache), str(config.DEFAULT_CACHE_DIR))
    except Exception as e:  # a failed carry-over must never stop the app
        return f'Could not carry over data from the previous version: {e}'
    return f'Carried over {" and ".join(done)} from FrameFlow' if done else None


def _rewrite_thumbnail_paths(old, new):
    c = sqlite3.connect(config.DB_PATH)
    try:
        c.execute('UPDATE videos SET thumbnail_path = ? || substr(thumbnail_path, ?) '
                  'WHERE thumbnail_path LIKE ?', (new, len(old) + 1, old + '%'))
        c.execute('DELETE FROM settings WHERE key = ? AND value LIKE ?', ('cache_dir', f'%{old}%'))
        c.commit()
    except sqlite3.Error:
        pass  # legacy schema without these tables: thumbnails just regenerate
    finally:
        c.close()
