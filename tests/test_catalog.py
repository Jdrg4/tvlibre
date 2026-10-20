import os
import tempfile
import unittest

from tvlibre.catalog import Catalog
from tvlibre.config import Channel, Config
from tvlibre.net import HttpError
from tvlibre.state import State


def vod(platform, slug, n, started):
    return {'id': '%s-vod-%s' % (platform, n), 'platform': platform, 'kind': 'vod', 'channel': slug,
            'title': 't', 'started_at': started, 'duration_s': 3600, 'viewers': None, 'thumb': None, 'ref': n}


class FakeProvider:
    def __init__(self, live, vods, error=None):
        self.live, self.vods, self.error, self.calls = live, vods, error, 0

    def channel_state(self, slug, n):
        self.calls += 1
        if self.error:
            raise self.error
        return self.live, self.vods[:n]


class CatalogTest(unittest.TestCase):
    def setUp(self):
        fd, path = tempfile.mkstemp(suffix='.json')
        os.close(fd)
        os.remove(path)
        self.state = State(path)
        self.cfg = Config(channels=[Channel('twitch', 'ejemplo_twitch'), Channel('kick', 'ejemplo_kick')])
        self.tw = FakeProvider({'id': 'twitch-live-ejemplo_twitch', 'platform': 'twitch', 'kind': 'live',
                                'channel': 'ejemplo_twitch'},
                               [vod('twitch', 'ejemplo_twitch', 't1', '2026-10-19T10:00:00Z'),
                                vod('twitch', 'ejemplo_twitch', 't2', '2026-10-15T10:00:00Z')])
        self.ki = FakeProvider(None, [vod('kick', 'ejemplo_kick', 'k1', '2026-10-17T10:00:00Z'),
                                      vod('kick', 'ejemplo_kick', 'k2', '2026-10-12T10:00:00Z')])
        self.now = [1000.0]
        self.cat = Catalog(self.cfg, {'twitch': self.tw, 'kick': self.ki}, self.state, clock=lambda: self.now[0])

    def test_mezcla_por_fecha(self):
        ids = [v['id'] for v in self.cat.home()['vods']]
        self.assertEqual(ids, ['twitch-vod-t1', 'kick-vod-k1', 'twitch-vod-t2', 'kick-vod-k2'])

    def test_proveedor_caido(self):
        self.ki.error = HttpError(500, 'https://kick.com/api/v2/channels/ejemplo_kick')
        home = self.cat.home()
        self.assertEqual(len(home['vods']), 2)
        self.assertEqual(len(home['live']), 1)
        self.assertEqual(len(home['errors']), 1)
        self.assertTrue(home['errors'][0].startswith('kick/ejemplo_kick: '))

    def test_proveedor_colgado(self):
        # una plataforma que no responde no puede dejar la portada más allá del timeout de la TV
        import time as _t

        class Colgado(FakeProvider):
            def channel_state(self, slug, n):
                _t.sleep(3)
                return None, []
        cat = Catalog(self.cfg, {'twitch': self.tw, 'kick': Colgado(None, [])}, self.state, timeout=0.5)
        t0 = _t.monotonic()
        home = cat.home()
        self.assertLess(_t.monotonic() - t0, 2)
        self.assertEqual(len(home['vods']), 2)
        self.assertTrue(home['errors'][0].startswith('kick/ejemplo_kick: '))

    def test_cache(self):
        self.cat.home()
        self.cat.home()
        self.assertEqual(self.tw.calls, 1)
        self.now[0] += 61
        self.cat.home()
        self.assertEqual(self.tw.calls, 2)

    def test_resume_en_items(self):
        self.state.set_resume('kick-vod-k1', 600, 3600)
        vods = {v['id']: v for v in self.cat.home()['vods']}
        self.assertEqual(vods['kick-vod-k1']['resume_s'], 600)
        self.assertNotIn('resume_s', vods['twitch-vod-t1'])

    def test_brillo_en_home(self):
        self.state.set_brightness(70)
        self.assertEqual(self.cat.home()['brightness'], 70)

    def test_calidad_por_defecto_en_home(self):
        self.cfg.default_quality = 720
        self.assertEqual(self.cat.home()['default_quality'], 720)

    def test_route(self):
        self.assertEqual(self.cat.route({'platform': 'kick', 'kind': 'live'}), 'direct')
        self.assertEqual(self.cat.route({'platform': 'kick', 'kind': 'vod'}), 'proxy')
        self.assertEqual(self.cat.route({'platform': 'twitch', 'kind': 'live'}), 'proxy')

    def test_item_refresca_si_falta(self):
        self.cat.home()
        self.ki.vods.append(vod('kick', 'ejemplo_kick', 'k9', '2026-10-01T10:00:00Z'))
        self.assertEqual(self.cat.item('kick-vod-k9')['ref'], 'k9')
        with self.assertRaises(KeyError):
            self.cat.item('kick-vod-nada')


if __name__ == '__main__':
    unittest.main()
