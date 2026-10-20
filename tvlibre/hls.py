"""Lectura y reescritura de playlists HLS para reproductores viejos."""
import re
from typing import NamedTuple
from urllib.parse import urljoin

# Lo que entiende un reproductor HLS de 2014; el resto (DATERANGE, prefetch de Twitch...) se quita.
KEEP_TAGS = ('#EXTM3U', '#EXTINF', '#EXT-X-VERSION', '#EXT-X-TARGETDURATION', '#EXT-X-MEDIA-SEQUENCE',
             '#EXT-X-STREAM-INF', '#EXT-X-ENDLIST', '#EXT-X-DISCONTINUITY', '#EXT-X-PLAYLIST-TYPE')


class Variant(NamedTuple):
    height: int
    fps: float
    url: str
    bandwidth: int = 0


def variants(master, base_url):
    lines = master.splitlines()
    out = []
    for i, line in enumerate(lines):
        if not line.startswith('#EXT-X-STREAM-INF'):
            continue
        h = re.search(r'RESOLUTION=\d+x(\d+)', line)
        fps = re.search(r'FRAME-RATE=([\d.]+)', line)
        bw = re.search(r'[^-]BANDWIDTH=(\d+)', line)
        uri = next((l for l in lines[i + 1:] if l and not l.startswith('#')), None)
        if h and uri:
            out.append(Variant(int(h.group(1)), float(fps.group(1)) if fps else 30.0, urljoin(base_url, uri),
                               int(bw.group(1)) if bw else 0))
    return out


def pick_variant(master, base_url, max_height):
    vs = variants(master, base_url)
    if not vs:
        return base_url
    fit = [v for v in vs if v.height <= max_height]
    if fit:
        best_h = max(v.height for v in fit)
        same = [v for v in fit if v.height == best_h]
        # a igual altura: menos fps; luego menos ancho de banda (evita la "chunked"/source, perfil High y más pesada)
        return min(same, key=lambda v: (v.fps, v.bandwidth)).url
    return min(vs, key=lambda v: v.height).url


def rewrite_playlist(text, base_url, link):
    out, init = [], None
    for line in text.splitlines():
        if line.startswith('#EXT-X-MAP'):
            m = re.search(r'URI="([^"]+)"', line)
            init = urljoin(base_url, m.group(1)) if m else None
            continue
        if line.startswith('#'):
            if line.startswith(KEEP_TAGS):
                out.append(line)
            continue
        if line.strip():
            out.append(link(urljoin(base_url, line.strip()), init))
    return '\n'.join(out) + '\n'


def muted_ranges(playlist):
    """Tramos [inicio, fin] en segundos que Twitch silenció por derechos de autor (segmentos "-muted")."""
    out, t, dur = [], 0.0, None
    for line in playlist.splitlines():
        line = line.strip()
        if line.startswith('#EXTINF:'):
            dur = float(line[8:].split(',')[0])
        elif line and not line.startswith('#') and dur is not None:
            if '-muted' in line:
                if out and out[-1][1] == t:
                    out[-1][1] = t + dur
                else:
                    out.append([t, t + dur])
            t, dur = t + dur, None
    return [[int(a), int(b)] for a, b in out]
