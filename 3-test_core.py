import hashlib, io, json, os, sys, tarfile, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import core


def make_tar(files):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode='w:gz') as tf:
        for name, data in files.items():
            b = data.encode()
            ti = tarfile.TarInfo(name)
            ti.size = len(b)
            tf.addfile(ti, io.BytesIO(b))
    return buf.getvalue()


APP = {'name': 'demo-app', 'version': '1.0.0', 'description': 'Demo',
       'url': 'https://example.com/demo.tar.gz', 'sha256': '', 'run': 'run.sh'}


class TestProbe(unittest.TestCase):
    def test_probe_success(self):
        seen = []
        def ex(argv):
            seen.append(argv)
            return 0, ''
        self.assertTrue(core.run_probe(ex))
        self.assertIn('osascript', seen[0][0])
        self.assertIn('administrator privileges', seen[0][-1])
        self.assertIn(core.STORE_DIR, seen[0][-1])

    def test_probe_denied_is_friendly(self):
        def ex(argv):
            return 1, 'User canceled. (-128)'
        with self.assertRaises(core.BowerError) as ctx:
            core.run_probe(ex)
        self.assertIn('declined', str(ctx.exception))

    def test_probe_other_failure(self):
        with self.assertRaises(core.BowerError) as ctx:
            core.run_probe(lambda a: (2, 'osascript: no such file'))
        self.assertIn('setup failed', str(ctx.exception).lower())


class TestCatalog(unittest.TestCase):
    def test_missing_key(self):
        with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False) as f:
            json.dump({'apps': [{'name': 'x'}]}, f)
            path = f.name
        with self.assertRaises(core.BowerError):
            core.load_catalog(path)
        os.unlink(path)


class TestInstall(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.store = os.path.join(self.tmp, 'store')
        self.state = os.path.join(self.tmp, 'state.json')

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def app_tar(self):
        blob = make_tar({'run.sh': '#!/bin/bash\necho hi\n', 'README': 'demo'})
        app = dict(APP, sha256=hashlib.sha256(blob).hexdigest())
        return app, blob

    def test_install_verify_extract(self):
        app, blob = self.app_tar()
        dest = core.install(app, self.store, self.state, fetch_fn=lambda url: blob)
        self.assertTrue(os.path.exists(os.path.join(dest, 'run.sh')))
        state = core.load_state(self.state)
        self.assertEqual(state['demo-app']['version'], '1.0.0')

    def test_checksum_mismatch_refused(self):
        app, blob = self.app_tar()
        app['sha256'] = '0' * 64
        with self.assertRaises(core.BowerError) as ctx:
            core.install(app, self.store, self.state, fetch_fn=lambda url: blob)
        self.assertIn('checksum', str(ctx.exception))
        self.assertFalse(os.path.exists(os.path.join(self.store, 'demo-app')))

    def test_traversal_refused(self):
        blob = make_tar({'../evil': 'nope'})
        app = dict(APP, sha256=hashlib.sha256(blob).hexdigest())
        with self.assertRaises(core.BowerError):
            core.install(app, self.store, self.state, fetch_fn=lambda url: blob)

    def test_remove(self):
        app, blob = self.app_tar()
        core.install(app, self.store, self.state, fetch_fn=lambda url: blob)
        core.remove('demo-app', self.store, self.state)
        self.assertFalse(os.path.isdir(os.path.join(self.store, 'demo-app')))
        self.assertEqual(core.load_state(self.state), {})

    def test_run_app(self):
        app, blob = self.app_tar()
        core.install(app, self.store, self.state, fetch_fn=lambda url: blob)
        seen = []
        def ex(argv):
            seen.append(argv)
            return 0, 'ok'
        rc, out = core.run_app('demo-app', self.state, ex)
        self.assertEqual(rc, 0)
        self.assertTrue(seen[0][1].endswith('run.sh'))

    def test_run_missing(self):
        with self.assertRaises(core.BowerError):
            core.run_app('nope', self.state, lambda a: (0, ''))


if __name__ == '__main__':
    unittest.main(verbosity=1)
