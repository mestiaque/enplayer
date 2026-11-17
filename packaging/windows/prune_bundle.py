"""Removes what ENPlayer never loads from the Windows bundle.

build-windows.sh copies every file of the MSYS2 packages ENPlayer needs and of all their
dependencies. MSYS2 builds FFmpeg and mpv with almost every option, so that closure has
~180 packages: command-line tools (x265.exe, gtk4-demo.exe, sqlite tools, whisper/llama
servers, ...), libraries only those tools use, GPU back-ends of a speech-recognition model
library, Python packages and test suites ENPlayer does not import. The bundle was ~790 MB.

Kept:
  * the programs ENPlayer runs: ENPlayer.exe, python(w).exe, ffmpeg.exe, ffprobe.exe, and
    GLib's helpers (gspawn-*.exe, gdbus.exe);
  * every DLL those programs, the Python extension modules, the GTK/GdkPixbuf/GIO plug-ins,
    the GObject typelibs and libmpv load, followed recursively through their import tables;
  * the Python packages ENPlayer imports (gi, cairo, PIL, numpy, mpv, neplayer).

Usage:  python prune_bundle.py <bundle dir>      (needs objdump on PATH, or OBJDUMP=...)
At the end every remaining .exe/.dll/.pyd is checked: each DLL it imports must be in the
bundle or be part of Windows, otherwise the script fails (so a mistake breaks the build,
not the user's copy).
"""
import glob
import os
import re
import shutil
import subprocess
import sys

KEEP_EXES = {'enplayer.exe', 'python.exe', 'pythonw.exe', 'ffmpeg.exe', 'ffprobe.exe', 'gdbus.exe'}
KEEP_SITE = {'gi', 'cairo', 'PIL', 'numpy', 'numpy.libs', 'mpv.py', 'neplayer', '__pycache__'}
# Typelibs of libraries ENPlayer never imports through GObject introspection (GStreamer, ...).
DROP_TYPELIBS = ('Gst', 'CudaGst', 'Nice', 'DBusGLib', 'Json', 'Vulkan')
# Data and plug-ins only used by tools, Tcl/Tk or FFmpeg filters that ENPlayer does not use
# (lib/mpg123 holds libout123's audio-output plug-ins; FFmpeg only uses the mpg123 decoder).
DROP_DIRS = ('lib/terminfo', 'share/terminfo', 'lib/tcl8*', 'lib/tk8*', 'lib/dde*', 'lib/itcl*',
             'lib/reg1*', 'lib/tdbc*', 'lib/thread2*', 'lib/sqlite3*', 'lib/frei0r-1', 'lib/ladspa',
             'lib/lv2', 'lib/vamp', 'lib/mpg123', 'lib/gstreamer-1.0', 'share/sqlite', 'share/libmysofa',
             'share/gst-plugins-base', 'share/gstreamer-1.0')


def size(path):
    total = 0
    for root, _dirs, files in os.walk(path):
        for f in files:
            p = os.path.join(root, f)
            if not os.path.islink(p):
                total += os.path.getsize(p)
    return total


def rm(path):
    if os.path.isdir(path) and not os.path.islink(path):
        shutil.rmtree(path)
    elif os.path.lexists(path):
        os.remove(path)


def imports(objdump, path):
    out = subprocess.run([objdump, '-p', path], capture_output=True, text=True, check=True).stdout
    return [m.lower() for m in re.findall(r'DLL Name: (\S+)', out)]


def main(bundle):
    objdump = os.environ.get('OBJDUMP') or shutil.which('objdump')
    if not objdump:
        sys.exit('objdump not found (install binutils or set OBJDUMP)')
    os.chdir(bundle)
    before = size('.')
    pylib = glob.glob('lib/python3.*')[0]
    site = os.path.join(pylib, 'site-packages')

    # 1. Python: only the packages ENPlayer imports; no tests or optimised-bytecode copies.
    for name in os.listdir(site):
        if name in KEEP_SITE or (name.endswith('.dist-info') and
                                 name.split('-')[0].lower() in ('numpy', 'pillow', 'pygobject', 'pycairo', 'python_mpv')):
            continue
        rm(os.path.join(site, name))
    for path in glob.glob(os.path.join(site, 'numpy', '**', 'tests'), recursive=True):
        rm(path)
    for sub in ('f2py', '_pyinstaller', '_core/include', 'random/_examples', 'random/lib', 'doc'):
        rm(os.path.join(site, 'numpy', sub))
    for path in glob.glob(os.path.join(site, 'numpy', '**', '*.pyi'), recursive=True):
        rm(path)
    for path in glob.glob(os.path.join(pylib, '**', '*.opt-[12].pyc'), recursive=True):
        rm(path)
    rm(os.path.join(pylib, 'pydoc_data'))
    for path in glob.glob(os.path.join(pylib, 'lib-dynload', '_tkinter*.pyd')):  # tkinter is not bundled
        rm(path)

    # 2. Data and plug-ins of features ENPlayer does not use.
    for pattern in DROP_DIRS:
        for d in glob.glob(pattern):
            rm(d)
    for t in glob.glob('lib/girepository-1.0/*.typelib'):
        if os.path.basename(t).startswith(DROP_TYPELIBS):
            rm(t)

    # 3. Programs: only the ones ENPlayer starts.
    for exe in glob.glob('bin/*.exe'):
        base = os.path.basename(exe).lower()
        if base not in KEEP_EXES and not base.startswith('gspawn-'):
            rm(exe)

    # 4. DLLs: keep what is reachable from the programs, Python modules, plug-ins, typelibs.
    bindlls = {f.lower(): f for f in os.listdir('bin') if f.lower().endswith('.dll')}
    roots = glob.glob('bin/*.exe') + ['bin/' + bindlls['libmpv-2.dll']]
    roots += glob.glob(os.path.join(pylib, '**', '*.pyd'), recursive=True)
    roots += [p for p in glob.glob('lib/**/*.dll', recursive=True)]  # pixbuf loaders, GIO modules, ...
    for t in glob.glob('lib/girepository-1.0/*.typelib'):
        for m in re.findall(rb'([\w.+-]+\.dll)', open(t, 'rb').read()):
            name = m.decode().lower()
            if name in bindlls:
                roots.append('bin/' + bindlls[name])
    needed, todo = set(), list(roots)
    while todo:
        p = todo.pop()
        if p in needed:
            continue
        needed.add(p)
        todo += ['bin/' + bindlls[d] for d in imports(objdump, p) if d in bindlls]
    kept = {os.path.basename(p).lower() for p in needed if p.startswith('bin/')}
    removed = [f for low, f in bindlls.items() if low not in kept]
    for f in removed:
        rm(os.path.join('bin', f))

    # 5. Check: every import of every remaining binary resolves.
    present = {f.lower() for f in os.listdir('bin')}
    system = os.path.join(os.environ.get('SystemRoot', r'C:\Windows'), 'System32')
    missing, external = [], set()
    for p in glob.glob('bin/*.exe') + glob.glob('bin/*.dll') + glob.glob('lib/**/*.dll', recursive=True) \
            + glob.glob(os.path.join(pylib, '**', '*.pyd'), recursive=True):
        for d in imports(objdump, p):
            if d in present or d.startswith(('api-ms-', 'ext-ms-')):
                continue
            if re.match(r'(vcruntime|msvcp|concrt|vcomp|ucrtbased)', d):
                missing.append(f'{p} -> {d} (Visual C++ runtime: not part of a fresh Windows)')
                continue
            if os.path.isdir(system):
                if not os.path.exists(os.path.join(system, d)):
                    missing.append(f'{p} -> {d}')
            external.add(d)
    print(f'Removed {len(removed)} unused DLLs; bundle {before / 2**20:.0f} MB -> {size(".") / 2**20:.0f} MB')
    print('Windows DLLs used:', ' '.join(sorted(external)))
    if missing:
        sys.exit('Imports that are neither bundled nor part of Windows:\n  ' + '\n  '.join(missing))


if __name__ == '__main__':
    main(sys.argv[1])
