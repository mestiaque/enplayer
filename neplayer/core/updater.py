"""In-app updates. New versions are published as GitHub releases of mestiaque/enplayer.

check()    -> asks the GitHub API for the latest release (the only network request ENPlayer makes,
              and only when the user allows it).
download() -> fetches the installer for this platform and verifies its SHA-256 when GitHub
              publishes one.
install()  -> Ubuntu: `pkexec apt-get install <deb>` (system password prompt, upgrades in place);
              Windows: runs the Inno Setup installer silently, which upgrades the same install.
restart()  -> starts the new version after this process has quit.

Nothing here touches GTK, so it can run on worker threads and be unit-tested.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from neplayer.config import APP_NAME, VERSION

REPO = 'mestiaque/enplayer'
API_LATEST = f'https://api.github.com/repos/{REPO}/releases/latest'
RELEASES_PAGE = f'https://github.com/{REPO}/releases/latest'
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
        # bundled build: <app>\bin\pythonw.exe + <app>\lib\...\neplayer
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
    try:
        with urllib.request.urlopen(_request(API_LATEST), timeout=timeout) as r:
            data = json.loads(r.read().decode('utf-8'))
    except Exception as e:
        raise UpdateError(f'Could not reach GitHub: {e}') from e
    return update_from_release(data, kind)


def update_from_release(data, kind):
    tag = data.get('tag_name') or ''
    if not tag or data.get('draft') or data.get('prerelease') or not is_newer(tag):
        return None
    up = Update(version='.'.join(map(str, parse_version(tag))), notes=(data.get('body') or '').strip(),
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
        pythonw = Path(sys.executable).parent / 'pythonw.exe'
        # wait for ENPlayer to exit, install silently over the same folder, start the new version
        cmd = (f'timeout /t 2 /nobreak >nul & "{path}" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART '
               f'/CLOSEAPPLICATIONS & start "" "{pythonw}" -m neplayer.main')
        flags = getattr(subprocess, 'DETACHED_PROCESS', 0) | getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0)
        subprocess.Popen(['cmd', '/c', cmd], creationflags=flags, close_fds=True)
        return
    raise UpdateError('This copy of ENPlayer was not installed from a package; download the new version '
                      'from ' + RELEASES_PAGE)


def restart():
    """Start the freshly installed ENPlayer once this process has exited (Ubuntu)."""
    exe = shutil.which('enplayer') or '/usr/bin/enplayer'
    subprocess.Popen(['sh', '-c', f'sleep 1.5; exec "{exe}"'], start_new_session=True, close_fds=True,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
