import os
import re
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

def live_pl(seq, segs):
    """Playlist de directo: segs es una lista de nombres; los que empiezan por "ad" son anuncios."""
    out = ['#EXTM3U', '#EXT-X-VERSION:6', '#EXT-X-TARGETDURATION:5', '#EXT-X-MEDIA-SEQUENCE:%d' % seq]
    prev_ad = None
    for s in segs:
        ad = s.startswith('ad')
        if prev_ad is not None and ad != prev_ad:
            out.append('#EXT-X-DISCONTINUITY')
        if ad != prev_ad:
            out.append('#EXT-X-MAP:URI="%s"' % ('ad-init.mp4' if ad else 'init.mp4'))
        out += ['#EXTINF:2.000,%s' % ('Amazon|123' if ad else 'live'), s + '.mp4']
        prev_ad = ad
    return '\n'.join(out) + '\n'


class RewriteLiveTest(unittest.TestCase):
    def link(self, url, init):
        return 'L:%s|%s' % (url.rsplit('/', 1)[1], init.rsplit('/', 1)[1] if init else '')

    def segs(self, out):
        return [l.split('|')[0][2:].replace('.mp4', '') for l in out.splitlines() if l.startswith('L:')]

    def seq(self, out):
        return int(re.search(r'MEDIA-SEQUENCE:(\d+)', out).group(1))

    def test_anuncio_a_mitad_se_quita_y_la_secuencia_sigue(self):
        st = {}
        a = hls.rewrite_live(live_pl(500, ['s1', 's2', 's3']), BASE, self.link, st)
        self.assertEqual((self.seq(a), self.segs(a)), (0, ['s1', 's2', 's3']))
        self.assertNotIn('DISCONTINUITY', a)
        b = hls.rewrite_live(live_pl(502, ['s3', 'ad1', 'ad2']), BASE, self.link, st)
        self.assertEqual((self.seq(b), self.segs(b)), (2, ['s3']))
        c = hls.rewrite_live(live_pl(503, ['ad1', 'ad2', 's4', 's5']), BASE, self.link, st)
        self.assertEqual((self.seq(c), self.segs(c)), (3, ['s4', 's5']))
        # corte solo donde hubo hueco, y el segmento lleva su propio init
        self.assertIn('#EXT-X-DISCONTINUITY\n#EXTINF:2.000,live\nL:s4.mp4|init.mp4', c)
        self.assertNotIn('Amazon', b + c)
        self.assertNotIn('ad-init', b + c)

    def test_el_corte_que_sale_de_la_ventana_se_cuenta(self):
        st = {}
        hls.rewrite_live(live_pl(1, ['s1', 'ad1']), BASE, self.link, st)
        hls.rewrite_live(live_pl(2, ['ad1', 's2', 's3']), BASE, self.link, st)
        d = hls.rewrite_live(live_pl(4, ['s3', 's4']), BASE, self.link, st)
        self.assertEqual((self.seq(d), self.segs(d)), (2, ['s3', 's4']))
        self.assertNotIn('#EXT-X-DISCONTINUITY\n', d)
        self.assertIn('#EXT-X-DISCONTINUITY-SEQUENCE:1', d)

    def test_anuncio_inicial_sin_corte(self):
        st = {}
        a = hls.rewrite_live(live_pl(0, ['ad1', 'ad2']), BASE, self.link, st)
        self.assertEqual((self.seq(a), self.segs(a)), (0, []))
        b = hls.rewrite_live(live_pl(1, ['ad2', 's1', 's2']), BASE, self.link, st)
        self.assertEqual((self.seq(b), self.segs(b)), (0, ['s1', 's2']))
        self.assertNotIn('DISCONTINUITY', b)

    def test_sin_anuncios_queda_igual_que_antes(self):
        out = hls.rewrite_live(fixture('live_ads.m3u8'), BASE, self.link, {})
        self.assertEqual(self.segs(out), ['seg100.ts', 'seg101.ts'])
        self.assertIn('#EXT-X-DISCONTINUITY', out)
        self.assertNotIn('DATERANGE', out)


class MutedRangesTest(unittest.TestCase):
    def test_tramos_silenciados(self):
        pl = ('#EXTM3U\n#EXT-X-MAP:URI="init-0.mp4"\n#EXTINF:10.000,\n0.mp4\n#EXTINF:10.000,\n1-muted.mp4\n'
              '#EXTINF:10.000,\n2-muted.mp4\n#EXTINF:10.000,\n3.mp4\n#EXTINF:5.000,\n4-muted.mp4\n#EXT-X-ENDLIST\n')
        self.assertEqual(hls.muted_ranges(pl), [[10, 30], [40, 45]])

    def test_sin_silencios(self):
        self.assertEqual(hls.muted_ranges(fixture('vod_fmp4.m3u8')), [])


if __name__ == '__main__':
    unittest.main()
