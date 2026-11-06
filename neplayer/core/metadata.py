"""Metadata extraction via ffprobe. Never call from the GTK main thread."""
import json
import logging
import os
import shutil
import subprocess
from pathlib import Path
from neplayer.core.paths import norm_path

log = logging.getLogger(__name__)

FFPROBE = shutil.which('ffprobe')
FFMPEG = shutil.which('ffmpeg')

# Never flash a console window for each ffprobe/ffmpeg call on Windows.
NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)


class MetadataError(Exception):
    pass


def _fps(stream):
    for key in ('avg_frame_rate', 'r_frame_rate'):
        val = stream.get(key) or ''
        if '/' in val:
            num, den = val.split('/', 1)
            try:
                if float(den) > 0:
                    f = float(num) / float(den)
                    if 0 < f < 1000:
                        return round(f, 3)
            except ValueError:
                pass
    return 0.0


def nice_title(path):
    stem = Path(path).stem
    return stem.replace('_', ' ').replace('.', ' ').strip() or Path(path).name


def probe(path, timeout=30):
    """Return metadata dict for a video file. Raises MetadataError on failure."""
    if FFPROBE is None:
        raise MetadataError('ffprobe is not installed')
    st = os.stat(path)
    meta = {
        'file_path': norm_path(path),
        'title': nice_title(path),
        'file_size': st.st_size,
        'file_mtime': st.st_mtime,
    }
    try:
        out = subprocess.run(
            [FFPROBE, '-v', 'error', '-print_format', 'json', '-show_format', '-show_streams',
             str(path)],
            capture_output=True, timeout=timeout, check=False, creationflags=NO_WINDOW)
    except subprocess.TimeoutExpired as e:
        raise MetadataError('ffprobe timed out') from e
    if out.returncode != 0:
        msg = out.stderr.decode(errors='replace').strip().splitlines()
        raise MetadataError(msg[-1] if msg else f'ffprobe exited with {out.returncode}')
    try:
        data = json.loads(out.stdout or b'{}')
    except ValueError as e:
        raise MetadataError('ffprobe returned invalid output') from e

    fmt = data.get('format', {})
    streams = data.get('streams', [])
    video = next((s for s in streams if s.get('codec_type') == 'video'
                  and not s.get('disposition', {}).get('attached_pic')), None)
    audio = [s for s in streams if s.get('codec_type') == 'audio']
    if video is None:
        if not audio:
            raise MetadataError('No video or audio stream found')
        return _audio_meta(meta, fmt, streams, audio)
    subs = [s for s in streams if s.get('codec_type') == 'subtitle']

    duration = 0.0
    for candidate in (fmt.get('duration'), video.get('duration')):
        try:
            duration = float(candidate)
            break
        except (TypeError, ValueError):
            continue

    width, height = int(video.get('width') or 0), int(video.get('height') or 0)
    rotation = 0
    for sd in video.get('side_data_list', []) or []:
        if 'rotation' in sd:
            rotation = abs(int(sd['rotation']))
    rotate_tag = (video.get('tags') or {}).get('rotate')
    if rotate_tag:
        rotation = abs(int(rotate_tag))
    if rotation in (90, 270):
        width, height = height, width

    def stream_info(s):
        tags = s.get('tags') or {}
        return {'index': s.get('index'), 'codec': s.get('codec_name'),
                'language': tags.get('language'), 'title': tags.get('title'),
                'channels': s.get('channels')}

    meta.update({
        'duration': duration,
        'width': width,
        'height': height,
        'fps': _fps(video),
        'video_codec': video.get('codec_name'),
        'audio_codec': audio[0].get('codec_name') if audio else None,
        'bitrate': int(fmt.get('bit_rate') or 0),
        'container': fmt.get('format_name'),
        'audio_streams': [stream_info(s) for s in audio],
        'subtitle_streams': [stream_info(s) for s in subs],
    })
    return meta


def _tags(*sources):
    """Merge container and stream tags, case-insensitively (ID3, Vorbis, MP4 keys)."""
    out = {}
    for src in sources:
        for k, v in (src.get('tags') or {}).items():
            out.setdefault(k.lower(), str(v).strip())
    return out


def _int_prefix(text):
    """'3/12' -> 3, '2019-05-01' -> 2019."""
    digits = ''
    for ch in str(text or '').strip():
        if not ch.isdigit():
            break
        digits += ch
    return int(digits) if digits else 0


def _audio_meta(meta, fmt, streams, audio):
    tags = _tags(fmt, *audio)
    duration = 0.0
    for candidate in (fmt.get('duration'), audio[0].get('duration')):
        try:
            duration = float(candidate)
            break
        except (TypeError, ValueError):
            continue
    a = audio[0]
    meta.update({
        'media_kind': 'audio',
        'title': tags.get('title') or meta['title'],
        'artist': tags.get('artist') or tags.get('album_artist') or tags.get('albumartist'),
        'album': tags.get('album'),
        'album_artist': tags.get('album_artist') or tags.get('albumartist'),
        'track': _int_prefix(tags.get('track') or tags.get('tracknumber')),
        'year': _int_prefix(tags.get('date') or tags.get('year') or tags.get('originaldate')),
        'genre': tags.get('genre'),
        'duration': duration,
        'width': 0,
        'height': 0,
        'fps': 0,
        'video_codec': None,
        'audio_codec': a.get('codec_name'),
        'bitrate': int(fmt.get('bit_rate') or a.get('bit_rate') or 0),
        'container': fmt.get('format_name'),
        'audio_streams': [{'index': a.get('index'), 'codec': a.get('codec_name'),
                           'language': (a.get('tags') or {}).get('language'), 'title': None,
                           'channels': a.get('channels'), 'sample_rate': a.get('sample_rate')}],
        'subtitle_streams': [],
        'has_cover': any(s.get('disposition', {}).get('attached_pic') for s in streams),
    })
    return meta


def fallback_meta(path, error):
    """Minimal record for files ffprobe can't read, so they still show up."""
    st = os.stat(path)
    return {'file_path': norm_path(path), 'title': nice_title(path), 'file_size': st.st_size,
            'file_mtime': st.st_mtime, 'error': str(error)[:300]}
