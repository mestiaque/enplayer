"""Audio equalizer: 10-band graphic EQ, preamp, enhancements and a safety limiter.

Everything runs inside mpv as FFmpeg audio filters (the `af` property). mpv 0.34 cannot change
filter parameters live (`af-command` is rejected), so the chain is re-set on every change. mpv keeps
filters whose parameters did not change, so moving one slider only rebuilds that band: no gap in
playback. Changes are coalesced so dragging a slider does not flood mpv.
"""
import logging
import math

from gi.repository import GLib

from neplayer.config import EQ_DEFAULTS

log = logging.getLogger(__name__)

BANDS = (31, 62, 125, 250, 500, 1000, 2000, 4000, 8000, 16000)
BAND_LABELS = ('31', '62', '125', '250', '500', '1k', '2k', '4k', '8k', '16k')
GAIN_MAX = 12.0          # ± dB per band
PREAMP_MIN, PREAMP_MAX = -12.0, 6.0
WIDTH_OCTAVES = 1.0      # one band per octave → neighbouring bands blend smoothly

FLAT = (0.0,) * len(BANDS)
PRESETS = {
    'Flat': FLAT,
    'Bass Boost': (6, 5, 4, 2, 0.5, 0, 0, 0, 0, 0),
    'Bass Reducer': (-6, -5, -4, -2, -0.5, 0, 0, 0, 0, 0),
    'Treble Boost': (0, 0, 0, 0, 0, 0.5, 2, 4, 5, 6),
    'Vocal': (-2, -2, -1, 1, 3, 4, 4, 3, 1, 0),
    'Rock': (5, 4, 3, 1, -1, -1, 1, 3, 4, 5),
    'Pop': (-1, 0, 2, 3, 4, 3, 1, 0, -1, -1),
    'Jazz': (3, 2, 1, 2, -1, -1, 0, 1, 2, 3),
    'Classical': (4, 3, 2, 1, -1, -1, 0, 2, 3, 4),
    'Electronic': (5, 4, 1, 0, -2, 1, 0, 1, 4, 5),
    'Hip-Hop': (5, 5, 3, 1, -1, -1, 1, 0, 2, 3),
    'Acoustic': (4, 3, 2, 1, 1, 1, 2, 3, 2, 1),
    'Speech': (-4, -3, -1, 1, 3, 4, 4, 3, 1, -1),
    'Loudness': (6, 4, 2, 0, 0, 0, 0, 1, 3, 4),
    'Late Night': (-3, -2, -1, 0, 1, 2, 2, 1, 0, -1),
}
CUSTOM = 'Custom'

# name, settings key, tooltip
ENHANCEMENTS = (
    ('Volume leveling', 'eq_leveling', 'Evens out loud and quiet passages'),
    ('Stereo widening', 'eq_widen', 'A wider, more open stereo image'),
    ('Headphone crossfeed', 'eq_crossfeed', 'Less fatiguing stereo on headphones'),
)

DEFAULTS = EQ_DEFAULTS
KEYS = frozenset(DEFAULTS)


def clean_gains(gains):
    """Exactly len(BANDS) floats, clamped and rounded to 0.5 dB."""
    out = []
    for i in range(len(BANDS)):
        try:
            g = float(gains[i])
        except (IndexError, TypeError, ValueError):
            g = 0.0
        out.append(round(max(-GAIN_MAX, min(GAIN_MAX, g)) * 2) / 2)
    return out


def preset_for(gains, user_presets=None):
    """Name of the preset these gains match, or CUSTOM."""
    g = clean_gains(gains)
    for name, values in list(PRESETS.items()) + list((user_presets or {}).items()):
        if clean_gains(values) == g:
            return name
    return CUSTOM


def _num(x):
    return f'{x:g}'


def build_af(settings):
    """mpv `af` value for the current settings ('' = no processing at all)."""
    if not settings['eq_enabled']:
        return ''
    gains = clean_gains(settings['eq_gains'])
    preamp = float(settings['eq_preamp'])
    chain = []
    if preamp:
        chain.append(f'@eqpre:lavfi-volume=volume={_num(preamp)}dB')
    for i, (f, g) in enumerate(zip(BANDS, gains)):
        if g:
            chain.append(f'@eq{i}:lavfi-equalizer=f={f}:t=o:w={_num(WIDTH_OCTAVES)}:g={_num(g)}')
    if settings['eq_widen']:
        chain.append('@eqwide:lavfi-extrastereo=m=1.6')
    if settings['eq_crossfeed']:
        chain.append('@eqxfeed:lavfi-crossfeed=strength=0.3:range=0.6')
    if settings['eq_leveling']:
        chain.append('@eqlevel:lavfi-acompressor=threshold=0.1:ratio=3:attack=15:release=300:makeup=2.5')
    if not chain:
        return ''
    # Boosts can push peaks past full scale; a transparent limiter stops the crackle.
    chain.append('@eqlimit:lavfi-alimiter=limit=0.97:attack=5:release=60:level=disabled')
    return ','.join(chain)


# ---------------------------------------------------------------- response curve
_FS = 48000.0


def _peaking(f0, gain_db):
    """RBJ peaking biquad (what FFmpeg's `equalizer` uses), bandwidth in octaves."""
    a = 10 ** (gain_db / 40)
    w0 = 2 * math.pi * f0 / _FS
    alpha = math.sin(w0) * math.sinh(math.log(2) / 2 * WIDTH_OCTAVES * w0 / math.sin(w0))
    c = math.cos(w0)
    b = (1 + alpha * a, -2 * c, 1 - alpha * a)
    d = (1 + alpha / a, -2 * c, 1 - alpha / a)
    return b, d


def response_db(gains, preamp, freqs):
    """Combined magnitude response (dB) of the band filters + preamp at each frequency."""
    sections = [_peaking(f, g) for f, g in zip(BANDS, clean_gains(gains)) if g]
    out = []
    for f in freqs:
        w = 2 * math.pi * f / _FS
        z1 = complex(math.cos(w), -math.sin(w))
        z2 = z1 * z1
        total = float(preamp)
        for b, d in sections:
            h = (b[0] + b[1] * z1 + b[2] * z2) / (d[0] + d[1] * z1 + d[2] * z2)
            total += 20 * math.log10(max(abs(h), 1e-9))
        out.append(total)
    return out


# ---------------------------------------------------------------- mpv binding
class EqualizerController:
    """Keeps mpv's audio filters in sync with the eq_* settings."""

    def __init__(self, mpv, settings):
        self.mpv = mpv
        self.settings = settings
        self._applied = None
        self._src = None
        settings.connect('changed', self._on_changed)
        self.apply()

    def _on_changed(self, _s, key):
        if key in KEYS and self._src is None:
            # coalesce a burst of changes (slider drag, preset switch) into one update
            self._src = GLib.timeout_add(40, self._flush)

    def _flush(self):
        self._src = None
        self.apply()
        return False

    def apply(self):
        af = build_af(self.settings)
        if af == self._applied:
            return
        try:
            self.mpv['af'] = af
            self._applied = af
        except Exception:
            log.exception('Could not apply audio filters: %s', af)

    @property
    def active(self):
        """True when the current settings actually process the audio."""
        return bool(build_af(self.settings))

    def shutdown(self):
        if self._src is not None:
            GLib.source_remove(self._src)
            self._src = None
