"""Chat en vivo de Twitch por su IRC público, anónimo (usuario justinfan, solo lectura)."""
import random
import socket
import threading
import time
from collections import deque

HOST, PORT = 'irc.chat.twitch.tv', 6667


def parse_line(line):
    """PRIVMSG con etiquetas → mensaje normalizado; cualquier otra línea → None."""
    tags, rest = {}, line.rstrip('\r\n')
    if rest.startswith('@'):
        raw, _, rest = rest.partition(' ')
        for kv in raw[1:].split(';'):
            k, _, v = kv.partition('=')
            tags[k] = v
    parts = rest.split(' ', 3)
    if len(parts) < 4 or parts[1] != 'PRIVMSG':
        return None
    nick = parts[0][1:].split('!')[0]
    text = parts[3][1:] if parts[3].startswith(':') else parts[3]
    return {'id': tags.get('id') or '%s-%f' % (nick, time.time()), 'user': tags.get('display-name') or nick,
            'color': tags.get('color') or None, 'text': text, 'at': None}


class Live:
    """Una conexión por canal mientras alguien lo mire; se cierra sola si nadie pide mensajes en `idle` s."""

    def __init__(self, connect=socket.create_connection, idle=120, keep=100):
        self.connect, self.idle, self.keep = connect, idle, keep
        self._rooms, self._lock = {}, threading.Lock()

    def messages(self, login):
        with self._lock:
            room = self._rooms.get(login)
            if room is None:
                room = self._rooms[login] = {'buf': deque(maxlen=self.keep), 'seen': time.time()}
                threading.Thread(target=self._run, args=(login, room), daemon=True).start()
            room['seen'] = time.time()
            return list(room['buf'])

    def _run(self, login, room):
        while time.time() - room['seen'] < self.idle:
            sock = None
            try:
                sock = self.connect((HOST, PORT), timeout=10)
                sock.settimeout(1)
                sock.sendall(b'CAP REQ :twitch.tv/tags\r\nNICK justinfan%d\r\nJOIN #%s\r\n'
                             % (random.randint(10000, 99999), login.encode()))
                # recv con buffer propio: con makefile, tras el primer timeout Python deja el objeto inservible
                pending = b''
                while time.time() - room['seen'] < self.idle:
                    try:
                        data = sock.recv(65536)
                    except (TimeoutError, socket.timeout):
                        continue
                    if not data:
                        break  # Twitch cerró: se reconecta tras la pausa de abajo
                    pending += data
                    *lines, pending = pending.split(b'\r\n')
                    for raw in lines:
                        line = raw.decode('utf-8', 'replace')
                        if line.startswith('PING'):
                            sock.sendall(('PONG' + line[4:] + '\r\n').encode())
                            continue
                        msg = parse_line(line)
                        if msg:
                            room['buf'].append(msg)
            except OSError:
                pass
            finally:
                if sock:
                    sock.close()
            if time.time() - room['seen'] < self.idle:
                time.sleep(3)  # sin esto, un cierre limpio de Twitch reconectaba en bucle
        with self._lock:
            if self._rooms.get(login) is room:
                del self._rooms[login]


LIVE = Live()
