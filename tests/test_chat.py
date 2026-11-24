"""Chat de solo lectura: formatos de Twitch (anteriores) e IRC de Twitch (en vivo)."""
import threading
import time
import unittest

from tvlibre.providers import twitch, twitch_irc


class TwitchChatTest(unittest.TestCase):
    def test_comentarios_de_anterior(self):
        gql = {'data': {'video': {'comments': {'edges': [
            {'node': {'id': 'c1', 'contentOffsetSeconds': 3597, 'commenter': {'displayName': 'Uno'},
                      'message': {'userColor': '#112233', 'fragments': [{'text': 'hola '}, {'text': 'Kappa'}]}}},
            {'node': {'id': 'c2', 'contentOffsetSeconds': 3620, 'commenter': None,
                      'message': {'userColor': None, 'fragments': [{'text': 'x'}]}}}]}}}}
        msgs = twitch.parse_comments(gql)
        self.assertEqual(msgs[0], {'id': 'c1', 'user': 'Uno', 'color': '#112233', 'text': 'hola Kappa',
                                   'parts': [{'t': 'hola Kappa'}], 'at': 3597})
        self.assertEqual(msgs[1]['user'], '?')

    def test_irc_privmsg(self):
        line = ('@badge-info=;color=#FF4500;display-name=Alguien;id=abc-123;tmi-sent-ts=1 '
                ':alguien!alguien@alguien.tmi.twitch.tv PRIVMSG #canal :qué pasa :D')
        self.assertEqual(twitch_irc.parse_line(line),
                         {'id': 'abc-123', 'user': 'Alguien', 'color': '#FF4500', 'text': 'qué pasa :D',
                          'parts': [{'t': 'qué pasa :D'}], 'at': None})
        self.assertIsNone(twitch_irc.parse_line(':tmi.twitch.tv 001 justinfan1 :Welcome'))


class FakeSock:
    def __init__(self, lines):
        self.lines, self.sent, self.closed = list(lines), [], False

    def sendall(self, b):
        self.sent.append(b)

    def recv(self, n):
        if self.lines:
            return self.lines.pop(0).encode()
        time.sleep(0.05)
        if self.closed:
            return b''
        raise TimeoutError

    def settimeout(self, t):
        pass

    def close(self):
        self.closed = True


class LiveRealSocketTest(unittest.TestCase):
    def test_pausa_sin_mensajes_no_reconecta(self):
        # con makefile + timeout, tras el primer segundo en silencio Python deja el socket inservible y se reconectaba
        import socket
        ours, theirs = socket.socketpair()
        calls = []

        def connect(*a, **k):
            calls.append(1)
            return ours if len(calls) == 1 else socket.socketpair()[0]

        live = twitch_irc.Live(connect=connect, idle=5)
        live.messages('canal')

        def talk():
            time.sleep(1.5)
            theirs.sendall('@display-name=Uno;id=m1 :uno!uno@uno.tmi.twitch.tv PRIVMSG #canal :hola ñ\r\n'.encode())
        threading.Thread(target=talk, daemon=True).start()
        deadline = time.time() + 4
        while not live.messages('canal') and time.time() < deadline:
            time.sleep(0.1)
        self.assertEqual([m['text'] for m in live.messages('canal')], ['hola ñ'])
        self.assertEqual(len(calls), 1)
        live.idle = 0
        theirs.close()


class LiveTest(unittest.TestCase):
    def test_buffer_ping_y_cierre_por_inactividad(self):
        sock = FakeSock(['PING :tmi.twitch.tv\r\n',
                         '@color=;display-name=Uno;id=m1 :uno!uno@uno.tmi.twitch.tv PRIVMSG #canal :hola\r\n'])
        live = twitch_irc.Live(connect=lambda *a, **k: sock, idle=0.3)
        live.messages('canal')  # abre la conexión
        deadline = time.time() + 2
        while not live.messages('canal') and time.time() < deadline:
            time.sleep(0.05)
        self.assertEqual([m['id'] for m in live.messages('canal')], ['m1'])
        self.assertIn(b'PONG :tmi.twitch.tv\r\n', sock.sent)
        self.assertIn(b'JOIN #canal\r\n', sock.sent[0])
        time.sleep(1)  # nadie pide: se cierra sola
        self.assertTrue(sock.closed)
        self.assertNotIn('canal', live._rooms)


if __name__ == '__main__':
    unittest.main()
