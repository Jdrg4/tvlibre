# AGENTS.md

Lee `CLAUDE.md`: tiene los comandos, la arquitectura y lo medido en TVs reales.

Reglas no negociables:

1. El front (`tvlibre/web/`) es **ES5 + XHR**, sin CSS grid. Corre en navegadores de TV de 2014.
2. Toda URL que reciba la TV (`Location` y líneas de `.m3u8`) es **absoluta** y termina en `.m3u8` o `.ts`.
3. El servidor usa **solo la biblioteca estándar** de Python, más `ffmpeg`.
4. Solo red local: no se debilita `server.is_allowed`.
5. `python -m unittest discover -s tests -v` en verde antes de terminar.
