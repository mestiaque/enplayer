# ENPlayer

A native Ubuntu video library and player. Add your folders, and ENPlayer finds every video,
generates thumbnails, and shows a **live preview from the original file** when you rest the pointer
on a card. Click to play in a full mpv-powered player.

Built with GTK 4, libadwaita, libmpv (OpenGL render API), FFmpeg and SQLite. No Electron, no web view.

ENPlayer was previously called NEPLAYER (and before that FrameFlow). Installing the `enplayer` package
replaces the old one; your library, history and settings stay where they were.
Its sister app is **ENViewer**, the image viewer (`~/Videos/imview`).

## Features

**Library**
- Multiple folders, recursive (per-folder toggle), hidden folders ignored by default
- Incremental scanning: only new or changed files are probed again
- Live folder monitoring (Gio.FileMonitor) and drive plug/unplug detection
- Home dashboard: Continue Watching, Recently Added, Favorites, All Videos
- Search by title, file name or folder; filter by resolution, format, duration, favorites
- Sort by date added, name, duration, size, resolution
- Virtualized grid (Gtk.GridView), so 10,000+ videos stay smooth
- Unreadable or corrupt files are listed and labeled instead of crashing the scan

**Hover preview**
- Real playback from the original file. No GIFs or generated preview clips.
- Configurable delay (700 ms by default), muted, loops an 8-second segment from about ¼ of the way in
- Only one mpv preview engine exists for the whole app. It moves into whichever card is hovered and
  stops on leave, scroll, window blur or when the player opens.

**Player**
- Embedded mpv with hardware decoding (`auto-safe`, VA-API, or off)
- Seek bar with hover time, volume up to 130%, mute, speed 0.25×–3×
- Audio track and subtitle menus, auto-loaded external subtitles, load subtitle file
- Resume where you left off, Continue Watching, "Up next" countdown, previous/next
- Fullscreen, auto-hiding controls and cursor, screenshots, mpv statistics overlay
- Open any file (Ctrl+O, drag & drop, or `enplayer file.mkv`). Files from the same folder form the playlist.

**Music player**
- MP3, FLAC, M4A/AAC, OGG, Opus, WAV, WMA, AIFF, APE, WavPack in a separate **Music** section
- Title, artist, album, track, year and genre from tags; embedded cover art (generated art when missing)
- Now Playing screen, shuffle, repeat (all / one), gapless-feeling auto-advance
- Mini player keeps music playing while you browse the library

**Audio visualizer** (music only)
- 50 GPU (OpenGL shader) presets: circular / radial spectrum, classic & mirrored EQ bars, 3-D spectrum,
  Winamp-style LED analyzer, oscilloscope, stereo waveform, infinity loop, frequency rings, neon,
  particles, galaxy, liquid, tunnel, aurora, energy wave, pulse circle, dual-channel stereo spectrum,
  plus album-art presets (vinyl turntable, album spectrum ring, cover pulse, glass orb), podcast waveform,
  dot-matrix EQ, audio surface, synthwave grid, retro sun, HUD rings, cyberpunk EQ, polygon ring, sunburst,
  rainbow hills, starfield warp, kaleidoscope, hexagon grid, digital rain, stereo vectorscope,
  spectrogram waterfall, bouncing dots, square pulse, sound sphere, silk ribbons, beat fireworks,
  equalizer skyline, dot rings, lava blobs, dot wave field and ripple pond
- Reacts to the *real* audio: the playing file is decoded with ffmpeg in the background and analysed with
  an FFT at mpv's playback position (bass / mid / treble, beat detection, stereo channels)
- Controls: preset picker, next / previous / random, speed, sensitivity, bass response, particle density,
  glow, brightness, colour themes (incl. colours from the album art), background, FFT size,
  performance mode (60 / 30 / 24 fps), reduced motion, reset
- New presets: drop a `.glsl` file into `neplayer/visualizer/presets/` (see `header.glsl`); nothing else changes

## Keyboard shortcuts (player)

| Key | Action | Key | Action |
|---|---|---|---|
| Space / K | Play / pause | F / double-click | Fullscreen |
| ← / → | Seek 5 s | Esc | Exit fullscreen / back |
| Shift + ← / → | Seek 1 s | M | Mute |
| Ctrl + ← / → | Seek 60 s | ↑ / ↓ | Volume |
| J / L | Seek 10 s | S / A | Next subtitle / audio track |
| 0 – 9 | Jump to 0–90% | V | Toggle subtitles |
| , / . | Frame step | [ / ] / Backspace | Speed down / up / reset |
| N / P | Next / previous video | Home | Restart |
| I | Statistics | Ctrl + S | Screenshot |

Library: Ctrl+O open file, Ctrl+N add folder, Ctrl+F search, F5 rescan, F9 sidebar, Ctrl+? all shortcuts.

## Ubuntu te install korar niyom

Installer file: `dist/enplayer_1.4.3_all.deb`. Na thakle project folder e `bash packaging/build-deb.sh` chalan.

### Upay 1: Terminal die (shobcheye nirbhorjoggo)

**Ctrl+Alt+T** chepe Terminal khulun, tarpor eta paste kore Enter chapun:

```bash
sudo apt install ~/Videos/vplayer/dist/enplayer_1.4.3_all.deb
```

Password chaile apnar login password din. Type korar shomoy kichu dekhabe na, eta swabhabik.

### Upay 2: Mouse die

1. Files app e `Videos → vplayer → dist` folder e jan.
2. `enplayer_1.4.3_all.deb` e **right-click** kore **Open With Other Application → Software Install** select korun.
3. **Install** chepe password din.

> Ubuntu 22.04 er Software app majhe majhe `.deb` file thik moto khulte pare na. Tokhon Upay 1 use korun.

### Install er por

- **Activities** (Super/Windows key) chepe **ENPlayer** likhun, tarpor click korun.
- Dock e rakhte chaile icon e right-click kore **Add to Favorites** chapun.
- Terminal theke `enplayer` likheo khola jay.
- Prothombar khulle apnar **Videos** folder nije nije add hoye scan hobe.

### Uninstall

```bash
sudo apt remove enplayer
```

Ete apnar video file gulo muche jabe na.

Windows ar onno shob installer er niyom **[INSTALL.md](INSTALL.md)** e ache. Duita installer i
GitHub Actions (`.github/workflows/build.yml`) nije nije banay.

## Requirements (running from source)

Ubuntu 22.04 or newer (tested on 22.04 with GTK 4.6, libadwaita 1.1, mpv 0.34, FFmpeg 4.4).

```bash
sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 libmpv1 ffmpeg python3-pil
pip install --user python-mpv
```

On Ubuntu 24.04 the package is `libmpv2` instead of `libmpv1`.

## Run / install

```bash
./run.sh                       # run from source
./install.sh                   # per-user install: app-grid launcher + `enplayer` command
./uninstall.sh [--purge]       # remove (--purge also deletes the library DB and thumbnails)

bash packaging/build-deb.sh    # build dist/enplayer_1.4.3_all.deb
sudo apt install ./dist/enplayer_1.4.3_all.deb
sudo apt remove enplayer
```

Windows installer: `packaging/windows/build-windows.sh` (in an MSYS2 UCRT64 shell) bundles Python, GTK4,
libadwaita, mpv and FFmpeg into `dist/windows/ENPlayer/`, then `packaging/windows/enplayer.iss`
(Inno Setup) wraps it into `dist/ENPlayer-Setup-<version>.exe`. CI runs both steps on `windows-2022`.

A Flatpak manifest is in `packaging/io.github.enplayer.ENPlayer.flatpak.yml`. It hasn't been built
yet; fill in the source checksums first.

## Data locations

| What | Where |
|---|---|
| Library database | Linux `~/.local/share/neplayer/neplayer.db` · Windows `%LOCALAPPDATA%\NEPLAYER\neplayer.db` |
| Log file | next to the database: `neplayer.log` |
| Thumbnails (WebP 480×270) | Linux `~/.cache/neplayer/thumbnails/` · Windows `%LOCALAPPDATA%\NEPLAYER\Cache\thumbnails\` |

Override with `NEPLAYER_DATA_DIR` / `NEPLAYER_CACHE_DIR`. Set `NEPLAYER_DEBUG=1` for verbose logs.

## Tests

```bash
python3 -m unittest discover -s tests -v          # core: DB, ffprobe, thumbnails, scanner, 12k-row queries
python3 tests/e2e_harness.py LIBRARY_DIR OUT_DIR  # drives the real app: scan, previews, player, monitor
```

The end-to-end harness uses an isolated data dir and saves screenshots of the ENPlayer window into `OUT_DIR`.

## Architecture

```
neplayer/
  main.py, app.py, config.py
  core/      database (SQLite, WAL, per-thread connections), settings, metadata (ffprobe),
             thumbnail (ffmpeg, black-frame avoidance), scanner (incremental), file_monitor,
             cache (LRU prune), texture_cache (async decode), library (service façade, signals)
  workers/   scan_worker (sequential background scans), thumbnail_worker (priority queue)
  player/    mpv_widget (Gtk.GLArea + libmpv render API), playback_manager, shortcuts
  preview/   preview_manager (single shared engine, hover timers, lifecycle)
  ui/        main_window, sidebar, toolbar, home_view, video_grid, video_card,
             player_view, folders_view, settings_view
```

**Why GLArea + render API?** GTK 4 removed foreign-window embedding (GtkSocket / `wid`), so libmpv's
OpenGL render API drawing into a `Gtk.GLArea` is the supported way to embed mpv. The hover preview
uses the same widget. It's re-parented between cards, and its render context is created on realize and
freed on unrealize, so only one mpv preview core exists at any time.

## Updates

Installed copies update themselves: ENPlayer checks GitHub for a newer release once a day (Settings → General
→ *Check for updates automatically*, or *Check now*). **Update now** downloads the installer, verifies its
SHA-256 and installs it over the existing one, keeping your data. On Ubuntu the system asks for your
password; on Windows the installer runs silently and ENPlayer restarts. No uninstall is needed.

To publish an update: raise the version in neplayer/config.py (`VERSION`), commit, then

```bash
git tag v<new-version> && git push origin main --tags
```

GitHub Actions builds the `.deb` and the Windows installer and attaches them to a new Release, which is where the apps look.

## Developer

ENPlayer is developed by **M. Estiaque Ahmed Khan** · <info@mestiaque.com> · [mestiaque.com](https://mestiaque.com). Bug reports and ideas are welcome.
