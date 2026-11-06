"""End-to-end check that drives the real GTK app (needs a display).

Usage: python3 tests/e2e_harness.py LIBRARY_DIR OUT_DIR
Uses an isolated data/cache dir inside OUT_DIR, never your real library.
Screenshots capture only NEPLAYER's own window (via its X11 window id).
"""
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

LIB = Path(sys.argv[1]).resolve()
OUT = Path(sys.argv[2]).resolve()
OUT.mkdir(parents=True, exist_ok=True)
os.environ['NEPLAYER_DATA_DIR'] = str(OUT / 'data')
os.environ['NEPLAYER_CACHE_DIR'] = str(OUT / 'cache')
os.environ['NEPLAYER_NO_DEFAULT_FOLDER'] = '1'
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import gi  # noqa: E402
gi.require_version('Gtk', '4.0')
gi.require_version('GdkX11', '4.0')
from gi.repository import GdkX11, GLib, Gtk  # noqa: E402

from neplayer.app import NeplayerApp  # noqa: E402
from neplayer.ui.video_card import VideoCard, _registry  # noqa: E402

results = []


def check(name, cond, detail=''):
    results.append((name, bool(cond), detail))
    print(('PASS ' if cond else 'FAIL ') + name + (f' — {detail}' if detail else ''), flush=True)


def shot(win, name):
    xid = win.get_surface().get_xid()
    subprocess.run(['import', '-window', str(xid), str(OUT / f'{name}.png')], check=False)


def all_cards():
    out = []
    for s in _registry.values():
        out.extend(c for c in s if c.get_mapped() and c.item is not None)
    return out


def card_for(title):
    for c in all_cards():
        if c.item.data['title'].startswith(title):
            return c
    return None


def script(app):
    """Generator of (delay_ms) steps executed on the GTK main loop."""
    win = app.window
    lib = app.library
    win.set_default_size(1440, 900)
    yield 500
    if not app.db.list_folders():
        lib.add_folder(str(LIB))
    t0 = time.time()
    while (lib.is_scanning or lib.thumbs.pending()) and time.time() - t0 < 120:
        yield 300
    yield 600
    n = len(app.db.query_videos())
    check('scan found videos', n >= 9, f'{n} videos')
    broken = [v for v in app.db.query_videos() if v['error']]
    check('corrupt file recorded with error', len(broken) == 1)
    no_thumb = [v['title'] for v in app.db.query_videos() if not v['thumbnail_path'] and not v['error']]
    check('thumbnails generated', not no_thumb, str(no_thumb))

    win.navigate('home')
    yield 1500
    shot(win, '01-home')

    win.navigate('all')
    yield 1500
    shot(win, '02-grid')

    # ---------- hover preview
    card = card_for('Deep Zoom')
    check('card found for preview', card is not None)
    pm = win.previews
    pm.hover_enter(card)
    yield 200
    check('preview not started before delay', pm.active_card is None)
    yield 2600
    check('preview active on hovered card', pm.active_card is card,
          f'last stop reason: {pm.last_stop_reason}, mapped={card.get_mapped()}, active={win.is_active()}')
    check('preview rendered real frames', card.has_css_class('preview-live'))
    pos = pm._area.mpv.time_pos if pm._area else None
    check('preview playing from original file', pos is not None and pos > 5, f'time_pos={pos}')
    shot(win, '03-preview')
    pm.hover_leave(card)
    yield 300
    check('preview stops on leave', pm.active_card is None and pm._area.get_parent() is None)

    # ---------- rapid hover stress
    threads_before = threading.active_count()
    cards = all_cards()
    starts_before = pm.starts
    for i in range(60):
        c = cards[i % len(cards)]
        pm.hover_enter(c)
        yield 15
        pm.hover_leave(c)
    check('rapid hovering never starts previews', pm.starts == starts_before,
          f'{pm.starts - starts_before} starts')
    playable = [c for c in cards if not c.item.data.get('error')]
    for i in range(12):  # repeated full start/stop cycles
        c = playable[i % len(playable)]
        pm.hover_enter(c)
        yield int(app.settings['preview_delay_ms']) + 500
        pm.hover_leave(c)
        yield 60
    attached = sum(1 for c in cards if c.preview_slot.get_first_child() is not None)
    check('at most one preview surface attached', attached == 0, f'{attached} attached after stop')
    check('every preview cycle started', pm.starts - starts_before == 12,
          f'{pm.starts - starts_before} starts, last stop: {pm.last_stop_reason}, window active: {win.is_active()}')
    threads_after = threading.active_count()
    check('no thread leak from previews', threads_after <= threads_before + 2,
          f'{threads_before} -> {threads_after}')

    # ---------- full player
    ep = app.db.get_video_by_path(LIB / 'Shows' / 'Season1' / 'Episode 01 - Pilot.mkv')
    win.play(ep, card_for('Episode 01'))
    yield 3000
    p = win.player
    check('player visible', win.pages.get_visible_child_name() == 'player')
    tp = p.mpv.time_pos
    check('player is playing', tp is not None and tp > 1, f'time_pos={tp}')
    auds = [t for t in p._tracks if t['type'] == 'audio']
    subs = [t for t in p._tracks if t['type'] == 'sub']
    check('two audio tracks detected', len(auds) == 2)
    check('external subtitle auto-loaded', len(subs) >= 1)
    p._set_track('sid', str(subs[0]['id'])) if subs else None
    p.show_controls(force=True)
    yield 800
    shot(win, '04-player')
    p.cycle('aid')
    yield 300
    check('audio track switched', p.mpv.aid == 2, f'aid={p.mpv.aid}')
    p.seek_relative(20)
    yield 800
    check('seek works', (p.mpv.time_pos or 0) > 20, f'time_pos={p.mpv.time_pos}')
    p._set_speed(1.5)
    yield 100
    check('speed change', abs((p.mpv.speed or 0) - 1.5) < 0.01)
    p.toggle_pause()
    yield 300
    check('pause works', p.mpv.pause is True)
    p.toggle_pause()
    pos_before_close = p.mpv.time_pos
    win.close_player()
    yield 500
    saved = app.db.get_video(ep['id'])
    check('position saved on close', abs(saved['position'] - pos_before_close) < 3,
          f'{saved["position"]:.1f} vs {pos_before_close:.1f}')
    check('appears in continue watching',
          any(v['id'] == ep['id'] for v in app.db.query_videos('continue')))

    # resume
    win.play(app.db.get_video(ep['id']))
    yield 1500
    check('resumes from saved position', (p.mpv.time_pos or 0) >= saved['position'] - 1,
          f'time_pos={p.mpv.time_pos}')
    # next / prev playlist
    win.close_player()
    yield 300
    app.settings.set('sort', 'name_asc')
    win.navigate('folder', folder_id=ep['folder_id'])
    yield 500
    listing = [v['title'] for v in win.grid.video_list()]
    expected = listing[listing.index(ep['title']) + 1]
    win.play(ep, card_for('Episode 01'))
    yield 800
    p.next()
    yield 1500
    got = (p.manager.current or {}).get('title', '')
    check('next video follows grid order', got == expected, f'{got} (expected {expected})')
    check('next video actually playing', (p.mpv.time_pos or 0) > 0.2 and p.mpv.path.endswith(got.split()[0]) or
          os.path.basename(p.mpv.path or '').startswith(got), str(p.mpv.path))
    win.close_player()
    yield 300

    # broken file
    bad = app.db.get_video_by_path(LIB / 'Clips' / 'Broken Download.mp4')
    win.play(bad)
    yield 1500
    check('broken file shows error instead of crashing', p.error_box.get_visible())
    shot(win, '05-error')
    win.close_player()
    yield 300

    # favorites
    lib.set_favorite(ep['id'], True)
    win.navigate('favorites')
    yield 400
    check('favorites view lists favorite', len(win.grid.video_list()) == 1)

    # search & filter
    win.navigate('all')
    win.header.search.set_text('mandel')
    yield 700
    check('search filters grid', [v['title'] for v in win.grid.video_list()] == ['Deep Zoom Mandelbrot'])
    win.header.search.set_text('')
    win.header.filters['resolution'] = '4k'
    win._refresh_view()
    yield 300
    check('resolution filter', [v['title'] for v in win.grid.video_list()] == ['Rule 110 4K'])
    win.header.reset_filters()
    yield 300

    win.navigate('folders')
    yield 600
    shot(win, '06-folders')
    win.navigate('settings')
    yield 600
    shot(win, '07-settings')

    # file monitor: add a file, expect auto rescan
    newf = LIB / 'Clips' / 'Monitor Test.mp4'
    import shutil
    shutil.copy(LIB / 'Movies' / 'Test Pattern.mp4', newf)
    t0 = time.time()
    found = False
    while time.time() - t0 < 15:
        yield 500
        if app.db.get_video_by_path(newf):
            found = True
            break
    check('file monitor picks up new file', found)
    newf.unlink()
    t0 = time.time()
    gone = False
    while time.time() - t0 < 15:
        yield 500
        if app.db.get_video_by_path(newf) is None:
            gone = True
            break
    check('file monitor handles deletion', gone)

    win.navigate('home')
    yield 800
    shot(win, '08-home-after')
    app.quit()


def main():
    app = NeplayerApp()

    def on_activate(_a):
        gen = script(app)

        def step():
            try:
                delay = next(gen)
            except StopIteration:
                return False
            except Exception:
                import traceback
                traceback.print_exc()
                results.append(('harness exception', False, ''))
                app.quit()
                return False
            GLib.timeout_add(delay, step)
            return False
        GLib.timeout_add(300, step)
    app.connect_after('activate', on_activate)
    app.run([])
    failed = [r for r in results if not r[1]]
    print(f'\n{len(results) - len(failed)}/{len(results)} checks passed')
    sys.exit(1 if failed else 0)


if __name__ == '__main__':
    main()
