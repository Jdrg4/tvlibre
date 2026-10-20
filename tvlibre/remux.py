"""Conversión de segmentos fMP4 a MPEG-TS con ffmpeg, sin recodificar."""
import shutil
import subprocess
import threading

_SLOTS = threading.BoundedSemaphore(3)
CMD = ['ffmpeg', '-loglevel', 'error', '-i', 'pipe:0', '-c', 'copy', '-copyts', '-muxdelay', '0',
       '-f', 'mpegts', 'pipe:1']


class RemuxError(Exception):
    pass


def available():
    return shutil.which('ffmpeg') is not None


def to_ts(init, segment):
    with _SLOTS:
        try:
            r = subprocess.run(CMD, input=init + segment, capture_output=True, timeout=30)
        except subprocess.TimeoutExpired:
            raise RemuxError('ffmpeg tardó más de 30 s') from None
    if r.returncode or not r.stdout:
        raise RemuxError('ffmpeg falló: ' + r.stderr.decode(errors='replace')[-200:].strip())
    return r.stdout
