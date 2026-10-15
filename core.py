"""Bowerbird core: admin-at-launch setup and app install/run/remove logic.

macOS-only. Bowerbird asks for administrator ONCE at launch through the native
macOS password dialog (osascript "do shell script ... with administrator
privileges"), and uses that one approval to create its app folder and hand
ownership to the user. After that, installing and running apps needs no
further prompts.

All process execution and network access is injectable so tests run offline
on any platform.
"""
import hashlib, json, os, shutil, subprocess, sys, tarfile, tempfile, urllib.request

STORE_DIR = '/Applications/Bowerbird'
CATALOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'catalog.json')
STATE_DIR = os.path.expanduser('~/Library/Application Support/bowerbird')
STATE_FILE = os.path.join(STATE_DIR, 'installed.json')
UA = 'bowerbird/1.0'


class BowerError(Exception):
    """User-facing failure with a clear message."""


def is_macos():
    return sys.platform == 'darwin'


def run_probe(exec_fn=None):
    """Ask for administrator once (native password dialog), create the store
    folder and give it to the user. Returns True on success.
    Raises BowerError with a friendly message if denied or unavailable."""
    exec_fn = exec_fn or _exec
    cmd = ('mkdir -p %s && chown "$USER" %s && chmod 755 %s'
           % (_q(STORE_DIR), _q(STORE_DIR), _q(STORE_DIR)))
    rc, out = exec_fn(['osascript', '-e',
                       'do shell script "%s" with administrator privileges' % cmd])
    if rc != 0:
        low = out.lower()
        if 'canceled' in low or 'cancelled' in low or '128' in low:
            raise BowerError(
                'Bowerbird needs administrator permission once at launch to set up '
                'its app folder. You declined, so it cannot continue. Run it again '
                'and enter your Mac password when asked.')
        raise BowerError('Administrator setup failed: ' + (out.strip() or 'unknown error'))
    return True


def _q(path):
    return path.replace('\\', '\\\\').replace('"', '\\"')


def _exec(argv):
    p = subprocess.run(argv, capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def load_catalog(path=CATALOG_FILE):
    with open(path) as f:
        data = json.load(f)
    apps = data.get('apps', [])
    base = os.path.dirname(os.path.abspath(path))
    for app in apps:
        for key in ('name', 'version', 'description', 'url', 'sha256', 'run'):
            if key not in app:
                raise BowerError('catalog entry %r is missing %s'
                                 % (app.get('name', '?'), key))
        url = app['url']
        if '://' not in url:  # bundled relative path -> absolute file URL
            app['url'] = 'file://' + os.path.join(base, url)
    return apps


def load_state(path=STATE_FILE):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_state(state, path=STATE_FILE):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(state, f, indent=1)
    os.replace(tmp, path)


def _download(url, fetch_fn=None):
    fetch_fn = fetch_fn or _fetch
    return fetch_fn(url)


def _fetch(url):
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def app_dir(name, store_dir=STORE_DIR):
    safe = ''.join(c for c in name if c.isalnum() or c in '-_')
    if not safe or safe != name:
        raise BowerError('Bad app name in catalog: %r' % name)
    return os.path.join(store_dir, safe)


def install(app, store_dir=STORE_DIR, state_path=STATE_FILE, fetch_fn=None,
            extract_fn=None):
    """Download, verify, and unpack one catalog app. Returns its folder."""
    blob = _download(app['url'], fetch_fn)
    got = hashlib.sha256(blob).hexdigest()
    if got.lower() != app['sha256'].lower():
        raise BowerError('%s failed its checksum - not installed.' % app['name'])
    dest = app_dir(app['name'], store_dir)
    if os.path.exists(dest):
        shutil.rmtree(dest)
    os.makedirs(dest)
    (extract_fn or _extract)(blob, dest)
    state = load_state(state_path)
    state[app['name']] = {'version': app['version'], 'dir': dest, 'run': app['run']}
    save_state(state, state_path)
    return dest


def _extract(blob, dest):
    with tempfile.NamedTemporaryFile(suffix='.tar.gz', delete=False) as t:
        t.write(blob)
        tmp = t.name
    try:
        with tarfile.open(tmp) as tf:
            for member in tf.getmembers():
                target = os.path.realpath(os.path.join(dest, member.name))
                if not target.startswith(os.path.realpath(dest) + os.sep):
                    raise BowerError('Archive tried to escape its folder - refused.')
            tf.extractall(dest)
    finally:
        os.unlink(tmp)


def remove(name, store_dir=STORE_DIR, state_path=STATE_FILE):
    dest = app_dir(name, store_dir)
    if os.path.isdir(dest):
        shutil.rmtree(dest)
    state = load_state(state_path)
    state.pop(name, None)
    save_state(state, state_path)


def run_app(name, state_path=STATE_FILE, exec_fn=None):
    state = load_state(state_path)
    if name not in state:
        raise BowerError('%s is not installed.' % name)
    entry = state[name]
    script = os.path.join(entry['dir'], entry['run'])
    if not os.path.exists(script):
        raise BowerError('%s is damaged (missing %s) - reinstall it.' % (name, entry['run']))
    exec_fn = exec_fn or _exec
    rc, out = exec_fn(['bash', script])
    return rc, out
