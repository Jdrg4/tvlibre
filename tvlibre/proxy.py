"""Proxy HLS: reescribe playlists con URLs absolutas y sirve segmentos (fMP4 → TS si hace falta)."""
import hashlib
import threading
from collections import OrderedDict

from tvlibre import hls, net, remux


def _key(*parts):
    return hashlib.sha1('|'.join(p or '' for p in parts).encode()).hexdigest()[:16]


class Proxy:
    def __init__(self, fetch=net.fetch, to_ts=remux.to_ts, max_entries=20000):
        self.fetch, self.to_ts, self.max_entries = fetch, to_ts, max_entries
        self._lock = threading.Lock()
        self._entries = OrderedDict()   # clave -> {'url', 'init', 'playlist', 'resolver'}
        self._inits = OrderedDict()     # url del init -> bytes (64 como máximo)

    def _put(self, key, entry):
        with self._lock:
            self._entries[key] = entry
            self._entries.move_to_end(key)
            while len(self._entries) > self.max_entries:
                self._entries.popitem(last=False)

    def _get(self, key):
        with self._lock:
            entry = self._entries[key]  # KeyError si caducó o nunca existió
            self._entries.move_to_end(key)
            return entry

    def open(self, resolver):
        url = resolver()
        key = _key(url)
        self._put(key, {'url': url, 'init': None, 'playlist': True, 'resolver': resolver})
        return key

    def _link(self, host):
        def link(url, init):
            is_pl = not init and '.m3u8' in url.split('?')[0]
            k = _key(url, init)
            self._put(k, {'url': url, 'init': init, 'playlist': is_pl, 'resolver': None})
            return 'http://%s/h/%s.%s' % (host, k, 'm3u8' if is_pl else 'ts')
        return link

    def _init(self, url):
        with self._lock:
            if url in self._inits:
                return self._inits[url]
        data = self.fetch(url)
        with self._lock:
            self._inits[url] = data
            while len(self._inits) > 64:
                self._inits.popitem(last=False)
        return data

    def serve(self, key, host):
        e = self._get(key)
        if e['playlist']:
            try:
                text = self.fetch(e['url'])
            except net.HttpError as err:
                # token de Twitch caducado: se pide uno nuevo una vez y se reintenta
                if err.status not in (401, 403) or not e['resolver']:
                    raise
                e['url'] = e['resolver']()
                text = self.fetch(e['url'])
            return hls.rewrite_playlist(text.decode(), e['url'], self._link(host)).encode(), \
                'application/vnd.apple.mpegurl'
        data = self.fetch(e['url'])
        if e['init']:
            data = self.to_ts(self._init(e['init']), data)
        return data, 'video/mp2t'
