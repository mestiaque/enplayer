#!/bin/bash
# Removes the per-user install. Pass --purge to also delete library database and thumbnail cache.
set -euo pipefail
PREFIX="${PREFIX:-$HOME/.local}"
rm -f "$PREFIX/bin/enplayer" "$PREFIX/bin/neplayer" \
      "$PREFIX/share/applications/io.github.enplayer.ENPlayer.desktop" \
      "$PREFIX/share/icons/hicolor/scalable/apps/io.github.enplayer.ENPlayer.svg" \
      "$PREFIX/share/applications/io.github.neplayer.NEPlayer.desktop" \
      "$PREFIX/share/icons/hicolor/scalable/apps/io.github.neplayer.NEPlayer.svg"
update-desktop-database -q "$PREFIX/share/applications" 2>/dev/null || true
if [ "${1:-}" = "--purge" ]; then
  rm -rf "${XDG_DATA_HOME:-$HOME/.local/share}/neplayer" "${XDG_CACHE_HOME:-$HOME/.cache}/neplayer"
  echo "Removed ENPlayer and its library data."
else
  echo "Removed ENPlayer. Library data kept (use --purge to delete it)."
fi
