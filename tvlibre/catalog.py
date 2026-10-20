"""Portada: quién está en vivo, los anteriores de todos los canales mezclados por fecha y otros directos parecidos."""
import threading
import time
from concurrent.futures import ThreadPoolExecutor, wait

from tvlibre.config import Channel

DISCOVER_TTL = 300
DISCOVER_MAX = 16
DISCOVER_TIMEOUT = 60


def _thread(fn):
    threading.Thread(target=fn, daemon=True).start()


class Catalog:
    def __init__(self, config, providers, state, clock=time.time, ttl=60, timeout=8, spawn=_thread):
        self.config, self.providers, self.state = config, providers, state
        self.clock, self.ttl, self.timeout, self.spawn = clock, ttl, timeout, spawn
        self._lock = threading.Lock()
        self._cache, self._at, self._items = None, None, {}
        self._disc, self._disc_at, self._disc_gen, self._disc_busy = None, None, 0, False

    def _run(self, fns, timeout=None):
        """Corre en paralelo y con tope: una plataforma colgada no puede pasar el timeout de la TV (30 s).
        Devuelve el resultado de cada función o la excepción que dio."""
        if not fns:
            return []
        pool = ThreadPoolExecutor(max_workers=len(fns))
        futures = [pool.submit(f) for f in fns]
        timeout = timeout or self.timeout
        wait(futures, timeout=timeout)
        pool.shutdown(wait=False)
        out = []
        for fut in futures:
            if not fut.done():
                out.append(TimeoutError('no respondió en %d s' % timeout))
                continue
            try:
                out.append(fut.result())
            except Exception as e:  # una plataforma caída no tumba lo demás
                out.append(e)
        return out

    # ---------- canales seguidos ----------
    def channels(self):
        saved = self.state.channels()
        if saved is None:  # nunca se editaron desde la pantalla: valen los de la configuración
            return list(self.config.channels)
        return [Channel(c['platform'], c['slug']) for c in saved]

    def follow(self, platform, slug, on):
        with self._lock:
            rest = [c for c in self.channels() if (c.platform, c.slug) != (platform, slug)]
            if on:
                rest.append(Channel(platform, slug))
            self.state.set_channels([{'platform': c.platform, 'slug': c.slug} for c in rest])
            self._cache = self._disc = None
            self._disc_gen += 1  # una búsqueda de descubrir en curso ya no vale: excluye otros canales

    def search(self, q):
        following = {(c.platform, c.slug) for c in self.channels()}
        plats = list(self.providers)
        per, errors = [], []
        for p, r in zip(plats, self._run([lambda p=p: self.providers[p].search(q) for p in plats])):
            if isinstance(r, Exception):
                errors.append('%s: %s' % (p, str(r)[:120]))
                continue
            per.append([dict(x, following=(x['platform'], x['slug']) in following) for x in r])
        # se alternan las plataformas: si no, los 8 de una tapaban al canal real de la otra
        results = [lst[i] for i in range(max(map(len, per), default=0)) for lst in per if i < len(lst)]
        want = q.strip().lower()
        # primero el canal que se escribió tal cual, luego los que están en vivo; sort es estable
        results.sort(key=lambda x: (x['slug'] != want and (x.get('name') or '').lower() != want, not x.get('live')))
        return {'results': results, 'errors': errors}

    # ---------- portada ----------
    def _build(self):
        live, vods, errors = [], [], []
        chans = self.channels()
        n = self.config.vods_per_channel
        res = self._run([lambda ch=ch: self.providers[ch.platform].channel_state(ch.slug, n) for ch in chans])
        for ch, r in zip(chans, res):
            if isinstance(r, Exception):
                errors.append('%s/%s: %s' % (ch.platform, ch.slug, str(r)[:120]))
                continue
            l, v = r
            if l:
                live.append(l)
            vods.extend(v)
        vods.sort(key=lambda x: x['started_at'] or '', reverse=True)
        self._items = {i['id']: i for i in live + vods}
        return {'live': live, 'vods': vods, 'errors': errors}

    def _discover(self):
        """Lo último que haya de "También en vivo". Si caducó, se renueva aparte: son muchas peticiones en serie
        y no pueden frenar la portada ni tener tomado el lock."""
        stale = self._disc is None or self.clock() - self._disc_at >= DISCOVER_TTL
        if stale and not self._disc_busy:
            self._disc_busy = True
            self.spawn(self._refresh_discover)
        return self._disc or []

    def _refresh_discover(self):
        gen, chans = self._disc_gen, self.channels()
        try:
            exclude = {c.slug for c in chans}
            by = {}
            for c in chans:
                by.setdefault(c.platform, []).append(c.slug)
            plats = list(by)
            res = self._run([lambda p=p: self.providers[p].discover(by[p], exclude, 12) for p in plats],
                            DISCOVER_TIMEOUT)
            items = [i for r in res if not isinstance(r, Exception) for i in r]  # opcional: sin error visible
            items.sort(key=lambda i: i.get('viewers') or 0, reverse=True)
            if gen == self._disc_gen:
                self._disc, self._disc_at = items, self.clock()
        finally:
            self._disc_busy = False

    def home(self, force=False):
        with self._lock:
            if force or self._cache is None or self.clock() - self._at >= self.ttl:
                self._cache, self._at = self._build(), self.clock()
            base = self._cache
            live_ids = {i['id'] for i in base['live']}
            disc = [i for i in self._discover() if i['id'] not in live_ids][:DISCOVER_MAX]
            for i in disc:
                self._items.setdefault(i['id'], i)
            chans = [{'platform': c.platform, 'slug': c.slug} for c in self.channels()]
        vods = []
        for v in base['vods']:
            r = self.state.resume(v['id'])
            vods.append(dict(v, resume_s=r) if r is not None else v)
        return {'live': base['live'], 'vods': vods, 'discover': disc, 'channels': chans, 'errors': base['errors'],
                'brightness': self.state.brightness(),
                'default_quality': 720 if self.config.default_quality == 720 else 1080}

    def item(self, item_id):
        if item_id not in self._items:
            self.home(force=True)
        return self._items[item_id]

    @staticmethod
    def route(item):
        return 'direct' if item['platform'] == 'kick' and item['kind'] == 'live' else 'proxy'
