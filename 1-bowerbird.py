#!/usr/bin/env python3
"""Bowerbird - a tiny terminal app store for macOS.

Asks for administrator once at launch (native macOS password dialog), sets up
its app folder in /Applications, then installs and runs apps without asking
again. Catalog-driven, color-block fullscreen UI, stdlib only.

BOWERBIRD_DEMO=1 runs a fully offline demo (no admin prompt, fake catalog) -
also used by the tests, since none of the development machines are Macs.
"""
import curses, hashlib, io, json, os, sys, tarfile, tempfile

import core

APP = 'bowerbird'
VERSION = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                      'app-version.json')))['version']
DEMO = os.environ.get('BOWERBIRD_DEMO') == '1'
DEMO_DENY = os.environ.get('BOWERBIRD_DEMO_DENY') == '1'

C_TITLE, C_BAR, C_SEL, C_OK, C_ERR, C_DIM, C_NAME = range(1, 8)


def demo_catalog(tmp):
    """Two tiny real apps, built on the fly, for the offline demo."""
    def tarball(dirname, script):
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode='w:gz') as tf:
            data = script.encode()
            ti = tarfile.TarInfo('run.sh')
            ti.size = len(data)
            tf.addfile(ti, io.BytesIO(data))
        return buf.getvalue()
    apps = []
    for name, desc, line in (
            ('hello-mac', 'says hello from your Mac', 'echo hello from bowerbird'),
            ('sys-peek', 'one-screen system snapshot', 'uname -a && uptime')):
        blob = tarball(name, '#!/bin/bash\n%s\n' % line)
        path = os.path.join(tmp, name + '.tar.gz')
        with open(path, 'wb') as f:
            f.write(blob)
        apps.append({'name': name, 'version': '1.0.0', 'description': desc,
                     'url': 'file://' + path, 'sha256': hashlib.sha256(blob).hexdigest(),
                     'run': 'run.sh'})
    return apps


def demo_fetch(url):
    assert url.startswith('file://')
    with open(url[7:], 'rb') as f:
        return f.read()


class App:
    def __init__(self, stdscr, store_dir, state_path, apps, fetch_fn):
        self.s = stdscr
        self.store_dir = store_dir
        self.state_path = state_path
        self.apps = apps
        self.fetch_fn = fetch_fn
        self.sel = 0
        self.status = ('', C_DIM)

    def set_status(self, text, color=C_DIM):
        self.status = (text, color)

    def draw(self):
        self.s.erase()
        h, w = self.s.getmaxyx()
        self.s.addstr(0, 0, (' BOWERBIRD %s - your Mac app store' % VERSION).ljust(w - 1)[:w - 1],
                      curses.color_pair(C_BAR))
        state = core.load_state(self.state_path)
        y = 2
        for i, app in enumerate(self.apps):
            inst = state.get(app['name'])
            if inst and inst['version'] != app['version']:
                mark = 'update %s -> %s' % (inst['version'], app['version'])
                color = C_OK
            elif inst:
                mark = 'installed %s' % inst['version']
                color = C_OK
            else:
                mark = 'not installed'
                color = C_DIM
            attr = curses.color_pair(C_SEL) if i == self.sel else curses.color_pair(C_NAME)
            line = ' %-18s %-28s %s' % (app['name'], app['description'][:28], mark)
            try:
                self.s.addstr(y, 2, line.ljust(w - 4)[:w - 4], attr)
            except curses.error:
                pass
            y += 1
        if not self.apps:
            self.s.addstr(2, 2, '(the catalog is empty)', curses.color_pair(C_DIM))
        text, color = self.status
        base = 'arrows move  Enter install/run  X remove  Q quit'
        self.s.addstr(h - 1, 0, (' %s  %s' % (text, base))[:w - 1].ljust(w - 1),
                      curses.color_pair(color))
        self.s.refresh()

    def run(self):
        while True:
            self.draw()
            ch = self.s.getch()
            if ch in (ord('q'), ord('Q')):
                return
            if ch in (curses.KEY_UP, ord('k')):
                self.sel = max(0, self.sel - 1)
            elif ch in (curses.KEY_DOWN, ord('j')):
                self.sel = min(len(self.apps) - 1, self.sel + 1)
            elif ch in (10, 13) and self.apps:
                self.activate(self.apps[self.sel])
            elif ch in (ord('x'), ord('X')) and self.apps:
                app = self.apps[self.sel]
                core.remove(app['name'], self.store_dir, self.state_path)
                self.set_status('Removed %s' % app['name'], C_OK)

    def activate(self, app):
        state = core.load_state(self.state_path)
        if app['name'] not in state or state[app['name']]['version'] != app['version']:
            self.set_status('Installing %s...' % app['name'])
            self.draw()
            try:
                core.install(app, self.store_dir, self.state_path, self.fetch_fn)
                self.set_status('Installed %s %s - press Enter again to run it'
                                % (app['name'], app['version']), C_OK)
            except core.BowerError as e:
                self.set_status(str(e), C_ERR)
            return
        curses.endwin()
        try:
            rc, out = core.run_app(app['name'], self.state_path)
            print(out)
        except core.BowerError as e:
            print(e)
            rc = 1
        input('press Enter to return to Bowerbird ')
        self.s.refresh()
        if rc != 0:
            self.set_status('%s exited with %d' % (app['name'], rc), C_ERR)
        else:
            self.set_status('%s finished' % app['name'], C_OK)


def splash(s):
    s.erase()
    h, w = s.getmaxyx()
    art = [' ___ ___ _ _ _ ___ ___ ___ ___ ___ ',
           '| . | . | | | | -_|  _| . |_ _|  \\',
           '|___|___|_____|___|_| |___|___|__/']
    y = h // 2 - 4
    for i, line in enumerate(art):
        s.addstr(y + i, max(0, (w - len(line)) // 2), line,
                 curses.color_pair(C_TITLE) | curses.A_BOLD)
    s.addstr(y + 4, max(0, (w - 40) // 2), 'asking for administrator...',
             curses.color_pair(C_DIM))
    s.refresh()


def init_colors():
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(C_TITLE, curses.COLOR_MAGENTA, -1)
    curses.init_pair(C_BAR, curses.COLOR_BLACK, curses.COLOR_MAGENTA)
    curses.init_pair(C_SEL, curses.COLOR_BLACK, curses.COLOR_WHITE)
    curses.init_pair(C_OK, curses.COLOR_GREEN, -1)
    curses.init_pair(C_ERR, curses.COLOR_RED, -1)
    curses.init_pair(C_DIM, curses.COLOR_BLUE, -1)
    curses.init_pair(C_NAME, curses.COLOR_WHITE, -1)


def main():
    if '--version' in sys.argv:
        print(VERSION)
        return 0
    if not core.is_macos() and not DEMO:
        print('Bowerbird is a Mac app store - it only runs on macOS.')
        return 1
    if DEMO:
        tmp = tempfile.mkdtemp(prefix='bowerbird-demo-')
        store_dir = os.path.join(tmp, 'store')
        state_path = os.path.join(tmp, 'state.json')
        apps = demo_catalog(tmp)
        fetch_fn = demo_fetch
        probe = (lambda: (_ for _ in ()).throw(core.BowerError(
            'Bowerbird needs administrator permission once at launch to set up '
            'its app folder. You declined, so it cannot continue. Run it again '
            'and enter your Mac password when asked.'))) if DEMO_DENY else (lambda: True)
    else:
        store_dir, state_path = core.STORE_DIR, core.STATE_FILE
        apps = core.load_catalog()
        fetch_fn = None
        probe = core.run_probe
    stdscr = curses.initscr()
    curses.noecho()
    curses.cbreak()
    stdscr.keypad(True)
    try:
        init_colors()
        splash(stdscr)
        try:
            probe()
        except core.BowerError as e:
            curses.endwin()
            print(e)
            return 1
        try:
            curses.curs_set(0)
        except curses.error:
            pass
        App(stdscr, store_dir, state_path, apps, fetch_fn).run()
    finally:
        curses.endwin()
    return 0


if __name__ == '__main__':
    sys.exit(main())
