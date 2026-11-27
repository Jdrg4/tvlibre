# tvlibre: guía para colaboradores (y agentes)

App web para el navegador integrado de Smart TVs viejos (y canal de Roku) que muestra directos y streams
anteriores de cualquier canal de Twitch. Kick se quitó en 2026-11: solo Twitch. Un servidor Python en la red local hace el trabajo pesado y la TV solo pinta la
interfaz y reproduce HLS.

## Comandos

```bash
python -m unittest discover -s tests -v                 # toda la suite (las de ffmpeg se saltan si no está)
python -m tvlibre --config config.example.json --verbose # servidor local en :8099
```

En la TV: `/` es la app y `/diagnostico` muestra capacidades, teclas y pruebas de video.

## Arquitectura

| Módulo | Responsabilidad |
|---|---|
| `tvlibre/config.py` | Carga el JSON de configuración (canales, puerto, estado, `language`); las entradas `kick` se ignoran con aviso |
| `tvlibre/providers/twitch.py` | GQL no oficial: `channel_state`, `channel_page` (página de cualquier canal), `item(id)` (rehace un item por su id), `master_url`, `search`, `top` (lo más visto por idioma) y `discover`, con sus `parse_*` puros |
| `tvlibre/catalog.py` | Portada (directos, anteriores, "Lo más visto" y "También en vivo", caché de 60 s y 5 min), página de canal (60 s), búsqueda, seguir/dejar de seguir; `item()` cae a `provider.item()` si el id no salió en pantalla |
| `tvlibre/hls.py` | Elige variante y reescribe playlists (URLs absolutas, etiquetas filtradas, `#EXT-X-MAP`); en directo, `rewrite_live` quita los anuncios intercalados y renumera |
| `tvlibre/providers/twitch_irc.py` | Chat en vivo de Twitch por IRC anónimo: un hilo por canal, se cierra a los 120 s sin pedidos |
| `tvlibre/proxy.py` | Sesiones de playlist con renovación de token, segmentos, LRU |
| `tvlibre/remux.py` | Convierte fMP4 a MPEG-TS con `ffmpeg -c copy` (máximo 3 a la vez) |
| `tvlibre/state.py` | Brillo, canales seguidos y puntos de retomar en un JSON, con escritura atómica |
| `tvlibre/server.py` | HTTP (`ThreadingHTTPServer`), rutas (`/api/home`, `/api/channel/<login>`, `/api/search`, `/play/<id>.m3u8`…) y filtro de solo red local |
| `tvlibre/web/` | Front en ES5: `index.html`, `app.js`, `app.css` y `diagnostico.html` |
| `roku/` | Canal de Roku (BrightScript + SceneGraph) sobre la misma API; `roku/build.py <url>` arma el zip |

Un item (directo o anterior) es un dict con `id` (`<plataforma>-<live|vod>-<ref>`, con caracteres
`[a-z0-9_-]`), `platform`, `kind`, `channel`, `title`, `started_at` (ISO UTC), `duration_s`,
`viewers`, `thumb` y `ref`; además `name` (displayName de Twitch) y, en directos, `category`.

## Lo medido en una TV real (Chrome 39, 1280x720)

Estas reglas salen de pruebas en hardware, no de suposiciones. No las cambies sin volver a medir con
`/diagnostico`.

- **Front solo en ES5 + XHR.** Nada de `=>`, `let`/`const`, plantillas, clases, `fetch` ni CSS
  grid. `tests/test_frontend_es5.py` lo vigila.
- **El reproductor no sigue redirecciones relativas** (error 4). Toda `Location` y toda URL dentro
  de una `.m3u8` va absoluta.
- **Decide el tipo por la extensión.** Los enlaces del proxy terminan en `.m3u8` o `.ts`.
- **Se entrega la playlist de una variante, nunca la maestra.** Con la maestra, la TV elegía
  1080p60 de perfil High y fallaba.
- **Los anuncios a mitad del directo congelaban el video** (a los ~12 min, medido): Twitch los intercala con otro
  init y un `#EXT-X-DISCONTINUITY`. El proxy los quita (`hls.rewrite_live`) y la TV y el Roku tienen un vigilante
  que vuelve a pedir el video si pasa 12 s quieto. Con `twitch_token_file` y sub al canal, Twitch ni los manda.
- **Twitch directo falla (error 3), por el proxy funciona.** Todo va por el proxy. Los anteriores vienen en
  fMP4, que la TV no decodifica, por eso se convierten.

## Lo medido en un Roku real (Express 4K+, Roku OS 15.3)

- **Con "Control por aplicaciones móviles → Acceso a la red" en *Limitado*, el instalador (puerto 80) y la
  consola (8085) rechazan la conexión** aunque el modo desarrollador esté activo. En *Permisivo* y tras
  reiniciar, funcionan.
- Los canales beta exigen un `.pkg` firmado, que solo genera el instalador del propio Roku: no sirven sin él.
- **Durante un video, el `*` lo toma el Roku** para su menú de Opciones (volumen, accesibilidad): no llega al canal.
  El chat se alterna con OK y la pausa va en ⏯.
- Errores de compilación y de ejecución: `telnet <ip-del-roku> 8085`. Ojo con nombres de variable que son
  funciones de BrightScript (`pos`, `len`, `str`, `val`, `mid`, `tab`…): no compilan.
  `tests/test_roku.py` vigila los más comunes.
- La IP del servidor no va en el repo: `build.py` la escribe en el `manifest` del zip.
- El foco del reproductor y del brillo va al nodo `keys`: con `m.top.setFocus` la fila oculta se quedaba con el
  foco y OK abría otra tarjeta en pleno video.
- **El icono del canal sale de `mm_icon_focus_fhd` (540x405)** porque el canal es `ui_resolutions=fhd`. Sin esa clave,
  en Roku OS 15 el canal quedó sin icono. Además el Roku guarda el icono según la versión: `build.py` pone un
  `build_version` nuevo en cada build. `tests/test_roku.py` vigila los tamaños.
- Los anteriores de Twitch traen tramos silenciados por derechos (segmentos `-muted`, audio a -91 dB): no es un
  fallo de la conversión; `/api/muted/<id>` los da y la barra los avisa.

## Reglas

- Servidor: **solo biblioteca estándar** más el binario `ffmpeg`. Nada de `pip install`.
- La API de Twitch no es oficial: todo acceso a ella vive en `providers/`.
- Solo red local: `server.is_allowed` rechaza las IP que no son privadas. No se debilita.
- Las fixtures de `tests/fixtures/` son respuestas reales **anonimizadas**: sin nombres de canales,
  IDs ni títulos reales.

## Antes de abrir un PR

- [ ] `python -m unittest discover -s tests -v` en verde, incluidas las de ffmpeg.
- [ ] Si tocaste el front o el proxy: probado en una TV real con `/diagnostico` y la app.
- [ ] El README sigue diciendo la verdad sobre lo que cambiaste.
