"""Twitch vía su GQL público (API no oficial: puede cambiar sin aviso)."""
import json
import re
from datetime import datetime
from urllib.parse import urlencode

from tvlibre import chatparts, net

GQL = 'https://gql.twitch.tv/gql'
CLIENT_ID = 'kimne78kx3ncx6brgo4mv6wki5h1ko'  # el del sitio web de Twitch; público
HEADERS = {'Client-ID': CLIENT_ID}
PARAMS = '{platform:"web",playerBackend:"mediaplayer",playerType:"site"}'
LOGIN_RE = re.compile(r'^[a-z0-9_]{1,25}$')
LANG_RE = re.compile(r'^[a-z]{2}$')

LIVE_FIELDS = 'title viewersCount createdAt game{name} previewImageURL(width:640,height:360)'
VIDEO_FIELDS = 'id title lengthSeconds createdAt previewThumbnailURL(width:640,height:360)'
CHANNEL_QUERY = ('query($l:String!,$n:Int!){user(login:$l){login displayName stream{%s} '
                 'videos(first:$n,type:ARCHIVE,sort:TIME){edges{node{%s}}}}}' % (LIVE_FIELDS, VIDEO_FIELDS))
PAGE_QUERY = ('query($l:String!,$n:Int!,$h:Int!){user(login:$l){login displayName description '
              'profileImageURL(width:150) followers{totalCount} lastBroadcast{startedAt game{name}} stream{%s} '
              'videos(first:$n,type:ARCHIVE,sort:TIME){edges{node{%s}}} '
              'highlights:videos(first:$h,type:HIGHLIGHT,sort:TIME){edges{node{%s}}}}}'
              % (LIVE_FIELDS, VIDEO_FIELDS, VIDEO_FIELDS))
VIDEO_QUERY = 'query($v:ID!){video(id:$v){%s owner{login displayName}}}' % VIDEO_FIELDS


def _ts(iso):
    return datetime.strptime(iso[:19], '%Y-%m-%dT%H:%M:%S').timestamp()


def _live(s, login, name):
    return {'id': 'twitch-live-' + login, 'platform': 'twitch', 'kind': 'live', 'channel': login, 'name': name,
            'title': s.get('title') or '', 'started_at': s.get('createdAt'), 'duration_s': None,
            'viewers': s.get('viewersCount'), 'thumb': s.get('previewImageURL'), 'ref': login,
            'category': (s.get('game') or {}).get('name')}


def _vod(n, login, name):
    return {'id': 'twitch-vod-' + n['id'], 'platform': 'twitch', 'kind': 'vod', 'channel': login, 'name': name,
            'title': n.get('title') or '', 'started_at': n['createdAt'], 'duration_s': n.get('lengthSeconds'),
            'viewers': None, 'thumb': n.get('previewThumbnailURL'), 'ref': n['id']}


def _user(gql, login):
    user = (gql.get('data') or {}).get('user')
    if not user:
        raise ValueError('el canal de Twitch "%s" no existe' % login)
    return user, user.get('displayName') or login


def _vods(conn, login, name, live):
    out = []
    for e in (conn or {}).get('edges') or []:
        n = e['node']
        # el directo en curso aparece como anterior con el mismo inicio que el stream
        if live and live['started_at'] and abs(_ts(n['createdAt']) - _ts(live['started_at'])) < 600:
            continue
        out.append(_vod(n, login, name))
    return out


def parse_channel(gql, login, vods):
    user, name = _user(gql, login)
    live = _live(user['stream'], login, name) if user.get('stream') else None
    return live, _vods(user.get('videos'), login, name, live)[:vods]


def channel_state(slug, vods):
    # se piden 2 de más por si se descarta el directo en curso
    gql = net.fetch_json(GQL, {'query': CHANNEL_QUERY, 'variables': {'l': slug, 'n': vods + 2}}, HEADERS)
    return parse_channel(gql, slug, vods)


def parse_page(gql, login, vods):
    """Página de un canal cualquiera: quién es, su directo, sus anteriores y sus destacados."""
    user, name = _user(gql, login)
    live = _live(user['stream'], login, name) if user.get('stream') else None
    last = user.get('lastBroadcast') or {}
    return {'channel': {'platform': 'twitch', 'slug': login, 'name': name,
                        'description': (user.get('description') or '').strip(),
                        'avatar': user.get('profileImageURL'),
                        'followers': (user.get('followers') or {}).get('totalCount'),
                        'last_live': last.get('startedAt'), 'category': (last.get('game') or {}).get('name')},
            'live': live, 'vods': _vods(user.get('videos'), login, name, live)[:vods],
            'highlights': _vods(user.get('highlights'), login, name, None)}


def channel_page(slug, vods):
    gql = net.fetch_json(GQL, {'query': PAGE_QUERY, 'variables': {'l': slug, 'n': vods + 2, 'h': 20}}, HEADERS)
    return parse_page(gql, slug, vods)


def parse_video(gql, ref):
    v = (gql.get('data') or {}).get('video')
    if not v or not v.get('owner'):
        raise KeyError('video desconocido: %s' % ref)
    return _vod(v, v['owner']['login'], v['owner'].get('displayName') or v['owner']['login'])


def item(item_id):
    """Rehace un item a partir de su id, aunque el canal no se siga ni haya salido en la portada."""
    m = re.match(r'^twitch-(live|vod)-([a-z0-9_]+)$', item_id)
    if not m:
        raise KeyError(item_id)
    kind, ref = m.groups()
    if kind == 'live':
        if not LOGIN_RE.match(ref):
            raise KeyError(item_id)
        # basta con el canal: si no está en vivo, Twitch lo dirá al pedir el acceso
        return {'id': item_id, 'platform': 'twitch', 'kind': 'live', 'channel': ref, 'name': ref, 'title': '',
                'started_at': None, 'duration_s': None, 'viewers': None, 'thumb': None, 'ref': ref}
    if not ref.isdigit():
        raise KeyError(item_id)
    return parse_video(net.fetch_json(GQL, {'query': VIDEO_QUERY, 'variables': {'v': ref}}, HEADERS), ref)


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


# ---------- buscar y descubrir ----------
SEARCH_FIELDS = 'login displayName profileImageURL(width:150) followers{totalCount} stream{viewersCount game{name}}'
# dos búsquedas en una consulta: la general de Twitch y la de nombres que empiezan así (encuentra "alexby11" al
# escribir "alexby", que la general a veces entierra)
SEARCH_QUERY = ('query($q:String!){searchFor(userQuery:$q,platform:"web",target:{index:CHANNEL,limit:30}){channels{'
                'edges{item{...on User{%s}}}}} searchUsers(userQuery:$q,first:30){edges{node{%s}}}}'
                % (SEARCH_FIELDS, SEARCH_FIELDS))
EXACT_MIN_FOLLOWERS = 1000  # el nombre exacto va primero solo si es un canal de verdad, no una cuenta vacía
# el idioma va en el texto de la consulta (ya validado): en game.streams es texto y en streams es un enum
STREAMS_QUERY = ('query($g:String!,$n:Int!){game(name:$g){name streams(first:$n,options:{languages:["%s"]}){edges{node{'
                 'broadcaster{login displayName} ' + LIVE_FIELDS + '}}}}}')
TOP_QUERY = ('query($n:Int!){streams(first:$n,options:{languages:[%s]}){edges{node{broadcaster{login displayName} '
             + LIVE_FIELDS + '}}}}')
SEARCH_MAX = 12


def _result(u):
    s = u.get('stream')
    return {'platform': 'twitch', 'slug': u['login'], 'name': u.get('displayName') or u['login'],
            'avatar': u.get('profileImageURL'), 'live': bool(s), 'viewers': s.get('viewersCount') if s else None,
            'followers': (u.get('followers') or {}).get('totalCount'),
            'category': ((s or {}).get('game') or {}).get('name')}


def parse_search(gql, q=''):
    """Junta las dos búsquedas sin repetir y ordena por seguidores: el streamer conocido arriba aunque esté offline.
    El que se llama exactamente como lo escrito va primero si tiene público."""
    data = gql.get('data') or {}
    users = [e.get('item') for e in ((((data.get('searchFor') or {}).get('channels') or {}).get('edges')) or [])]
    users += [e.get('node') for e in (((data.get('searchUsers') or {}).get('edges')) or [])]
    out, seen = [], set()
    for u in users:
        if (u or {}).get('login') and u['login'] not in seen:  # la búsqueda también trae cosas que no son canales
            seen.add(u['login'])
            out.append(_result(u))
    want = q.strip().lower().replace(' ', '')
    out.sort(key=lambda r: (not (r['slug'] == want and (r['followers'] or 0) >= EXACT_MIN_FOLLOWERS),
                            -(r['followers'] or 0)))
    return out[:SEARCH_MAX]


def search(q):
    return parse_search(net.fetch_json(GQL, {'query': SEARCH_QUERY, 'variables': {'q': q}}, HEADERS), q)


def parse_streams(gql, exclude):
    game = (gql.get('data') or {}).get('game') or {}
    out = []
    for e in ((game.get('streams') or {}).get('edges')) or []:
        n = e['node']
        b = n.get('broadcaster') or {}
        if not b.get('login') or b['login'] in exclude:
            continue
        it = _live(n, b['login'], b.get('displayName') or b['login'])
        it['category'] = it['category'] or game.get('name')
        out.append(it)
    return out


def parse_top(gql, exclude):
    out = []
    for e in (((gql.get('data') or {}).get('streams') or {}).get('edges')) or []:
        n = e['node']
        b = n.get('broadcaster') or {}
        if b.get('login') and b['login'] not in exclude:
            out.append(_live(n, b['login'], b.get('displayName') or b['login']))
    return out


def _lang(lang):
    if not LANG_RE.match(lang or ''):
        raise ValueError('idioma inválido: %r' % lang)
    return lang


def top(lang, exclude, n):
    """Lo más visto ahora en ese idioma, de todo Twitch."""
    gql = net.fetch_json(GQL, {'query': TOP_QUERY % _lang(lang).upper(), 'variables': {'n': n + len(exclude)}},
                         HEADERS)
    return parse_top(gql, exclude)[:n]


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


def discover(slugs, exclude, n, lang='es'):
    """Directos en tu idioma de los juegos de tus canales."""
    query = STREAMS_QUERY % _lang(lang)
    out, seen = [], set()
    for g in _games(slugs) if slugs else []:
        gql = net.fetch_json(GQL, {'query': query, 'variables': {'g': g, 'n': n}}, HEADERS)
        for it in parse_streams(gql, exclude):
            if it['id'] not in seen:
                seen.add(it['id'])
                out.append(it)
    return out


# ---------- chat (solo lectura) ----------
EMOTE_URL = 'https://static-cdn.jtvnw.net/emoticons/v2/%s/default/dark/1.0'
COMMENTS_QUERY = ('query($v:ID!,$t:Int!){video(id:$v){comments(contentOffsetSeconds:$t){edges{node{id '
                  'contentOffsetSeconds commenter{displayName} message{userColor fragments{text emote{emoteID}}}}}}}}')


def parse_comments(gql):
    edges = ((((gql.get('data') or {}).get('video') or {}).get('comments') or {}).get('edges')) or []
    out = []
    for e in edges:
        n = e['node']
        msg = n.get('message') or {}
        frags = msg.get('fragments') or []
        chunks = [{'e': EMOTE_URL % f['emote']['emoteID']} if (f.get('emote') or {}).get('emoteID')
                  else (f.get('text') or '') for f in frags]
        out.append({'id': n['id'], 'user': (n.get('commenter') or {}).get('displayName') or '?',
                    'color': msg.get('userColor'), 'text': ''.join(f.get('text') or '' for f in frags),
                    'parts': chatparts.build(chunks), 'at': n.get('contentOffsetSeconds')})
    return out


def chat(item, t):
    if item['kind'] == 'live':
        from tvlibre.providers import twitch_irc
        return {'messages': twitch_irc.LIVE.messages(item['channel']), 'until': None}
    t = int(t)
    gql = net.fetch_json(GQL, {'query': COMMENTS_QUERY, 'variables': {'v': item['ref'], 't': t}}, HEADERS)
    msgs = [m for m in parse_comments(gql) if (m['at'] or 0) >= t]
    # la página trae unos 50 mensajes; el siguiente pedido empieza donde terminó esta
    return {'messages': msgs, 'until': (max(m['at'] for m in msgs) + 1) if msgs else t + 30}
