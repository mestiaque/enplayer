"""Audio analysis for the visualizer: real PCM → spectrum, waveform, bands, beats.

mpv plays the audio but does not hand its samples to the application, so the
same file is decoded a second time with ffmpeg (in short segments, in the
background) and analysed at mpv's current playback position. Everything runs
offline; nothing here touches the GTK main loop except `Analyzer.analyze`, which
is cheap (one numpy FFT per frame).
"""
import logging
import subprocess
import threading
from dataclasses import dataclass, field

import numpy as np

from neplayer.core.metadata import FFMPEG, NO_WINDOW

log = logging.getLogger(__name__)

RATE = 22050          # Hz — enough for a visualizer (Nyquist 11 kHz), half the decode cost
SEGMENT = 8.0         # seconds decoded per ffmpeg call
N_BANDS = 128         # log-spaced spectrum bands sent to the GPU
N_WAVE = 512          # waveform samples sent to the GPU
HISTORY = 64          # spectrum frames kept for 3-D / waterfall presets
F_MIN, F_MAX = 30.0, 11000.0


class PcmSource:
    """Decoded stereo float PCM for one file, fetched in cached segments.

    `window(t, n)` returns the n samples (L, R) ending at time t. Segments are
    decoded on a background thread; until one is ready, silence is returned so
    the UI never blocks.
    """

    def __init__(self, path):
        self.path = path
        self._segments = {}          # segment index -> np.ndarray (frames, 2) float32
        self._pending = set()
        self._lock = threading.Lock()
        self._closed = False

    def close(self):
        self._closed = True
        with self._lock:
            self._segments.clear()

    def _decode(self, idx):
        start = idx * SEGMENT
        cmd = [FFMPEG, '-v', 'error', '-nostdin', '-ss', f'{start:.3f}', '-i', self.path, '-t', f'{SEGMENT:.3f}',
               '-vn', '-ac', '2', '-ar', str(RATE), '-f', 'f32le', '-']
        try:
            out = subprocess.run(cmd, capture_output=True, timeout=30, check=False, creationflags=NO_WINDOW)
            data = np.frombuffer(out.stdout, dtype=np.float32)
            data = data[: len(data) // 2 * 2].reshape(-1, 2) if len(data) else np.zeros((0, 2), np.float32)
        except Exception:
            log.exception('visualizer decode failed for %s', self.path)
            data = np.zeros((0, 2), np.float32)
        with self._lock:
            self._pending.discard(idx)
            if not self._closed:
                self._segments[idx] = data
                # keep memory bounded: only segments near the playhead
                for k in [k for k in self._segments if abs(k - idx) > 3]:
                    del self._segments[k]

    def _request(self, idx):
        if idx < 0 or FFMPEG is None:
            return
        with self._lock:
            if idx in self._segments or idx in self._pending:
                return
            self._pending.add(idx)
        threading.Thread(target=self._decode, args=(idx,), daemon=True, name='viz-decode').start()

    def ready(self, idx):
        with self._lock:
            return idx in self._segments

    def window(self, t, n):
        out = np.zeros((n, 2), np.float32)
        end = int(round(t * RATE))
        start = end - n
        seg_len = int(SEGMENT * RATE)
        first, last = max(0, start) // seg_len, max(0, end - 1) // seg_len
        missing = []
        with self._lock:  # never call _request() while holding the lock (it takes it too)
            for idx in range(first, last + 1):
                seg = self._segments.get(idx)
                if seg is None:
                    missing.append(idx)
                    continue
                s0 = idx * seg_len
                a, b = max(start, s0), min(end, s0 + len(seg))
                if b > a:
                    out[a - start:b - start] = seg[a - s0:b - s0]
        for idx in missing + [last + 1]:  # + prefetch the next segment
            self._request(idx)
        return out


@dataclass
class Frame:
    """Everything a preset can read for one rendered frame."""
    bands: np.ndarray = field(default_factory=lambda: np.zeros(N_BANDS, np.float32))     # 0..1, smoothed
    bands_l: np.ndarray = field(default_factory=lambda: np.zeros(N_BANDS, np.float32))
    bands_r: np.ndarray = field(default_factory=lambda: np.zeros(N_BANDS, np.float32))
    peaks: np.ndarray = field(default_factory=lambda: np.zeros(N_BANDS, np.float32))     # falling peak caps
    wave_l: np.ndarray = field(default_factory=lambda: np.zeros(N_WAVE, np.float32))     # -1..1
    wave_r: np.ndarray = field(default_factory=lambda: np.zeros(N_WAVE, np.float32))
    history: np.ndarray = field(default_factory=lambda: np.zeros((HISTORY, N_BANDS), np.float32))
    bass: float = 0.0
    mid: float = 0.0
    treble: float = 0.0
    level: float = 0.0
    beat: float = 0.0          # 1.0 on a detected beat, decays to 0
    beats: int = 0             # number of beats so far


def band_edges(n_fft, rate=RATE, n_bands=N_BANDS):
    """FFT bin index ranges for log-spaced bands between F_MIN and F_MAX."""
    freqs = np.geomspace(F_MIN, min(F_MAX, rate / 2 - 1), n_bands + 1)
    bins = np.clip(np.round(freqs * n_fft / rate).astype(int), 1, n_fft // 2)
    lo = bins[:-1]
    hi = np.maximum(bins[1:], lo + 1)
    return lo, hi


class Analyzer:
    """FFT + smoothing + band energies + beat detection.

    Tunables (live): fft_size (1024/2048/4096), sensitivity (gain), bass_response.
    """

    def __init__(self, fft_size=2048, sensitivity=1.0, bass_response=1.0):
        self.frame = Frame()
        self.sensitivity = sensitivity
        self.bass_response = bass_response
        self.set_fft_size(fft_size)
        self._gain_ref = 0.05      # adaptive loudness reference (auto-gain)
        self._bass_avg = 0.0
        self._bass_var = 0.0
        self._since_beat = 1.0

    def set_fft_size(self, n):
        n = int(n) if int(n) in (1024, 2048, 4096, 8192) else 2048
        self.fft_size = n
        self._window = np.hanning(n).astype(np.float32)
        self._lo, self._hi = band_edges(n)
        # weights so every band counts its bins once (vectorised band averaging)
        self._cum_idx = np.stack([self._lo, self._hi])

    def _bands(self, mag):
        cs = np.concatenate([[0.0], np.cumsum(mag)])
        return (cs[self._hi] - cs[self._lo]) / (self._hi - self._lo)

    def analyze(self, stereo, dt, playing=True):
        """stereo: (fft_size, 2) float32 ending at the playhead. dt: seconds since last frame."""
        f = self.frame
        dt = float(min(max(dt, 0.0), 0.1))
        if not playing or stereo is None or len(stereo) < self.fft_size:
            decay = np.float32(np.exp(-dt * 6))
            for a in (f.bands, f.bands_l, f.bands_r, f.peaks):
                a *= decay
            f.wave_l *= decay
            f.wave_r *= decay
            f.bass *= float(decay); f.mid *= float(decay); f.treble *= float(decay); f.level *= float(decay)
            f.beat *= float(np.exp(-dt * 5))
            self._push_history()
            return f

        x = stereo[-self.fft_size:]
        mono = x.mean(axis=1)
        spec_m = np.abs(np.fft.rfft(mono * self._window))
        spec_l = np.abs(np.fft.rfft(x[:, 0] * self._window))
        spec_r = np.abs(np.fft.rfft(x[:, 1] * self._window))
        raw = self._bands(spec_m) / (self.fft_size / 4)
        raw_l = self._bands(spec_l) / (self.fft_size / 4)
        raw_r = self._bands(spec_r) / (self.fft_size / 4)

        # Auto-gain: follow the loudness of the track so quiet and loud music both fill the screen.
        loud = float(np.percentile(raw, 95)) if raw.size else 0.0
        self._gain_ref = max(0.004, self._gain_ref + (loud - self._gain_ref) * (0.05 if loud > self._gain_ref else 0.004))
        gain = self.sensitivity / (self._gain_ref * 1.6)

        def shape(v):
            # perceptual curve + gentle tilt so treble isn't always tiny
            tilt = np.linspace(1.0, 2.2, N_BANDS, dtype=np.float32)
            y = np.sqrt(np.clip(v * gain * tilt, 0, None))
            y[: N_BANDS // 6] *= self.bass_response
            return np.clip(y, 0, 1.2).astype(np.float32)

        target, tl, tr = shape(raw), shape(raw_l), shape(raw_r)
        up, down = 1 - np.exp(-dt * 28), 1 - np.exp(-dt * 7)   # fast attack, slower release
        for cur, tgt in ((f.bands, target), (f.bands_l, tl), (f.bands_r, tr)):
            k = np.where(tgt > cur, up, down).astype(np.float32)
            cur += (tgt - cur) * k
        f.peaks = np.maximum(f.peaks - dt * 0.35, f.bands).astype(np.float32)

        # Waveform: last N_WAVE samples, normalised by recent peak.
        w = x[-N_WAVE * 2::2] if len(x) >= N_WAVE * 2 else x[-N_WAVE:]
        peak = max(float(np.abs(w).max()), 0.05)
        f.wave_l = (w[:N_WAVE, 0] / peak).astype(np.float32)
        f.wave_r = (w[:N_WAVE, 1] / peak).astype(np.float32)

        b = f.bands
        nb = N_BANDS
        f.bass = float(b[: nb // 6].mean())
        f.mid = float(b[nb // 6: nb * 3 // 5].mean())
        f.treble = float(b[nb * 3 // 5:].mean())
        f.level = float(min(1.0, np.sqrt(np.mean(mono ** 2)) * 4 / max(self._gain_ref * 20, 0.2) * self.sensitivity))

        # Beat: bass energy jumps above its running average by a margin (with a refractory period).
        e = float(raw[: nb // 6].mean())
        self._bass_avg += (e - self._bass_avg) * min(1.0, dt * 3)
        self._bass_var += ((e - self._bass_avg) ** 2 - self._bass_var) * min(1.0, dt * 3)
        self._since_beat += dt
        thresh = self._bass_avg + max(1.4 * np.sqrt(self._bass_var), self._bass_avg * 0.3) / max(self.sensitivity, 0.3)
        if e > thresh and e > self._gain_ref * 0.4 and self._since_beat > 0.18:
            f.beat = 1.0
            f.beats += 1
            self._since_beat = 0.0
        else:
            f.beat *= float(np.exp(-dt * 5))
        self._push_history()
        return f

    def _push_history(self):
        h = self.frame.history
        h[1:] = h[:-1]
        h[0] = self.frame.bands
