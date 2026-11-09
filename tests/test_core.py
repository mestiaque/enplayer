"""Core tests: database, metadata, thumbnails, incremental scanning.

Run with: python3 -m unittest discover -s tests -v
"""
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from neplayer.core import metadata, scanner, thumbnail  # noqa: E402
from neplayer.core.database import Database  # noqa: E402
from neplayer.config import DEFAULT_EXTENSIONS  # noqa: E402

EXTS = set(DEFAULT_EXTENSIONS)


def make_video(path, seconds=3, size='320x240', black_lead=0, audio=True):
    vf = f'testsrc2=size={size}:rate=25'
    cmd = ['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', f'{vf}:duration={seconds}']
    if audio:
        cmd += ['-f', 'lavfi', '-i', f'sine=frequency=440:duration={seconds}']
    filt = []
    if black_lead:
        filt = ['-vf', f"drawbox=enable='lt(t,{black_lead})':color=black:t=fill"]
    cmd += filt + ['-c:v', 'libx264', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p']
    if path.suffix == '.webm':
        cmd[cmd.index('libx264')] = 'libvpx'
        cmd.remove('-preset'); cmd.remove('ultrafast')
    if audio:
        cmd += ['-c:a', 'libopus' if path.suffix == '.webm' else 'aac']
    cmd += ['-shortest', str(path)]
    subprocess.run(cmd, check=True)


@unittest.skipIf(shutil.which('ffmpeg') is None, 'ffmpeg required')
class CoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix='neplayer-test-'))
        cls.lib = cls.tmp / 'lib'
        (cls.lib / 'sub' / 'deeper').mkdir(parents=True)
        (cls.lib / '.hidden').mkdir()
        make_video(cls.lib / 'a.mp4')
        make_video(cls.lib / 'sub' / 'b.mkv', size='1920x1080', seconds=2)
        make_video(cls.lib / 'sub' / 'deeper' / 'c.webm', seconds=2, audio=False)
        make_video(cls.lib / '.hidden' / 'hidden.mp4', seconds=1)
        make_video(cls.lib / 'blackstart.mp4', seconds=10, black_lead=3)
        (cls.lib / 'corrupt.mp4').write_bytes(os.urandom(4096))
        (cls.lib / 'notes.txt').write_text('not a video')
        # TypeScript sources share the .ts extension with MPEG-TS video.
        (cls.lib / 'code.ts').write_text('export const x: number = 1;\n' * 20)
        (cls.lib / 'node_modules' / 'pkg').mkdir(parents=True)
        make_video(cls.lib / 'node_modules' / 'pkg' / 'fixture.mp4', seconds=1)
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(cls.lib / 'a.mp4'), '-c', 'copy',
                        '-f', 'mpegts', str(cls.lib / 'broadcast.ts')], check=True)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        self.db = Database(self.tmp / f'db-{self._testMethodName}.sqlite')

    def test_probe(self):
        m = metadata.probe(self.lib / 'sub' / 'b.mkv')
        self.assertEqual((m['width'], m['height']), (1920, 1080))
        self.assertAlmostEqual(m['duration'], 2, delta=0.3)
        self.assertEqual(m['video_codec'], 'h264')
        self.assertEqual(m['audio_codec'], 'aac')
        self.assertEqual(m['fps'], 25)
        self.assertEqual(len(m['audio_streams']), 1)

    def test_probe_corrupt_raises(self):
        with self.assertRaises(metadata.MetadataError):
            metadata.probe(self.lib / 'corrupt.mp4')

    def test_thumbnail_avoids_black(self):
        out = self.tmp / 'thumbs' / 'x.webp'
        thumbnail.generate(self.lib / 'blackstart.mp4', 10, out)
        from PIL import Image, ImageStat
        with Image.open(out) as im:
            self.assertEqual(im.size, (480, 270))
            self.assertGreater(ImageStat.Stat(im.convert('L')).mean[0], 30)

    def test_scan_incremental(self):
        f = self.db.add_folder(self.lib)
        r = scanner.scan_folder(self.db, f, EXTS)
        # hidden, .txt, TypeScript .ts and node_modules ignored; real MPEG-TS + corrupt included
        self.assertEqual(r.found, 6)
        self.assertEqual(r.added, 6)
        self.assertEqual(r.failed, 1)
        vids = self.db.query_videos()
        self.assertEqual(len(vids), 6)
        self.assertIsNotNone(self.db.get_video_by_path(self.lib / 'broadcast.ts'))
        self.assertIsNone(self.db.get_video_by_path(self.lib / 'code.ts'))
        corrupt = self.db.get_video_by_path(self.lib / 'corrupt.mp4')
        self.assertIsNotNone(corrupt['error'])

        r2 = scanner.scan_folder(self.db, f, EXTS)
        self.assertEqual((r2.added, r2.updated, r2.removed), (0, 0, 0))

        extra = self.lib / 'new.mp4'
        make_video(extra, seconds=1)
        try:
            r3 = scanner.scan_folder(self.db, f, EXTS)
            self.assertEqual(r3.added, 1)
        finally:
            extra.unlink()
        r4 = scanner.scan_folder(self.db, f, EXTS)
        self.assertEqual(r4.removed, 1)

    def test_scan_non_recursive_and_hidden(self):
        f = self.db.add_folder(self.lib, include_subdirs=False)
        r = scanner.scan_folder(self.db, f, EXTS)
        self.assertEqual(r.found, 4)
        f2 = self.db.add_folder(self.tmp)  # parent folder, hidden allowed
        r2 = scanner.scan_folder(self.db, dict(f2, include_subdirs=1), EXTS, ignore_hidden=False)
        self.assertEqual(r2.found, 7)

    def test_disconnected_folder(self):
        f = self.db.add_folder(self.tmp / 'gone')
        r = scanner.scan_folder(self.db, f, EXTS)
        self.assertFalse(r.available)
        self.assertEqual(self.db.get_folder(f['id'])['available'], 0)

    def test_query_filters_favorites_history(self):
        f = self.db.add_folder(self.lib)
        scanner.scan_folder(self.db, f, EXTS)
        b = self.db.get_video_by_path(self.lib / 'sub' / 'b.mkv')
        self.assertEqual([v['id'] for v in self.db.query_videos(filters={'resolution': '1080'})], [b['id']])
        self.assertEqual(len(self.db.query_videos(filters={'format': 'mkv'})), 1)
        self.assertEqual(len(self.db.query_videos(search='deeper')), 1)
        names = [v['title'] for v in self.db.query_videos(sort='name_asc')]
        self.assertEqual(names, sorted(names, key=str.lower))
        self.db.set_favorite(b['id'], True)
        self.assertEqual(len(self.db.query_videos(view='favorites')), 1)
        self.db.save_position(b['id'], 42.0, False)
        cont = self.db.query_videos(view='continue')
        self.assertEqual(cont[0]['position'], 42.0)
        self.db.save_position(b['id'], 0, True)
        self.assertEqual(len(self.db.query_videos(view='continue')), 0)

    def test_concurrent_writes(self):
        f = self.db.add_folder(self.lib)
        errors = []

        def writer(n):
            try:
                for i in range(50):
                    self.db.upsert_video(f['id'], {'file_path': f'/x/{n}/{i}.mp4', 'title': 't',
                                                   'file_size': i, 'file_mtime': i})
            except Exception as e:
                errors.append(e)
        ts = [threading.Thread(target=writer, args=(n,)) for n in range(6)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        self.assertEqual(errors, [])
        self.assertEqual(len(self.db.query_videos()), 300)

    def test_large_library_query_speed(self):
        f = self.db.add_folder('/fake')
        now = time.time()
        with self.db.write() as c:
            c.executemany(
                'INSERT INTO videos(folder_id,title,file_path,file_size,duration,width,height,'
                'file_mtime,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)',
                [(f['id'], f'Video {i}', f'/fake/v{i}.mp4', i * 1000, i % 3600, 1920, 1080, 0,
                  now - i, now) for i in range(12000)])
        t0 = time.perf_counter()
        rows = self.db.query_videos(search='Video 11', sort='name_asc')
        dt = time.perf_counter() - t0
        self.assertGreater(len(rows), 100)
        self.assertLess(dt, 0.5)




LEGACY_SCHEMA = """
CREATE TABLE folders (id INTEGER PRIMARY KEY, path TEXT UNIQUE, name TEXT, enabled INTEGER DEFAULT 1,
    last_scanned_at TIMESTAMP, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE videos (id INTEGER PRIMARY KEY, folder_id INTEGER, title TEXT, file_path TEXT UNIQUE,
    file_size INTEGER, duration REAL, width INTEGER, height INTEGER, fps REAL, video_codec TEXT,
    audio_codec TEXT, bitrate INTEGER, thumbnail_path TEXT, file_mtime INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(folder_id) REFERENCES folders(id));
CREATE TABLE playback_history (id INTEGER PRIMARY KEY, video_id INTEGER, position REAL,
    completed INTEGER DEFAULT 0, last_played_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(video_id) REFERENCES videos(id));
CREATE TABLE favorites (id INTEGER PRIMARY KEY, video_id INTEGER UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY(video_id) REFERENCES videos(id));
CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT);
"""


class MigrationTests(unittest.TestCase):
    def test_upgrade_from_legacy_schema(self):
        import sqlite3
        tmp = Path(tempfile.mkdtemp(prefix='neplayer-mig-'))
        try:
            path = tmp / 'old.db'
            c = sqlite3.connect(path)
            c.executescript(LEGACY_SCHEMA)
            c.execute("INSERT INTO folders(id, path, name) VALUES (1, '/old/Downloads', 'Downloads')")
            c.execute("INSERT INTO videos(id, folder_id, title, file_path, file_size, duration, width, height,"
                      " file_mtime) VALUES (7, 1, 'Old Clip', '/old/Downloads/a.mp4', 100, 60, 1280, 720, 123)")
            c.execute("INSERT INTO videos(id, folder_id, file_path) VALUES (8, 1, '/old/Downloads/b.mkv')")
            c.execute("INSERT INTO favorites(video_id) VALUES (7)")
            c.execute("INSERT INTO playback_history(video_id, position) VALUES (7, 30)")
            c.execute("INSERT INTO playback_history(video_id, position) VALUES (7, 12)")  # duplicate rows
            c.commit()
            c.close()

            db = Database(path)
            from neplayer.core.database import SCHEMA_VERSION
            self.assertEqual(db.conn.execute('PRAGMA user_version').fetchone()[0], SCHEMA_VERSION)
            cols = {r[1] for r in db.conn.execute('PRAGMA table_info(videos)')}
            self.assertTrue({'media_kind', 'artist', 'album', 'track'} <= cols)  # music columns added in place
            self.assertEqual([f['path'] for f in db.list_folders()], ['/old/Downloads'])
            vids = {v['id']: v for v in db.query_videos()}
            self.assertEqual(set(vids), {7, 8})
            self.assertEqual(vids[8]['title'], '/old/Downloads/b.mkv')
            self.assertTrue(vids[7]['favorite'])
            self.assertIsInstance(vids[7]['created_at'], float)
            self.assertEqual(db.folder_index(1)['/old/Downloads/a.mp4']['file_mtime'], 0)  # forces re-probe
            self.assertIn('missing', db._columns(db.conn, 'videos'))
            # upserts and cascading deletes work on the rebuilt tables
            db.save_position(7, 45.0, False)
            self.assertEqual(db.get_video(7)['position'], 45.0)
            db.remove_folder(1)
            self.assertEqual(db.query_videos(), [])
            db.close()
            # reopening is a no-op
            Database(path).close()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == '__main__':
    unittest.main()


class ThemeSettingTests(unittest.TestCase):
    """The old on/off "Dark theme" switch migrates to the Dark/Light/Glass choice."""

    def _settings(self, stored):
        from neplayer.core.settings import Settings
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        db = Database(Path(d) / 't.db')
        for k, v in stored.items():
            db.set_setting(k, v)
        return Settings(db)

    def test_default_is_dark(self):
        self.assertEqual(self._settings({})['theme'], 'dark')

    def test_old_light_switch_becomes_light(self):
        self.assertEqual(self._settings({'dark_theme': False})['theme'], 'light')

    def test_explicit_theme_wins_and_bad_values_fall_back(self):
        self.assertEqual(self._settings({'dark_theme': False, 'theme': 'glass'})['theme'], 'glass')
        self.assertEqual(self._settings({'theme': 'neon'})['theme'], 'dark')

    def test_every_theme_has_its_stylesheets(self):
        from neplayer.config import RESOURCES_DIR
        for t in ('dark', 'light', 'glass'):
            for suffix in ('.colors.css', '.css'):
                self.assertTrue((RESOURCES_DIR / 'styles' / 'themes' / f'{t}{suffix}').is_file(), t + suffix)


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'needs ffmpeg')
class MusicTests(unittest.TestCase):
    """Audio files are probed as music, listed in the Music view and given album art."""

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.song = self.dir / 'song.mp3'
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=3',
                        '-metadata', 'title=Test Song', '-metadata', 'artist=Tester', '-metadata', 'album=Demo',
                        '-metadata', 'track=2/9', '-metadata', 'date=2020', str(self.song)], check=True)

    def test_probe_reads_tags(self):
        m = metadata.probe(self.song)
        self.assertEqual(m['media_kind'], 'audio')
        self.assertEqual((m['title'], m['artist'], m['album'], m['track'], m['year']),
                         ('Test Song', 'Tester', 'Demo', 2, 2020))
        self.assertAlmostEqual(m['duration'], 3.0, delta=0.2)

    def test_music_view_and_art(self):
        db = Database(self.dir / 'lib.db')
        folder = db.add_folder(self.dir)
        from neplayer.config import AUDIO_EXTENSIONS
        res = scanner.scan_folder(db, folder, set(DEFAULT_EXTENSIONS) | set(AUDIO_EXTENSIONS))
        self.assertEqual(res.added, 1)
        self.assertEqual([v['title'] for v in db.query_videos('music')], ['Test Song'])
        self.assertEqual(db.query_videos('all'), [])  # "All Videos" excludes music
        v = db.query_videos('music')[0]
        db.save_position(v['id'], 1.5, False)
        self.assertEqual(db.query_videos('continue'), [])  # songs never appear in Continue Watching
        out = thumbnail.generate(str(self.song), 3.0, self.dir / 't.webp')
        # no embedded cover: a marker instead of a picture; the card draws a themed music icon
        self.assertTrue(out.endswith(thumbnail.NO_ART_SUFFIX) and Path(out).exists())
        cover, bg = thumbnail.cover_art(str(self.song), 1, self.dir / 'cache', 'Demo')
        self.assertTrue(Path(cover).exists() and Path(bg).exists())

    def test_placeholder_is_a_music_note(self):
        img = thumbnail.placeholder_art(size=200)
        self.assertEqual(img.size, (200, 200))
        # a white note in the middle of a dark backdrop
        self.assertGreater(img.crop((70, 70, 130, 130)).convert('L').getextrema()[1], 230)
        self.assertLess(img.getpixel((198, 198))[1], 90)

    def test_song_thumb_path_changes_with_art_version(self):
        a = thumbnail.thumb_path('/c', '/m/x.mp3', 1)
        self.assertNotEqual(a, thumbnail.thumb_path('/c', '/m/x.mp4', 1))
        self.assertEqual(thumbnail.no_art_path(a).suffix, thumbnail.NO_ART_SUFFIX)

    def test_song_cards_are_remade_once_for_the_new_placeholder(self):
        path = self.dir / 'lib.db'
        db = Database(path)
        folder = db.add_folder(self.dir)
        make_video(self.dir / 'clip.mp4', seconds=1)
        from neplayer.config import AUDIO_EXTENSIONS
        scanner.scan_folder(db, folder, set(DEFAULT_EXTENSIONS) | set(AUDIO_EXTENSIONS))
        song, clip = db.query_videos('music')[0], db.query_videos('all')[0]
        for v in (song, clip):
            db.set_thumbnail(v['id'], f'/tmp/{v["id"]}.webp')
        db.set_setting('audio_art_version', 'old')
        db = Database(path)                                  # next start: song card reset, video kept
        self.assertIsNone(db.get_video(song['id'])['thumbnail_path'])
        self.assertEqual(db.get_video(clip['id'])['thumbnail_path'], f'/tmp/{clip["id"]}.webp')
        db.set_thumbnail(song['id'], '/tmp/new.webp')
        db = Database(path)                                  # and only once
        self.assertEqual(db.get_video(song['id'])['thumbnail_path'], '/tmp/new.webp')


class EqualizerTests(unittest.TestCase):
    """Settings → mpv filter chain, presets and the response curve."""

    def setUp(self):
        from neplayer.player import equalizer as eq
        self.eq = eq
        self.s = dict(eq.DEFAULTS, eq_gains=list(eq.FLAT))

    def test_flat_or_off_means_no_processing(self):
        self.assertEqual(self.eq.build_af(self.s), '')
        self.s.update(eq_gains=list(self.eq.PRESETS['Rock']), eq_enabled=False)
        self.assertEqual(self.eq.build_af(self.s), '')

    def test_chain_has_changed_bands_extras_and_limiter(self):
        self.s.update(eq_gains=[0, 0, 0, 0, 0, 3, 0, 0, 0, -2], eq_preamp=-4.0, eq_crossfeed=True)
        af = self.eq.build_af(self.s).split(',')
        self.assertEqual(af[0], '@eqpre:lavfi-volume=volume=-4dB')
        self.assertIn('@eq5:lavfi-equalizer=f=1000:t=o:w=1:g=3', af)
        self.assertIn('@eq9:lavfi-equalizer=f=16000:t=o:w=1:g=-2', af)
        self.assertEqual(sum(f.startswith('@eq') and 'equalizer' in f for f in af), 2)  # flat bands skipped
        self.assertTrue(any('crossfeed' in f for f in af))
        self.assertIn('alimiter', af[-1])

    def test_gains_are_cleaned_and_presets_matched(self):
        self.assertEqual(self.eq.clean_gains([99, -99, 'x', 1.26]), [12, -12, 0, 1.5] + [0.0] * 6)
        self.assertEqual(self.eq.preset_for(self.eq.PRESETS['Vocal']), 'Vocal')
        self.assertEqual(self.eq.preset_for([1] * 10, {'Mine': [1] * 10}), 'Mine')
        self.assertEqual(self.eq.preset_for([1, 2] + [0] * 8), self.eq.CUSTOM)
        for name, gains in self.eq.PRESETS.items():
            self.assertEqual(len(gains), len(self.eq.BANDS), name)

    def test_response_curve_peaks_at_the_band(self):
        gains = [0] * 10
        gains[5] = 6
        r = self.eq.response_db(gains, -2, [1000, 30, 15000])
        self.assertAlmostEqual(r[0], 4.0, delta=0.05)      # +6 band, -2 preamp
        self.assertAlmostEqual(r[1], -2.0, delta=0.05)     # far away: preamp only
        self.assertAlmostEqual(r[2], -2.0, delta=0.1)


class PlaylistTests(unittest.TestCase):
    """Shuffle visits every item once; repeat all wraps; repeat off stops at the end."""

    def _manager(self, **settings):
        from neplayer.player.playback_manager import PlaybackManager
        s = {'shuffle': False, 'repeat': 'off', 'resume_playback': True, 'keep_history': True}
        s.update(settings)
        items = [{'id': i, 'file_path': f'/m/{i}.mp3'} for i in range(6)]
        m = PlaybackManager(None, s)
        m.set_playlist(items, items[2])
        return m, s

    def test_sequential_and_repeat(self):
        m, s = self._manager()
        self.assertEqual(m.current['id'], 2)
        seen = [m.current['id']]
        while m.go(1):
            seen.append(m.current['id'])
        self.assertEqual(seen, [2, 3, 4, 5])
        s['repeat'] = 'all'
        self.assertTrue(m.has_next())
        self.assertEqual(m.go(1)['id'], 0)

    def test_shuffle_plays_everything_once(self):
        m, _ = self._manager(shuffle=True)
        self.assertEqual(m.current['id'], 2)  # the chosen item plays first
        order = [m.current['id']]
        while m.go(1):
            order.append(m.current['id'])
        self.assertEqual(sorted(order), list(range(6)))


@unittest.skipUnless(shutil.which('ffmpeg'), 'needs ffmpeg')
class VisualizerAnalysisTests(unittest.TestCase):
    """The visualizer reacts to real audio: right frequencies, beats, no blocking."""

    def test_bands_and_beats(self):
        import numpy as np
        from neplayer.visualizer.analysis import Analyzer, RATE
        t = np.arange(RATE * 4) / RATE
        sig = 0.02 * np.random.randn(len(t))
        for k in np.arange(0, 4, 0.5):  # kick drum every 0.5 s
            i0, n = int(k * RATE), int(0.12 * RATE)
            sig[i0:i0 + n] += 0.8 * np.exp(-np.arange(n) / RATE * 30) * np.sin(2 * np.pi * 55 * np.arange(n) / RATE)
        a = Analyzer(2048)
        st = np.stack([sig, sig], 1).astype(np.float32)
        for i in range(240):
            end = int((i + 1) / 60 * RATE)
            if end >= 2048:
                a.analyze(st[end - 2048:end], 1 / 60)
        self.assertEqual(a.frame.beats, 8)
        self.assertGreater(a.frame.history.max(), 0.1)

    def test_pcm_source_never_blocks_and_decodes(self):
        import time as _t
        from neplayer.visualizer.analysis import PcmSource
        d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, d, True)
        f = d / 'tone.wav'
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=20',
                        '-ac', '2', str(f)], check=True)
        src = PcmSource(str(f))
        t0 = _t.monotonic()
        w = src.window(9.0, 2048)          # segment 1 not decoded yet: returns silence immediately
        self.assertLess(_t.monotonic() - t0, 0.1)
        self.assertEqual(w.shape, (2048, 2))
        for _ in range(100):               # background decode fills it in
            if src.ready(1):
                break
            _t.sleep(0.05)
        self.assertGreater(float(abs(src.window(9.0, 2048)).max()), 0.05)  # ffmpeg sine amplitude is 1/8

    def test_presets_are_discovered(self):
        from neplayer.visualizer.presets import load_presets
        presets = load_presets()
        self.assertEqual(len(presets), 50)
        self.assertEqual(len({p.id for p in presets}), 50)
        self.assertTrue(all('vec4 render()' in p.body for p in presets))


class UpdaterTests(unittest.TestCase):
    def test_versions(self):
        from neplayer.core import updater
        self.assertEqual(updater.parse_version('v1.4.0'), (1, 4, 0))
        self.assertEqual(updater.parse_version('2.0'), (2, 0, 0))
        self.assertTrue(updater.is_newer('v1.10.0', '1.9.3'))
        self.assertFalse(updater.is_newer('v1.4.0', '1.4.0'))
        self.assertFalse(updater.is_newer('v1.3.9', '1.4.0'))

    def _release(self, tag):
        return {'tag_name': tag, 'body': 'Fixes', 'html_url': 'https://example.invalid/r', 'assets': [
            {'name': 'ENPlayer-Setup-9.0.0.exe', 'browser_download_url': 'https://x/win.exe', 'size': 3},
            {'name': 'enplayer_9.0.0_all.deb', 'browser_download_url': 'https://x/a.deb', 'size': 5,
             'digest': 'sha256:' + 'ab' * 32}]}

    def test_release_selection(self):
        from neplayer.core import updater
        up = updater.update_from_release(self._release('v9.0.0'), 'deb')
        self.assertEqual((up.version, up.asset_name, up.sha256), ('9.0.0', 'enplayer_9.0.0_all.deb', 'ab' * 32))
        self.assertEqual(updater.update_from_release(self._release('v9.0.0'), 'windows').asset_name,
                         'ENPlayer-Setup-9.0.0.exe')
        src = updater.update_from_release(self._release('v9.0.0'), None)   # running from source
        self.assertFalse(src.installable)
        self.assertIsNone(updater.update_from_release(self._release('v0.1.0'), 'deb'))
        self.assertIsNone(updater.update_from_release(dict(self._release('v9.0.0'), prerelease=True), 'deb'))

    def test_download_verifies_checksum(self):
        import hashlib
        from neplayer.core import updater
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        src = tmp / 'pkg.deb'
        src.write_bytes(b'new version' * 1000)
        good = hashlib.sha256(src.read_bytes()).hexdigest()
        seen = []
        up = updater.Update('9.0.0', '', '', 'enplayer_9.0.0_all.deb', src.as_uri(), 0, good)
        out = updater.download(up, tmp / 'dl', lambda d, t: seen.append(d))
        self.assertEqual(out.read_bytes(), src.read_bytes())
        self.assertTrue(seen)
        bad = updater.Update('9.0.0', '', '', 'x.deb', src.as_uri(), 0, '0' * 64)
        with self.assertRaises(updater.UpdateError):
            updater.download(bad, tmp / 'dl')
        self.assertFalse((tmp / 'dl' / 'x.deb').exists())
