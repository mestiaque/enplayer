"""Asynchronous thumbnail decoding into Gdk.Texture with an LRU cache."""
import logging
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Gdk', '4.0')
from gi.repository import Gdk, GLib

log = logging.getLogger(__name__)


class TextureCache:
    def __init__(self, capacity=600):
        self._cap = capacity
        self._cache = OrderedDict()
        self._waiting = {}  # path -> [callbacks]
        self._pool = ThreadPoolExecutor(max_workers=3, thread_name_prefix='tex')

    def get(self, path):
        tex = self._cache.get(path)
        if tex is not None:
            self._cache.move_to_end(path)
        return tex

    def load(self, path, callback):
        """callback(texture_or_None) is invoked on the GTK thread."""
        tex = self.get(path)
        if tex is not None:
            callback(tex)
            return
        cbs = self._waiting.get(path)
        if cbs is not None:
            cbs.append(callback)
            return
        self._waiting[path] = [callback]
        self._pool.submit(self._decode, path)

    def invalidate(self, path=None):
        if path is None:
            self._cache.clear()
        else:
            self._cache.pop(path, None)

    def _decode(self, path):
        data = None
        try:
            from PIL import Image
            with Image.open(path) as im:
                alpha = im.mode in ('RGBA', 'LA', 'PA') or 'transparency' in im.info
                im = im.convert('RGBA' if alpha else 'RGB')
                data = (im.width, im.height, im.tobytes(), alpha)
        except Exception as e:
            log.debug('Cannot decode %s: %s', path, e)
        GLib.idle_add(self._finish, path, data)

    def _finish(self, path, data):
        tex = None
        if data is not None:
            w, h, raw, alpha = data
            fmt, bpp = (Gdk.MemoryFormat.R8G8B8A8, 4) if alpha else (Gdk.MemoryFormat.R8G8B8, 3)
            tex = Gdk.MemoryTexture.new(w, h, fmt, GLib.Bytes.new(raw), w * bpp)
            self._cache[path] = tex
            while len(self._cache) > self._cap:
                self._cache.popitem(last=False)
        for cb in self._waiting.pop(path, []):
            try:
                cb(tex)
            except Exception:
                log.exception('texture callback failed')
        return False

    def shutdown(self):
        self._pool.shutdown(wait=False, cancel_futures=True)
