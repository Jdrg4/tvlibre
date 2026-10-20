import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request

from tvlibre.config import Channel, Config
from tvlibre.proxy import Proxy
from tvlibre.server import build, is_allowed
from tvlibre.state import State

MASTER = ('#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=1,RESOLUTION=1920x1080,FRAME-RATE=30.000\n1080/i.m3u8\n'
          '#EXT-X-STREAM-INF:BANDWIDTH=1,RESOLUTION=1280x720,FRAME-RATE=30.000\n720/i.m3u8\n').encode()
ITEMS = {
    'kick-live-ejemplo_kick': {'id': 'kick-live-ejemplo_kick', 'platform': 'kick', 'kind': 'live'},
    'twitch-vod-1001': {'id': 'twitch-vod-1001', 'platform': 'twitch', 'kind': 'vod', 'duration_s': 3600},
}


class FakeCatalog:
    def home(self):
        return {'live': [], 'vods': list(ITEMS.values()), 'errors': [], 'brightness': 100}

    def item(self, item_id):
        return ITEMS[item_id]

    @staticmethod
    def route(item):
        return 'direct' if item['platform'] == 'kick' and item['kind'] == 'live' else 'proxy'


class FakeProvider:
    def __init__(self, url):
        self.url = url

    def master_url(self, item):
        return self.url


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


class ServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.state = State(os.path.join(cls.tmp, 'state.json'))
        pages = {'https://kick.cdn/m.m3u8': MASTER, 'https://tw.cdn/m.m3u8': MASTER,
                 'https://images.kick.com/x/720.webp': b'RIFF'}
        fetch = lambda url, *a, **k: pages[url]
        cfg = Config(port=0, state_path=os.path.join(cls.tmp, 'state.json'), channels=[Channel('kick', 'ejemplo_kick')])
        cls.srv = build(cfg, catalog=FakeCatalog(), state=cls.state, proxy=Proxy(fetch=fetch), fetch=fetch,
                        providers={'kick': FakeProvider('https://kick.cdn/m.m3u8'),
                                   'twitch': FakeProvider('https://tw.cdn/m.m3u8')})
        cls.base = 'http://127.0.0.1:%d' % cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def get(self, path):
        opener = urllib.request.build_opener(NoRedirect)
        try:
            r = opener.open(self.base + path, timeout=5)
            return r.status, r.headers, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.headers, e.read()

    def post(self, path, data):
        r = urllib.request.Request(self.base + path, data=json.dumps(data).encode(),
                                   headers={'Content-Type': 'application/json'})
        return urllib.request.urlopen(r, timeout=5).status

    def test_ip_publica_403(self):
        self.assertFalse(is_allowed('8.8.8.8'))
        self.assertFalse(is_allowed('200.1.2.3'))
        for ip in ('100.64.0.1', '192.168.1.50', '127.0.0.1', '10.0.0.5', '172.20.1.1', '::1'):
            self.assertTrue(is_allowed(ip), ip)

    def test_img_cacheable(self):
        code, h, _ = self.get('/img?u=' + urllib.parse.quote('https://images.kick.com/x/720.webp', safe=''))
        self.assertEqual(code, 200)
        self.assertEqual(h.get_all('Cache-Control'), ['max-age=3600'])

    def raw_post(self, path, body, ctype, host=None):
        h = {'Content-Type': ctype}
        if host:
            h['Host'] = host
        r = urllib.request.Request(self.base + path, data=body, headers=h)
        try:
            return urllib.request.urlopen(r, timeout=5).status
        except urllib.error.HTTPError as e:
            return e.code

    def test_post_sin_json_415(self):
        # un <form> o fetch "simple" de otra web manda text/plain sin preflight CORS
        self.assertEqual(self.raw_post('/api/state', b'{"brightness": 40}', 'text/plain'), 415)
        self.assertNotEqual(self.state.brightness(), 40)

    def test_host_ajeno_403(self):
        # DNS rebinding: el navegador manda el nombre del atacante en Host
        self.assertEqual(self.get_host('/api/home', 'evil.example.com:8099'), 403)
        self.assertEqual(self.get_host('/api/home', '192.168.1.20:8099'), 200)
        self.assertEqual(self.get_host('/api/home', 'localhost:8099'), 200)

    def get_host(self, path, host):
        r = urllib.request.Request(self.base + path, headers={'Host': host})
        try:
            return urllib.request.urlopen(r, timeout=5).status
        except urllib.error.HTTPError as e:
            return e.code

    def test_post_infinito_400(self):
        self.assertEqual(self.raw_post('/api/state', b'{"brightness": Infinity}', 'application/json'), 400)

    def test_diagnostico_con_tope(self):
        import tvlibre.server as srv
        path = os.path.join(self.tmp, 'diagnostico.jsonl')
        with open(path, 'a', encoding='utf-8') as f:
            f.write('x' * (srv.DIAG_MAX + 1))
        size = os.path.getsize(path)
        self.assertEqual(self.post('/api/diagnostico', {'keys': [1]}), 204)
        self.assertEqual(os.path.getsize(path), size)
        os.remove(path)

    def test_play_redirect_absoluto(self):
        code, h, _ = self.get('/play/kick-live-ejemplo_kick.m3u8?q=720')
        self.assertEqual(code, 302)
        self.assertEqual(h['Location'], 'https://kick.cdn/720/i.m3u8')
        code, h, _ = self.get('/play/twitch-vod-1001.m3u8?q=1080')
        self.assertEqual(code, 302)
        self.assertTrue(h['Location'].startswith(self.base + '/h/'), h['Location'])
        self.assertTrue(h['Location'].endswith('.m3u8'))

    def test_play_item_invalido(self):
        self.assertEqual(self.get('/play/../../etc.m3u8')[0], 404)
        self.assertEqual(self.get('/play/twitch-vod-9999.m3u8')[0], 404)

    def test_h_desconocida_404(self):
        self.assertEqual(self.get('/h/0123456789abcdef.ts')[0], 404)

    def test_img_host_no_permitido(self):
        self.assertEqual(self.get('/img?u=https://evil.com/x.jpg')[0], 400)
        self.assertEqual(self.get('/img?u=https://images.kick.com.evil.com/x.jpg')[0], 400)

    def test_home_json(self):
        code, _, body = self.get('/api/home')
        self.assertEqual(code, 200)
        self.assertTrue({'live', 'vods', 'errors', 'brightness'} <= set(json.loads(body)))

    def test_resume_post(self):
        self.assertEqual(self.post('/api/resume', {'id': 'twitch-vod-1001', 'position_s': 700, 'duration_s': 3600}), 204)
        self.assertEqual(self.state.resume('twitch-vod-1001'), 700)

    def test_brillo_post(self):
        self.assertEqual(self.post('/api/state', {'brightness': 50}), 204)
        self.assertEqual(self.state.brightness(), 50)

    def test_diagnostico_post(self):
        path = os.path.join(self.tmp, 'diagnostico.jsonl')
        before = open(path).read().count('\n') if os.path.exists(path) else 0
        self.assertEqual(self.post('/api/diagnostico', {'keys': [37, 13]}), 204)
        with open(path, encoding='utf-8') as f:
            lines = f.read().splitlines()
        self.assertEqual(len(lines), before + 1)
        self.assertEqual(json.loads(lines[-1])['data'], {'keys': [37, 13]})

    def test_diagnostico_pagina(self):
        code, h, body = self.get('/diagnostico')
        self.assertEqual(code, 200)
        self.assertIn(b'/api/diagnostico', body)

    def test_static_sin_escape(self):
        self.assertEqual(self.get('/static/..%2F..%2Fconfig.py')[0], 404)


if __name__ == '__main__':
    unittest.main()
