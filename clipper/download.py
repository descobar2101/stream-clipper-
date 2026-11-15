"""Descarga de audio y de fragmentos de video con yt-dlp."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path


def is_url(source: str) -> bool:
    return source.startswith(("http://", "https://"))


def _yt_dlp_cmd() -> list[str]:
    exe = shutil.which("yt-dlp")
    return [exe] if exe else [sys.executable, "-m", "yt_dlp"]


def get_info(url: str, cookies: str | None = None) -> dict:
    """Devuelve los metadatos del video/stream (título, duración, etc.)."""
    cmd = _yt_dlp_cmd() + ["-J", "--no-warnings", "--no-playlist"]
    if cookies:
        cmd += ["--cookies", cookies]
    out = subprocess.run(cmd + [url], check=True, capture_output=True, text=True)
    return json.loads(out.stdout)


def download_audio(url: str, workdir: Path, cookies: str | None = None) -> Path:
    """Descarga solo el audio (mucho más ligero que el video completo)."""
    workdir.mkdir(parents=True, exist_ok=True)
    template = str(workdir / "audio.%(ext)s")
    cmd = _yt_dlp_cmd() + [
        "-f", "bestaudio/best",
        "--no-playlist",
        "-o", template,
    ]
    if cookies:
        cmd += ["--cookies", cookies]
    subprocess.run(cmd + [url], check=True)
    files = sorted(workdir.glob("audio.*"))
    if not files:
        raise RuntimeError("No se pudo descargar el audio del stream.")
    return files[0]


def download_section(url: str, start: float, end: float, out_path: Path,
                     cookies: str | None = None, max_height: int = 1080) -> Path:
    """Descarga solo el trozo [start, end] del video, no el stream entero."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fmt = (f"bv*[height<={max_height}]+ba/b[height<={max_height}]/bv*+ba/b")
    cmd = _yt_dlp_cmd() + [
        "-f", fmt,
        "--no-playlist",
        "--download-sections", f"*{start:.2f}-{end:.2f}",
        "--force-keyframes-at-cuts",
        "--merge-output-format", "mp4",
        "-o", str(out_path.with_suffix("")) + ".%(ext)s",
    ]
    if cookies:
        cmd += ["--cookies", cookies]
    subprocess.run(cmd + [url], check=True)
    candidates = sorted(out_path.parent.glob(out_path.stem + ".*"))
    if not candidates:
        raise RuntimeError(f"No se pudo descargar el fragmento {start}-{end}.")
    return candidates[0]
