"""Chat de solo lectura: formatos de Kick, Twitch (anteriores) e IRC de Twitch (en vivo)."""
import threading
import time
import unittest

from tvlibre.providers import kick, twitch, twitch_irc


def kick_msg(i, when, text='hola', color='#AABBCC'):
    return {'id': 'k%d' % i, 'content': text, 'type': 'message', 'created_at': when,
            'sender': {'username': 'usuario%d' % i, 'identity': {'color': color}}}


class KickChatTest(unittest.TestCase):
    def test_en_vivo_cronologico_y_emotes(self):
        # Kick entrega el más nuevo primero
        js = {'data': {'messages': [kick_msg(2, '2026-10-20T04:18:53Z', 'jaja [emote:4148144:catblobDance] ok'),
                                    kick_msg(1, '2026-10-20T04:18:46Z')]}}
        msgs = kick.parse_messages(js)
        self.assertEqual([m['id'] for m in msgs], ['k1', 'k2'])
        self.assertEqual(msgs[1]['text'], 'jaja :catblobDance: ok')
        self.assertEqual((msgs[0]['user'], msgs[0]['color'], msgs[0]['at']), ('usuario1', '#AABBCC', None))

    def test_anterior_con_segundo_y_filtro(self):
        js = {'data': {'messages': [kick_msg(1, '2026-10-19T01:10:02Z'), kick_msg(2, '2026-10-19T00:10:00Z')]}}
        msgs = kick.parse_messages(js, started_at='2026-10-19T00:10:01Z', since=3600)
        self.assertEqual([(m['id'], m['at']) for m in msgs], [('k1', 3601)])

    def test_anterior_pide_la_hora_absoluta(self):
        urls = []
        orig = kick.net.fetch_json
        kick.net.fetch_json = lambda url, *a, **k: urls.append(url) or (
            {'id': 77} if url.endswith('/canal_k') else {'data': {'messages': []}})
        kick._ids.clear()
        try:
            r = kick.chat({'kind': 'vod', 'channel': 'canal_k', 'started_at': '2026-10-19T00:10:01Z'}, 3600)
        finally:
            kick.net.fetch_json = orig
        self.assertIn('/77/messages?start_time=2026-10-19T01%3A10%3A01.000Z', urls[-1])
        self.assertEqual(r, {'messages': [], 'until': 3605})


class TwitchChatTest(unittest.TestCase):
    def test_comentarios_de_anterior(self):
        gql = {'data': {'video': {'comments': {'edges': [
            {'node': {'id': 'c1', 'contentOffsetSeconds': 3597, 'commenter': {'displayName': 'Uno'},
                      'message': {'userColor': '#112233', 'fragments': [{'text': 'hola '}, {'text': 'Kappa'}]}}},
            {'node': {'id': 'c2', 'contentOffsetSeconds': 3620, 'commenter': None,
                      'message': {'userColor': None, 'fragments': [{'text': 'x'}]}}}]}}}}
        msgs = twitch.parse_comments(gql)
        self.assertEqual(msgs[0], {'id': 'c1', 'user': 'Uno', 'color': '#112233', 'text': 'hola Kappa', 'at': 3597})
        self.assertEqual(msgs[1]['user'], '?')

    def test_irc_privmsg(self):
        line = ('@badge-info=;color=#FF4500;display-name=Alguien;id=abc-123;tmi-sent-ts=1 '
                ':alguien!alguien@alguien.tmi.twitch.tv PRIVMSG #canal :qué pasa :D')
        self.assertEqual(twitch_irc.parse_line(line),
                         {'id': 'abc-123', 'user': 'Alguien', 'color': '#FF4500', 'text': 'qué pasa :D', 'at': None})
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
