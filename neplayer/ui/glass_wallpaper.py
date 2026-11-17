"""The Glass theme's wallpaper ("liquid glass"): the accent colour at full strength with 3D ribbons —
the same design as the other EN* apps' glass-ribbons.svg + glass-sheen.svg — drawn with Pillow into
a PNG that the stylesheet uses as the window background.

GTK's CSS has no masks or backdrop blur, so the picture is rendered here, once per accent colour,
and cached (about half a second the first time). The ribbon edges are a little softer than in the
web apps: without a backdrop blur, the translucent sheets show the wallpaper as it is."""
import math
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

W, H = 1600, 1000
SOFT = 4  # px of blur on the ribbon edges

# The ribbons (SVG paths of glass-ribbons.svg, smooth "S" segments written out as curves).
RIBBON_THIN = [('M', -120, 300), ('C', 260, 120, 560, 430, 930, 250), ('C', 1300, 70, 1440, -60, 1760, 20),
               ('L', 1760, 190), ('C', 1440, 110, 1180, 470, 870, 480), ('C', 560, 490, 260, 360, -120, 470)]
RIBBON_MAIN = [('M', -120, 700), ('C', 300, 470, 650, 900, 1040, 540), ('C', 1430, 180, 1500, 80, 1760, 190),
               ('L', 1760, 560), ('C', 1450, 420, 1270, 860, 900, 930), ('C', 530, 1000, 280, 1010, -120, 1080)]
RIBBON_FOLD = [('M', 760, 1100), ('C', 1060, 820, 1340, 960, 1760, 650), ('L', 1760, 1100)]
RIBBON_LOW = [('M', -120, 980), ('C', 220, 900, 420, 1000, 700, 1100), ('L', -120, 1100)]
# glass-sheen.svg: deep folds under the ribbons, a broad light inside the main one, rims on the edges.
FOLD_MAIN = [('M', -120, 1080), ('C', 280, 1010, 900, 930, 900, 930), ('C', 1270, 860, 1450, 420, 1760, 560),
             ('L', 1760, 660), ('C', 1450, 520, 1300, 920, 930, 1000), ('C', 560, 1080, 280, 1090, -120, 1150)]
FOLD_THIN = [('M', -120, 470), ('C', 260, 360, 870, 480, 870, 480), ('C', 1180, 470, 1440, 110, 1760, 190),
             ('L', 1760, 270), ('C', 1440, 200, 1190, 540, 870, 560), ('C', 550, 580, 260, 450, -120, 560)]
FOLD_TOP = [('M', -120, 700), ('C', 300, 470, 650, 900, 1040, 540), ('C', 1430, 180, 1500, 80, 1760, 190),
            ('L', 1760, 120), ('C', 1500, 0, 1040, 450, 1040, 450), ('C', 650, 800, 300, 380, -120, 610)]
SHEEN = [('M', -60, 790), ('C', 330, 600, 660, 920, 1050, 610), ('C', 1440, 300, 1480, 200, 1720, 270),
         ('L', 1720, 360), ('C', 1480, 290, 1280, 720, 980, 780), ('C', 680, 840, 330, 760, -60, 900)]
RIM_MAIN = [('M', -120, 700), ('C', 300, 470, 650, 900, 1040, 540), ('C', 1430, 180, 1500, 80, 1760, 190)]
RIM_THIN = [('M', -120, 300), ('C', 260, 120, 560, 430, 930, 250), ('C', 1300, 70, 1440, -60, 1760, 20)]
RIM_FOLD = [('M', 760, 1100), ('C', 1060, 820, 1340, 960, 1760, 650)]


def _points(segs, steps=48):
    """The outline of an SVG-like path (M/L/C segments) as a list of points."""
    pts, cur = [], (0, 0)
    for op, *p in segs:
        if op in ('M', 'L'):
            cur = (p[0], p[1])
            pts.append(cur)
        else:
            (x0, y0), (x1, y1, x2, y2, x3, y3) = cur, p
            for i in range(1, steps + 1):
                t = i / steps
                u = 1 - t
                pts.append((u * u * u * x0 + 3 * u * u * t * x1 + 3 * u * t * t * x2 + t * t * t * x3,
                            u * u * u * y0 + 3 * u * u * t * y1 + 3 * u * t * t * y2 + t * t * t * y3))
            cur = (x3, y3)
    return pts


def _shape(segs, blur=0.0):
    """Mask (mode L) of a filled path, softened by `blur` px (which also smooths its edge)."""
    m = Image.new('L', (W, H), 0)
    ImageDraw.Draw(m).polygon(_points(segs), fill=255)
    return m.filter(ImageFilter.GaussianBlur(blur)) if blur else m


def _lines(strokes, blur=0.0):
    """Mask of stroked paths [(segs, width, alpha)], drawn at 2x and scaled down (smooth edges)."""
    m = Image.new('L', (W * 2, H * 2), 0)
    d = ImageDraw.Draw(m)
    for segs, width, a in strokes:
        d.line([(x * 2, y * 2) for x, y in _points(segs)], fill=round(255 * a), width=max(1, round(width * 2)), joint='curve')
    m = m.resize((W, H), Image.LANCZOS)
    return m.filter(ImageFilter.GaussianBlur(blur)) if blur else m


def _gradient(x0, y0, x1, y1, stops):
    """Mask whose value runs from (x0, y0) to (x1, y1) through `stops` [(offset, 0..1)]."""
    n = 512
    strip = []
    for i in range(n):
        t = i / (n - 1)
        for (o0, a0), (o1, a1) in zip(stops, stops[1:]):
            if o0 <= t <= o1:
                strip.append(round(255 * (a0 + (a1 - a0) * ((t - o0) / ((o1 - o0) or 1)))))
                break
        else:
            strip.append(round(255 * (stops[0][1] if t < stops[0][0] else stops[-1][1])))
    # Padded with the end values on both sides, then mapped onto the canvas with an affine
    # transform: each pixel takes the strip value at its projection on the vector.
    pad = 2 * n
    line = Image.new('L', (n + 2 * pad, 1))
    line.putdata([strip[0]] * pad + strip + [strip[-1]] * pad)
    dx, dy = x1 - x0, y1 - y0
    k = (n - 1) / (dx * dx + dy * dy)
    return line.transform((W, H), Image.AFFINE, (dx * k, dy * k, pad - (x0 * dx + y0 * dy) * k, 0, 0, 0),
                          resample=Image.BILINEAR)


def _scaled(mask, factor):
    return mask.point(lambda v: round(v * factor))


def _layer(img, colour, mask):
    layer = Image.new('RGBA', (W, H), colour + (0,))
    layer.putalpha(mask)
    img.alpha_composite(layer)


def _rgb(hex_colour):
    h = hex_colour.lstrip('#')
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _radial(cx, cy, rx, ry, alpha, stop):
    """Mask of a CSS radial-gradient: `alpha` at (cx, cy), fading to 0 at `stop` of the (rx, ry) ellipse."""
    w, h = W // 4, H // 4
    m = Image.new('L', (w, h))
    m.putdata([round(255 * alpha * max(0.0, 1 - math.hypot((x * 4 - cx) / rx, (y * 4 - cy) / ry) / stop))
               for y in range(h) for x in range(w)])
    return m.resize((W, H), Image.BILINEAR)


def _soft(mask, blur):
    """`mask` blurred by `blur` px (done at half size: the result is smooth anyway)."""
    return mask.resize((W // 2, H // 2), Image.BILINEAR).filter(ImageFilter.GaussianBlur(blur / 2)).resize((W, H), Image.BILINEAR)


def render(accent, path):
    """Writes the wallpaper for `accent` ('#rrggbb') to `path` (PNG)."""
    acc = _rgb(accent)
    img = Image.new('RGBA', (W, H), acc + (255,))

    # Light from the top left, depth towards the bottom right and the top right corner.
    _layer(img, (255, 255, 255), _radial(W * 0.02, -H * 0.08, 900, 620, 0.42, 0.6))
    _layer(img, (0, 0, 0), _radial(W * 1.04, H * 1.12, 1200, 900, 0.46, 0.64))
    _layer(img, (0, 0, 0), _radial(W * 0.96, -H * 0.10, 700, 500, 0.18, 0.7))

    # Ribbons: a lighter accent (a white wash from the top), alpha as in glass-ribbons.svg.
    fill = Image.new('RGBA', (W, H), acc + (255,))
    _layer(fill, (255, 255, 255), _gradient(0, 0, 0, H * 0.7, ((0, 0.6), (1, 0))))
    for segs, grad, k in ((RIBBON_THIN, (0, 20, 0, 480, ((0, 0.95), (1, 0.3))), 1),
                          (RIBBON_MAIN, (0, 190, 0, 1080, ((0, 1), (0.4, 0.7), (1, 0.25))), 1),
                          (RIBBON_FOLD, (760, 650, 1760, 1100, ((0, 0.85), (1, 0.2))), 1),
                          (RIBBON_LOW, (0, 900, 0, 1100, ((0, 0.95), (1, 0.3))), 0.6)):
        mask = ImageChops.multiply(_shape(segs, SOFT), _gradient(*grad))
        img = Image.composite(fill, img, _scaled(mask, k) if k != 1 else mask)

    # Depth: deep folds under the ribbons, a broad light inside the main one.
    for segs, a in ((FOLD_MAIN, 0.5), (FOLD_THIN, 0.42), (FOLD_TOP, 0.3)):
        _layer(img, (0, 0, 0), _scaled(_soft(_shape(segs), 26), a))
    _layer(img, (255, 255, 255), _scaled(_soft(_shape(SHEEN), 30), 0.55))

    # Specular rims along the upper edges: a soft glow plus a thin bright line.
    _layer(img, (255, 255, 255), _lines(((RIM_MAIN, 9, 0.9), (RIM_THIN, 6, 0.75), (RIM_FOLD, 6, 0.7)), 6))
    _layer(img, (255, 255, 255), _lines(((RIM_MAIN, 2, 0.95), (RIM_THIN, 1.5, 0.85), (RIM_FOLD, 1.5, 0.8))))

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(str(path) + '.tmp')
    img.convert('RGB').save(tmp, 'PNG', compress_level=1)
    tmp.replace(path)
    return Path(path)


def wallpaper(accent, cache_dir):
    """The cached wallpaper for `accent`, rendered on first use."""
    name = 'glass-wallpaper-v2-' + accent.lstrip('#').lower() + '.png'
    path = Path(cache_dir) / name
    if not path.is_file():
        render(accent, path)
    return path
