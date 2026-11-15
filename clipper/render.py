"""Corte y formato final de los clips con ffmpeg."""
from __future__ import annotations

import subprocess
from pathlib import Path

VERTICAL_FILTER = (
    "[0:v]split=2[bgsrc][fgsrc];"
    "[bgsrc]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
    "boxblur=20:2,eq=brightness=-0.08[bg];"
    "[fgsrc]scale=1080:-2[fg];"
    "[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1"
)


def _escape_sub_path(path: Path) -> str:
    # ffmpeg necesita escapar ":" y "\" dentro del filtro subtitles
    return str(path.resolve()).replace("\\", "/").replace(":", r"\:").replace("'", r"\'")


def render_clip(src: Path, out: Path, start: float | None = None,
                duration: float | None = None, vertical: bool = False,
                subtitles: Path | None = None) -> Path:
    """Corta (si start/duration) y da formato al clip.

    - vertical=True  -> 1080x1920 con fondo difuminado (TikTok / Shorts / Reels)
    - subtitles=.srt -> subtítulos quemados en el video
    """
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]
    if start is not None:
        cmd += ["-ss", f"{start:.2f}"]
    cmd += ["-i", str(src)]
    if duration is not None:
        cmd += ["-t", f"{duration:.2f}"]

    filters = VERTICAL_FILTER if vertical else "[0:v]setsar=1"
    if subtitles is not None:
        style = ("FontName=Arial,FontSize=13,Bold=1,PrimaryColour=&H00FFFFFF,"
                 "OutlineColour=&H00000000,BorderStyle=1,Outline=2,Shadow=0,"
                 "Alignment=2,MarginV=" + ("70" if vertical else "30"))
        filters += f",subtitles='{_escape_sub_path(subtitles)}':force_style='{style}'"
    filters += "[v]"

    cmd += [
        "-filter_complex", filters,
        "-map", "[v]", "-map", "0:a?",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", "-b:a", "160k",
        "-movflags", "+faststart",
        str(out),
    ]
    subprocess.run(cmd, check=True)
    return out


def make_srt(media: Path, out_srt: Path, model_size: str = "small",
             language: str | None = None) -> Path | None:
    """Transcribe el clip con faster-whisper y guarda un .srt (opcional)."""
    try:
        from faster_whisper import WhisperModel  # type: ignore
    except ImportError:
        print("  [subs] faster-whisper no está instalado; clip sin subtítulos.")
        return None

    model = WhisperModel(model_size, device="auto", compute_type="int8")
    segments, _ = model.transcribe(str(media), language=language, vad_filter=True,
                                   word_timestamps=True)

    def ts(t: float) -> str:
        h, rem = divmod(t, 3600)
        m, s = divmod(rem, 60)
        return f"{int(h):02d}:{int(m):02d}:{int(s):02d},{int((s % 1) * 1000):03d}"

    # Frases cortas (máx. ~5 palabras) que se leen mejor en formato vertical
    lines: list[tuple[float, float, str]] = []
    for seg in segments:
        words = list(seg.words or [])
        for i in range(0, len(words), 5):
            group = words[i:i + 5]
            text = "".join(w.word for w in group).strip()
            if text:
                lines.append((group[0].start, group[-1].end, text))

    if not lines:
        return None
    with out_srt.open("w", encoding="utf-8") as f:
        for n, (a, b, text) in enumerate(lines, 1):
            f.write(f"{n}\n{ts(a)} --> {ts(b)}\n{text}\n\n")
    return out_srt
