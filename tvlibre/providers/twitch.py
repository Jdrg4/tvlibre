"""Twitch vía su GQL público (API no oficial: puede cambiar sin aviso)."""
import json
from datetime import datetime
from urllib.parse import urlencode

from tvlibre import net

GQL = 'https://gql.twitch.tv/gql'
CLIENT_ID = 'kimne78kx3ncx6brgo4mv6wki5h1ko'  # el del sitio web de Twitch; público
HEADERS = {'Client-ID': CLIENT_ID}
PARAMS = '{platform:"web",playerBackend:"mediaplayer",playerType:"site"}'
CHANNEL_QUERY = ('query($l:String!,$n:Int!){user(login:$l){displayName stream{id title viewersCount createdAt '
                 'previewImageURL(width:640,height:360)} videos(first:$n,type:ARCHIVE,sort:TIME){edges{node{id title '
                 'lengthSeconds createdAt previewThumbnailURL(width:640,height:360)}}}}}')


def _ts(iso):
    return datetime.strptime(iso, '%Y-%m-%dT%H:%M:%SZ').timestamp()


def parse_channel(gql, login, vods):
    user = (gql.get('data') or {}).get('user')
    if not user:
        raise ValueError('el canal de Twitch "%s" no existe' % login)
    s = user.get('stream')
    live = None
    if s:
        live = {'id': 'twitch-live-' + login, 'platform': 'twitch', 'kind': 'live', 'channel': login,
                'title': s.get('title') or '', 'started_at': s['createdAt'], 'duration_s': None,
                'viewers': s.get('viewersCount'), 'thumb': s.get('previewImageURL'), 'ref': login}
    out = []
    for e in user['videos']['edges']:
        n = e['node']
        # el directo en curso aparece como anterior con el mismo inicio que el stream
        if live and abs(_ts(n['createdAt']) - _ts(live['started_at'])) < 600:
            continue
        out.append({'id': 'twitch-vod-' + n['id'], 'platform': 'twitch', 'kind': 'vod', 'channel': login,
                    'title': n.get('title') or '', 'started_at': n['createdAt'], 'duration_s': n.get('lengthSeconds'),
                    'viewers': None, 'thumb': n.get('previewThumbnailURL'), 'ref': n['id']})
    return live, out[:vods]


def channel_state(slug, vods):
    # se piden 2 de más por si se descarta el directo en curso
    gql = net.fetch_json(GQL, {'query': CHANNEL_QUERY, 'variables': {'l': slug, 'n': vods + 2}}, HEADERS)
    return parse_channel(gql, slug, vods)


def _token(field, arg_name, arg_value):
    q = 'query($v:%s){%s(%s:$v,params:%s){value signature}}' % (
        'ID!' if arg_name == 'id' else 'String!', field, arg_name, PARAMS)
    return net.fetch_json(GQL, {'query': q, 'variables': {'v': arg_value}}, HEADERS)['data'][field]


def master_url(item):
    if item['kind'] == 'live':
        t = _token('streamPlaybackAccessToken', 'channelName', item['ref'])
        path = 'api/channel/hls/%s.m3u8' % item['ref']
    else:
        t = _token('videoPlaybackAccessToken', 'id', item['ref'])
        path = 'vod/%s.m3u8' % item['ref']
    if not t:
        raise ValueError('Twitch no entregó acceso a %s' % item['id'])
    return 'https://usher.ttvnw.net/%s?%s' % (path, urlencode(
        {'sig': t['signature'], 'token': t['value'], 'allow_source': 'true'}))


SEARCH_QUERY = ('query($q:String!){searchFor(userQuery:$q,platform:"web"){channels{edges{item{...on User{login '
                'displayName profileImageURL(width:150) stream{viewersCount}}}}}}}')
STREAMS_QUERY = ('query($g:String!,$n:Int!){game(name:$g){name streams(first:$n,options:{languages:["es"]}){edges{node{'
                 'broadcaster{login displayName} title viewersCount createdAt previewImageURL(width:640,height:360)}}}}}')


def parse_search(gql):
    out = []
    edges = ((((gql.get('data') or {}).get('searchFor') or {}).get('channels') or {}).get('edges')) or []
    for e in edges:
        u = e.get('item') or {}
        if not u.get('login'):
            continue  # la búsqueda también devuelve cosas que no son canales
        s = u.get('stream')
        out.append({'platform': 'twitch', 'slug': u['login'], 'name': u.get('displayName') or u['login'],
                    'avatar': u.get('profileImageURL'), 'live': bool(s), 'viewers': s.get('viewersCount') if s else None})
    return out[:8]


def search(q):
    return parse_search(net.fetch_json(GQL, {'query': SEARCH_QUERY, 'variables': {'q': q}}, HEADERS))


def parse_streams(gql, exclude):
    game = (gql.get('data') or {}).get('game') or {}
    out = []
    for e in ((game.get('streams') or {}).get('edges')) or []:
        n = e['node']
        login = (n.get('broadcaster') or {}).get('login')
        if not login or login in exclude:
            continue
        out.append({'id': 'twitch-live-' + login, 'platform': 'twitch', 'kind': 'live', 'channel': login,
                    'title': n.get('title') or '', 'started_at': n.get('createdAt'), 'duration_s': None,
                    'viewers': n.get('viewersCount'), 'thumb': n.get('previewImageURL'), 'ref': login,
                    'category': game.get('name')})
    return out


def _games(slugs):
    # una sola consulta con un alias por canal: el juego del directo o, si no está en vivo, el del último
    parts = ['u%d:user(login:%s){stream{game{name}} lastBroadcast{game{name}}}' % (i, json.dumps(s))
             for i, s in enumerate(slugs)]
    data = net.fetch_json(GQL, {'query': '{%s}' % ' '.join(parts)}, HEADERS).get('data') or {}
    games = []
    for i in range(len(slugs)):
        u = data.get('u%d' % i) or {}
        g = (((u.get('stream') or {}).get('game')) or ((u.get('lastBroadcast') or {}).get('game')) or {}).get('name')
        if g and g not in games:
            games.append(g)
    return games


def discover(slugs, exclude, n):
    """Directos en español de los juegos de tus canales."""
    out, seen = [], set()
    for g in _games(slugs) if slugs else []:
        gql = net.fetch_json(GQL, {'query': STREAMS_QUERY, 'variables': {'g': g, 'n': n}}, HEADERS)
        for it in parse_streams(gql, exclude):
            if it['id'] not in seen:
                seen.add(it['id'])
                out.append(it)
    return out
