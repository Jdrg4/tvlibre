"""Guarda: el front corre en navegadores de TV de 2014 (Chrome 39): solo ES5 y CSS sin grid."""
import glob
import os
import re
import unittest

WEB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tvlibre', 'web')
PROHIBIDO = [r'=>', r'\blet\s', r'\bconst\s', r'`', r'\bclass\s+[A-Za-z_]', r'\bfetch\(', r'display:\s*grid',
             r'\.\.\.[A-Za-z_\[]', r'\basync\s+function', r'\bawait\s']


class Es5Test(unittest.TestCase):
    def test_frontend_es5(self):
        files = glob.glob(os.path.join(WEB, '*.js')) + glob.glob(os.path.join(WEB, '*.html')) + \
            glob.glob(os.path.join(WEB, '*.css'))
        self.assertTrue(files)
        hallazgos = []
        for path in files:
            with open(path, encoding='utf-8') as f:
                for n, line in enumerate(f, 1):
                    for pat in PROHIBIDO:
                        if re.search(pat, line):
                            hallazgos.append('%s:%d %s' % (os.path.basename(path), n, pat))
        self.assertEqual(hallazgos, [])

    def test_index_existe(self):
        for name in ('index.html', 'app.js', 'app.css'):
            self.assertTrue(os.path.exists(os.path.join(WEB, name)), name)


if __name__ == '__main__':
    unittest.main()
