"""Estado persistente: brillo, canales seguidos y punto de retomar de cada video (un JSON compartido)."""
import json
import os
import threading


class State:
    def __init__(self, path):
        self.path = path
        self._lock = threading.Lock()
        try:
            with open(path, encoding='utf-8') as f:
                self._data = json.load(f)
            if not isinstance(self._data, dict):
                raise ValueError
        except (OSError, ValueError):
            self._data = {}
        self._data.setdefault('brightness', 100)
        self._data.setdefault('resume', {})

    def _save(self):
        tmp = self.path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(self._data, f)
        os.replace(tmp, self.path)

    def brightness(self):
        return self._data['brightness']

    def set_brightness(self, v):
        with self._lock:
            self._data['brightness'] = max(30, min(100, int(v)))
            self._save()

    def channels(self):
        # None mientras nunca se hayan editado desde la pantalla: valen los de la configuración
        return self._data.get('channels')

    def set_channels(self, channels):
        with self._lock:
            self._data['channels'] = [{'platform': c['platform'], 'slug': c['slug']} for c in channels]
            self._save()

    def resume(self, item_id):
        return self._data['resume'].get(item_id)

    def set_resume(self, item_id, position_s, duration_s):
        position_s = int(position_s)
        done = duration_s and position_s >= 0.95 * duration_s
        with self._lock:
            if position_s < 30 or done:
                self._data['resume'].pop(item_id, None)
            else:
                self._data['resume'][item_id] = position_s
            self._save()
