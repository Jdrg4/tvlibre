"""Twitch vía su GQL público (API no oficial: puede cambiar sin aviso)."""
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
