"""Typed settings persisted in the SQLite settings table."""
import gi

gi.require_version('Gtk', '4.0')
from gi.repository import GObject

from neplayer.config import DEFAULT_SETTINGS

THEMES = ('dark', 'light', 'glass')


class Settings(GObject.Object):
    __gsignals__ = {
        'changed': (GObject.SignalFlags.RUN_FIRST, None, (str,)),
    }

    def __init__(self, db):
        super().__init__()
        self._db = db
        self._values = dict(DEFAULT_SETTINGS)
        stored = db.get_all_settings()
        for k, v in stored.items():
            if k in DEFAULT_SETTINGS and type(v) is type(DEFAULT_SETTINGS[k]):
                self._values[k] = v
            elif k in DEFAULT_SETTINGS and isinstance(DEFAULT_SETTINGS[k], float) and isinstance(v, int):
                self._values[k] = float(v)
        # Migrate the old on/off "Dark theme" switch to the theme choice.
        if 'theme' not in stored and stored.get('dark_theme') is False:
            self._values['theme'] = 'light'
        if self._values['theme'] not in THEMES:
            self._values['theme'] = 'dark'

    def __getitem__(self, key):
        return self._values[key]

    def get(self, key, default=None):
        return self._values.get(key, default)

    def set(self, key, value):
        if self._values.get(key) == value:
            return
        self._values[key] = value
        self._db.set_setting(key, value)
        self.emit('changed', key)

    def reset(self, key):
        self.set(key, DEFAULT_SETTINGS[key])

    @staticmethod
    def _split(text):
        return {e.strip().lower().lstrip('.') for e in text.split(',') if e.strip()}

    @property
    def video_extensions(self):
        return self._split(self['extensions'])

    @property
    def audio_extensions(self):
        return self._split(self['audio_extensions']) if self['music_enabled'] else set()

    @property
    def extensions(self):
        """Everything the library scans: videos, plus music when enabled."""
        return self.video_extensions | self.audio_extensions
