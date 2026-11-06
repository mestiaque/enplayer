#!/bin/bash
# Per-user install (no root): adds `enplayer` to ~/.local/bin and a launcher to the app grid.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
PREFIX="${PREFIX:-$HOME/.local}"

echo "Checking system dependencies…"
missing=()
python3 -c "import gi; gi.require_version('Gtk','4.0'); gi.require_version('Adw','1')" 2>/dev/null || missing+=(python3-gi gir1.2-gtk-4.0 gir1.2-adw-1)
python3 -c "import PIL" 2>/dev/null || missing+=(python3-pil)
command -v ffmpeg >/dev/null || missing+=(ffmpeg)
ldconfig -p | grep -q 'libmpv\.so' || missing+=(libmpv1)
if [ ${#missing[@]} -gt 0 ]; then
  echo "Installing: ${missing[*]}"
  sudo apt-get install -y "${missing[@]}"
fi
python3 -c "import mpv" 2>/dev/null || pip3 install --user python-mpv

# remove a launcher left by the old NEPLAYER name
rm -f "$PREFIX/bin/neplayer" "$PREFIX/share/applications/io.github.neplayer.NEPlayer.desktop" \
      "$PREFIX/share/icons/hicolor/scalable/apps/io.github.neplayer.NEPlayer.svg"
install -d "$PREFIX/bin" "$PREFIX/share/applications" "$PREFIX/share/icons/hicolor/scalable/apps"
cat > "$PREFIX/bin/enplayer" <<SH
#!/bin/sh
for v in GDK_PIXBUF_MODULE_FILE GDK_PIXBUF_MODULEDIR GIO_MODULE_DIR GSETTINGS_SCHEMA_DIR GTK_EXE_PREFIX GTK_IM_MODULE_FILE GTK_PATH LOCPATH; do
  eval "val=\\${\$v:-}"; case "\$val" in *snap*) unset "\$v" ;; esac
done
export PYTHONPATH="$ROOT\${PYTHONPATH:+:\$PYTHONPATH}"
exec python3 -m neplayer.main "\$@"
SH
chmod 755 "$PREFIX/bin/enplayer"
sed "s|^Exec=enplayer|Exec=$PREFIX/bin/enplayer|; s|^TryExec=enplayer|TryExec=$PREFIX/bin/enplayer|" \
  "$ROOT/packaging/io.github.enplayer.ENPlayer.desktop" > "$PREFIX/share/applications/io.github.enplayer.ENPlayer.desktop"
install -m644 "$ROOT/packaging/io.github.enplayer.ENPlayer.svg" "$PREFIX/share/icons/hicolor/scalable/apps/"
update-desktop-database -q "$PREFIX/share/applications" 2>/dev/null || true
gtk-update-icon-cache -q -t "$PREFIX/share/icons/hicolor" 2>/dev/null || true
echo "Installed. Launch ENPlayer from the app grid or run: enplayer"
