"""Entry point: `python3 -m neplayer.main [FILE|FOLDER...]`."""
import locale
import logging
import logging.handlers
import os
import sys


def _setup_logging():
    from neplayer.config import DATA_DIR, LOG_PATH
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    level = logging.DEBUG if os.environ.get('NEPLAYER_DEBUG') else logging.INFO
    handlers = [logging.handlers.RotatingFileHandler(LOG_PATH, maxBytes=2_000_000, backupCount=2)]
    if sys.stderr is not None and sys.stderr.isatty() or os.environ.get('NEPLAYER_DEBUG'):
        handlers.append(logging.StreamHandler())
    logging.basicConfig(level=level, handlers=handlers,
                        format='%(asctime)s %(levelname)s %(name)s: %(message)s')

    # Uncaught exceptions (including ones inside GTK callbacks) go to the log
    # file too, so problems are diagnosable when started from the app menu.
    def hook(exc_type, exc, tb):
        logging.getLogger('neplayer').error('Uncaught exception', exc_info=(exc_type, exc, tb))
        sys.__excepthook__(exc_type, exc, tb)
    sys.excepthook = hook


def _check_deps():
    missing = []
    try:
        import gi
        gi.require_version('Gtk', '4.0')
        gi.require_version('Adw', '1')
    except (ImportError, ValueError):
        missing.append('GTK4 / libadwaita bindings (sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1)')
    try:
        import mpv  # noqa: F401
    except (ImportError, OSError) as e:
        missing.append(f'libmpv / python-mpv ({e}) — sudo apt install libmpv1 && pip install python-mpv')
    try:
        import PIL  # noqa: F401
    except ImportError:
        missing.append('Pillow (sudo apt install python3-pil)')
    try:
        import numpy  # noqa: F401  (audio visualizer)
    except ImportError:
        missing.append('NumPy (sudo apt install python3-numpy)')
    if missing and sys.platform == 'win32':
        _windows_error('ENPlayer could not start because files are missing:\n\n' + '\n'.join(missing) +
                       '\n\nPlease reinstall ENPlayer.')
    if missing:
        sys.stderr.write('ENPlayer is missing dependencies:\n  ' + '\n  '.join(missing) + '\n')
        sys.exit(1)


def _prepare_windows():
    """Make bundled DLLs (libmpv, GTK) and ffmpeg.exe findable, set taskbar identity."""
    if sys.platform != 'win32':
        return
    bindir = os.path.dirname(os.path.abspath(sys.executable))
    os.environ['PATH'] = bindir + os.pathsep + os.environ.get('PATH', '')
    try:
        os.add_dll_directory(bindir)
    except (AttributeError, OSError):
        pass
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('ENPlayer.ENPlayer')
    except Exception:
        pass


def main(argv=None):
    _prepare_windows()
    from neplayer.core import legacy
    carried = legacy.migrate()
    _setup_logging()
    if carried:
        logging.getLogger('neplayer').info(carried)
    _check_deps()
    from gi.repository import GLib
    GLib.set_prgname('enplayer')  # X11 WM_CLASS → matches StartupWMClass in the .desktop file
    from neplayer.app import NeplayerApp
    app = NeplayerApp()
    rc = app.run(argv if argv is not None else sys.argv)
    # mpv requires LC_NUMERIC=C; restore in case anything reset it.
    locale.setlocale(locale.LC_NUMERIC, 'C')
    return rc


def _windows_error(text):
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, text, 'ENPlayer', 0x10)
    except Exception:
        pass


if __name__ == '__main__':
    sys.exit(main())
