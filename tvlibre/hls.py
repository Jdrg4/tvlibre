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


def _is_ad(extinf):
    """Twitch titula sus segmentos: "live" los del directo y "Amazon|…" (u otro) los anuncios que intercala."""
    title = extinf.split(',', 1)[1].strip() if ',' in extinf else ''
    return title not in ('', 'live')


def rewrite_live(text, base_url, link, state):
    """Como rewrite_playlist, pero quita los anuncios que Twitch intercala en el directo.

    El anuncio viene con otro formato (otro init, otra resolución) tras un #EXT-X-DISCONTINUITY, y ahí el
    reproductor de la TV y del Roku se quedaba congelado (medido: anuncio a los ~12 min de directo). Sin los
    anuncios, la secuencia se renumera para que siga seguida y se marca un DISCONTINUITY solo donde hubo hueco.
    `state` es un dict de la sesión ({} al empezar) que guarda la numeración entre recargas."""
    seqs = state.setdefault('seq', {})       # url del segmento → número propio
    disc = state.setdefault('disc', set())   # segmentos que van después de un anuncio quitado
    head, body, init, pending, extinf, kept = [], [], None, [], None, {}
    gap = False
    for line in text.splitlines():
        if line.startswith('#EXT-X-MAP'):
            m = re.search(r'URI="([^"]+)"', line)
            init = urljoin(base_url, m.group(1)) if m else None
        elif line.startswith('#EXTINF'):
            extinf = line
        elif line.startswith('#'):
            if line.startswith(('#EXTM3U', '#EXT-X-VERSION', '#EXT-X-TARGETDURATION', '#EXT-X-PLAYLIST-TYPE')):
                head.append(line)
            elif line.startswith('#EXT-X-ENDLIST'):
                pending.append(line)
        elif line.strip() and extinf:
            url = urljoin(base_url, line.strip())
            if _is_ad(extinf):
                gap = True
            else:
                if url not in seqs:
                    seqs[url] = state.get('next', 0)
                    state['next'] = seqs[url] + 1
                    if gap and seqs[url] > 0:
                        disc.add(url)
                gap = False
                kept[url] = seqs[url]
                if url in disc:
                    body.append('#EXT-X-DISCONTINUITY')
                body.extend([extinf, link(url, init)])
            extinf = None
    # solo se recuerda lo que sigue en la ventana: la sesión puede durar horas
    first = min(kept.values()) if kept else state.get('next', 0)
    # los cortes que ya salieron por arriba de la ventana se cuentan en DISCONTINUITY-SEQUENCE (lo pide el HLS)
    gone = {u for u in disc if u not in kept and seqs.get(u, first) < first}
    state['dseq'] = state.get('dseq', 0) + len(gone)
    state['seq'] = kept
    state['disc'] = disc - gone
    head.append('#EXT-X-MEDIA-SEQUENCE:%d' % first)
    if state['dseq']:
        head.append('#EXT-X-DISCONTINUITY-SEQUENCE:%d' % state['dseq'])
    return '\n'.join(head + body + pending) + '\n'


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
