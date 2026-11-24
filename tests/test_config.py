import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr
from io import StringIO

from tvlibre.config import load_config

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def write_tmp(data):
    f = tempfile.NamedTemporaryFile('w', suffix='.json', delete=False, encoding='utf-8')
    json.dump(data, f)
    f.close()
    return f.name


class ConfigTest(unittest.TestCase):
    def test_carga_ejemplo(self):
        cfg = load_config(os.path.join(ROOT, 'config.example.json'))
        self.assertEqual([c.platform for c in cfg.channels], ['twitch'] * len(cfg.channels))
        self.assertEqual(cfg.port, 8099)
        self.assertEqual(cfg.vods_per_channel, 20)
        self.assertEqual(cfg.language, 'es')

    def test_plataforma_invalida(self):
        with self.assertRaises(ValueError):
            load_config(write_tmp({'channels': [{'platform': 'youtube', 'slug': 'x'}]}))

    def test_kick_se_ignora_con_aviso(self):
        # una configuración de antes no impide arrancar
        err = StringIO()
        with redirect_stderr(err):
            cfg = load_config(write_tmp({'channels': [{'platform': 'kick', 'slug': 'k'},
                                                      {'platform': 'twitch', 'slug': 'T'}]}))
        self.assertEqual([(c.platform, c.slug) for c in cfg.channels], [('twitch', 't')])
        self.assertIn('kick/k', err.getvalue())

    def test_sin_plataforma_es_twitch(self):
        self.assertEqual(load_config(write_tmp({'channels': [{'slug': 'x'}]})).channels[0].platform, 'twitch')

    def test_sin_canales_vale(self):
        # se pueden agregar desde la pantalla
        self.assertEqual(load_config(write_tmp({'channels': []})).channels, [])

    def test_idioma(self):
        self.assertEqual(load_config(write_tmp({'language': 'EN'})).language, 'en')
        with self.assertRaises(ValueError):
            load_config(write_tmp({'language': 'es"]'}))


if __name__ == '__main__':
    unittest.main()
