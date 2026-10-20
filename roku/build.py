"""Arma el canal de Roku listo para instalar.

    python roku/build.py http://192.168.1.10:8099     ->  roku/dist/tvlibre-roku.zip
"""
import os
import re
import sys
import zipfile

ROOT = os.path.dirname(os.path.abspath(__file__))
PARTS = ('manifest', 'source', 'components', 'images')


def build(server, out):
    server = server.rstrip('/')
    if not re.match(r'^http://[A-Za-z0-9.\-\[\]:]+$', server):
        raise ValueError('el servidor va como http://<ip>:<puerto>, sin ruta')
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
        for part in PARTS:
            base = os.path.join(ROOT, part)
            paths = [base] if os.path.isfile(base) else \
                sorted(os.path.join(d, f) for d, _, fs in os.walk(base) for f in fs)
            for p in paths:
                rel = os.path.relpath(p, ROOT).replace(os.sep, '/')
                if rel == 'manifest':
                    with open(p, encoding='utf-8') as f:
                        text = f.read()
                    z.writestr(rel, re.sub(r'(?m)^tvlibre_server=.*$', 'tvlibre_server=' + server, text))
                else:
                    z.write(p, rel)
    return out


if __name__ == '__main__':
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    print(build(sys.argv[1], os.path.join(ROOT, 'dist', 'tvlibre-roku.zip')))
