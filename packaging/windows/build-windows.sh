#!/bin/bash
# Builds a self-contained Windows bundle of ENPlayer.
#
# Run inside an MSYS2 **UCRT64** shell on Windows (GitHub Actions does this automatically):
#     bash packaging/windows/build-windows.sh
# Output: dist/windows/ENPlayer/   (then compile enplayer.iss with Inno Setup for the installer)
#
# The bundle contains only the files owned by the needed MSYS2 packages and their
# dependencies (python, GTK4, libadwaita, mpv, ffmpeg) plus ENPlayer itself.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PREFIX="${MINGW_PREFIX:-/ucrt64}"
PKG_PREFIX="${MINGW_PACKAGE_PREFIX:-mingw-w64-ucrt-x86_64}"
OUT="$ROOT/dist/windows/ENPlayer"

PKGS=(
  "$PKG_PREFIX-python"
  "$PKG_PREFIX-python-gobject"
  "$PKG_PREFIX-python-pillow"
  "$PKG_PREFIX-python-numpy"
  "$PKG_PREFIX-gtk4"
  "$PKG_PREFIX-libadwaita"
  "$PKG_PREFIX-adwaita-icon-theme"
  "$PKG_PREFIX-librsvg"
  "$PKG_PREFIX-mpv"
  "$PKG_PREFIX-ffmpeg"
)

echo "==> Installing build packages"
# gcc (with binutils: windres, objdump) builds ENPlayer.exe and checks the DLLs; it is not bundled.
pacman -S --needed --noconfirm pacman-contrib rsync "$PKG_PREFIX-python-pip" "$PKG_PREFIX-gcc" "${PKGS[@]}"

echo "==> Resolving dependency closure"
mapfile -t ALL < <(for p in "${PKGS[@]}"; do pactree -u -l "$p"; done | sort -u | grep "^$PKG_PREFIX-")
echo "    ${#ALL[@]} packages"

echo "==> Copying files"
rm -rf "$OUT"
mkdir -p "$OUT"
LIST="$(mktemp)"
pacman -Ql "${ALL[@]}" | awk '{print $2}' | grep "^$PREFIX/" | grep -v '/$' | sed "s|^$PREFIX/||" > "$LIST"
# --ignore-missing-args: some packages list files that are not on disk (e.g. openal hrtf/Default)
rsync -a --ignore-missing-args --files-from="$LIST" "$PREFIX/" "$OUT/"
rm -f "$LIST"

echo "==> Pruning files that are not needed at runtime"
rm -rf "$OUT/include" "$OUT/share/doc" "$OUT/share/man" "$OUT/share/info" "$OUT/share/gtk-doc" \
       "$OUT/share/aclocal" "$OUT/share/pkgconfig" "$OUT/lib/pkgconfig" "$OUT/lib/cmake" \
       "$OUT/share/gettext" "$OUT/share/vala" "$OUT/share/gir-1.0" "$OUT/share/bash-completion" \
       "$OUT/share/installed-tests" "$OUT/libexec/installed-tests"
find "$OUT/lib" -name '*.a' -delete
PYLIB="$(ls -d "$OUT"/lib/python3.* | head -1)"
rm -rf "$PYLIB/test" "$PYLIB/idlelib" "$PYLIB/tkinter" "$PYLIB/turtledemo" "$PYLIB/ensurepip"
# Keep only English + Bengali UI translations of GTK/libadwaita.
if [ -d "$OUT/share/locale" ]; then
  find "$OUT/share/locale" -mindepth 1 -maxdepth 1 -type d ! -name 'en*' ! -name 'bn*' -exec rm -rf {} +
fi

echo "==> Installing python-mpv and ENPlayer"
SITE="$PYLIB/site-packages"
"$PREFIX/bin/python" -m pip install --no-deps --no-compile --target "$SITE" python-mpv \
  || "$PREFIX/bin/python" -m pip install --break-system-packages --no-deps --no-compile --target "$SITE" python-mpv
rsync -a --exclude '__pycache__' --exclude '*.pyc' "$ROOT/neplayer" "$SITE/"
cp "$ROOT/packaging/windows/enplayer.ico" "$OUT/enplayer.ico"
cp "$ROOT/README.md" "$OUT/README.md"

echo "==> ENPlayer.exe (named program for Open with, taskbar and Default apps; see launcher.c)"
VER="$(sed -n "s/^VERSION = '\(.*\)'/\1/p" "$ROOT/neplayer/config.py")"
PYVER="$(basename "$PYLIB")"
BUILD="$(mktemp -d)"
cp "$ROOT/packaging/windows/launcher.c" "$ROOT/packaging/windows/launcher.rc" "$ROOT/packaging/windows/enplayer.ico" "$BUILD/"
printf '#define VER_NUM %s,0\n#define VER_STR "%s"\n' "${VER//./,}" "$VER" > "$BUILD/version.h"
(cd "$BUILD" && windres launcher.rc -O coff -o launcher.res &&
  gcc -O2 -Wall -municode -mwindows -I"$PREFIX/include/$PYVER" launcher.c launcher.res \
      -L"$PREFIX/lib" -l"$PYVER" -o "$OUT/bin/ENPlayer.exe")
rm -rf "$BUILD"

echo "==> Regenerating runtime caches inside the bundle"
glib-compile-schemas "$OUT/share/glib-2.0/schemas"
gtk4-update-icon-cache -q -t -f "$OUT/share/icons/hicolor" || true
gtk4-update-icon-cache -q -t -f "$OUT/share/icons/Adwaita" || true
LOADERS_DIR="$(ls -d "$OUT"/lib/gdk-pixbuf-2.0/2.10.0 2>/dev/null || true)"
if [ -n "$LOADERS_DIR" ]; then
  # Relative module paths keep the bundle relocatable (gdk-pixbuf resolves them
  # against the installation prefix on Windows).
  GDK_PIXBUF_MODULEDIR="$LOADERS_DIR/loaders" gdk-pixbuf-query-loaders \
    | sed "s|$(cygpath -m "$OUT")/||g; s|$OUT/||g" > "$LOADERS_DIR/loaders.cache"
fi

echo "==> Pre-compiling Python bytecode"
"$OUT/bin/python.exe" -m compileall -q "$SITE/neplayer" "$SITE/mpv.py" || true

echo "==> Removing what ENPlayer never loads (see prune_bundle.py)"
OBJDUMP="$PREFIX/bin/objdump" "$PREFIX/bin/python" "$ROOT/packaging/windows/prune_bundle.py" "$OUT"

echo "==> Smoke test (imports with the bundled interpreter only)"
PATH="$OUT/bin:/usr/bin" "$OUT/bin/python.exe" -X faulthandler -u - <<'PY'
def step(name):
    print('  ok:', name, flush=True)
import gi
gi.require_version('Gtk', '4.0'); gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw
step(f'GTK {Gtk.get_major_version()}.{Gtk.get_minor_version()} / Adw {Adw.get_major_version()}.{Adw.get_minor_version()}')
import numpy
step(f'numpy {numpy.__version__}')
from PIL import features
assert features.check('webp'), 'Pillow without WebP'
step('Pillow with WebP')
import mpv
step('python-mpv import')
import locale
locale.setlocale(locale.LC_NUMERIC, 'C')  # libmpv requires it (ENPlayer does the same at start-up)
step('libmpv ' + str(mpv.MPV(vo='null', terminal='no').mpv_version))
import neplayer.main, neplayer.ui.main_window
step('ENPlayer modules')
PY

echo "==> ENPlayer.exe starts Python and ENPlayer (GApplication prints its --help and exits)"
PATH="$OUT/bin:/usr/bin" timeout 120 "$OUT/bin/ENPlayer.exe" --help | tee /dev/stderr | grep -q -- '--version\|Usage' \
  || { echo "ENPlayer.exe did not start"; exit 1; }

du -sh "$OUT"
echo "Bundle ready: $OUT"
