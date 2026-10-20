import os
import unittest

from tvlibre.net import HttpError
from tvlibre.proxy import Proxy

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fixtures')


def fixture(name):
    with open(os.path.join(FIX, name), 'rb') as f:
        return f.read()


class FakeNet:
    def __init__(self, pages):
        self.pages, self.calls = pages, []

    def __call__(self, url, *a, **k):
        self.calls.append(url)
        v = self.pages[url]
        if isinstance(v, Exception):
            raise v
        return v


VOD = 'https://cdn.example.net/x/index.m3u8'


class ProxyTest(unittest.TestCase):
    def test_playlist_absoluta(self):
        p = Proxy(fetch=FakeNet({VOD: fixture('live_ads.m3u8')}))
        key = p.open(lambda: VOD)
        body, ctype = p.serve(key, 'tv.local:8099')
        self.assertEqual(ctype, 'application/vnd.apple.mpegurl')
        segs = [l for l in body.decode().splitlines() if l and not l.startswith('#')]
        self.assertEqual(len(segs), 3)
        for s in segs:
            self.assertTrue(s.startswith('http://tv.local:8099/h/'), s)
            self.assertTrue(s.endswith('.ts'), s)

    def test_segmento_fmp4_pasa_por_to_ts(self):
        net = FakeNet({VOD: fixture('vod_fmp4.m3u8'), 'https://cdn.example.net/x/init-0.mp4': b'INIT',
                       'https://cdn.example.net/x/0.mp4': b'S0', 'https://cdn.example.net/x/1.mp4': b'S1'})
        calls = []
        p = Proxy(fetch=net, to_ts=lambda init, seg: calls.append((init, seg)) or b'G' + seg)
        body, _ = p.serve(p.open(lambda: VOD), 'h')
        segs = [l for l in body.decode().splitlines() if l.startswith('http')]
        out = [p.serve(s.rsplit('/', 1)[1].split('.')[0], 'h') for s in segs]
        self.assertEqual(calls, [(b'INIT', b'S0'), (b'INIT', b'S1')])
        self.assertEqual(out[0], (b'GS0', 'video/mp2t'))
        self.assertEqual(net.calls.count('https://cdn.example.net/x/init-0.mp4'), 1)

    def test_segmento_ts_sin_conversion(self):
        net = FakeNet({VOD: fixture('live_ads.m3u8'), 'https://cdn.example.net/x/seg100.ts': b'G100'})
        p = Proxy(fetch=net, to_ts=lambda *a: self.fail('no debe convertir'))
        body, _ = p.serve(p.open(lambda: VOD), 'h')
        first = [l for l in body.decode().splitlines() if l.startswith('http')][0]
        self.assertEqual(p.serve(first.rsplit('/', 1)[1].split('.')[0], 'h'), (b'G100', 'video/mp2t'))

    def test_renueva_token(self):
        new = 'https://cdn.example.net/x/index.m3u8?token=2'
        net = FakeNet({VOD: HttpError(403, VOD), new: fixture('live_ads.m3u8')})
        urls = iter([VOD, new])
        n = [0]

        def resolver():
            n[0] += 1
            return next(urls)
        p = Proxy(fetch=net)
        key = p.open(resolver)
        body, _ = p.serve(key, 'h')
        self.assertEqual(n[0], 2)
        self.assertIn('#EXTM3U', body.decode())

    def test_lru(self):
        p = Proxy(fetch=FakeNet({}), max_entries=2)
        k1 = p.open(lambda: 'https://a/1.m3u8')
        p.open(lambda: 'https://a/2.m3u8')
        p.open(lambda: 'https://a/3.m3u8')
        with self.assertRaises(KeyError):
            p.serve(k1, 'h')


if __name__ == '__main__':
    unittest.main()
