# 🎬 Stream Clipper

Le das el **link de un stream** (Twitch, YouTube, Kick y casi cualquier web que soporte
[yt-dlp](https://github.com/yt-dlp/yt-dlp)) y te saca **clips de los mejores momentos**,
listos para subir a TikTok, YouTube Shorts, Instagram Reels o X.

## ¿Cómo sabe cuáles son los mejores momentos?

1. **Audio** – descarga solo el audio (rápido) y mide el volumen segundo a segundo.
   Los gritos, risas, explosiones y reacciones fuertes destacan sobre el volumen normal
   de *esa parte* del stream.
2. **Chat** – si el stream tiene chat (VODs de Twitch, directos de YouTube), cuenta
   cuántos mensajes llegan por segundo y da puntos extra a los de "hype"
   (`KEKW`, `POG`, `jajaja`, `CLIP`, `NO WAY`, `!!!`...). El chat reacciona unos segundos
   tarde, así que la herramienta lo compensa.
3. Junta las dos señales, elige los N picos más fuertes sin que se repitan, y
   **descarga solo esos trozos** del video (no el stream entero de 6 horas).
4. Los corta con ffmpeg. Opcional: **formato vertical 9:16** con fondo difuminado y
   **subtítulos automáticos** con Whisper.

Cada clip empieza unos segundos *antes* del pico para que se entienda el contexto.

---

## Opción A: usarlo desde GitHub (sin instalar nada)

1. Sube este repositorio a tu GitHub (ver más abajo).
2. Ve a la pestaña **Actions** → **Sacar clips de un stream** → **Run workflow**.
3. Pega el link, elige cuántos clips, la duración y si los quieres en vertical.
4. Cuando termine (verde ✅), entra en la ejecución y descarga **clips** en la sección
   *Artifacts*. Es un .zip con los videos y un `highlights.json`.

> ⚠️ YouTube a veces bloquea los servidores de GitHub ("Sign in to confirm you're not a bot").
> Si te pasa, usa la opción B en tu ordenador. Con Twitch normalmente funciona sin problema.

## Opción B: usarlo en tu ordenador

### 1. Instalar

Necesitas **Python 3.10+** y **ffmpeg**.

- **Windows**: `winget install Python.Python.3.12` y `winget install Gyan.FFmpeg`
- **macOS**: `brew install python ffmpeg`
- **Linux**: `sudo apt install python3 python3-pip ffmpeg`

Luego, dentro de la carpeta del proyecto:

```bash
pip install -r requirements.txt
# opcional, solo si quieres subtítulos:
pip install -r requirements-subs.txt
```

### 2. Usar

```bash
# Lo básico: 8 clips de 30 s
python -m clipper "https://www.twitch.tv/videos/123456789"

# 5 clips de 45 s en vertical para TikTok/Shorts, con subtítulos en español
python -m clipper "https://www.youtube.com/watch?v=XXXX" -n 5 -l 45 --vertical --subs --subs-lang es

# Primero mirar qué momentos encuentra, sin descargar nada de video
python -m clipper "https://www.twitch.tv/videos/123456789" --dry-run

# También funciona con un video que ya tengas descargado
python -m clipper mi_stream.mp4 --vertical
```

Los clips quedan en la carpeta `clips/`, junto con `highlights.json`, que tiene la
hora de cada momento, su puntuación y un link directo a ese segundo del stream.

### Opciones

| Opción | Qué hace | Por defecto |
|---|---|---|
| `-n`, `--num-clips` | Cuántos clips sacar | 8 |
| `-l`, `--length` | Duración de cada clip (segundos) | 30 |
| `-o`, `--output` | Carpeta de salida | `clips` |
| `--vertical` | 1080×1920 con fondo difuminado | no |
| `--subs` | Subtítulos automáticos (Whisper) | no |
| `--subs-lang` | Idioma de los subtítulos (`es`, `en`...) | automático |
| `--subs-model` | `tiny` / `base` / `small` / `medium` (más grande = mejor y más lento) | `small` |
| `--no-chat` | Ignorar el chat, usar solo el audio | no |
| `--chat-delay` | Segundos que tarda el chat en reaccionar | 6 |
| `--min-score` | Puntuación mínima; bájala (ej. `0.5`) si encuentra pocos momentos | 1.0 |
| `--skip-start` / `--skip-end` | Ignorar el principio/final del stream (segundos) | 60 / 30 |
| `--max-height` | Resolución máxima a descargar | 1080 |
| `--cookies` | Archivo `cookies.txt` para VODs que piden login | – |
| `--dry-run` | Solo listar los momentos | no |

## Consejos

- **Streams de Just Chatting / reacciones**: el chat es la mejor señal; deja el chat activado.
- **Streams de juegos con mucha música**: si salen momentos "falsos" por la música alta,
  sube `--min-score` a 1.5–2.
- **Clips para TikTok/Shorts**: `-l 30 --vertical --subs` suele funcionar muy bien.
- Revisa siempre los clips antes de subirlos: la herramienta encuentra momentos
  intensos, pero tú decides cuáles son graciosos de verdad.

## Derechos

Usa la herramienta con tus propios streams o con contenido que tengas permiso para
clipear (muchos streamers permiten clips; otros no). Respeta las normas de cada plataforma.

## Estructura

```
clipper/
  cli.py        # comandos y flujo principal
  download.py   # descarga de audio y de trozos de video (yt-dlp)
  audio.py      # volumen segundo a segundo (ffmpeg + numpy)
  chat.py       # actividad del chat (chat-downloader)
  scoring.py    # combina señales y elige los mejores momentos
  render.py     # corte, formato vertical y subtítulos (ffmpeg, faster-whisper)
.github/workflows/clips.yml   # botón "Run workflow" en GitHub
```

Licencia MIT.
