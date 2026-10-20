"""Un mensaje de chat como partes {'t': texto} o {'e': url de imagen}.

Ni el Roku ni el navegador de la TV traen fuente de emojis, y los emotes de Kick y Twitch son imágenes:
todo lo que no es texto se dibuja como imagen (los emojis con Twemoji, el set abierto de Twitter)."""

TWEMOJI = 'https://cdn.jsdelivr.net/gh/jdecked/twemoji@15.1.0/assets/72x72/'
ZWJ, VS16 = 0x200D, 0xFE0F


def _base(cp):
    return (0x1F000 <= cp <= 0x1FAFF or 0x2600 <= cp <= 0x27BF or 0x2300 <= cp <= 0x23FF
            or 0x2B00 <= cp <= 0x2BFF or cp in (0x203C, 0x2049, 0x3030, 0x303D))


def _skin(cp):
    return 0x1F3FB <= cp <= 0x1F3FF


def _regional(cp):
    return 0x1F1E6 <= cp <= 0x1F1FF


def _url(seq):
    if ZWJ not in seq:  # la regla de nombres de Twemoji: sin ZWJ, el FE0F no va
        seq = [c for c in seq if c != VS16]
    return TWEMOJI + '-'.join('%x' % c for c in seq) + '.png'


def split_emoji(text):
    out, buf, cps, i = [], '', [ord(c) for c in text], 0
    while i < len(cps):
        cp = cps[i]
        if _regional(cp) and i + 1 < len(cps) and _regional(cps[i + 1]):  # bandera: dos letras regionales
            seq, i = [cp, cps[i + 1]], i + 2
        elif _base(cp):
            seq, i = [cp], i + 1
            while i < len(cps):
                if cps[i] == VS16 or _skin(cps[i]):
                    seq.append(cps[i])
                    i += 1
                elif cps[i] == ZWJ and i + 1 < len(cps) and _base(cps[i + 1]):
                    seq += [ZWJ, cps[i + 1]]
                    i += 2
                else:
                    break
        else:
            if cp != VS16:
                buf += chr(cp)
            i += 1
            continue
        if buf:
            out.append({'t': buf})
            buf = ''
        out.append({'e': _url(seq)})
    if buf:
        out.append({'t': buf})
    return out


def build(chunks):
    """Une trozos (str o {'e': url}) en partes, con los emojis del texto ya separados."""
    out = []
    for c in chunks:
        for p in (split_emoji(c) if isinstance(c, str) else [c]):
            if 't' in p and out and 't' in out[-1]:
                out[-1] = {'t': out[-1]['t'] + p['t']}
            elif p.get('t') != '':
                out.append(p)
    return out
