#!/bin/bash
# Build an installable .deb:  bash packaging/build-deb.sh   ->  dist/enplayer_<ver>_all.deb
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VERSION="$(python3 -c "import sys; sys.path.insert(0, '$ROOT'); from neplayer.config import VERSION; print(VERSION)")"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
PKG="$STAGE/enplayer_${VERSION}_all"

install -d "$PKG/DEBIAN" "$PKG/usr/lib/enplayer" "$PKG/usr/bin" \
           "$PKG/usr/share/applications" "$PKG/usr/share/icons/hicolor/scalable/apps" "$PKG/usr/share/icons/hicolor/512x512/apps" \
           "$PKG/usr/share/metainfo" "$PKG/usr/share/doc/enplayer"

# application code (no tests / caches)
rsync -a --exclude '__pycache__' --exclude '*.pyc' "$ROOT/neplayer" "$PKG/usr/lib/enplayer/"

# vendor python-mpv (single file, GPLv2+/LGPLv2.1+) — Ubuntu's python3-mpv is too old
MPV_PY="$(python3 -c 'import mpv; print(mpv.__file__)' 2>/dev/null || true)"
if [ -z "$MPV_PY" ]; then
  echo "python-mpv not found: pip install --user python-mpv" >&2; exit 1
fi
install -m644 "$MPV_PY" "$PKG/usr/lib/enplayer/mpv.py"

cat > "$PKG/usr/bin/enplayer" <<'SH'
#!/bin/sh
for v in GDK_PIXBUF_MODULE_FILE GDK_PIXBUF_MODULEDIR GIO_MODULE_DIR GSETTINGS_SCHEMA_DIR GTK_EXE_PREFIX GTK_IM_MODULE_FILE GTK_PATH LOCPATH; do
  eval "val=\${$v:-}"; case "$val" in *snap*) unset "$v" ;; esac
done
export PYTHONPATH="/usr/lib/enplayer${PYTHONPATH:+:$PYTHONPATH}"
exec python3 -m neplayer.main "$@"
SH
chmod 755 "$PKG/usr/bin/enplayer"

install -m644 "$ROOT/packaging/io.github.enplayer.ENPlayer.desktop" "$PKG/usr/share/applications/"
install -m644 "$ROOT/packaging/io.github.enplayer.ENPlayer.svg" "$PKG/usr/share/icons/hicolor/scalable/apps/"
install -m644 "$ROOT/neplayer/resources/icons/enplayer-512.png" "$PKG/usr/share/icons/hicolor/512x512/apps/io.github.enplayer.ENPlayer.png"
install -m644 "$ROOT/packaging/io.github.enplayer.ENPlayer.metainfo.xml" "$PKG/usr/share/metainfo/"
install -m644 "$ROOT/README.md" "$PKG/usr/share/doc/enplayer/README.md"

SIZE="$(du -sk "$PKG/usr" | cut -f1)"
cat > "$PKG/DEBIAN/control" <<CTRL
Package: enplayer
Version: $VERSION
Section: video
Priority: optional
Architecture: all
Installed-Size: $SIZE
Depends: python3 (>= 3.10), python3-gi, gir1.2-gtk-4.0, gir1.2-adw-1, libmpv1 | libmpv2, ffmpeg, python3-pil, python3-numpy, libgl1, libegl1
Recommends: va-driver-all
Conflicts: frameflow, neplayer
Replaces: frameflow, neplayer
Provides: frameflow, neplayer
Maintainer: Estiaque <natoreit20@gmail.com>
Description: Video and music player with live hover previews
 ENPlayer scans your folders, builds a thumbnail library and plays real
 hover previews straight from the original files. The built-in mpv player
 supports resume, subtitles, audio tracks, speed control and full keyboard use.
CTRL

cat > "$PKG/DEBIAN/postinst" <<'SH'
#!/bin/sh
set -e
command -v update-desktop-database >/dev/null && update-desktop-database -q /usr/share/applications || true
command -v gtk-update-icon-cache >/dev/null && gtk-update-icon-cache -q -t /usr/share/icons/hicolor || true
SH
cp "$PKG/DEBIAN/postinst" "$PKG/DEBIAN/postrm"
chmod 755 "$PKG/DEBIAN/postinst" "$PKG/DEBIAN/postrm"

mkdir -p "$ROOT/dist"
dpkg-deb --root-owner-group --build "$PKG" "$ROOT/dist/enplayer_${VERSION}_all.deb"
echo "Built $ROOT/dist/enplayer_${VERSION}_all.deb"
