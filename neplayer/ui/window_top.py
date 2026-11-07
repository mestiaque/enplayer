"""Keep a GTK 4 window above other windows.

GTK 4 has no keep-above API, so this talks to the platform directly: Win32 on
Windows and an EWMH client message on X11. Wayland has no such protocol, so a
marker file makes the next start use XWayland instead (see main.py).
"""
import ctypes
import logging
import sys

log = logging.getLogger('neplayer.window_top')

_NET_WM_STATE_REMOVE = 0
_NET_WM_STATE_ADD = 1
_CLIENT_MESSAGE = 33
_SUBSTRUCTURE_MASK = (1 << 19) | (1 << 20)


class _ClientMessage(ctypes.Structure):
    _fields_ = [('type', ctypes.c_int), ('serial', ctypes.c_ulong), ('send_event', ctypes.c_int),
                ('display', ctypes.c_void_p), ('window', ctypes.c_ulong),
                ('message_type', ctypes.c_ulong), ('format', ctypes.c_int),
                ('data', ctypes.c_long * 5)]


class _XEvent(ctypes.Union):
    _fields_ = [('client', _ClientMessage), ('pad', ctypes.c_long * 24)]


def _set_x11(xid, on):
    x = ctypes.CDLL('libX11.so.6')
    x.XOpenDisplay.restype = ctypes.c_void_p
    x.XOpenDisplay.argtypes = [ctypes.c_char_p]
    x.XDefaultRootWindow.restype = ctypes.c_ulong
    x.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
    x.XInternAtom.restype = ctypes.c_ulong
    x.XInternAtom.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
    x.XSendEvent.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_long,
                             ctypes.POINTER(_XEvent)]
    x.XFlush.argtypes = [ctypes.c_void_p]
    x.XCloseDisplay.argtypes = [ctypes.c_void_p]
    display = x.XOpenDisplay(None)
    if not display:
        return False
    try:
        ev = _XEvent()
        ev.client.type = _CLIENT_MESSAGE
        ev.client.window = xid
        ev.client.message_type = x.XInternAtom(display, b'_NET_WM_STATE', 0)
        ev.client.format = 32
        ev.client.data[0] = _NET_WM_STATE_ADD if on else _NET_WM_STATE_REMOVE
        ev.client.data[1] = x.XInternAtom(display, b'_NET_WM_STATE_ABOVE', 0)
        ev.client.data[3] = 1  # source: normal application
        root = x.XDefaultRootWindow(display)
        ok = x.XSendEvent(display, root, 0, _SUBSTRUCTURE_MASK, ctypes.byref(ev))
        x.XFlush(display)
        return bool(ok)
    finally:
        x.XCloseDisplay(display)


def _set_windows(window, on):
    import gi
    gi.require_version('GdkWin32', '4.0')
    from gi.repository import GdkWin32
    hwnd = GdkWin32.Win32Surface.get_handle(window.get_surface())
    user32 = ctypes.windll.user32
    user32.SetWindowPos.argtypes = [ctypes.c_void_p, ctypes.c_void_p] + [ctypes.c_int] * 4 + [ctypes.c_uint]
    insert_after = ctypes.c_void_p(-1 if on else -2)  # HWND_TOPMOST / HWND_NOTOPMOST
    no_move_size_activate = 0x0002 | 0x0001 | 0x0010
    return bool(user32.SetWindowPos(hwnd, insert_after, 0, 0, 0, 0, no_move_size_activate))


def set_always_on_top(window, on):
    """Apply the state to a mapped window. Returns False where it is not possible."""
    surface = window.get_surface()
    if surface is None:
        return False
    try:
        if sys.platform == 'win32':
            return _set_windows(window, on)
        if 'X11' in surface.__gtype__.name:
            import gi
            gi.require_version('GdkX11', '4.0')
            from gi.repository import GdkX11
            return _set_x11(GdkX11.X11Surface.get_xid(surface), on)
    except (AttributeError, ImportError, OSError, ValueError):
        log.exception('Could not change always-on-top')
    return False


def needs_xwayland(window):
    """True when the window runs on native Wayland, where the state cannot be set."""
    surface = window.get_surface()
    return sys.platform != 'win32' and surface is not None and 'Wayland' in surface.__gtype__.name
