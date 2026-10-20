"""Portada: quién está en vivo y los anteriores de todos los canales, mezclados por fecha."""
import threading
import time
from concurrent.futures import ThreadPoolExecutor, wait


class Catalog:
    def __init__(self, config, providers, state, clock=time.time, ttl=60, timeout=8):
        self.config, self.providers, self.state = config, providers, state
        self.clock, self.ttl, self.timeout = clock, ttl, timeout
        self._lock = threading.Lock()
        self._cache, self._at, self._items = None, None, {}

    def _build(self):
        live, vods, errors = [], [], []
        chans = self.config.channels
        # en paralelo y con tope: una plataforma colgada no puede pasar el timeout de la TV (30 s)
        pool = ThreadPoolExecutor(max_workers=len(chans))
        futures = [pool.submit(self.providers[ch.platform].channel_state, ch.slug, self.config.vods_per_channel)
                   for ch in chans]
        wait(futures, timeout=self.timeout)
        pool.shutdown(wait=False)
        for ch, fut in zip(chans, futures):
            try:
                if not fut.done():
                    raise TimeoutError('no respondió en %d s' % self.timeout)
                l, v = fut.result()
            except Exception as e:  # una plataforma caída no tumba la portada
                errors.append('%s/%s: %s' % (ch.platform, ch.slug, str(e)[:120]))
                continue
            if l:
                live.append(l)
            vods.extend(v)
        vods.sort(key=lambda x: x['started_at'] or '', reverse=True)
        self._items = {i['id']: i for i in live + vods}
        return {'live': live, 'vods': vods, 'errors': errors}

    def home(self, force=False):
        with self._lock:
            if force or self._cache is None or self.clock() - self._at >= self.ttl:
                self._cache, self._at = self._build(), self.clock()
            base = self._cache
        vods = []
        for v in base['vods']:
            r = self.state.resume(v['id'])
            vods.append(dict(v, resume_s=r) if r is not None else v)
        return {'live': base['live'], 'vods': vods, 'errors': base['errors'], 'brightness': self.state.brightness(),
                'default_quality': 720 if self.config.default_quality == 720 else 1080}

    def item(self, item_id):
        if item_id not in self._items:
            self.home(force=True)
        return self._items[item_id]

    @staticmethod
    def route(item):
        return 'direct' if item['platform'] == 'kick' and item['kind'] == 'live' else 'proxy'
