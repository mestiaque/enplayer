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


def thumb_path(cache_dir, file_path, mtime):
    key = hashlib.sha1(f'{file_path}\0{mtime}'.encode()).hexdigest()
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


ICON_PNG = Path(__file__).resolve().parent.parent / 'resources' / 'icons' / 'enplayer-512.png'


def placeholder_art(size=600):
    """Artwork for songs without an embedded cover: the ENPlayer icon on a deep violet backdrop."""
    from PIL import Image, ImageDraw, ImageFilter
    # soft diagonal gradient in the icon's colours (violet → indigo)
    import numpy as np
    t = (np.add.outer(np.arange(size), np.arange(size)) / max(2 * size - 2, 1))[..., None]
    c1, c2 = np.array([46, 16, 101], float), np.array([30, 27, 75], float)
    img = Image.fromarray((c1 + (c2 - c1) * t).astype(np.uint8), 'RGB')
    try:
        with Image.open(ICON_PNG) as icon:
            icon = icon.convert('RGBA')
            side = int(size * 0.62)
            icon = icon.resize((side, side), Image.LANCZOS)
            glow = Image.new('RGBA', (size, size), (0, 0, 0, 0))
            ImageDraw.Draw(glow).ellipse([size * .2, size * .2, size * .8, size * .8], fill=(109, 40, 217, 140))
            img = img.convert('RGBA')
            img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(size / 10)))
            img.alpha_composite(icon, ((size - side) // 2, (size - side) // 2))
    except OSError:
        pass
    return img.convert('RGB')


def cover_art(file_path, mtime, cache_dir, seed=''):
    """(cover_path, blurred_background_path) cached on disk; falls back to generated art."""
    key = hashlib.sha1(f'{file_path}\0{mtime}\0icon-placeholder'.encode()).hexdigest()
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
        if extract_cover(file_path, tmp, size=512, timeout=timeout):
            art = Image.open(tmp).convert('RGB')
        else:
            art = placeholder_art(size=512)
        W, H = THUMB_WIDTH, THUMB_HEIGHT
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
