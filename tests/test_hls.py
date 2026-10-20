import os
import unittest

from tvlibre import hls

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fixtures')
BASE = 'https://cdn.example.net/x/master.m3u8'


def fixture(name):
    with open(os.path.join(FIX, name), encoding='utf-8') as f:
        return f.read()


class PickVariantTest(unittest.TestCase):
    def test_pick_1080(self):
        # a igual altura gana la de menos fps; con empate, la primera (aquí: 1080p60, no chunked)
        url = hls.pick_variant(fixture('master.m3u8'), BASE, 1080)
        self.assertEqual(url, 'https://cdn.example.net/x/1080p60/index.m3u8')

    def test_pick_720(self):
        self.assertEqual(hls.pick_variant(fixture('master.m3u8'), BASE, 720),
                         'https://cdn.example.net/x/720p60/index.m3u8')

    def test_pick_menor_que_todas(self):
        self.assertEqual(hls.pick_variant(fixture('master.m3u8'), BASE, 100),
                         'https://cdn.example.net/x/360p30/index.m3u8')

    def test_media_playlist_devuelve_base(self):
        self.assertEqual(hls.pick_variant(fixture('vod_fmp4.m3u8'), BASE, 1080), BASE)


class RewriteTest(unittest.TestCase):
    def setUp(self):
        self.calls = []

    def link(self, url, init):
        self.calls.append((url, init))
        return 'http://tv/h/%d.ts' % len(self.calls)

    def test_rewrite_quita_etiquetas(self):
        out = hls.rewrite_playlist(fixture('live_ads.m3u8'), BASE, self.link)
        self.assertNotIn('DATERANGE', out)
        self.assertNotIn('PROGRAM-DATE-TIME', out)
        self.assertIn('#EXT-X-DISCONTINUITY', out)
        self.assertIn('#EXT-X-MEDIA-SEQUENCE:100', out)
        self.assertEqual([c[0] for c in self.calls], [
            'https://cdn.example.net/x/seg100.ts', 'https://ads.example.net/ad1.ts',
            'https://cdn.example.net/x/seg101.ts'])
        self.assertEqual(out.count('http://tv/h/'), 3)

    def test_rewrite_init(self):
        out = hls.rewrite_playlist(fixture('vod_fmp4.m3u8'), BASE, self.link)
        self.assertEqual(self.calls[0], ('https://cdn.example.net/x/0.mp4', 'https://cdn.example.net/x/init-0.mp4'))
        self.assertNotIn('EXT-X-MAP', out)
        self.assertNotIn('TWITCH-TOTAL-SECS', out)
        self.assertIn('#EXT-X-ENDLIST', out)
        self.assertEqual(out.count('#EXTINF'), 2)

    def test_rewrite_sin_init(self):
        hls.rewrite_playlist(fixture('live_ads.m3u8'), BASE, self.link)
        self.assertTrue(all(init is None for _, init in self.calls))




class MutedRangesTest(unittest.TestCase):
    def test_tramos_silenciados(self):
        pl = ('#EXTM3U\n#EXT-X-MAP:URI="init-0.mp4"\n#EXTINF:10.000,\n0.mp4\n#EXTINF:10.000,\n1-muted.mp4\n'
              '#EXTINF:10.000,\n2-muted.mp4\n#EXTINF:10.000,\n3.mp4\n#EXTINF:5.000,\n4-muted.mp4\n#EXT-X-ENDLIST\n')
        self.assertEqual(hls.muted_ranges(pl), [[10, 30], [40, 45]])

    def test_sin_silencios(self):
        self.assertEqual(hls.muted_ranges(fixture('vod_fmp4.m3u8')), [])


if __name__ == '__main__':
    unittest.main()
