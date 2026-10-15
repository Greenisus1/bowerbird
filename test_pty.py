"""Event-driven PTY smoke test for Bowerbird (offline demo mode)."""
import fcntl, os, pty, re, select, struct, subprocess, tempfile, termios, time

HERE = os.path.dirname(os.path.abspath(__file__))

def run(env_extra=None):
    m, s = pty.openpty()
    fcntl.ioctl(s, termios.TIOCSWINSZ, struct.pack('HHHH', 30, 90, 0, 0))
    env = dict(os.environ, TERM='xterm-256color', LANG='C.UTF-8',
               PYTHONDONTWRITEBYTECODE='1', BOWERBIRD_DEMO='1')
    env.update(env_extra or {})
    p = subprocess.Popen(['python3', os.path.join(HERE, 'bowerbird.py')],
                         stdin=s, stdout=s, stderr=s, close_fds=True, env=env)
    os.close(s)
    return m, p

def read_out(m, window):
    out = b''; end = time.monotonic() + window
    while time.monotonic() < end:
        r, _, _ = select.select([m], [], [], .2)
        if not r: continue
        try: chunk = os.read(m, 65536)
        except OSError: break
        if not chunk: break
        out += chunk
    return out

def wait_out(m, buf, tokens, timeout=15):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        buf += read_out(m, .3)
        plain = re.sub(rb'\x1b\[[0-9;?]*[A-Za-z]|\x1b.', b'', bytes(buf))
        if all(t in plain for t in tokens): return plain
    raise AssertionError('tokens not found: %r\n%s' % (tokens, bytes(buf)[-1200:]))

def send(m, data, wait=.3):
    os.write(m, data); time.sleep(wait)

def clean(p, m):
    try: p.terminate(); p.wait(timeout=2)
    except Exception: pass
    try: os.close(m)
    except OSError: pass

def main():
    # happy path: splash -> catalog -> install -> run -> remove -> quit
    m, p = run()
    buf = bytearray()
    try:
        wait_out(m, buf, [b'hello-mac', b'sys-peek', b'not installed'])
        send(m, b'\n', .8)                      # install hello-mac
        wait_out(m, buf, [b'Installed hello-mac 1.0.0'])
        send(m, b'\n', .8)                      # run it
        wait_out(m, buf, [b'press Enter to return'])
        send(m, b'\n', .5)
        wait_out(m, buf, [b'hello-mac finished'])
        send(m, b'x', .4)                       # remove
        wait_out(m, buf, [b'Removed hello-mac'])
        send(m, b'q')
        end = time.monotonic() + 8
        while p.poll() is None and time.monotonic() < end: time.sleep(.1)
        assert p.poll() == 0, 'did not exit 0: %r' % p.poll()
    finally:
        clean(p, m)
    # denial path: clear message, exit 1
    m, p = run({'BOWERBIRD_DEMO_DENY': '1'})
    buf = bytearray()
    try:
        wait_out(m, buf, [b'declined', b'cannot continue'])
        end = time.monotonic() + 8
        while p.poll() is None and time.monotonic() < end: time.sleep(.1)
        assert p.poll() == 1, 'denial should exit 1, got %r' % p.poll()
    finally:
        clean(p, m)
    print('PTY PASS')

if __name__ == '__main__':
    main()
