"""Carga del archivo de configuración (JSON)."""
import json
import re
import sys
from dataclasses import dataclass, field

PLATFORMS = ('twitch',)
RETIRED = ('kick',)  # se quitó: sus canales se ignoran con un aviso en vez de impedir el arranque


@dataclass
class Channel:
    platform: str
    slug: str


@dataclass
class Config:
    port: int = 8099
    state_path: str = 'state.json'
    channels: list = field(default_factory=list)
    vods_per_channel: int = 20
    default_quality: int = 1080
    language: str = 'es'  # idioma de "Lo más visto" y "También en vivo"
    twitch_token_file: str = None  # archivo con el auth-token de tu cuenta (opcional: sin anuncios si eres sub)


def load_config(path):
    with open(path, encoding='utf-8') as f:
        raw = json.load(f)
    channels = []
    for c in raw.get('channels') or []:
        platform = c.get('platform', 'twitch')
        if platform in RETIRED:
            print('aviso: se ignora %s/%s (tvlibre ya solo usa Twitch)' % (platform, c.get('slug')), file=sys.stderr)
            continue
        if platform not in PLATFORMS:
            raise ValueError('plataforma no soportada: %r (usa twitch)' % platform)
        if not c.get('slug'):
            raise ValueError('canal sin slug: %r' % c)
        channels.append(Channel(platform, c['slug'].lower()))
    language = str(raw.get('language', 'es')).lower()
    if not re.match(r'^[a-z]{2}$', language):
        raise ValueError('language va como código de dos letras (es, en, pt…): %r' % language)
    return Config(
        port=int(raw.get('port', 8099)),
        state_path=raw.get('state_path', 'state.json'),
        channels=channels,
        vods_per_channel=int(raw.get('vods_per_channel', 20)),
        default_quality=int(raw.get('default_quality', 1080)),
        language=language,
        twitch_token_file=raw.get('twitch_token_file') or None,
    )
