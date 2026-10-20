"""Partes de un mensaje de chat: texto, emotes de Kick/Twitch y emojis (como imágenes)."""
import unittest

from tvlibre import chatparts
from tvlibre.providers import kick, twitch, twitch_irc

TW = 'https://cdn.jsdelivr.net/gh/jdecked/twemoji@15.1.0/assets/72x72/'


class EmojiTest(unittest.TestCase):
    def test_texto_y_emojis(self):
        self.assertEqual(chatparts.split_emoji('hola 😂 ok'),
                         [{'t': 'hola '}, {'e': TW + '1f602.png'}, {'t': ' ok'}])

    def test_secuencias_y_selector(self):
        # 👨‍💻 es un solo emoji (ZWJ); ❤️ lleva FE0F, que Twemoji no usa en el nombre
        self.assertEqual(chatparts.split_emoji('👨‍💻❤️'), [{'e': TW + '1f468-200d-1f4bb.png'}, {'e': TW + '2764.png'}])

    def test_tono_de_piel(self):
        self.assertEqual(chatparts.split_emoji('👍🏽'), [{'e': TW + '1f44d-1f3fd.png'}])

    def test_sin_emojis(self):
        self.assertEqual(chatparts.split_emoji('ñandú: ¿qué?'), [{'t': 'ñandú: ¿qué?'}])


class EmotesTest(unittest.TestCase):
    def test_kick(self):
        js = {'data': {'messages': [{'id': 'k1', 'type': 'message', 'created_at': '2026-10-20T04:18:46Z',
                                     'content': 'jaja [emote:4148144:catblobDance]🔥',
                                     'sender': {'username': 'u', 'identity': {}}}]}}
        m = kick.parse_messages(js)[0]
        self.assertEqual(m['parts'], [{'t': 'jaja '}, {'e': 'https://files.kick.com/emotes/4148144/fullsize'},
                                      {'e': TW + '1f525.png'}])
        self.assertEqual(m['text'], 'jaja :catblobDance:🔥')

    def test_twitch_irc(self):
        line = ('@display-name=Uno;emotes=25:5-9;id=m1 :uno!uno@uno.tmi.twitch.tv PRIVMSG #canal :hola Kappa ñ')
        self.assertEqual(twitch_irc.parse_line(line)['parts'],
                         [{'t': 'hola '}, {'e': 'https://static-cdn.jtvnw.net/emoticons/v2/25/default/dark/1.0'},
                          {'t': ' ñ'}])

    def test_twitch_irc_accion(self):
        line = '@display-name=Uno;id=m2 :uno!uno@uno.tmi.twitch.tv PRIVMSG #canal :\x01ACTION baila\x01'
        self.assertEqual(twitch_irc.parse_line(line)['text'], 'baila')

    def test_twitch_anterior(self):
        gql = {'data': {'video': {'comments': {'edges': [{'node': {
            'id': 'c1', 'contentOffsetSeconds': 5, 'commenter': {'displayName': 'Uno'},
            'message': {'userColor': None, 'fragments': [{'text': 'jaja ', 'emote': None},
                                                         {'text': 'JinxLUL', 'emote': {'emoteID': 'emotesv2_abc'}}]}}}]}}}}
        self.assertEqual(twitch.parse_comments(gql)[0]['parts'],
                         [{'t': 'jaja '}, {'e': 'https://static-cdn.jtvnw.net/emoticons/v2/emotesv2_abc/default/dark/1.0'}])


if __name__ == '__main__':
    unittest.main()
