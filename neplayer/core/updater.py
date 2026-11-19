"""In-app updates. New versions are published as GitHub releases of mestiaque/enplayer.

check()    -> asks the GitHub API for the latest release (the only network request ENPlayer makes,
              and only when the user allows it).
download() -> fetches the installer for this platform and verifies its SHA-256 when GitHub
              publishes one.
install()  -> Ubuntu: `pkexec apt-get install <deb>` (system password prompt, upgrades in place);
              Windows: a hidden PowerShell script waits for ENPlayer to quit, runs the Inno Setup
              installer silently over the same folder and starts the new version (log in
              %TEMP%\\ENPlayer-update.log).
restart()  -> starts the new version after this process has quit.

Nothing here touches GTK, so it can run on worker threads and be unit-tested.
"""
import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from neplayer.config import APP_NAME, VERSION

REPO = 'mestiaque/enplayer'
API_LATEST = f'https://api.github.com/repos/{REPO}/releases/latest'
# The latest release, as published to the public mestiaque/en-releases repository: a plain file (no
# API rate limit), readable although this repository is private. The release API is the fallback.
MANIFEST = 'https://raw.githubusercontent.com/mestiaque/en-releases/main/enplayer.json'
RELEASES_PAGE = 'https://github.com/mestiaque/en-releases/releases'
DEB_INSTALL_DIR = Path('/usr/lib/enplayer')


class UpdateError(Exception):
    pass


@dataclass
class Update:
    version: str
    notes: str
    page: str
    asset_name: str = ''
    url: str = ''
    size: int = 0
    sha256: str = ''

    @property
    def installable(self):
        return bool(self.url)


def parse_version(text):
    """'v1.4.0' / '1.4' / '1.4.0-beta' -> (1, 4, 0). Unparseable parts count as 0."""
    nums = [int(n) for n in re.findall(r'\d+', str(text).split('-')[0])[:3]]
    return tuple(nums + [0] * (3 - len(nums)))


def is_newer(remote, local=VERSION):
    return parse_version(remote) > parse_version(local)


def install_kind():
    """How this copy was installed: 'deb', 'windows', or None (running from source)."""
    here = Path(__file__).resolve()
    if sys.platform == 'win32':
        # bundled build: <app>\bin\pythonw.exe (+ ENPlayer.exe since 1.4.10) + <app>\lib\...\neplayer
        return 'windows' if (Path(sys.executable).parent / 'pythonw.exe').exists() and 'site-packages' in str(here) else None
    if DEB_INSTALL_DIR in here.parents and shutil.which('apt-get'):
        return 'deb'
    return None


def pick_asset(assets, kind):
    for a in assets:
        name = a.get('name', '')
        if kind == 'deb' and name.startswith('enplayer_') and name.endswith('_all.deb'):
            return a
        if kind == 'windows' and name.lower().startswith('enplayer-setup') and name.lower().endswith('.exe'):
            return a
    return None


def _request(url):
    return urllib.request.Request(url, headers={
        'User-Agent': f'{APP_NAME}/{VERSION} (update check)',
        'Accept': 'application/vnd.github+json',
    })


def check(timeout=10, kind=None):
    """Latest release if it is newer than this version, else None. Raises UpdateError on failure."""
    if os.environ.get('SNAP'):
        return None  # the Snap Store updates this copy
    kind = install_kind() if kind is None else kind
    data, error = None, None
    for url in (MANIFEST, API_LATEST):
        try:
            with urllib.request.urlopen(_request(url), timeout=timeout) as r:
                data = json.loads(r.read().decode('utf-8'))
            break
        except Exception as e:
            error = e
    if data is None:
        raise UpdateError(f'Could not reach GitHub: {error}') from error
    return update_from_release(data, kind)


# Lines GitHub adds to generated release notes: a link to the code changes, pull-request credits.
_NOTES_NOISE = re.compile(r'full changelog|made their first contribution|github\.com/\S+/(compare|commits)/'
                          r'|^\s*#*\s*new contributors\s*$', re.I)


def clean_notes(text):
    """Release notes as plain text for the update dialog: GitHub's generated links ("Full Changelog:
    https://github.com/.../compare/...") and Markdown marks are left out."""
    lines = []
    for line in str(text).replace('\r', '').split('\n'):
        if _NOTES_NOISE.search(line):
            continue
        line = re.sub(r'\s+by @\S+ in https://github\.com/\S+', '', line)   # "* Fix by @x in https://.../pull/3"
        line = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', line)                 # [text](link) -> text
        line = re.sub(r'\*\*|__|`', '', line)
        line = re.sub(r'^\s*#{1,6}\s*', '', line)
        line = re.sub(r'^(\s*)[*-]\s+', '\\1\u2022 ', line)
        lines.append(line.rstrip())
    return re.sub(r'\n{3,}', '\n\n', '\n'.join(lines)).strip()


def update_from_release(data, kind):
    tag = data.get('tag_name') or ''
    if not tag or data.get('draft') or data.get('prerelease') or not is_newer(tag):
        return None
    up = Update(version='.'.join(map(str, parse_version(tag))), notes=clean_notes(data.get('body') or ''),
                page=data.get('html_url') or RELEASES_PAGE)
    asset = pick_asset(data.get('assets') or [], kind) if kind else None
    if asset:
        digest = asset.get('digest') or ''
        up.asset_name = asset['name']
        up.url = asset.get('browser_download_url', '')
        up.size = int(asset.get('size') or 0)
        up.sha256 = digest.split(':', 1)[1] if digest.startswith('sha256:') else ''
    return up


def download(update, dest_dir, progress=None, cancelled=lambda: False):
    """Download the installer to dest_dir; progress(done, total). Returns the file path."""
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    out = dest_dir / update.asset_name
    part = out.with_suffix(out.suffix + '.part')
    h = hashlib.sha256()
    try:
        with urllib.request.urlopen(_request(update.url), timeout=30) as r, open(part, 'wb') as f:
            total = int(r.headers.get('Content-Length') or update.size or 0)
            done = 0
            while True:
                if cancelled():
                    raise UpdateError('Download cancelled')
                chunk = r.read(256 * 1024)
                if not chunk:
                    break
                f.write(chunk)
                h.update(chunk)
                done += len(chunk)
                if progress:
                    progress(done, total)
    except UpdateError:
        part.unlink(missing_ok=True)
        raise
    except Exception as e:
        part.unlink(missing_ok=True)
        raise UpdateError(f'Download failed: {e}') from e
    if update.sha256 and h.hexdigest() != update.sha256.lower():
        part.unlink(missing_ok=True)
        raise UpdateError('The downloaded file is damaged (checksum mismatch). Please try again.')
    os.replace(part, out)
    os.chmod(out, 0o644)  # apt's sandbox user must be able to read it
    return out


def _ps(text):
    """A PowerShell single-quoted string literal."""
    return "'" + str(text).replace("'", "''") + "'"


def _win(path):
    """A Windows path with backslashes. The bundled (MSYS2) Python writes Windows paths with forward
    slashes, which Inno Setup's /DIR= and some Windows tools do not take everywhere."""
    return str(path).replace('/', '\\')


def windows_update_script(installer, app_dir, exe, pid, log, all_users=False):
    """PowerShell that finishes a Windows update once ENPlayer (process `pid`) has quit: runs the
    Inno Setup installer silently over `app_dir`, then starts `exe`. Every step goes to `log`.
    `all_users`: the copy lives in a folder this user cannot write (Program Files), so the installer
    runs in administrative mode (/ALLUSERS, Windows asks for permission); otherwise /CURRENTUSER.

    It runs through -EncodedCommand: a `cmd /c "..."` line breaks here, because Windows programs
    escape the quotes around paths as \\" , which cmd.exe does not understand, and because the
    `timeout` command fails without a console."""
    installer, app_dir, exe, log = _win(installer), _win(app_dir), _win(exe), _win(log)
    dir_arg = _ps('/DIR="%s"' % app_dir)   # Inno Setup reads the quoted folder itself
    return '\n'.join([
        "$ErrorActionPreference = 'Continue'",
        f"$log = {_ps(log)}",
        "function Log($m) { Add-Content -LiteralPath $log -Value ((Get-Date -Format s) + '  ' + $m) -Encoding UTF8 }",
        f"Log 'Update: waiting for ENPlayer (process {int(pid)}) to quit'",
        f"Wait-Process -Id {int(pid)} -Timeout 60 -ErrorAction SilentlyContinue",
        "try {",
        f"  $p = Start-Process -FilePath {_ps(installer)} -Wait -PassThru -ArgumentList "
        f"'/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/CLOSEAPPLICATIONS', "
        f"'{'/ALLUSERS' if all_users else '/CURRENTUSER'}', {dir_arg}",
        "  Log ('Installer finished with exit code ' + $p.ExitCode)",
        "} catch { Log ('The installer did not run: ' + $_) }",
        f"try {{ Start-Process -FilePath {_ps(exe)} }} catch {{ Log ('Could not start ENPlayer: ' + $_) }}",
    ])


def folder_writable(path):
    """True if this user can create files in `path`. os.access() cannot tell on Windows (it ignores
    the folder's permissions), so try it."""
    probe = Path(path) / f'.enplayer-write-test-{os.getpid()}'
    try:
        probe.write_bytes(b'')
        probe.unlink()
        return True
    except OSError:
        return False


def powershell_command(script):
    """Arguments that run `script` in a hidden Windows PowerShell (no quoting involved)."""
    ps = Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32' / 'WindowsPowerShell' / 'v1.0' / 'powershell.exe'
    encoded = base64.b64encode(script.encode('utf-16-le')).decode('ascii')
    return [str(ps), '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-WindowStyle', 'Hidden',
            '-EncodedCommand', encoded]


def install(path, kind=None):
    """Install the downloaded package. Ubuntu: blocks until apt finishes. Windows: the installer
    runs after this process quits (call restart/quit right after). Raises UpdateError."""
    kind = install_kind() if kind is None else kind
    path = Path(path).resolve()
    if kind == 'deb':
        if not shutil.which('pkexec'):
            raise UpdateError('pkexec is missing; install the update with: sudo apt install ' + str(path))
        r = subprocess.run(['pkexec', 'apt-get', 'install', '-y', '--allow-downgrades', str(path)],
                           capture_output=True, text=True, check=False)
        if r.returncode in (126, 127):
            raise UpdateError('Update cancelled: the administrator password was not entered.')
        if r.returncode != 0:
            tail = (r.stderr or r.stdout).strip().splitlines()[-3:]
            raise UpdateError('Installing the update failed:\n' + '\n'.join(tail))
        return
    if kind == 'windows':
        bin_dir = Path(sys.executable).parent           # <app>\bin (ENPlayer.exe since 1.4.10)
        app_dir = bin_dir.parent
        script = windows_update_script(path, app_dir, bin_dir / 'ENPlayer.exe', os.getpid(),
                                       Path(tempfile.gettempdir()) / 'ENPlayer-update.log',
                                       all_users=not folder_writable(app_dir))
        try:
            subprocess.Popen(powershell_command(script), close_fds=True,
                             creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)
                             | getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0))
        except OSError as e:
            raise UpdateError(f'Could not start the installer: {e}') from e
        return
    raise UpdateError('This copy of ENPlayer runs from the source code and cannot update itself')


def restart():
    """Start the freshly installed ENPlayer once this process has exited (Ubuntu)."""
    exe = shutil.which('enplayer') or '/usr/bin/enplayer'
    subprocess.Popen(['sh', '-c', f'sleep 1.5; exec "{exe}"'], start_new_session=True, close_fds=True,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
