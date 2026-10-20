"""Cliente HTTP mínimo (biblioteca estándar)."""
import json
import urllib.error
import urllib.request

UA = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36'


class HttpError(Exception):
    def __init__(self, status, url=''):
        super().__init__('HTTP %s en %s' % (status, url.split('?')[0]))
        self.status = status


def fetch(url, data=None, headers=None, timeout=15):
    h = {'User-Agent': UA}
    h.update(headers or {})
    body = None
    if data is not None:
        body = json.dumps(data).encode()
        h.setdefault('Content-Type', 'application/json')
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=body, headers=h), timeout=timeout) as f:
            return f.read()
    except urllib.error.HTTPError as e:
        raise HttpError(e.code, url) from None


def fetch_json(url, data=None, headers=None, timeout=15):
    return json.loads(fetch(url, data, headers, timeout))
