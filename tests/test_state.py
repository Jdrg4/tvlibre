import os
import tempfile
import unittest

from tvlibre.state import State


class StateTest(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix='.json')
        os.close(fd)
        os.remove(self.path)

    def tearDown(self):
        if os.path.exists(self.path):
            os.remove(self.path)

    def test_state_umbral(self):
        s = State(self.path)
        s.set_resume('a', 20, 1000)
        self.assertIsNone(s.resume('a'))
        s.set_resume('a', 500, 1000)
        self.assertEqual(s.resume('a'), 500)
        s.set_resume('a', 960, 1000)
        self.assertIsNone(s.resume('a'))
        s.set_resume('b', 500, None)
        self.assertEqual(s.resume('b'), 500)

    def test_canales_ida_y_vuelta(self):
        s = State(self.path)
        self.assertIsNone(s.channels())
        s.set_channels([{'platform': 'kick', 'slug': 'a'}])
        self.assertEqual(State(self.path).channels(), [{'platform': 'kick', 'slug': 'a'}])

    def test_state_persiste(self):
        State(self.path).set_brightness(60)
        self.assertEqual(State(self.path).brightness(), 60)

    def test_brillo_acotado(self):
        s = State(self.path)
        self.assertEqual(s.brightness(), 100)
        s.set_brightness(5)
        self.assertEqual(s.brightness(), 30)
        s.set_brightness(250)
        self.assertEqual(s.brightness(), 100)

    def test_state_archivo_corrupto(self):
        with open(self.path, 'w') as f:
            f.write('{')
        self.assertEqual(State(self.path).brightness(), 100)


if __name__ == '__main__':
    unittest.main()
