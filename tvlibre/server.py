"""Servidor HTTP de tvlibre (solo red local)."""
import ipaddress
import json
import os
import re
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from tvlibre import hls, net
from tvlibre.catalog import Catalog
from tvlibre.providers import kick, twitch
from tvlibre.proxy import Proxy
from tvlibre.state import State

WEB = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'web')
LAN = [ipaddress.ip_network(n) for n in
       ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16', '127.0.0.0/8', '100.64.0.0/10', '::1/128')]
ITEM_RE = re.compile(r'^[a-z0-9_-]+$')
STATIC_RE = re.compile(r'^[A-Za-z0-9_-]+\.(html|js|css|png|svg|ico)$')
IMG_HOSTS = ('jtvnw.net', 'kick.com', 'live-video.net')
DIAG_MAX = 5 * 1024 * 1024
TYPES = {'html': 'text/html; charset=utf-8', 'js': 'application/javascript; charset=utf-8',
         'css': 'text/css; charset=utf-8', 'png': 'image/png', 'svg': 'image/svg+xml', 'ico': 'image/x-icon',
         'jpg': 'image/jpeg', 'jpeg': 'image/jpeg', 'webp': 'image/webp'}


def is_allowed(ip):
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    if getattr(addr, 'ipv4_mapped', None):
        addr = addr.ipv4_mapped
    return any(addr in n for n in LAN if n.version == addr.version)


def host_allowed(host):
    # contra DNS rebinding: solo se atiende si el navegador llegó por IP o por localhost
    name = (host or '').strip().lower()
    if name.startswith('['):
        name = name[1:name.find(']')]
    elif name.count(':') == 1:
        name = name.split(':')[0]
    if name == 'localhost':
        return True
    try:
        ipaddress.ip_address(name)
        return True
    except ValueError:
        return False


def _img_allowed(url):
    p = urlparse(url)
    host = (p.hostname or '').lower()
    return p.scheme == 'https' and any(host == h or host.endswith('.' + h) for h in IMG_HOSTS)


def make_handler(app):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'

        def log_message(self, fmt, *args):
            if app.get('verbose'):
                super().log_message(fmt, *args)

        def send(self, code, body=b'', ctype='text/plain; charset=utf-8', headers=None):
            self.send_response(code)
            self.send_header('Content-Type', ctype)
            self.send_header('Content-Length', str(len(body)))
            h = {'Cache-Control': 'no-store'}
            h.update(headers or {})
            for k, v in h.items():
                self.send_header(k, v)
            self.end_headers()
            if self.command != 'HEAD':
                self.wfile.write(body)

        def redirect(self, location):
            if location.startswith('/'):  # el reproductor de la TV no sigue redirecciones relativas
                location = 'http://%s%s' % (self.headers.get('Host'), location)
            self.send(302, headers={'Location': location})

        def file(self, name):
            ext = name.rsplit('.', 1)[1]
            with open(os.path.join(WEB, name), 'rb') as f:
                self.send(200, f.read(), TYPES[ext])

        def body_json(self):
            n = int(self.headers.get('Content-Length') or 0)
            return json.loads(self.rfile.read(n) or b'{}')

        def guard(self):
            if not is_allowed(self.client_address[0]) or not host_allowed(self.headers.get('Host')):
                self.send(403, b'tvlibre solo atiende la red local')
                return False
            return True

        def do_GET(self):
            if not self.guard():
                return
            u = urlparse(self.path)
            path, qs = u.path, parse_qs(u.query)
            try:
                if path == '/':
                    return self.file('index.html')
                if path == '/diagnostico':
                    return self.file('diagnostico.html')
                if path.startswith('/static/'):
                    name = path[len('/static/'):]
                    if not STATIC_RE.match(name) or not os.path.exists(os.path.join(WEB, name)):
                        return self.send(404, b'no existe')
                    return self.file(name)
                if path == '/api/home':
                    return self.send(200, json.dumps(app['catalog'].home()).encode(), 'application/json')
                m = re.match(r'^/api/muted/(.+)$', path)
                if m:
                    return self.muted(m.group(1))
                m = re.match(r'^/play/(.+)\.m3u8$', path)
                if m:
                    return self.play(m.group(1), qs)
                m = re.match(r'^/h/([0-9a-f]{16})\.(m3u8|ts)$', path)
                if m:
                    try:
                        body, ctype = app['proxy'].serve(m.group(1), self.headers.get('Host'))
                    except KeyError:
                        return self.send(404, b'enlace caducado')
                    return self.send(200, body, ctype)
                if path == '/img':
                    url = (qs.get('u') or [''])[0]
                    if not _img_allowed(url):
                        return self.send(400, b'host de imagen no permitido')
                    ext = urlparse(url).path.rsplit('.', 1)[-1].lower()
                    return self.send(200, app['fetch'](url), TYPES.get(ext, 'image/jpeg'),
                                     {'Cache-Control': 'max-age=3600'})
                return self.send(404, b'no existe')
            except Exception as e:  # proveedor o CDN caídos: mensaje corto, nunca un traceback
                return self.send(502, ('error: %s' % str(e)[:200]).encode())

        def muted(self, item_id):
            # tramos que Twitch dejó en silencio: el reproductor los avisa para que no parezcan una falla
            if not ITEM_RE.match(item_id):
                return self.send(404, b'video desconocido')
            try:
                item = app['catalog'].item(item_id)
            except KeyError:
                return self.send(404, b'video desconocido')
            ranges = []
            if item['platform'] == 'twitch' and item['kind'] == 'vod':
                if item_id not in app['muted']:  # no cambian: se calculan una vez
                    master = app['providers']['twitch'].master_url(item)
                    variant = hls.pick_variant(app['fetch'](master).decode(), master, 1080)
                    app['muted'][item_id] = hls.muted_ranges(app['fetch'](variant).decode())
                ranges = app['muted'][item_id]
            return self.send(200, json.dumps({'ranges': ranges}).encode(), 'application/json')

        def play(self, item_id, qs):
            if not ITEM_RE.match(item_id):
                return self.send(404, b'video desconocido')
            try:
                item = app['catalog'].item(item_id)
            except KeyError:
                return self.send(404, b'video desconocido')
            q = 720 if (qs.get('q') or [''])[0] == '720' else 1080
            provider, fetch = app['providers'][item['platform']], app['fetch']

            def resolve():
                master = provider.master_url(item)
                return hls.pick_variant(fetch(master).decode(), master, q)
            if app['catalog'].route(item) == 'direct':
                return self.redirect(resolve())
            return self.redirect('/h/%s.m3u8' % app['proxy'].open(resolve))

        def do_POST(self):
            if not self.guard():
                return
            # application/json obliga a un preflight CORS que este servidor no contesta: otra web no puede escribir aquí
            if not (self.headers.get('Content-Type') or '').startswith('application/json'):
                return self.send(415, b'se espera application/json')
            try:
                data = self.body_json()
                if self.path == '/api/state':
                    app['state'].set_brightness(int(data['brightness']))
                elif self.path == '/api/diagnostico':
                    line = json.dumps({'t': time.strftime('%Y-%m-%dT%H:%M:%S'), 'ip': self.client_address[0],
                                       'data': data}, ensure_ascii=False)
                    with app['lock']:
                        full = os.path.exists(app['diag_path']) and os.path.getsize(app['diag_path']) > DIAG_MAX
                        if not full:
                            with open(app['diag_path'], 'a', encoding='utf-8') as f:
                                f.write(line[:20000] + '\n')
                elif self.path == '/api/resume':
                    if not ITEM_RE.match(str(data.get('id', ''))):
                        return self.send(400, b'id invalido')
                    app['state'].set_resume(data['id'], float(data['position_s']), data.get('duration_s'))
                else:
                    return self.send(404, b'no existe')
            except (ValueError, KeyError, TypeError, OverflowError):
                return self.send(400, b'datos invalidos')
            self.send(204)

    return Handler


def build(config, catalog=None, state=None, proxy=None, providers=None, fetch=net.fetch, verbose=False):
    state = state or State(config.state_path)
    providers = providers or {'twitch': twitch, 'kick': kick}
    app = {'state': state, 'providers': providers, 'fetch': fetch, 'verbose': verbose, 'lock': threading.Lock(), 'muted': {},
           'diag_path': os.path.join(os.path.dirname(os.path.abspath(config.state_path)), 'diagnostico.jsonl'),
           'catalog': catalog or Catalog(config, providers, state),
           'proxy': proxy or Proxy(fetch=fetch)}
    server = ThreadingHTTPServer(('0.0.0.0', config.port), make_handler(app))
    server.daemon_threads = True
    return server


def main(argv=None):
    import argparse
    from tvlibre.config import load_config
    from tvlibre import remux
    ap = argparse.ArgumentParser(prog='tvlibre')
    ap.add_argument('--config', default='config.json')
    ap.add_argument('--verbose', action='store_true')
    args = ap.parse_args(argv)
    config = load_config(args.config)
    if not remux.available():
        print('aviso: no se encontró ffmpeg; los anteriores de Twitch no se podrán reproducir', file=sys.stderr)
    server = build(config, verbose=args.verbose)
    print('tvlibre escuchando en el puerto %d (solo red local)' % config.port, flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
