"""Kick vía su API v2 pública (no oficial: puede cambiar sin aviso)."""
from urllib.parse import urlencode

from tvlibre import net

API = 'https://kick.com/api/v2/channels/'
SEARCH = 'https://kick.com/api/search?'
LIVESTREAMS = 'https://web.kick.com/api/v1/livestreams?'
HEADERS = {'Accept': 'application/json'}


def _iso(kick_time):
    # Kick da "AAAA-MM-DD HH:MM:SS" en UTC
    return kick_time.replace(' ', 'T') + 'Z' if kick_time and 'T' not in kick_time else kick_time


def parse_channel(channel, videos, slug, vods):
    ls = channel.get('livestream')
    live = None
    if ls and ls.get('is_live', True):
        live = {'id': 'kick-live-' + slug, 'platform': 'kick', 'kind': 'live', 'channel': slug,
                'title': ls.get('session_title') or '', 'started_at': _iso(ls.get('start_time')), 'duration_s': None,
                'viewers': ls.get('viewer_count'), 'thumb': (ls.get('thumbnail') or {}).get('url'),
                'ref': channel.get('playback_url')}
    out = []
    for v in videos:
        if v.get('is_live') or not v.get('duration'):  # directo en curso
            # su miniatura (images.kick.com) carga; la de stream.kick.com/thumbnails/livestream da 403
            if live and (v.get('thumbnail') or {}).get('src'):
                live['thumb'] = v['thumbnail']['src']
            continue
        out.append({'id': 'kick-vod-' + v['video']['uuid'], 'platform': 'kick', 'kind': 'vod', 'channel': slug,
                    'title': v.get('session_title') or '', 'started_at': _iso(v.get('start_time')),
                    'duration_s': int(v['duration']) // 1000, 'viewers': None,
                    'thumb': (v.get('thumbnail') or {}).get('src'), 'ref': v.get('source')})
    return live, out[:vods]


def channel_state(slug, vods):
    channel = net.fetch_json(API + slug, headers=HEADERS)
    videos = net.fetch_json(API + slug + '/videos', headers=HEADERS)
    return parse_channel(channel, videos, slug, vods)


def master_url(item):
    if item['kind'] == 'live':
        # la URL del directo cambia entre emisiones: se pide fresca
        return net.fetch_json(API + item['channel'], headers=HEADERS)['playback_url']
    return item['ref']


def parse_search(js):
    out = []
    for c in (js.get('channels') or [])[:8]:
        user = c.get('user') or {}
        out.append({'platform': 'kick', 'slug': c['slug'], 'name': user.get('username') or c['slug'],
                    'avatar': user.get('profilePic') or user.get('profile_pic'), 'live': bool(c.get('isLive')),
                    'viewers': None})
    return out


def search(q):
    return parse_search(net.fetch_json(SEARCH + urlencode({'searched_word': q}), headers=HEADERS))


def parse_livestreams(js, exclude):
    out = []
    for ls in (js.get('data') or {}).get('livestreams') or []:
        slug = (ls.get('channel') or {}).get('slug')
        if not slug or slug in exclude:
            continue
        out.append({'id': 'kick-live-' + slug, 'platform': 'kick', 'kind': 'live', 'channel': slug,
                    'title': ls.get('title') or '', 'started_at': ls.get('start_time'), 'duration_s': None,
                    'viewers': ls.get('viewer_count'), 'thumb': (ls.get('thumbnail') or {}).get('src'),
                    'ref': None, 'category': (ls.get('category') or {}).get('name')})
    return out


def _category_ids(slug):
    ch = net.fetch_json(API + slug, headers=HEADERS)
    cats = ((ch.get('livestream') or {}).get('categories') or []) + (ch.get('recent_categories') or [])[:1]
    return [c['id'] for c in cats if c.get('id')]


def discover(slugs, exclude, n):
    """Directos en español de las categorías de tus canales (los más vistos primero)."""
    ids = []
    for s in slugs:
        for i in _category_ids(s):
            if i not in ids:
                ids.append(i)
    base = {'limit': n, 'sort': 'viewer_count_desc', 'language': 'es'}
    queries = [dict(base, category_id=i) for i in ids] or [base]
    out, seen = [], set()
    for q in queries:
        for it in parse_livestreams(net.fetch_json(LIVESTREAMS + urlencode(q), headers=HEADERS), exclude):
            if it['id'] not in seen:
                seen.add(it['id'])
                out.append(it)
    return out
