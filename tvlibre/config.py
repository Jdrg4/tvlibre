"""Carga del archivo de configuración (JSON)."""
import json
from dataclasses import dataclass, field

PLATFORMS = ('twitch', 'kick')


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


def load_config(path):
    with open(path, encoding='utf-8') as f:
        raw = json.load(f)
    channels = []
    for c in raw.get('channels') or []:
        if c.get('platform') not in PLATFORMS:
            raise ValueError('plataforma no soportada: %r (usa %s)' % (c.get('platform'), ' o '.join(PLATFORMS)))
        if not c.get('slug'):
            raise ValueError('canal sin slug: %r' % c)
        channels.append(Channel(c['platform'], c['slug'].lower()))
    if not channels:
        raise ValueError('la configuración no tiene canales')
    return Config(
        port=int(raw.get('port', 8099)),
        state_path=raw.get('state_path', 'state.json'),
        channels=channels,
        vods_per_channel=int(raw.get('vods_per_channel', 20)),
        default_quality=int(raw.get('default_quality', 1080)),
    )
