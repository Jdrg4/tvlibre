"""Kick vía su API v2 pública (no oficial: puede cambiar sin aviso)."""
import re
from datetime import datetime, timezone
from urllib.parse import urlencode

from tvlibre import chatparts, net

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


# ---------- chat (solo lectura) ----------
EMOTE_RE = re.compile(r'\[emote:(\d+):([^\]]+)\]')
EMOTE_URL = 'https://files.kick.com/emotes/%s/fullsize'
CHAT_WINDOW = 5  # medido: con start_time, Kick devuelve los mensajes de 5 s
_ids = {}  # slug → id de canal (no cambia)


def _secs(iso):
    return datetime.strptime(iso[:19], '%Y-%m-%dT%H:%M:%S').replace(tzinfo=timezone.utc).timestamp()


def parse_messages(js, started_at=None, since=None):
    out = []
    for m in (js.get('data') or {}).get('messages') or []:
        if m.get('type') not in (None, 'message', 'reply'):
            continue
        at = None
        if started_at:
            at = int(_secs(m['created_at']) - _secs(started_at))
            if since is not None and at < since:
                continue
        sender, content = m.get('sender') or {}, m.get('content') or ''
        chunks, pos = [], 0
        for e in EMOTE_RE.finditer(content):
            chunks += [content[pos:e.start()], {'e': EMOTE_URL % e.group(1)}]
            pos = e.end()
        out.append({'id': str(m['id']), 'user': sender.get('username') or '?',
                    'color': (sender.get('identity') or {}).get('color'),
                    'text': EMOTE_RE.sub(r':\2:', content), 'parts': chatparts.build(chunks + [content[pos:]]),
                    'at': at})
    out.sort(key=lambda x: x['at'] if x['at'] is not None else 0)
    return out if started_at else out[::-1]  # en vivo Kick da el más nuevo primero


def chat(item, t):
    slug = item['channel']
    if slug not in _ids:
        _ids[slug] = net.fetch_json(API + slug, headers=HEADERS)['id']
    url = 'https://kick.com/api/v2/channels/%d/messages' % _ids[slug]
    if item['kind'] == 'live':
        return {'messages': parse_messages(net.fetch_json(url, headers=HEADERS)), 'until': None}
    t = int(t)
    when = datetime.fromtimestamp(_secs(item['started_at']) + t, timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z')
    js = net.fetch_json(url + '?' + urlencode({'start_time': when}), headers=HEADERS)
    return {'messages': parse_messages(js, item['started_at'], t), 'until': t + CHAT_WINDOW}
