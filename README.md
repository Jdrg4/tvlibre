# tvlibre

> **English summary:** tvlibre turns the built-in web browser of an old Smart TV (tested on a 2014-era
> Chrome 39 engine) into a remote-friendly app to watch **Kick and Twitch** channels: who is live right
> now, plus past broadcasts with seeking and resume. A small Python server on your home network does
> the heavy lifting — it talks to Kick and Twitch, rewrites HLS playlists so the old TV player accepts
> them, and remuxes Twitch's fMP4 VODs to MPEG-TS with ffmpeg (no re-encoding). Python standard library
> only, plus ffmpeg. **LAN only — never expose it to the internet.** MIT license.

Muchos Smart TV viejos traen un sistema que ya no recibe apps: no hay Kick, no hay Twitch y no hay
forma de instalarlos. Pero su **navegador integrado sí reproduce video HLS**. tvlibre aprovecha eso.
Un servidor pequeño en tu red consulta Kick y Twitch, adapta el video a lo que entiende la TV y le
sirve una interfaz pensada para el control remoto:

- Arriba, **"En vivo ahora"**, con tus canales que estén transmitiendo.
- Abajo, sus **streams anteriores**, mezclados por fecha. Se pueden adelantar, y si los dejas a
  medias continúan donde ibas.
- **Brillo propio**, por si las apps de tu TV te lo fuerzan al máximo.
- 1080p por defecto, con 720p a un botón si el wifi no da.
- Funciona con las flechas del control **y** con el puntero (la "manito") que muestran algunos navegadores de TV.

## ¿Sirve en mi TV?

Instálalo (abajo) y abre en el navegador de la TV `http://<ip-del-servidor>:8099/diagnostico`.
Esa página muestra qué soporta el navegador, registra los códigos de las teclas de tu control y, con
**Probar video**, reproduce un directo y un anterior de tus canales y prueba el adelanto. Si los
videos salen OK, tvlibre funciona en tu TV.

Lo que necesita la TV es un navegador que reproduzca HLS en `<video>`. No hace falta ES6.

## Requisitos

- Un equipo de tu red que quede encendido, con **Linux** (o cualquier sistema con Python), **Python 3.10
  o superior** y **ffmpeg**. ffmpeg solo hace falta para los anteriores de Twitch, que se convierten
  al vuelo de fMP4 a MPEG-TS sin recodificar.
- La TV y ese equipo en la misma red.

## Instalación (Debian/Ubuntu)

```bash
sudo apt install -y python3 ffmpeg git
sudo git clone https://github.com/Jdrg4/tvlibre /opt/tvlibre
sudo mkdir -p /etc/tvlibre /var/lib/tvlibre
sudo cp /opt/tvlibre/config.example.json /etc/tvlibre/config.json
sudo chown "$USER" /var/lib/tvlibre
sudo nano /etc/tvlibre/config.json          # pon tus canales y "state_path": "/var/lib/tvlibre/state.json"
sudo cp /opt/tvlibre/deploy/tvlibre@.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now "tvlibre@$USER"
```

Después, en la TV, abre `http://<ip-del-servidor>:8099/`. Si el navegador de la TV permite
favoritos o página de inicio, guárdala ahí.

Para probarlo sin instalar nada: copia `config.example.json` a `config.local.json`, cambia los slugs de ejemplo por canales reales (con los de ejemplo la portada solo mostrará errores) y corre `python3 -m tvlibre --config config.local.json`.

## Configuración

```json
{
  "port": 8099,
  "state_path": "/var/lib/tvlibre/state.json",
  "vods_per_channel": 20,
  "default_quality": 1080,
  "channels": [
    {"platform": "kick", "slug": "nombre_del_canal"},
    {"platform": "twitch", "slug": "nombre_del_canal"}
  ]
}
```

- `slug` es el nombre del canal como aparece en su URL (`kick.com/<slug>`, `twitch.tv/<slug>`).
  Puedes poner varios canales de cada plataforma.
- `state_path` es donde se guardan el brillo y los puntos de retomar.

## Control remoto

| Dónde | Tecla | Hace |
|---|---|---|
| Portada | Flechas | Moverse entre tarjetas y filas |
| Portada | OK | Abrir el directo o el anterior |
| Portada, sobre el ☀ | ← → | Bajar o subir el brillo |
| Reproductor | ← → | Retroceder o adelantar 10 s (mantener: 30 s y 60 s) |
| Reproductor | OK | Pausa |
| Reproductor | ↑ ↓ | Subir o bajar el brillo |
| Reproductor | Atrás | Volver a la portada (guarda dónde ibas) |
| Con puntero | Clic | Tarjetas, flechas ‹ › de cada fila, −/+ del brillo y botones del reproductor (calidad incluida) |

## Seguridad: solo en tu red

tvlibre **rechaza cualquier petición que no venga de una IP privada** (10/8, 172.16/12, 192.168/16,
loopback y 100.64/10 de Tailscale). Aun así, **no abras su puerto en el router**. Expuesto a
internet sería un proxy de video abierto que consumiría tu ancho de banda. Para usarlo fuera de casa,
usa una VPN como Tailscale.

Además, para que ninguna web abierta en otro navegador de tu casa pueda usarlo, tvlibre solo atiende si se entra **por IP** (`http://192.168.x.x:8099/`) o por `localhost`, nunca por un nombre de dominio, y solo acepta escrituras con `Content-Type: application/json`.

## Cómo funciona

```
TV (navegador) ──HTTP──▶ tvlibre (tu red) ──HTTPS──▶ Kick / Twitch
```

- **Kick en vivo:** la TV lo pide directo a la CDN de Kick.
- **Twitch en vivo y los anteriores:** pasan por tvlibre, que reescribe cada playlist HLS con URLs
  absolutas y sin las etiquetas que un reproductor viejo no entiende.
- **Anteriores de Twitch:** vienen en fMP4, y tvlibre convierte cada segmento a MPEG-TS con
  `ffmpeg -c copy`, como máximo 3 a la vez.

## Aviso

tvlibre usa las **APIs públicas no oficiales** de Kick y Twitch, las mismas que usan sus sitios web,
así que puede dejar de funcionar si cambian. No tiene relación con Kick, Twitch ni ningún fabricante
de televisores. Es para uso personal: no sirve contenido que tu cuenta no podría ver (no hay
inicio de sesión, así que el contenido solo para suscriptores no aparece) y no quita la publicidad
que las plataformas meten en el stream.

## Limitaciones conocidas

- Un enlace `/play/<id>` con un id inexistente fuerza a recargar la portada: no tiene límite de frecuencia.
- `/img` sigue redirecciones de los CDN permitidos y no limita el tamaño de la imagen.
- Un video de más de unos 55 h (más de 20 000 segmentos) olvidaría sus primeros segmentos.
- Si la TV corta una descarga al adelantar, el registro del servicio muestra un error de conexión inofensivo.
- Si Twitch empezara a mandar fechas con milisegundos, ese canal fallaría en la portada.

## Desarrollo

```bash
python -m unittest discover -s tests -v
```

Lee `CLAUDE.md` antes de contribuir. Ahí están las reglas que no se negocian: el front en ES5, las
URLs absolutas para el reproductor de la TV y solo la biblioteca estándar.

## Licencia

MIT. Ver [LICENSE](LICENSE).
