import json
import os
import tempfile
import unittest

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
        self.assertEqual(len(cfg.channels), 2)
        self.assertEqual(cfg.port, 8099)
        self.assertEqual(cfg.vods_per_channel, 20)

    def test_plataforma_invalida(self):
        with self.assertRaises(ValueError):
            load_config(write_tmp({'channels': [{'platform': 'youtube', 'slug': 'x'}]}))

    def test_sin_canales(self):
        with self.assertRaises(ValueError):
            load_config(write_tmp({'channels': []}))


if __name__ == '__main__':
    unittest.main()
