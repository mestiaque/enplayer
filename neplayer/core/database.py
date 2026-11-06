"""SQLite storage. One connection per thread, WAL mode, serialized writes."""
import json
import logging
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path

log = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS folders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    include_subdirs INTEGER NOT NULL DEFAULT 1,
    available INTEGER NOT NULL DEFAULT 1,
    last_scanned_at REAL,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS videos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    folder_id INTEGER REFERENCES folders(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    file_path TEXT NOT NULL UNIQUE,
    file_size INTEGER NOT NULL DEFAULT 0,
    duration REAL NOT NULL DEFAULT 0,
    width INTEGER NOT NULL DEFAULT 0,
    height INTEGER NOT NULL DEFAULT 0,
    fps REAL NOT NULL DEFAULT 0,
    video_codec TEXT,
    audio_codec TEXT,
    bitrate INTEGER NOT NULL DEFAULT 0,
    container TEXT,
    audio_streams TEXT,
    subtitle_streams TEXT,
    thumbnail_path TEXT,
    file_mtime REAL NOT NULL DEFAULT 0,
    missing INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_videos_folder ON videos(folder_id);
CREATE INDEX IF NOT EXISTS idx_videos_title ON videos(title COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_videos_created ON videos(created_at);
CREATE INDEX IF NOT EXISTS idx_videos_duration ON videos(duration);
CREATE INDEX IF NOT EXISTS idx_videos_size ON videos(file_size);
CREATE INDEX IF NOT EXISTS idx_videos_height ON videos(height);

CREATE TABLE IF NOT EXISTS playback_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id INTEGER NOT NULL UNIQUE REFERENCES videos(id) ON DELETE CASCADE,
    position REAL NOT NULL DEFAULT 0,
    completed INTEGER NOT NULL DEFAULT 0,
    last_played_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_history_played ON playback_history(last_played_at);

CREATE TABLE IF NOT EXISTS favorites (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id INTEGER NOT NULL UNIQUE REFERENCES videos(id) ON DELETE CASCADE,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""

VIDEO_COLUMNS = """
v.id, v.folder_id, v.title, v.file_path, v.file_size, v.duration, v.width,
v.height, v.fps, v.video_codec, v.audio_codec, v.bitrate, v.container,
v.audio_streams, v.subtitle_streams, v.thumbnail_path, v.file_mtime,
v.missing, v.error, v.created_at, v.updated_at,
v.media_kind, v.artist, v.album, v.album_artist, v.track, v.year, v.genre,
(f.video_id IS NOT NULL) AS favorite,
COALESCE(h.position, 0) AS position,
COALESCE(h.completed, 0) AS completed,
h.last_played_at AS last_played_at
"""

VIDEO_FROM = """
FROM videos v
LEFT JOIN favorites f ON f.video_id = v.id
LEFT JOIN playback_history h ON h.video_id = v.id
LEFT JOIN folders fo ON fo.id = v.folder_id
"""

SORTS = {
    'recent': 'v.created_at DESC, v.id DESC',
    'name_asc': 'v.title COLLATE NOCASE ASC',
    'name_desc': 'v.title COLLATE NOCASE DESC',
    'duration_desc': 'v.duration DESC',
    'duration_asc': 'v.duration ASC',
    'size_desc': 'v.file_size DESC',
    'resolution_desc': 'v.height DESC, v.width DESC',
    'last_played': 'h.last_played_at DESC',
    'artist': "COALESCE(NULLIF(v.album_artist, ''), v.artist, '~') COLLATE NOCASE, v.album COLLATE NOCASE, v.track, v.title COLLATE NOCASE",
}


SCHEMA_VERSION = 3

# Columns added after v2 (music support); created in place so existing libraries are kept.
EXTRA_COLUMNS = {
    'media_kind': "TEXT NOT NULL DEFAULT 'video'",
    'artist': 'TEXT', 'album': 'TEXT', 'album_artist': 'TEXT',
    'track': 'INTEGER NOT NULL DEFAULT 0', 'year': 'INTEGER NOT NULL DEFAULT 0', 'genre': 'TEXT',
}

_TS = "COALESCE(CAST(strftime('%s', {col}) AS REAL), CAST({col} AS REAL), CAST(strftime('%s','now') AS REAL))"


def _ts(col):
    """Convert legacy TIMESTAMP text (or numbers) to unix seconds."""
    return _TS.format(col=col)


def _kind_from_path(path):
    from neplayer.config import AUDIO_EXTENSIONS
    return 'audio' if Path(path).suffix.lower().lstrip('.') in AUDIO_EXTENSIONS else 'video'


class Database:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._write_lock = threading.RLock()
        with self._write_lock:
            self._migrate(self.conn)
            self.conn.executescript(SCHEMA)
            self._add_columns(self.conn)
            self.conn.execute(f'PRAGMA user_version={SCHEMA_VERSION}')
            self._refresh_audio_art()

    ART_VERSION = 'enplayer-icon-1'

    def _refresh_audio_art(self):
        """Songs without cover art now use the ENPlayer icon as their placeholder: re-make their
        grid cards once (only audio rows; video thumbnails are untouched)."""
        c = self.conn
        row = c.execute("SELECT value FROM settings WHERE key='audio_art_version'").fetchone()
        if row is not None and row[0] == json.dumps(self.ART_VERSION):
            return
        c.execute("UPDATE videos SET thumbnail_path=NULL WHERE media_kind='audio'")
        c.execute("INSERT INTO settings(key, value) VALUES('audio_art_version', ?) "
                  "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (json.dumps(self.ART_VERSION),))
        c.commit()

    # --- schema upgrades -------------------------------------------------
    @staticmethod
    def _columns(c, table):
        return {r[1] for r in c.execute(f'PRAGMA table_info({table})')}

    def _add_columns(self, c):
        have = self._columns(c, 'videos')
        for name, decl in EXTRA_COLUMNS.items():
            if name not in have:
                c.execute(f'ALTER TABLE videos ADD COLUMN {name} {decl}')
        c.execute('CREATE INDEX IF NOT EXISTS idx_videos_kind ON videos(media_kind)')

    def _migrate(self, c):
        if c.execute('PRAGMA user_version').fetchone()[0] >= SCHEMA_VERSION:
            return
        tables = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if 'videos' not in tables or 'missing' in self._columns(c, 'videos'):
            return  # fresh database, or already current
        log.info('Upgrading library database from an older version')
        legacy = [t for t in ('folders', 'videos', 'playback_history', 'favorites', 'settings') if t in tables]
        c.execute('PRAGMA foreign_keys=OFF')
        c.execute('BEGIN IMMEDIATE')
        try:
            for t in legacy:
                c.execute(f'ALTER TABLE {t} RENAME TO {t}_legacy')
            # Indexes followed the renamed tables; drop them so the new ones can be created.
            for (name,) in c.execute("SELECT name FROM sqlite_master WHERE type='index' "
                                     "AND name LIKE 'idx_%'").fetchall():
                c.execute(f'DROP INDEX IF EXISTS {name}')
            for stmt in SCHEMA.split(';'):
                if stmt.strip():
                    c.execute(stmt)
            if 'folders' in legacy:
                cols = self._columns(c, 'folders_legacy')
                sub = 'include_subdirs' if 'include_subdirs' in cols else '1'
                c.execute(f"""INSERT OR IGNORE INTO folders(id, path, name, enabled, include_subdirs,
                              available, last_scanned_at, created_at)
                              SELECT id, path, COALESCE(name, path), COALESCE(enabled, 1), {sub}, 1,
                                     NULL, {_ts('created_at')}
                              FROM folders_legacy WHERE path IS NOT NULL""")
            if 'videos' in legacy:
                # file_mtime=0 makes the next scan re-probe every file, filling the new
                # metadata columns while keeping ids (so favorites/history survive).
                c.execute(f"""INSERT OR IGNORE INTO videos(id, folder_id, title, file_path, file_size,
                              duration, width, height, fps, video_codec, audio_codec, bitrate,
                              thumbnail_path, file_mtime, created_at, updated_at)
                              SELECT id, folder_id, COALESCE(title, file_path), file_path,
                                     COALESCE(file_size, 0), COALESCE(duration, 0), COALESCE(width, 0),
                                     COALESCE(height, 0), COALESCE(fps, 0), video_codec, audio_codec,
                                     COALESCE(bitrate, 0), NULL, 0, {_ts('created_at')}, {_ts('updated_at')}
                              FROM videos_legacy
                              WHERE file_path IS NOT NULL
                                AND (folder_id IS NULL OR folder_id IN (SELECT id FROM folders))""")
            if 'playback_history' in legacy:
                c.execute(f"""INSERT OR IGNORE INTO playback_history(video_id, position, completed, last_played_at)
                              SELECT video_id, COALESCE(position, 0), COALESCE(completed, 0),
                                     {_ts('last_played_at')}
                              FROM playback_history_legacy
                              WHERE video_id IN (SELECT id FROM videos)
                              ORDER BY last_played_at DESC""")
            if 'favorites' in legacy:
                c.execute(f"""INSERT OR IGNORE INTO favorites(video_id, created_at)
                              SELECT video_id, {_ts('created_at')} FROM favorites_legacy
                              WHERE video_id IN (SELECT id FROM videos)""")
            if 'settings' in legacy:
                c.execute('INSERT OR IGNORE INTO settings(key, value) SELECT key, value FROM settings_legacy')
            for t in legacy:
                c.execute(f'DROP TABLE {t}_legacy')
            c.execute(f'PRAGMA user_version={SCHEMA_VERSION}')
            c.execute('COMMIT')
        except BaseException:
            c.execute('ROLLBACK')
            raise
        finally:
            c.execute('PRAGMA foreign_keys=ON')

    # --- connections -----------------------------------------------------
    @property
    def conn(self):
        c = getattr(self._local, 'conn', None)
        if c is None:
            c = sqlite3.connect(self.path, timeout=15, isolation_level=None)
            c.row_factory = sqlite3.Row
            c.execute('PRAGMA journal_mode=WAL')
            c.execute('PRAGMA synchronous=NORMAL')
            c.execute('PRAGMA foreign_keys=ON')
            c.execute('PRAGMA busy_timeout=15000')
            self._local.conn = c
        return c

    @contextmanager
    def write(self):
        """Serialized write transaction."""
        with self._write_lock:
            c = self.conn
            c.execute('BEGIN IMMEDIATE')
            try:
                yield c
            except BaseException:
                c.execute('ROLLBACK')
                raise
            else:
                c.execute('COMMIT')

    def close(self):
        c = getattr(self._local, 'conn', None)
        if c is not None:
            c.close()
            self._local.conn = None

    # --- settings --------------------------------------------------------
    def get_all_settings(self):
        out = {}
        for row in self.conn.execute('SELECT key, value FROM settings'):
            try:
                out[row['key']] = json.loads(row['value'])
            except (TypeError, ValueError):
                pass
        return out

    def set_setting(self, key, value):
        with self.write() as c:
            c.execute('INSERT INTO settings(key, value) VALUES(?, ?) '
                      'ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                      (key, json.dumps(value)))

    # --- folders ---------------------------------------------------------
    def add_folder(self, path, include_subdirs=True):
        p = Path(path)
        with self.write() as c:
            c.execute('INSERT OR IGNORE INTO folders(path, name, include_subdirs, created_at) '
                      'VALUES(?, ?, ?, ?)', (str(p), p.name or str(p), int(include_subdirs), time.time()))
            row = c.execute('SELECT * FROM folders WHERE path=?', (str(p),)).fetchone()
        return dict(row)

    def list_folders(self):
        rows = self.conn.execute(
            'SELECT fo.*, (SELECT COUNT(*) FROM videos v WHERE v.folder_id=fo.id AND v.missing=0) AS video_count '
            'FROM folders fo ORDER BY fo.name COLLATE NOCASE').fetchall()
        return [dict(r) for r in rows]

    def get_folder(self, folder_id):
        r = self.conn.execute('SELECT * FROM folders WHERE id=?', (folder_id,)).fetchone()
        return dict(r) if r else None

    def update_folder(self, folder_id, **fields):
        if not fields:
            return
        cols = ', '.join(f'{k}=?' for k in fields)
        with self.write() as c:
            c.execute(f'UPDATE folders SET {cols} WHERE id=?', (*fields.values(), folder_id))

    def remove_folder(self, folder_id):
        with self.write() as c:
            thumbs = [r[0] for r in c.execute(
                'SELECT thumbnail_path FROM videos WHERE folder_id=? AND thumbnail_path IS NOT NULL',
                (folder_id,))]
            c.execute('DELETE FROM videos WHERE folder_id=?', (folder_id,))
            c.execute('DELETE FROM folders WHERE id=?', (folder_id,))
        return thumbs

    # --- videos ----------------------------------------------------------
    def folder_index(self, folder_id):
        """path -> (id, size, mtime, missing, has_thumb) for incremental scans."""
        rows = self.conn.execute(
            'SELECT id, file_path, file_size, file_mtime, missing, thumbnail_path, duration, error '
            'FROM videos WHERE folder_id=?', (folder_id,))
        return {r['file_path']: dict(r) for r in rows}

    def upsert_video(self, folder_id, meta):
        now = time.time()
        with self.write() as c:
            existing = c.execute('SELECT id FROM videos WHERE file_path=?',
                                 (meta['file_path'],)).fetchone()
            vals = (folder_id, meta['title'], meta['file_size'], meta.get('duration', 0),
                    meta.get('width', 0), meta.get('height', 0), meta.get('fps', 0),
                    meta.get('video_codec'), meta.get('audio_codec'), meta.get('bitrate', 0),
                    meta.get('container'), json.dumps(meta.get('audio_streams', [])),
                    json.dumps(meta.get('subtitle_streams', [])), meta['file_mtime'],
                    meta.get('error'), meta.get('media_kind') or _kind_from_path(meta['file_path']),
                    meta.get('artist'), meta.get('album'), meta.get('album_artist'),
                    int(meta.get('track') or 0), int(meta.get('year') or 0), meta.get('genre'))
            if existing:
                c.execute('UPDATE videos SET folder_id=?, title=?, file_size=?, duration=?, width=?, '
                          'height=?, fps=?, video_codec=?, audio_codec=?, bitrate=?, container=?, '
                          'audio_streams=?, subtitle_streams=?, file_mtime=?, error=?, media_kind=?, '
                          'artist=?, album=?, album_artist=?, track=?, year=?, genre=?, missing=0, '
                          'thumbnail_path=NULL, updated_at=? WHERE id=?',
                          (*vals, now, existing['id']))
                return existing['id']
            cur = c.execute('INSERT INTO videos(folder_id, title, file_size, duration, width, height, '
                            'fps, video_codec, audio_codec, bitrate, container, audio_streams, '
                            'subtitle_streams, file_mtime, error, media_kind, artist, album, album_artist, '
                            'track, year, genre, file_path, created_at, updated_at) '
                            'VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                            (*vals, meta['file_path'], now, now))
            return cur.lastrowid

    def set_missing(self, video_ids, missing=True):
        if not video_ids:
            return
        with self.write() as c:
            c.executemany('UPDATE videos SET missing=? WHERE id=?',
                          [(int(missing), i) for i in video_ids])

    def mark_folder_missing(self, folder_id, missing=True):
        with self.write() as c:
            c.execute('UPDATE videos SET missing=? WHERE folder_id=?', (int(missing), folder_id))

    def delete_videos(self, video_ids):
        with self.write() as c:
            c.executemany('DELETE FROM videos WHERE id=?', [(i,) for i in video_ids])

    def set_thumbnail(self, video_id, path):
        with self.write() as c:
            c.execute('UPDATE videos SET thumbnail_path=? WHERE id=?', (path, video_id))

    def clear_all_thumbnails(self):
        with self.write() as c:
            c.execute('UPDATE videos SET thumbnail_path=NULL')

    def get_video(self, video_id):
        r = self.conn.execute(f'SELECT {VIDEO_COLUMNS} {VIDEO_FROM} WHERE v.id=?',
                              (video_id,)).fetchone()
        return dict(r) if r else None

    def get_video_by_path(self, path):
        r = self.conn.execute(f'SELECT {VIDEO_COLUMNS} {VIDEO_FROM} WHERE v.file_path=?',
                              (str(path),)).fetchone()
        return dict(r) if r else None

    def videos_without_thumbnail(self, limit=100000):
        rows = self.conn.execute(
            'SELECT id, file_path, duration, file_mtime FROM videos '
            'WHERE thumbnail_path IS NULL AND missing=0 AND error IS NULL LIMIT ?', (limit,))
        return [dict(r) for r in rows]

    def query_videos(self, view='all', search='', sort='recent', filters=None,
                     folder_id=None, limit=None):
        filters = filters or {}
        where = ['v.missing=0', '(fo.enabled IS NULL OR fo.enabled=1)']
        args = []
        if view == 'all':
            where.append("v.media_kind='video'")
        elif view == 'music':
            where.append("v.media_kind='audio'")
        if view == 'favorites':
            where.append('f.video_id IS NOT NULL')
        elif view == 'continue':
            where.append("h.position > 5 AND h.completed=0 AND v.media_kind='video'")
            sort = 'last_played'
        elif view == 'recent':
            where.append('v.created_at > ?')
            args.append(time.time() - 30 * 86400)
            sort = 'recent' if sort == 'recent' else sort
        if folder_id is not None:
            where.append('v.folder_id=?')
            args.append(folder_id)
        if search:
            like = f'%{search.strip()}%'
            where.append('(v.title LIKE ? OR v.file_path LIKE ? OR fo.name LIKE ? OR v.artist LIKE ? '
                         'OR v.album LIKE ?)')
            args += [like, like, like, like, like]
        res = filters.get('resolution')
        if res == '4k':
            where.append('v.height >= 2000')
        elif res == '1080':
            where.append('v.height >= 1000 AND v.height < 2000')
        elif res == '720':
            where.append('v.height >= 700 AND v.height < 1000')
        elif res == 'sd':
            where.append('v.height < 700')
        fmt = filters.get('format')
        if fmt:
            where.append('LOWER(v.file_path) LIKE ?')
            args.append(f'%.{fmt.lower()}')
        dur = filters.get('duration')
        if dur == 'short':
            where.append('v.duration < 240')
        elif dur == 'medium':
            where.append('v.duration >= 240 AND v.duration < 1200')
        elif dur == 'long':
            where.append('v.duration >= 1200')
        if filters.get('favorites'):
            where.append('f.video_id IS NOT NULL')
        sql = (f'SELECT {VIDEO_COLUMNS} {VIDEO_FROM} WHERE {" AND ".join(where)} '
               f'ORDER BY {SORTS.get(sort, SORTS["recent"])}')
        if limit:
            sql += f' LIMIT {int(limit)}'
        return [dict(r) for r in self.conn.execute(sql, args)]

    def count_kind(self, kind):
        return self.conn.execute('SELECT COUNT(*) FROM videos WHERE missing=0 AND media_kind=?',
                                 (kind,)).fetchone()[0]

    def library_stats(self):
        r = self.conn.execute('SELECT COUNT(*) AS n, COALESCE(SUM(file_size),0) AS size, '
                              'COALESCE(SUM(duration),0) AS dur FROM videos WHERE missing=0').fetchone()
        return dict(r)

    # --- favorites & history --------------------------------------------
    def set_favorite(self, video_id, fav):
        with self.write() as c:
            if fav:
                c.execute('INSERT OR IGNORE INTO favorites(video_id, created_at) VALUES(?, ?)',
                          (video_id, time.time()))
            else:
                c.execute('DELETE FROM favorites WHERE video_id=?', (video_id,))

    def save_position(self, video_id, position, completed):
        with self.write() as c:
            c.execute('INSERT INTO playback_history(video_id, position, completed, last_played_at) '
                      'VALUES(?, ?, ?, ?) ON CONFLICT(video_id) DO UPDATE SET '
                      'position=excluded.position, completed=excluded.completed, '
                      'last_played_at=excluded.last_played_at',
                      (video_id, position, int(completed), time.time()))

    def clear_history(self, video_id=None):
        with self.write() as c:
            if video_id is None:
                c.execute('DELETE FROM playback_history')
            else:
                c.execute('DELETE FROM playback_history WHERE video_id=?', (video_id,))
