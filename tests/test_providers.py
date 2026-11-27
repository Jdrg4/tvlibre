import json
import os
import unittest

from tvlibre.providers import twitch

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fixtures')


def load(name):
    with open(os.path.join(FIX, name), encoding='utf-8') as f:
        return json.load(f)


class TwitchTest(unittest.TestCase):
    def test_twitch_offline(self):
        live, vods = twitch.parse_channel(load('twitch_channel.json'), 'ejemplo_twitch', 20)
        self.assertIsNone(live)
        self.assertEqual([v['id'] for v in vods], ['twitch-vod-1001', 'twitch-vod-1002', 'twitch-vod-1003'])
        self.assertEqual(vods[0]['duration_s'], 31470)
        self.assertEqual(vods[0]['kind'], 'vod')
        self.assertEqual(vods[0]['platform'], 'twitch')
        self.assertEqual(vods[0]['channel'], 'ejemplo_twitch')
        self.assertTrue(vods[0]['started_at'].endswith('Z'))
        self.assertTrue(vods[0]['thumb'].startswith('https://static-cdn.jtvnw.net/'))

    def test_twitch_live(self):
        live, _ = twitch.parse_channel(load('twitch_channel_live.json'), 'ejemplo_twitch', 20)
        self.assertEqual(live['id'], 'twitch-live-ejemplo_twitch')
        self.assertEqual(live['kind'], 'live')
        self.assertEqual(live['viewers'], 49413)
        self.assertIsNone(live['duration_s'])

    def test_twitch_live_excluye_grabacion(self):
        # mientras está en vivo, Twitch lista el directo en curso como anterior (empieza a la vez que el stream)
        _, vods = twitch.parse_channel(load('twitch_channel_live.json'), 'ejemplo_twitch', 20)
        self.assertNotIn('twitch-vod-1001', [v['id'] for v in vods])
        self.assertEqual(len(vods), 2)

    def test_limite_vods(self):
        _, vods = twitch.parse_channel(load('twitch_channel.json'), 'ejemplo_twitch', 2)
        self.assertEqual(len(vods), 2)



class DescubrirTest(unittest.TestCase):
    def test_twitch_parse_search(self):
        gql = {'data': {'searchFor': {'channels': {'edges': [
            {'item': {'login': 'uno', 'displayName': 'Uno', 'profileImageURL': 'https://static-cdn.jtvnw.net/u.png',
                      'stream': {'viewersCount': 321}}},
            {'item': {'login': 'dos', 'displayName': 'Dos', 'profileImageURL': None, 'stream': None}},
            {'item': {}}]}}}}
        res = twitch.parse_search(gql)
        self.assertEqual(res[0], {'platform': 'twitch', 'slug': 'uno', 'name': 'Uno',
                                  'avatar': 'https://static-cdn.jtvnw.net/u.png', 'live': True, 'viewers': 321,
                                  'followers': None, 'category': None})
        self.assertEqual((res[1]['live'], res[1]['viewers']), (False, None))
        self.assertEqual(len(res), 2)  # los resultados que no son canales se ignoran

    def test_twitch_parse_streams_excluye(self):
        def node(login, v):
            return {'node': {'broadcaster': {'login': login, 'displayName': login.title()}, 'title': 't',
                             'viewersCount': v, 'createdAt': '2026-10-20T01:00:00Z',
                             'previewImageURL': 'https://static-cdn.jtvnw.net/previews-ttv/live_user_%s.jpg' % login}}
        gql = {'data': {'game': {'name': 'Juego', 'streams': {'edges': [node('uno', 5), node('seguido', 9)]}}}}
        items = twitch.parse_streams(gql, {'seguido'})
        self.assertEqual([i['id'] for i in items], ['twitch-live-uno'])
        self.assertEqual((items[0]['ref'], items[0]['category'], items[0]['viewers']), ('uno', 'Juego', 5))


class PatchNet:
    """Sustituye net.fetch_json: responde según lo que aparezca en la consulta y guarda los pedidos."""
    def __init__(self, responses):
        self.responses, self.calls = responses, []

    def fetch(self, url, data=None, *a, **k):
        self.calls.append(data)
        for key, resp in self.responses:
            if key in data['query']:
                return resp
        raise AssertionError('consulta inesperada: ' + data['query'][:80])

    def __enter__(self):
        self.orig = twitch.net.fetch_json
        twitch.net.fetch_json = self.fetch
        return self.calls

    def __exit__(self, *a):
        twitch.net.fetch_json = self.orig


def video_node(i, created='2026-10-18T10:00:00Z'):
    return {'node': {'id': str(i), 'title': 'video %d' % i, 'lengthSeconds': 600, 'createdAt': created,
                     'previewThumbnailURL': 'https://static-cdn.jtvnw.net/cf_vods/x/%d.jpg' % i}}


class CualquierCanalTest(unittest.TestCase):
    def test_pagina_de_canal(self):
        gql = {'data': {'user': {
            'login': 'canal_a', 'displayName': 'CanalA', 'description': ' hola ',
            'profileImageURL': 'https://static-cdn.jtvnw.net/a.png', 'followers': {'totalCount': 1234},
            'lastBroadcast': {'startedAt': '2026-10-19T23:00:00Z', 'game': {'name': 'Juego'}},
            'stream': {'title': 'en vivo', 'viewersCount': 50, 'createdAt': '2026-10-19T23:00:00Z',
                       'game': {'name': 'Juego'}, 'previewImageURL': 'https://static-cdn.jtvnw.net/l.jpg'},
            'videos': {'edges': [video_node(1, '2026-10-19T23:00:05Z'), video_node(2)]},
            'highlights': {'edges': [video_node(3)]}}}}
        p = twitch.parse_page(gql, 'canal_a', 20)
        self.assertEqual(p['channel'], {'platform': 'twitch', 'slug': 'canal_a', 'name': 'CanalA', 'description': 'hola',
                                        'avatar': 'https://static-cdn.jtvnw.net/a.png', 'followers': 1234,
                                        'last_live': '2026-10-19T23:00:00Z', 'category': 'Juego'})
        self.assertEqual((p['live']['id'], p['live']['name'], p['live']['category']),
                         ('twitch-live-canal_a', 'CanalA', 'Juego'))
        self.assertEqual([v['id'] for v in p['vods']], ['twitch-vod-2'])  # el 1 es el directo en curso
        self.assertEqual([v['id'] for v in p['highlights']], ['twitch-vod-3'])

    def test_pagina_canal_inexistente(self):
        with self.assertRaises(ValueError):
            twitch.parse_page({'data': {'user': None}}, 'nadie', 20)

    def test_item_en_vivo_sin_consultar(self):
        with PatchNet([]) as calls:
            it = twitch.item('twitch-live-canal_a')
        self.assertEqual((it['kind'], it['ref'], it['channel']), ('live', 'canal_a', 'canal_a'))
        self.assertEqual(calls, [])

    def test_item_anterior_consulta_el_video(self):
        v = dict(video_node(77)['node'], owner={'login': 'canal_b', 'displayName': 'CanalB'})
        with PatchNet([('video(id:', {'data': {'video': v}})]) as calls:
            it = twitch.item('twitch-vod-77')
        self.assertEqual((it['id'], it['channel'], it['name'], it['ref']), ('twitch-vod-77', 'canal_b', 'CanalB', '77'))
        self.assertEqual(calls[0]['variables'], {'v': '77'})

    def test_item_invalido(self):
        for bad in ('twitch-vod-abc', 'kick-live-x', 'twitch-live-' + 'a' * 30, 'twitch-otro-1'):
            with self.assertRaises(KeyError, msg=bad):
                twitch.item(bad)
        with PatchNet([('video(id:', {'data': {'video': None}})]):
            with self.assertRaises(KeyError):
                twitch.item('twitch-vod-404')

    def test_lo_mas_visto(self):
        def node(login, v):
            return {'node': {'broadcaster': {'login': login, 'displayName': login.upper()}, 'title': 't',
                             'viewersCount': v, 'createdAt': '2026-10-20T01:00:00Z', 'game': {'name': 'G'},
                             'previewImageURL': None}}
        gql = {'data': {'streams': {'edges': [node('uno', 9), node('seguido', 8), node('dos', 7), node('tres', 6)]}}}
        with PatchNet([('streams(first:', gql)]) as calls:
            items = twitch.top('es', {'seguido'}, 2)
        self.assertEqual([i['id'] for i in items], ['twitch-live-uno', 'twitch-live-dos'])
        self.assertEqual((items[0]['name'], items[0]['category']), ('UNO', 'G'))
        self.assertIn('languages:[ES]', calls[0]['query'])  # en streams el idioma es un enum
        self.assertEqual(calls[0]['variables'], {'n': 3})  # pide de más por los que se excluyen
        with self.assertRaises(ValueError):
            twitch.top('es"]}){', set(), 2)

    def test_busqueda_junta_y_ordena_por_seguidores(self):
        def u(login, f):
            return {'login': login, 'followers': {'totalCount': f}, 'stream': None}
        gql = {'data': {'searchFor': {'channels': {'edges': [{'item': u('famoso11', 3000000)}, {'item': u('otro', 50)},
                                                             {'item': {}}]}},
                        'searchUsers': {'edges': [{'node': u('buscado', 85)}, {'node': u('famoso11', 3000000)},
                                                  {'node': u('mediano', 9000)}]}}}
        # el nombre exacto con 85 seguidores no tapa al streamer conocido
        self.assertEqual([r['slug'] for r in twitch.parse_search(gql, 'Buscado')],
                         ['famoso11', 'mediano', 'buscado', 'otro'])
        gql['data']['searchUsers']['edges'][0]['node']['followers']['totalCount'] = 1500
        self.assertEqual(twitch.parse_search(gql, ' BUSCADO ')[0]['slug'], 'buscado')

    def test_busqueda_una_sola_consulta(self):
        with PatchNet([('searchFor', {'data': {}})]) as calls:
            self.assertEqual(twitch.search('alexby'), [])
        self.assertEqual(len(calls), 1)
        self.assertIn('searchUsers', calls[0]['query'])

class CuentaTest(unittest.TestCase):
    TOKEN = 'a' * 30  # inventado

    def setUp(self):
        self.orig = twitch.net.fetch_json
        self.headers = []
        twitch._auth.update(token=None, login=None)

    def tearDown(self):
        twitch.net.fetch_json = self.orig
        twitch._auth.update(token=None, login=None)

    def fake(self, reject=False):
        def fetch(url, data=None, headers=None, *a, **k):
            self.headers.append(dict(headers or {}))
            if 'Authorization' in (headers or {}) and reject:
                raise twitch.net.HttpError(401, url)
            if 'currentUser' in data['query']:
                return {'data': {'currentUser': {'login': 'yo'}}}
            return {'data': {'streamPlaybackAccessToken': {'value': '{}', 'signature': 's'}}}
        twitch.net.fetch_json = fetch

    def test_el_token_va_en_el_pedido_de_acceso(self):
        self.fake()
        self.assertEqual(twitch.use_account('OAuth ' + self.TOKEN + '\n'), 'yo')
        twitch.master_url({'id': 'twitch-live-x', 'kind': 'live', 'ref': 'x'})
        self.assertEqual(self.headers[-1]['Authorization'], 'OAuth ' + self.TOKEN)

    def test_sin_cuenta_no_manda_token(self):
        self.fake()
        twitch.master_url({'id': 'twitch-live-x', 'kind': 'live', 'ref': 'x'})
        self.assertNotIn('Authorization', self.headers[-1])

    def test_token_invalido(self):
        self.fake(reject=True)
        for bad in ('', 'corto', 'con espacios dentro de el token 123'):
            with self.assertRaises(ValueError, msg=bad):
                twitch.use_account(bad)
        with self.assertRaises(ValueError):
            twitch.use_account(self.TOKEN)
        self.assertIsNone(twitch._auth['token'])

    def test_si_caduca_sigue_sin_cuenta(self):
        self.fake()
        twitch.use_account(self.TOKEN)
        self.fake(reject=True)
        url = twitch.master_url({'id': 'twitch-live-x', 'kind': 'live', 'ref': 'x'})
        self.assertIn('usher.ttvnw.net', url)
        self.assertNotIn('Authorization', self.headers[-1])
        self.assertIsNone(twitch._auth['token'])


if __name__ == '__main__':
    unittest.main()
