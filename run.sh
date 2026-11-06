#!/bin/bash
# Run from the source tree without installing.
cd "$(dirname "$0")"
# Terminals inside snap apps (e.g. VS Code) leak their own GTK/GIO module paths,
# which break GTK apps started from them. Drop any that point into /snap.
for v in GDK_PIXBUF_MODULE_FILE GDK_PIXBUF_MODULEDIR GIO_MODULE_DIR GSETTINGS_SCHEMA_DIR \
         GTK_EXE_PREFIX GTK_IM_MODULE_FILE GTK_PATH LOCPATH; do
  case "${!v}" in *snap*) unset "$v" ;; esac
done
PYTHONPATH="$PWD${PYTHONPATH:+:$PYTHONPATH}" exec python3 -m neplayer.main "$@"
