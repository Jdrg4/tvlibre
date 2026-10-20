"""Kick vía su API v2 pública (no oficial: puede cambiar sin aviso)."""
from tvlibre import net

API = 'https://kick.com/api/v2/channels/'
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
