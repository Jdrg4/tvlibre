import json
import os
import subprocess
import tempfile
import unittest

from tvlibre import remux


@unittest.skipUnless(remux.available(), 'sin ffmpeg')
class RemuxTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fd, path = tempfile.mkstemp(suffix='.mp4')
        os.close(fd)
        subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'lavfi', '-i', 'testsrc=size=320x240:rate=25',
                        '-f', 'lavfi', '-i', 'sine', '-t', '2', '-c:v', 'libx264', '-c:a', 'aac',
                        '-movflags', 'frag_keyframe+empty_moov+default_base_moof', '-f', 'mp4', path], check=True)
        with open(path, 'rb') as f:
            cls.fmp4 = f.read()
        os.remove(path)

    def test_to_ts_convierte(self):
        out = remux.to_ts(b'', self.fmp4)
        self.assertEqual(out[:1], b'G')
        fd, path = tempfile.mkstemp(suffix='.ts')
        with os.fdopen(fd, 'wb') as f:
            f.write(out)
        probe = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'stream=codec_name', '-of', 'json', path],
                               capture_output=True, check=True)
        os.remove(path)
        codecs = {s['codec_name'] for s in json.loads(probe.stdout)['streams']}
        self.assertEqual(codecs, {'h264', 'aac'})

    def test_to_ts_basura(self):
        with self.assertRaises(remux.RemuxError):
            remux.to_ts(b'', b'no es video')


if __name__ == '__main__':
    unittest.main()
