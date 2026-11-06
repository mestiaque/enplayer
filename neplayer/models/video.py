"""List-model item and display helpers for videos."""
import os

import gi

gi.require_version('Gtk', '4.0')
from gi.repository import GObject


class VideoItem(GObject.Object):
    __gtype_name__ = 'NeplayerVideoItem'

    def __init__(self, data):
        super().__init__()
        self.data = data

    @property
    def id(self):
        return self.data['id']

    def __getitem__(self, key):
        return self.data[key]

    def get(self, key, default=None):
        return self.data.get(key, default)


def format_duration(seconds):
    seconds = int(seconds or 0)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f'{h}:{m:02d}:{s:02d}' if h else f'{m}:{s:02d}'


def format_size(n):
    n = float(n or 0)
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if n < 1024 or unit == 'TB':
            return f'{n:.0f} {unit}' if unit in ('B', 'KB') else f'{n:.1f} {unit}'
        n /= 1024
    return ''


def resolution_label(width, height):
    if not height:
        return ''
    short = min(width or height, height)
    if height >= 2000 or width >= 3800:
        return '4K'
    if height >= 1400 or width >= 2500:
        return '1440p'
    if height >= 1000 or width >= 1900:
        return '1080p'
    if height >= 700 or width >= 1260:
        return '720p'
    return f'{short}p'


def file_format(path):
    return os.path.splitext(path)[1].lstrip('.').upper()
