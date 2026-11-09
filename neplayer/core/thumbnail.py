"""Static thumbnail generation with FFmpeg (WebP, 480x270)."""
import hashlib
import logging
import shutil
import subprocess
from pathlib import Path

from neplayer.config import AUDIO_EXTENSIONS, THUMB_HEIGHT, THUMB_WIDTH
from neplayer.core.metadata import FFMPEG, NO_WINDOW

log = logging.getLogger(__name__)


class ThumbnailError(Exception):
    pass


AUDIO_ART_VERSION = 'themed-note-1'  # bump to re-make every song card (also Database.ART_VERSION)


def no_art_path(thumb):
    """Marker stored instead of a picture for songs without cover art."""
    return Path(thumb).with_suffix(NO_ART_SUFFIX)


NO_ART_SUFFIX = '.noart'


def thumb_path(cache_dir, file_path, mtime):
    key = f'{file_path}\0{mtime}'
    if Path(file_path).suffix.lower().lstrip('.') in AUDIO_EXTENSIONS:
        key += f'\0{AUDIO_ART_VERSION}'
    key = hashlib.sha1(key.encode()).hexdigest()
    return Path(cache_dir) / 'thumbnails' / key[:2] / f'{key}.webp'


def _candidate_times(duration):
    if duration <= 0:
        return [0.0]
    if duration < 4:
        return [duration / 2]
    return [duration * f for f in (0.18, 0.33, 0.5, 0.08)]


_SCALE = (f'scale={THUMB_WIDTH}:{THUMB_HEIGHT}:force_original_aspect_ratio=decrease,'
          f'pad={THUMB_WIDTH}:{THUMB_HEIGHT}:(ow-iw)/2:(oh-ih)/2:color=black')


def _extract(path, t, out, timeout):
    # `thumbnail` picks the most representative frame from the next 60 frames,
    # which avoids fades and most black frames.
    cmd = [FFMPEG, '-v', 'error', '-nostdin', '-y', '-ss', f'{t:.3f}', '-i', str(path),
           '-an', '-sn', '-dn', '-vf', f'thumbnail=60,{_SCALE}', '-frames:v', '1',
           '-c:v', 'libwebp', '-quality', '82', str(out)]
    r = subprocess.run(cmd, capture_output=True, timeout=timeout, check=False,
                       creationflags=NO_WINDOW)
    return r.returncode == 0 and out.exists() and out.stat().st_size > 0


def _brightness(path):
    try:
        from PIL import Image, ImageStat
        with Image.open(path) as im:
            stat = ImageStat.Stat(im.convert('L').resize((96, 54)))
            return stat.mean[0], stat.stddev[0]
    except Exception:
        return 128.0, 50.0


def generate(file_path, duration, out_path, timeout=60):
    if Path(file_path).suffix.lower().lstrip('.') in AUDIO_EXTENSIONS:
        return audio_thumbnail(file_path, out_path, timeout)
    if FFMPEG is None:
        raise ThumbnailError('ffmpeg is not installed')
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_suffix('.tmp.webp')
    best = None
    try:
        for i, t in enumerate(_candidate_times(duration)):
            cand = out_path.with_suffix(f'.c{i}.webp')
            try:
                ok = _extract(file_path, t, cand, timeout)
            except subprocess.TimeoutExpired:
                ok = False
            if not ok:
                continue
            mean, std = _brightness(cand)
            score = std + min(mean, 120) * 0.3
            if best is None or score > best[0]:
                if best is not None:
                    best[1].unlink(missing_ok=True)
                best = (score, cand)
            else:
                cand.unlink(missing_ok=True)
            if mean > 30 and std > 18:  # good enough, not black/flat
                break
        if best is None:
            raise ThumbnailError('Could not decode any frame')
        shutil.move(str(best[1]), tmp)
        tmp.replace(out_path)
        return str(out_path)
    finally:
        for p in out_path.parent.glob(out_path.stem + '.c*.webp'):
            p.unlink(missing_ok=True)
        tmp.unlink(missing_ok=True)


# ------------------------------------------------------------------ music art
def extract_cover(file_path, out_path, size=600, timeout=30):
    """Embedded cover art (ID3 APIC, FLAC picture, MP4 covr) → JPEG. Returns True on success."""
    if FFMPEG is None:
        return False
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [FFMPEG, '-v', 'error', '-nostdin', '-y', '-i', str(file_path), '-an', '-map', '0:v:0',
           '-frames:v', '1', '-vf', f'scale={size}:{size}:force_original_aspect_ratio=decrease',
           '-q:v', '3', str(out_path)]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=timeout, check=False, creationflags=NO_WINDOW)
    except subprocess.TimeoutExpired:
        return False
    return r.returncode == 0 and out_path.exists() and out_path.stat().st_size > 0


def _music_glyph(side, rgba=(255, 255, 255, 240)):
    """A clean beamed music note (24-unit grid, lucide-style) drawn supersampled → RGBA side×side."""
    from PIL import Image, ImageDraw
    ss = 4
    S = side * ss
    u = S / 24
    im = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    w = 2.0 * u
    for x, y0, y1 in ((9, 18, 5), (21, 16, 3)):                       # stems
        d.rectangle([x * u - w / 2, y1 * u, x * u + w / 2, y0 * u], fill=rgba)
    d.polygon([(9 * u - w / 2, 5 * u), (21 * u + w / 2, 3 * u - .08 * u),   # slanted beam
               (21 * u + w / 2, 6.2 * u), (9 * u - w / 2, 8.2 * u)], fill=rgba)
    for cx, cy in ((6, 18), (18, 16)):                                # note heads
        d.ellipse([(cx - 3.3) * u, (cy - 3.3) * u, (cx + 3.3) * u, (cy + 3.3) * u], fill=rgba)
    return im.resize((side, side), Image.LANCZOS)


def _glass_art(W, H, opaque=False):
    """Frosted-glass tile with a centred music note. Translucent (RGBA) so the app's background
    shows through on grid cards; opaque=True flattens it onto a dark violet base (now-playing art)."""
    from PIL import Image, ImageDraw, ImageFilter
    import numpy as np
    y = np.linspace(0, 1, H)[:, None, None]
    x = np.linspace(0, 1, W)[None, :, None]
    top, bot = np.array([120, 110, 200, 82], float), np.array([60, 52, 120, 110], float)
    px = top + (bot - top) * y + np.zeros((1, W, 1))
    # soft diagonal sheen across the upper-left, like light on glass
    sheen = np.clip(1 - np.abs((x + y * .6) - .35) / .22, 0, 1) * (1 - y) * 22
    px[..., :3] += sheen
    px[..., 3] += sheen[..., 0]
    img = Image.fromarray(np.clip(px, 0, 255).astype(np.uint8), 'RGBA')
    if opaque:
        base = Image.new('RGBA', (W, H), (24, 20, 44, 255))
        base.alpha_composite(img)
        img = base
    m = min(W, H)
    # glass disc behind the note, with a faint rim
    r = int(m * .30)
    cx, cy = W // 2, H // 2
    glow = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse([cx - r, cy - r, cx + r, cy + r], fill=(167, 139, 250, 70))
    img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(m / 9)))
    disc = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    dd = ImageDraw.Draw(disc)
    dd.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(255, 255, 255, 26),
               outline=(255, 255, 255, 56), width=max(1, m // 180))
    img.alpha_composite(disc)
    side = int(m * .30)
    note = _music_glyph(side)
    shadow = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    shadow.paste((0, 0, 0, 90), (cx - side // 2 + 1, cy - side // 2 + max(2, m // 90)), note)
    img.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(max(2, m // 60))))
    img.alpha_composite(note, (cx - side // 2 - int(side * .02), cy - side // 2))
    return img


def placeholder_art(size=600):
    """Square artwork for songs without an embedded cover (now-playing view, visualizer)."""
    return _glass_art(size, size, opaque=True).convert('RGB')


def cover_art(file_path, mtime, cache_dir, seed=''):
    """(cover_path, blurred_background_path) cached on disk; falls back to generated art."""
    key = hashlib.sha1(f'{file_path}\0{mtime}\0glass-note-1'.encode()).hexdigest()
    base = Path(cache_dir) / 'covers' / key[:2]
    cover, blur = base / f'{key}.jpg', base / f'{key}-bg.jpg'
    if cover.exists() and blur.exists():
        return str(cover), str(blur)
    base.mkdir(parents=True, exist_ok=True)
    from PIL import Image, ImageFilter
    if not extract_cover(file_path, cover):
        placeholder_art().save(cover, quality=90)
    with Image.open(cover) as im:
        bg = im.convert('RGB').resize((96, 96)).filter(ImageFilter.GaussianBlur(10))
        bg.save(blur, quality=85)
    return str(cover), str(blur)


def audio_thumbnail(file_path, out_path, timeout=60):
    """Grid card for a song: square cover centred on a blurred copy of itself (16:9)."""
    from PIL import Image, ImageDraw, ImageEnhance, ImageFilter
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_suffix('.cover.jpg')
    try:
        W, H = THUMB_WIDTH, THUMB_HEIGHT
        if not extract_cover(file_path, tmp, size=512, timeout=timeout):
            # No embedded art: the card draws a themed music icon itself (see VideoCard).
            marker = no_art_path(out_path)
            marker.write_bytes(b'')
            return str(marker)
        art = Image.open(tmp).convert('RGB')
        scale = max(W / art.width, H / art.height)
        bg = art.resize((int(art.width * scale) + 1, int(art.height * scale) + 1))
        bg = bg.crop(((bg.width - W) // 2, (bg.height - H) // 2, (bg.width - W) // 2 + W, (bg.height - H) // 2 + H))
        bg = ImageEnhance.Brightness(bg.filter(ImageFilter.GaussianBlur(18))).enhance(0.62)
        side = int(H * 0.82)
        fg = art.resize((side, side)) if art.width == art.height else \
            art.resize((side, int(side * art.height / art.width)) if art.width > art.height
                       else (int(side * art.width / art.height), side))
        mask = Image.new('L', fg.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, fg.width - 1, fg.height - 1], radius=10, fill=255)
        shadow = Image.new('RGBA', (fg.width + 40, fg.height + 40), (0, 0, 0, 0))
        ImageDraw.Draw(shadow).rounded_rectangle([20, 24, fg.width + 20, fg.height + 24], radius=12, fill=(0, 0, 0, 120))
        shadow = shadow.filter(ImageFilter.GaussianBlur(10))
        x, y = (W - fg.width) // 2, (H - fg.height) // 2
        bg = bg.convert('RGBA')
        bg.alpha_composite(shadow, (x - 20, y - 20))
        bg.paste(fg, (x, y), mask)
        bg.convert('RGB').save(out_path, 'WEBP', quality=84)
        return str(out_path)
    except Exception as e:
        raise ThumbnailError(f'Could not create album art: {e}') from e
    finally:
        tmp.unlink(missing_ok=True)
