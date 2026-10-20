import json
import os
import unittest

from tvlibre.providers import kick, twitch

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


class KickTest(unittest.TestCase):
    def test_kick_live_excluye_grabacion(self):
        live, vods = kick.parse_channel(load('kick_channel_live.json'), load('kick_videos.json'), 'ejemplo_kick', 20)
        self.assertEqual(live['id'], 'kick-live-ejemplo_kick')
        self.assertEqual(live['viewers'], load('kick_channel_live.json')['livestream']['viewer_count'])
        self.assertNotIn('kick-vod-00000000-0000-4000-8000-000000000000', [v['id'] for v in vods])
        self.assertEqual(len(vods), 3)

    def test_kick_live_miniatura_de_la_grabacion(self):
        # la miniatura de stream.kick.com/thumbnails/livestream da 403; la del video en curso sí carga
        live, _ = kick.parse_channel(load('kick_channel_live.json'), load('kick_videos.json'), 'ejemplo_kick', 20)
        self.assertEqual(live['thumb'], 'https://images.kick.com/video_thumbnails/ejemplo/0/720.webp')

    def test_kick_duracion_ms(self):
        _, vods = kick.parse_channel(load('kick_channel_offline.json'), load('kick_videos.json'), 'ejemplo_kick', 20)
        first = vods[0]
        self.assertEqual(first['id'], 'kick-vod-00000000-0000-4000-8000-000000000001')
        self.assertEqual(first['duration_s'], 21083)
        self.assertEqual(first['started_at'], '2026-10-19T00:10:01Z')
        self.assertEqual(first['ref'], 'https://stream.kick.com/abc/ivs/v1/1/ejemplo/1/media/hls/master.m3u8')

    def test_kick_offline(self):
        live, _ = kick.parse_channel(load('kick_channel_offline.json'), load('kick_videos.json'), 'ejemplo_kick', 20)
        self.assertIsNone(live)

    def test_limite_vods(self):
        _, vods = kick.parse_channel(load('kick_channel_offline.json'), load('kick_videos.json'), 'ejemplo_kick', 2)
        self.assertEqual(len(vods), 2)


if __name__ == '__main__':
    unittest.main()
