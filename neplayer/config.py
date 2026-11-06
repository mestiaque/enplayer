"""Paths and static configuration."""
import os
import sys
from pathlib import Path

IS_WINDOWS = sys.platform == 'win32'

APP_ID = 'io.github.enplayer.ENPlayer'
APP_NAME = 'ENPlayer'
DEVELOPER = 'Estiaque'
DEVELOPER_EMAIL = 'natoreit20@gmail.com'
COPYRIGHT_YEAR = '2026'
VERSION = '1.4.1'

if IS_WINDOWS:
    _local = Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData' / 'Local'))
    _default_data = _local / 'NEPLAYER'
    _default_cache = _local / 'NEPLAYER' / 'Cache'
else:
    _default_data = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local' / 'share')) / 'neplayer'
    _default_cache = Path(os.environ.get('XDG_CACHE_HOME', Path.home() / '.cache')) / 'neplayer'

DATA_DIR = Path(os.environ.get('NEPLAYER_DATA_DIR', _default_data))
DEFAULT_CACHE_DIR = Path(os.environ.get('NEPLAYER_CACHE_DIR', _default_cache))
DB_PATH = DATA_DIR / 'neplayer.db'
LOG_PATH = DATA_DIR / 'neplayer.log'

RESOURCES_DIR = Path(__file__).resolve().parent / 'resources'

DEFAULT_EXTENSIONS = ('mp4', 'mkv', 'avi', 'mov', 'wmv', 'webm', 'flv', 'm4v',
                      'mpeg', 'ts', 'mpg', '3gp')

# Audio formats ENPlayer plays as music (mpv decodes all of them).
AUDIO_EXTENSIONS = ('mp3', 'flac', 'm4a', 'aac', 'ogg', 'oga', 'opus', 'wav', 'wma', 'aiff', 'aif',
                    'ape', 'wv', 'alac', 'mka', 'dsf')

THUMB_WIDTH = 480
THUMB_HEIGHT = 270

DEFAULT_SETTINGS = {
    # updates (asks GitHub for the latest release; no other network access)
    'check_updates': True,
    'last_update_check': 0,
    # library
    'scan_on_startup': True,
    'auto_monitor': True,
    'include_subdirs': True,
    'ignore_hidden': True,
    'extensions': ','.join(DEFAULT_EXTENSIONS),
    'music_enabled': True,
    'audio_extensions': ','.join(AUDIO_EXTENSIONS),
    'shuffle': False,
    'repeat': 'off',  # off | all | one
    # preview
    'preview_enabled': True,
    'preview_delay_ms': 700,
    'preview_duration_s': 8,
    'preview_volume': 0,
    'preview_max_height': 360,
    # appearance
    'theme': 'dark',  # dark | light | glass
    'accent': '#3b82f6',
    'dark_theme': True,  # legacy; migrated to 'theme'
    'grid_density': 'medium',  # small | medium | large
    'sidebar_visible': True,
    # playback
    'resume_playback': True,
    'default_volume': 80,
    'playback_speed': 1.0,
    'subtitle_lang': '',
    'audio_lang': '',
    'hwdec': 'auto-safe',  # auto-safe | no | vaapi | d3d11va
    'autoplay_next': True,
    # storage
    'cache_dir': str(DEFAULT_CACHE_DIR),
    'cache_limit_mb': 1024,
    # ui state
    'first_run_done': False,
    'startup_view': 'home',  # home | all | continue | favorites
    'keep_history': True,
    'sort': 'recent',
    'volume': 80,
}

# Same accent palette as Lumen.
ACCENTS = ['#3b82f6', '#6366f1', '#8b5cf6', '#ec4899', '#ef4444', '#f97316', '#eab308', '#22c55e', '#14b8a6', '#06b6d4']

# Audio visualizer (ENPlayer music player).
VIZ_DEFAULTS = {
    'viz_enabled': True, 'viz_preset': 'circular-spectrum', 'viz_speed': 1.0, 'viz_sensitivity': 1.0,
    'viz_bass': 1.0, 'viz_density': 0.6, 'viz_glow': 1.0, 'viz_brightness': 1.0, 'viz_theme': 'accent',
    'viz_background': 'cover', 'viz_fft': 2048, 'viz_quality': 'high', 'viz_reduced_motion': False,
}
DEFAULT_SETTINGS.update(VIZ_DEFAULTS)

DENSITY_WIDTH = {'small': 200, 'medium': 260, 'large': 340}
