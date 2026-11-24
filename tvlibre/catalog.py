"""Portada (directos, anteriores, "Lo más visto" y "También en vivo"), página de cualquier canal, búsqueda y
seguir/dejar de seguir."""
import threading
import time
from concurrent.futures import ThreadPoolExecutor, wait

from tvlibre.config import PLATFORMS, Channel

DISCOVER_TTL = 300
DISCOVER_MAX = 16
DISCOVER_TIMEOUT = 60
TOP_MAX = 24
PAGE_TTL = 60
PAGE_MAX = 50  # páginas de canal en caché


def _thread(fn):
    threading.Thread(target=fn, daemon=True).start()


class Catalog:
    def __init__(self, config, providers, state, clock=time.time, ttl=60, timeout=8, spawn=_thread):
        self.config, self.providers, self.state = config, providers, state
        self.clock, self.ttl, self.timeout, self.spawn = clock, ttl, timeout, spawn
        self._lock = threading.Lock()
        self._cache, self._at, self._items = None, None, {}
        self._disc, self._top, self._disc_at, self._disc_gen, self._disc_busy = None, None, None, 0, False
        self._pages = {}  # slug → (cuándo, página)

    def _run(self, fns, timeout=None):
        """Corre en paralelo y con tope: un canal colgado no puede pasar el timeout de la TV (30 s).
        Devuelve el resultado de cada función o la excepción que dio."""
        if not fns:
            return []
        pool = ThreadPoolExecutor(max_workers=min(len(fns), 16))
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
            except Exception as e:  # un canal caído no tumba lo demás
                out.append(e)
        return out

    def _remember(self, items):
        for i in items:
            if i:
                self._items[i['id']] = i

    def _with_resume(self, vods):
        out = []
        for v in vods:
            r = self.state.resume(v['id'])
            out.append(dict(v, resume_s=r) if r is not None else v)
        return out

    # ---------- canales seguidos ----------
    def channels(self):
        saved = self.state.channels()
        if saved is None:  # nunca se editaron desde la pantalla: valen los de la configuración
            chans = list(self.config.channels)
        else:
            chans = [Channel(c['platform'], c['slug']) for c in saved]
        return [c for c in chans if c.platform in PLATFORMS]  # los de Kick quedaron en state.json de antes

    def follow(self, platform, slug, on):
        with self._lock:
            rest = [c for c in self.channels() if (c.platform, c.slug) != (platform, slug)]
            if on:
                rest.append(Channel(platform, slug))
            self.state.set_channels([{'platform': c.platform, 'slug': c.slug} for c in rest])
            self._cache = self._disc = self._top = None
            self._disc_gen += 1  # una búsqueda de descubrir en curso ya no vale: excluye otros canales

    def search(self, q):
        following = {(c.platform, c.slug) for c in self.channels()}
        plats = list(self.providers)
        results, errors = [], []
        for p, r in zip(plats, self._run([lambda p=p: self.providers[p].search(q) for p in plats])):
            if isinstance(r, Exception):
                errors.append('%s: %s' % (p, str(r)[:120]))
                continue
            # el orden lo da la plataforma (por seguidores): "en vivo primero" enterraba a los streamers conocidos
            results.extend(dict(x, following=(x['platform'], x['slug']) in following) for x in r)
        return {'results': results, 'errors': errors}

    # ---------- página de un canal cualquiera ----------
    def channel(self, slug, platform='twitch'):
        with self._lock:
            hit = self._pages.get(slug)
            fresh = hit and self.clock() - hit[0] < PAGE_TTL
        if fresh:
            page = hit[1]
        else:
            r = self._run([lambda: self.providers[platform].channel_page(slug, max(30, self.config.vods_per_channel))])[0]
            if isinstance(r, Exception):
                raise r
            page = r
            with self._lock:
                if len(self._pages) >= PAGE_MAX:
                    self._pages.pop(min(self._pages, key=lambda k: self._pages[k][0]))
                self._pages[slug] = (self.clock(), page)
                self._remember([page['live']] + page['vods'] + page['highlights'])
        following = (platform, slug) in {(c.platform, c.slug) for c in self.channels()}
        return {'channel': dict(page['channel'], following=following), 'live': page['live'],
                'vods': self._with_resume(page['vods']), 'highlights': self._with_resume(page['highlights'])}

    # ---------- portada ----------
    def _build(self):
        live, vods, errors = [], [], []
        chans = self.channels()
        n = self.config.vods_per_channel
        res = self._run([lambda ch=ch: self.providers[ch.platform].channel_state(ch.slug, n) for ch in chans])
        for ch, r in zip(chans, res):
            if isinstance(r, Exception):
                errors.append('%s: %s' % (ch.slug, str(r)[:120]))
                continue
            l, v = r
            if l:
                live.append(l)
            vods.extend(v)
        live.sort(key=lambda x: x.get('viewers') or 0, reverse=True)
        vods.sort(key=lambda x: x['started_at'] or '', reverse=True)
        self._remember(live + vods)
        return {'live': live, 'vods': vods, 'errors': errors}

    def _discover(self):
        """Lo último que haya de "También en vivo" y "Lo más visto". Si caducó, se renueva aparte: son muchas
        peticiones en serie y no pueden frenar la portada ni tener tomado el lock."""
        stale = self._disc is None or self.clock() - self._disc_at >= DISCOVER_TTL
        if stale and not self._disc_busy:
            self._disc_busy = True
            self.spawn(self._refresh_discover)
        return self._disc or [], self._top or []

    def _refresh_discover(self):
        gen, chans = self._disc_gen, self.channels()
        lang = self.config.language
        try:
            exclude = {c.slug for c in chans}
            by = {}
            for c in chans:
                by.setdefault(c.platform, []).append(c.slug)
            plats = list(by)
            tops = [p for p in self.providers if hasattr(self.providers[p], 'top')]
            fns = [lambda p=p: self.providers[p].discover(by[p], exclude, 12, lang) for p in plats] + \
                  [lambda p=p: self.providers[p].top(lang, exclude, TOP_MAX) for p in tops]
            res = self._run(fns, DISCOVER_TIMEOUT)  # opcionales: sin error visible
            items = [i for r in res[:len(plats)] if not isinstance(r, Exception) for i in r]
            items.sort(key=lambda i: i.get('viewers') or 0, reverse=True)
            top = [i for r in res[len(plats):] if not isinstance(r, Exception) for i in r]
            top.sort(key=lambda i: i.get('viewers') or 0, reverse=True)
            if gen == self._disc_gen:
                self._disc, self._top, self._disc_at = items, top, self.clock()
        finally:
            self._disc_busy = False

    def home(self, force=False):
        with self._lock:
            if force or self._cache is None or self.clock() - self._at >= self.ttl:
                self._cache, self._at = self._build(), self.clock()
            base = self._cache
            live_ids = {i['id'] for i in base['live']}
            disc_all, top_all = self._discover()
            top = [i for i in top_all if i['id'] not in live_ids][:TOP_MAX]
            shown = live_ids | {i['id'] for i in top}
            # "También en vivo" no repite lo que ya está en "Lo más visto"
            disc = [i for i in disc_all if i['id'] not in shown][:DISCOVER_MAX]
            for i in disc + top:
                self._items.setdefault(i['id'], i)
            chans = [{'platform': c.platform, 'slug': c.slug} for c in self.channels()]
        return {'live': base['live'], 'vods': self._with_resume(base['vods']), 'top': top, 'discover': disc,
                'channels': chans, 'errors': base['errors'], 'brightness': self.state.brightness(),
                'default_quality': 720 if self.config.default_quality == 720 else 1080}

    def item(self, item_id):
        """El item con ese id. Si no salió en ninguna pantalla (otro canal, o el servidor se reinició) se le pide a
        la plataforma: así se puede ver cualquier directo o anterior."""
        if item_id in self._items:
            return self._items[item_id]
        platform = item_id.split('-', 1)[0]
        provider = self.providers.get(platform)
        if provider is None or not hasattr(provider, 'item'):
            raise KeyError(item_id)
        it = provider.item(item_id)  # KeyError si no existe
        self._items[item_id] = it
        return it
