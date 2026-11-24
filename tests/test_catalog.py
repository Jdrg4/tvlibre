import os
import tempfile
import unittest

from tvlibre.catalog import Catalog
from tvlibre.config import Channel, Config
from tvlibre.net import HttpError
from tvlibre.state import State


def vod(slug, n, started):
    return {'id': 'twitch-vod-%s' % n, 'platform': 'twitch', 'kind': 'vod', 'channel': slug,
            'title': 't', 'started_at': started, 'duration_s': 3600, 'viewers': None, 'thumb': None, 'ref': n}


def live(slug, viewers=1):
    return {'id': 'twitch-live-' + slug, 'platform': 'twitch', 'kind': 'live', 'channel': slug, 'viewers': viewers}


class FakeTwitch:
    """Un canal por slug: {slug: (directo, anteriores)}; error por slug o para todo."""
    def __init__(self, chans):
        self.chans, self.errors, self.error = chans, {}, None
        self.calls, self.found, self.disc, self.disc_calls = 0, [], [], 0
        self.tops, self.page_calls, self.items = [], 0, {}

    def _fail(self, slug=None):
        if self.error:
            raise self.error
        if slug in self.errors:
            raise self.errors[slug]

    def search(self, q):
        self._fail()
        return self.found

    def discover(self, slugs, exclude, n, lang):
        self.disc_calls += 1
        self._fail()
        return [i for i in self.disc if i['channel'] not in exclude]

    def top(self, lang, exclude, n):
        self._fail()
        return [i for i in self.tops if i['channel'] not in exclude][:n]

    def channel_state(self, slug, n):
        self.calls += 1
        self._fail(slug)
        l, v = self.chans[slug]
        return l, v[:n]

    def channel_page(self, slug, n):
        self.page_calls += 1
        self._fail(slug)
        if slug not in self.chans:
            raise ValueError('el canal de Twitch "%s" no existe' % slug)
        l, v = self.chans[slug]
        return {'channel': {'platform': 'twitch', 'slug': slug, 'name': slug.upper()}, 'live': l, 'vods': v[:n],
                'highlights': [vod(slug, 'h1', '2026-01-01T00:00:00Z')]}

    def item(self, item_id):
        if item_id not in self.items:
            raise KeyError(item_id)
        return self.items[item_id]


class CatalogTest(unittest.TestCase):
    def setUp(self):
        fd, path = tempfile.mkstemp(suffix='.json')
        os.close(fd)
        os.remove(path)
        self.state = State(path)
        self.cfg = Config(channels=[Channel('twitch', 'canal_a'), Channel('twitch', 'canal_b')])
        self.tw = FakeTwitch({
            'canal_a': (live('canal_a', 10), [vod('canal_a', 't1', '2026-10-19T10:00:00Z'),
                                              vod('canal_a', 't2', '2026-10-15T10:00:00Z')]),
            'canal_b': (None, [vod('canal_b', 'k1', '2026-10-17T10:00:00Z'),
                               vod('canal_b', 'k2', '2026-10-12T10:00:00Z')]),
            'otro': (live('otro', 5), [vod('otro', 'o1', '2026-10-10T10:00:00Z')])})
        self.now = [1000.0]
        self.cat = Catalog(self.cfg, {'twitch': self.tw}, self.state, clock=lambda: self.now[0],
                           spawn=lambda f: f())  # descubrir síncrono en los tests

    def test_mezcla_por_fecha(self):
        ids = [v['id'] for v in self.cat.home()['vods']]
        self.assertEqual(ids, ['twitch-vod-t1', 'twitch-vod-k1', 'twitch-vod-t2', 'twitch-vod-k2'])

    def test_directos_por_espectadores(self):
        self.tw.chans['canal_b'] = (live('canal_b', 99), [])
        self.assertEqual([l['id'] for l in self.cat.home()['live']], ['twitch-live-canal_b', 'twitch-live-canal_a'])

    def test_canal_caido(self):
        self.tw.errors['canal_b'] = HttpError(500, 'https://gql.twitch.tv/gql')
        home = self.cat.home()
        self.assertEqual(len(home['vods']), 2)
        self.assertEqual(len(home['live']), 1)
        self.assertEqual(len(home['errors']), 1)
        self.assertTrue(home['errors'][0].startswith('canal_b: '))

    def test_canal_colgado(self):
        # un canal que no responde no puede dejar la portada más allá del timeout de la TV
        import time as _t

        class Colgado(FakeTwitch):
            def channel_state(self, slug, n):
                if slug == 'canal_b':
                    _t.sleep(3)
                return super().channel_state(slug, n)
        cat = Catalog(self.cfg, {'twitch': Colgado(self.tw.chans)}, self.state, timeout=0.5, spawn=lambda f: None)
        t0 = _t.monotonic()
        home = cat.home()
        self.assertLess(_t.monotonic() - t0, 2)
        self.assertEqual(len(home['vods']), 2)
        self.assertTrue(home['errors'][0].startswith('canal_b: '))

    def test_cache(self):
        self.cat.home()
        self.cat.home()
        self.assertEqual(self.tw.calls, 2)  # uno por canal
        self.now[0] += 61
        self.cat.home()
        self.assertEqual(self.tw.calls, 4)

    def test_resume_en_items(self):
        self.state.set_resume('twitch-vod-k1', 600, 3600)
        vods = {v['id']: v for v in self.cat.home()['vods']}
        self.assertEqual(vods['twitch-vod-k1']['resume_s'], 600)
        self.assertNotIn('resume_s', vods['twitch-vod-t1'])

    def test_brillo_en_home(self):
        self.state.set_brightness(70)
        self.assertEqual(self.cat.home()['brightness'], 70)

    def test_calidad_por_defecto_en_home(self):
        self.cfg.default_quality = 720
        self.assertEqual(self.cat.home()['default_quality'], 720)

    # ---------- cualquier canal ----------
    def test_item_de_la_portada(self):
        self.cat.home()
        self.assertEqual(self.cat.item('twitch-vod-k1')['ref'], 'k1')

    def test_item_que_no_salio_en_ninguna_pantalla(self):
        # otro canal, o el servidor se reinició: se le pide a Twitch por su id
        self.tw.items['twitch-vod-x9'] = vod('alguien', 'x9', '2026-10-01T10:00:00Z')
        self.assertEqual(self.cat.item('twitch-vod-x9')['channel'], 'alguien')
        self.assertEqual(self.tw.calls, 0)  # sin recargar la portada entera
        with self.assertRaises(KeyError):
            self.cat.item('twitch-vod-nada')
        with self.assertRaises(KeyError):
            self.cat.item('kick-vod-viejo')

    def test_pagina_de_canal_sin_seguirlo(self):
        self.state.set_resume('twitch-vod-o1', 30, 600)
        p = self.cat.channel('otro')
        self.assertEqual((p['channel']['name'], p['channel']['following']), ('OTRO', False))
        self.assertEqual(p['live']['id'], 'twitch-live-otro')
        self.assertEqual(p['vods'][0]['resume_s'], 30)
        self.assertEqual(p['highlights'][0]['id'], 'twitch-vod-h1')
        # lo que muestra la página se puede reproducir sin más consultas
        self.assertEqual(self.cat.item('twitch-vod-o1')['channel'], 'otro')
        self.assertTrue(self.cat.channel('canal_a')['channel']['following'])

    def test_pagina_de_canal_en_cache(self):
        self.cat.channel('otro')
        self.cat.channel('otro')
        self.assertEqual(self.tw.page_calls, 1)
        self.now[0] += 61
        self.cat.channel('otro')
        self.assertEqual(self.tw.page_calls, 2)

    def test_pagina_de_canal_inexistente(self):
        with self.assertRaises(ValueError):
            self.cat.channel('nadie')

    # ---------- canales editables, búsqueda, "Lo más visto" y "También en vivo" ----------
    def test_channels_cae_a_config(self):
        self.assertEqual([(c.platform, c.slug) for c in self.cat.channels()],
                         [('twitch', 'canal_a'), ('twitch', 'canal_b')])

    def test_canales_de_kick_guardados_se_ignoran(self):
        # state.json de antes de quitar Kick
        self.state.set_channels([{'platform': 'kick', 'slug': 'viejo'}, {'platform': 'twitch', 'slug': 'canal_a'}])
        self.assertEqual([c.slug for c in self.cat.channels()], ['canal_a'])
        self.assertEqual(self.cat.home()['errors'], [])

    def test_follow_persiste_e_invalida(self):
        self.cat.home()
        self.cat.follow('twitch', 'otro', True)
        self.assertIn({'platform': 'twitch', 'slug': 'otro'}, self.state.channels())
        self.cat.home()
        self.assertEqual(self.tw.calls, 5)  # el caché se invalidó: 2 + 3 canales
        self.cat.follow('twitch', 'canal_a', False)
        self.assertEqual([c.slug for c in self.cat.channels()], ['canal_b', 'otro'])

    def test_unfollow_ultimo_canal(self):
        self.cat.follow('twitch', 'canal_a', False)
        self.cat.follow('twitch', 'canal_b', False)
        home = self.cat.home()
        self.assertEqual((home['live'], home['vods'], home['channels'], home['discover']), ([], [], [], []))

    def test_search_marca_seguidos(self):
        self.tw.found = [{'platform': 'twitch', 'slug': 'nuevo', 'live': False},
                         {'platform': 'twitch', 'slug': 'canal_a', 'live': True}]
        r = self.cat.search('x')
        # el orden es el de la plataforma (por seguidores)
        self.assertEqual([(x['slug'], x['following']) for x in r['results']], [('nuevo', False), ('canal_a', True)])
        self.assertEqual(r['errors'], [])

    def test_search_error(self):
        self.tw.error = HttpError(500, 'https://gql.twitch.tv/gql')
        r = self.cat.search('x')
        self.assertEqual(r['results'], [])
        self.assertTrue(r['errors'][0].startswith('twitch: '))

    def test_lo_mas_visto(self):
        self.tw.tops = [live('canal_a', 900), live('grande', 800), live('mediano', 50)]
        home = self.cat.home()
        self.assertEqual([t['id'] for t in home['top']], ['twitch-live-grande', 'twitch-live-mediano'])
        self.assertEqual(self.cat.item('twitch-live-grande')['viewers'], 800)

    def test_discover_excluye_y_no_repite(self):
        self.tw.disc = [live('poco', 5), live('canal_a', 99), live('mucho', 500), live('grande', 800)]
        self.tw.tops = [live('grande', 800)]
        disc = self.cat.home()['discover']
        self.assertEqual([d['id'] for d in disc], ['twitch-live-mucho', 'twitch-live-poco'])

    def test_discover_cache_5_min(self):
        self.cat.home()
        self.now[0] += 61
        self.cat.home()
        self.assertEqual(self.tw.disc_calls, 1)
        self.now[0] += 300
        self.cat.home()
        self.assertEqual(self.tw.disc_calls, 2)

    def test_discover_no_bloquea_la_portada(self):
        # descubrir hace muchas peticiones en serie: corre aparte y la portada usa lo último que haya
        pending = []
        cat = Catalog(self.cfg, {'twitch': self.tw}, self.state, clock=lambda: self.now[0], spawn=pending.append)
        self.tw.disc = [live('nuevo')]
        self.assertEqual(cat.home()['discover'], [])
        self.assertEqual(self.tw.disc_calls, 0)
        cat.home()
        self.assertEqual(len(pending), 1)  # no lanza otra búsqueda mientras la primera sigue
        pending.pop()()
        self.assertEqual([d['id'] for d in cat.home()['discover']], ['twitch-live-nuevo'])

    def test_discover_falla_silencioso(self):
        self.tw.error = HttpError(500, 'x')
        home = self.cat.home()
        self.assertEqual((home['discover'], home['top']), ([], []))
        self.assertEqual(len(home['errors']), 2)  # los de la portada (uno por canal), ninguno extra por descubrir

    def test_discover_reproducible(self):
        self.tw.disc = [live('nuevo')]
        self.cat.home()
        self.assertEqual(self.cat.item('twitch-live-nuevo')['channel'], 'nuevo')


if __name__ == '__main__':
    unittest.main()
