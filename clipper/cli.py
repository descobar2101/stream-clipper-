"""Stream Clipper: link de un stream -> clips de los mejores momentos."""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

from . import __version__
from .audio import loudness_per_second
from .chat import chat_activity
from .download import (download_audio, download_hls_range, download_section, get_info,
                       is_url, is_vod_url, pick_hls_format)
from .render import make_srt, render_clip
from .scoring import pick_highlights, score_timeline


def hms(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 3600:d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def timestamp_link(url: str, seconds: float) -> str:
    s = int(seconds)
    if "twitch.tv" in url:
        t = f"{s // 3600}h{s % 3600 // 60}m{s % 60}s"
        return f"{url.split('?')[0]}?t={t}"
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}t={s}"


def slugify(text: str, maxlen: int = 40) -> str:
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE).strip().lower()
    return re.sub(r"[\s_-]+", "-", text)[:maxlen] or "stream"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="stream-clipper",
        description="Saca clips de los mejores momentos de un stream (Twitch, YouTube, Kick...) "
                    "o de un archivo de video local.",
    )
    p.add_argument("source", help="Link del stream/VOD o ruta a un video local")
    p.add_argument("-n", "--num-clips", type=int, default=8, help="Cuántos clips sacar (def: 8)")
    p.add_argument("-l", "--length", type=float, default=30, help="Duración de cada clip en segundos (def: 30)")
    p.add_argument("-o", "--output", default="clips", help="Carpeta de salida (def: ./clips)")
    p.add_argument("--vertical", action="store_true", help="Formato 9:16 para TikTok / Shorts / Reels")
    p.add_argument("--subs", action="store_true", help="Subtítulos automáticos (requiere faster-whisper)")
    p.add_argument("--subs-lang", default=None, help="Idioma de los subtítulos, ej: es, en (def: automático)")
    p.add_argument("--subs-model", default="small", help="Modelo de Whisper: tiny/base/small/medium (def: small)")
    p.add_argument("--no-chat", action="store_true", help="No usar el chat, solo el audio")
    p.add_argument("--chat-delay", type=int, default=6, help="Segundos que tarda el chat en reaccionar (def: 6)")
    p.add_argument("--min-score", type=float, default=1.0, help="Puntuación mínima de un momento (def: 1.0)")
    p.add_argument("--skip-start", type=float, default=60, help="Ignorar los primeros N segundos (def: 60)")
    p.add_argument("--skip-end", type=float, default=30, help="Ignorar los últimos N segundos (def: 30)")
    p.add_argument("--max-height", type=int, default=1080, help="Resolución máxima a descargar (def: 1080)")
    p.add_argument("--cookies", default=None, help="Archivo cookies.txt (para VODs con login o bloqueos de YouTube)")
    p.add_argument("--dry-run", action="store_true", help="Solo mostrar los momentos encontrados, sin cortar clips")
    p.add_argument("--keep-temp", action="store_true", help="No borrar los archivos temporales")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if not shutil.which("ffmpeg"):
        print("ERROR: ffmpeg no está instalado. Mira el README para instalarlo.", file=sys.stderr)
        return 1

    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="stream-clipper-"))
    remote = is_url(args.source)
    live = False

    try:
        # 1) Fuente
        if remote:
            print("» Leyendo información del stream...")
            info = get_info(args.source, args.cookies)
            title = info.get("title") or "stream"
            live = bool(info.get("is_live") or info.get("live_status") == "is_live")
            if live and not is_vod_url(args.source, info):
                print(
                    "\nERROR: este link es el canal en directo, no un video.\n"
                    "  • Twitch: entra al canal → pestaña 'Videos' → copia el link del stream\n"
                    "    (tiene la forma twitch.tv/videos/123456789). Funciona aunque el\n"
                    "    directo siga en marcha: se usa todo lo emitido hasta ahora.\n"
                    "  • YouTube: espera a que termine el directo y usa el link del video.",
                    file=sys.stderr,
                )
                return 1
            if live:
                print("  (El directo sigue en marcha: se usará lo emitido hasta ahora.)")
            print(f"  {title}  ({hms(info.get('duration') or 0)})")
            print("» Descargando solo el audio para analizarlo...")
            if live:
                afmt = pick_hls_format(info, audio_only=True)
                audio_src, _ = download_hls_range(afmt["url"], tmp / "audio.ts",
                                                  headers=afmt.get("http_headers"))
            else:
                audio_src = download_audio(args.source, tmp, args.cookies)
        else:
            src = Path(args.source)
            if not src.exists():
                print(f"ERROR: no existe el archivo {src}", file=sys.stderr)
                return 1
            title = src.stem
            audio_src = src

        # 2) Análisis
        print("» Analizando el volumen segundo a segundo...")
        audio_db = loudness_per_second(audio_src)
        duration = len(audio_db)
        if duration < args.length:
            print("ERROR: el video es más corto que la duración de un clip.", file=sys.stderr)
            return 1

        chat = None
        if remote and not args.no_chat:
            print("» Leyendo el chat (puede tardar en streams largos)...")
            chat = chat_activity(args.source, duration)

        score = score_timeline(audio_db, chat, chat_delay=args.chat_delay)
        # No queremos la pantalla de "empezando pronto" ni la despedida
        a, b = int(args.skip_start), int(args.skip_end)
        if duration > a + b + args.length * 2:
            score[:a] = -99
            if b:
                score[-b:] = -99

        highlights = pick_highlights(score, args.num_clips, args.length, min_score=args.min_score)
        if not highlights:
            print("No se encontraron momentos destacados. Prueba con --min-score 0.5")
            return 0

        print(f"\n» {len(highlights)} momentos encontrados:")
        for i, h in enumerate(highlights, 1):
            print(f"  #{i:02d}  {hms(h.start)} → {hms(h.end)}   puntuación {h.score:.1f}")

        report = {
            "source": args.source,
            "title": title,
            "duration_seconds": duration,
            "used_chat": chat is not None,
            "clips": [],
        }

        # 3) Corte
        base = slugify(title)
        for i, h in enumerate(highlights, 1):
            name = f"{i:02d}_{base}_{hms(h.start).replace(':', '-')}"
            entry = {
                "n": i, "start": round(h.start, 2), "end": round(h.end, 2),
                "start_hms": hms(h.start), "score": round(h.score, 2),
                "link": timestamp_link(args.source, h.start) if remote else None,
            }
            if not args.dry_run:
                print(f"\n» Clip {i}/{len(highlights)} ({hms(h.start)})")
                if remote and live:
                    vfmt = pick_hls_format(info, audio_only=False, max_height=args.max_height)
                    piece, seg_start = download_hls_range(vfmt["url"], tmp / f"raw_{i:02d}.ts",
                                                          h.start, h.end,
                                                          headers=vfmt.get("http_headers"))
                    clip_start, clip_dur = h.start - seg_start, h.end - h.start
                elif remote:
                    piece = download_section(args.source, h.start, h.end, tmp / f"raw_{i:02d}.mp4",
                                             args.cookies, args.max_height)
                    clip_start, clip_dur = None, None
                else:
                    piece, clip_start, clip_dur = audio_src, h.start, h.end - h.start

                srt = None
                if args.subs:
                    plain = render_clip(piece, tmp / f"plain_{i:02d}.mp4", clip_start, clip_dur)
                    srt = make_srt(plain, tmp / f"{name}.srt", args.subs_model, args.subs_lang)
                    piece, clip_start, clip_dur = plain, None, None

                final = render_clip(piece, out_dir / f"{name}.mp4", clip_start, clip_dur,
                                    vertical=args.vertical, subtitles=srt)
                entry["file"] = final.name
                print(f"  ✓ {final}")
            report["clips"].append(entry)

        (out_dir / "highlights.json").write_text(json.dumps(report, indent=2, ensure_ascii=False),
                                                 encoding="utf-8")
        print(f"\n✔ Listo. Resumen en {out_dir / 'highlights.json'}")
        return 0
    finally:
        if args.keep_temp:
            print(f"(temporales en {tmp})")
        else:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
