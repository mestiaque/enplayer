"""Gtk.GLArea that renders an mpv core through the libmpv OpenGL render API.

This is the only reliable way to embed mpv in GTK4 (GTK4 has no foreign
window embedding). The widget owns one mpv core for its whole lifetime and
creates/frees the render context on realize/unrealize, so it can be moved
between parents (the hover preview is re-parented into whichever card is
being hovered).
"""
import ctypes
import locale
import logging
import sys

import gi

gi.require_version('Gtk', '4.0')
from gi.repository import GLib, GObject, Gtk

import mpv

log = logging.getLogger(__name__)

_GL_FRAMEBUFFER_BINDING = 0x8CA6


def _load(name):
    try:
        return ctypes.CDLL(name)
    except OSError:
        return None


_IS_WIN = sys.platform == 'win32'
_egl = _load('libEGL.dll' if _IS_WIN else 'libEGL.so.1')
_glx = None if _IS_WIN else _load('libGL.so.1')
_wgl = _load('opengl32.dll') if _IS_WIN else None
if _wgl is not None:
    _wgl.wglGetProcAddress.restype = ctypes.c_void_p
    _wgl.wglGetProcAddress.argtypes = [ctypes.c_char_p]
    _wgl.wglGetCurrentContext.restype = ctypes.c_void_p
    _k32 = ctypes.WinDLL('kernel32')
    _k32.GetProcAddress.restype = ctypes.c_void_p
    _k32.GetProcAddress.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
if _egl is not None:
    _egl.eglGetProcAddress.restype = ctypes.c_void_p
    _egl.eglGetProcAddress.argtypes = [ctypes.c_char_p]
    _egl.eglGetCurrentContext.restype = ctypes.c_void_p
if _glx is not None:
    _glx.glXGetProcAddressARB.restype = ctypes.c_void_p
    _glx.glXGetProcAddressARB.argtypes = [ctypes.c_char_p]


def _get_proc_address(_ctx, name):
    """Resolve GL symbols for whatever backend GDK picked (EGL, GLX or WGL)."""
    addr = None
    if _wgl is not None and _wgl.wglGetCurrentContext():
        addr = _wgl.wglGetProcAddress(name)
        # wglGetProcAddress returns small sentinel values for GL 1.1 core
        # functions, which must come straight from opengl32.dll instead.
        if addr in (None, 0, 1, 2, 3) or addr == ctypes.c_void_p(-1).value:
            addr = _k32.GetProcAddress(ctypes.c_void_p(_wgl._handle), name)
        return addr or 0
    if _egl is not None and _egl.eglGetCurrentContext():
        addr = _egl.eglGetProcAddress(name)
    if not addr and _glx is not None:
        addr = _glx.glXGetProcAddressARB(name)
    return addr or 0


_proc_fn = mpv.MpvGlGetProcAddressFn(_get_proc_address)
_glGetIntegerv = None


def _current_fbo():
    global _glGetIntegerv
    if _glGetIntegerv is None:
        addr = _get_proc_address(None, b'glGetIntegerv')
        if not addr:
            return 0
        _glGetIntegerv = ctypes.CFUNCTYPE(None, ctypes.c_uint, ctypes.POINTER(ctypes.c_int))(addr)
    val = ctypes.c_int(0)
    _glGetIntegerv(_GL_FRAMEBUFFER_BINDING, ctypes.byref(val))
    return val.value


def create_mpv(**opts):
    # mpv refuses to start unless LC_NUMERIC is "C"; GTK resets the locale
    # to the user's (e.g. bn_BD) during init, so force it here every time.
    locale.setlocale(locale.LC_NUMERIC, 'C')
    base = dict(vo='libmpv', keep_open='no', idle='yes', osc='no',
                input_default_bindings='no', input_vo_keyboard='no',
                terminal='no', hwdec='auto-safe')
    base.update(opts)
    return mpv.MPV(**base)


class MpvGLArea(Gtk.GLArea):
    __gtype_name__ = 'NeplayerMpvGLArea'
    __gsignals__ = {
        # Emitted (on the GTK thread) once the render context is ready.
        'ready': (GObject.SignalFlags.RUN_FIRST, None, ()),
        # Emitted after the first frame of a newly loaded file is drawn.
        'first-frame': (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    def __init__(self, **mpv_opts):
        super().__init__()
        self.set_auto_render(False)
        self.set_has_depth_buffer(False)
        self.set_has_stencil_buffer(False)
        self.set_hexpand(True)
        self.set_vexpand(True)
        self.mpv = create_mpv(**mpv_opts)
        self._ctx = None
        self._render_pending = False
        self._want_first_frame = False
        self._destroyed = False
        self.connect('realize', self._on_realize)
        self.connect('unrealize', self._on_unrealize)
        self.connect('render', self._on_render)

    @property
    def is_ready(self):
        return self._ctx is not None

    def expect_first_frame(self):
        self._want_first_frame = True

    # --- lifecycle -------------------------------------------------------
    def _on_realize(self, _area):
        self.make_current()
        if self.get_error() is not None:
            log.error('GL context error: %s', self.get_error())
            return
        try:
            self._ctx = mpv.MpvRenderContext(
                self.mpv, 'opengl',
                opengl_init_params={'get_proc_address': _proc_fn})
            self._ctx.update_cb = self._on_mpv_update
        except Exception:
            log.exception('Failed to create mpv render context')
            self._ctx = None
            return
        self.emit('ready')

    def _on_unrealize(self, _area):
        if self._ctx is not None:
            self.make_current()
            try:
                self._ctx.free()
            except Exception:
                log.exception('Failed to free mpv render context')
            self._ctx = None

    def _on_mpv_update(self):
        # Called from an mpv thread: only schedule work on the GTK thread.
        if not self._render_pending and not self._destroyed:
            self._render_pending = True
            GLib.idle_add(self._queue_render_idle, priority=GLib.PRIORITY_HIGH)

    def _queue_render_idle(self):
        self._render_pending = False
        if self._ctx is not None:
            self.queue_render()
        return False

    def _on_render(self, _area, _gl_ctx):
        if self._ctx is None:
            return True
        scale = self.get_scale_factor()
        w = self.get_width() * scale
        h = self.get_height() * scale
        if w <= 0 or h <= 0:
            return True
        try:
            new_frame = self._ctx.update()
            self._ctx.render(flip_y=True,
                             opengl_fbo={'w': w, 'h': h, 'fbo': _current_fbo()})
            if new_frame and self._want_first_frame and self.mpv.vo_configured:
                self._want_first_frame = False
                GLib.idle_add(self._emit_first_frame)
        except Exception:
            log.exception('mpv render failed')
        return True

    def _emit_first_frame(self):
        if not self._destroyed:
            self.emit('first-frame')
        return False

    def shutdown(self):
        """Terminate the mpv core. Call once when the widget is no longer needed."""
        if self._destroyed:
            return
        self._destroyed = True
        if self._ctx is not None and self.get_realized():
            self._on_unrealize(self)
        try:
            self.mpv.terminate()
        except Exception:
            log.exception('mpv terminate failed')
