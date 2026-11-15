"""Descarga de audio y de fragmentos de video con yt-dlp."""
from __future__ import annotations

import json
import re
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


# ---------------------------------------------------------------------------
# Videos de directos que siguen en marcha (p. ej. el VOD de Twitch de un stream
# que todavía no ha terminado). yt-dlp los trata como "en directo" y se quedaría
# esperando para siempre, así que leemos la lista de trozos (m3u8) nosotros y
# descargamos solo lo que ya se ha emitido.
# ---------------------------------------------------------------------------
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from urllib.parse import urljoin


@dataclass
class Segment:
    start: float
    duration: float
    uri: str


def is_vod_url(url: str, info: dict) -> bool:
    """¿Es un video grabado (aunque el directo siga) y no un canal en directo?"""
    extractor = (info.get("extractor") or info.get("extractor_key") or "").lower()
    return "/videos/" in url or "/v/" in url or "vod" in extractor or "watch?v=" in url


def pick_hls_format(info: dict, audio_only: bool, max_height: int = 1080) -> dict:
    formats = [f for f in info.get("formats") or [] if "m3u8" in (f.get("protocol") or "")]
    if not formats:
        raise RuntimeError("No se encontró una lista HLS (m3u8) para este video.")
    if audio_only:
        audio = [f for f in formats if f.get("vcodec") in (None, "none")]
        if audio:
            return audio[-1]
    video = [f for f in formats if (f.get("height") or 0) and f["height"] <= max_height]
    video = video or [f for f in formats if f.get("vcodec") not in (None, "none")] or formats
    return max(video, key=lambda f: ((f.get("height") or 0), (f.get("tbr") or 0)))


def _get(url: str, headers: dict | None = None, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers=headers or {"User-Agent": "Mozilla/5.0"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception:
            if attempt == 3:
                raise
    return b""


def hls_segments(m3u8_url: str, headers: dict | None = None) -> tuple[str | None, list[Segment]]:
    """Lee una lista m3u8 y devuelve (segmento de inicio, lista de trozos)."""
    text = _get(m3u8_url, headers).decode("utf-8", "replace")
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    # Si es una lista "maestra", seguimos la primera variante
    if any(ln.startswith("#EXT-X-STREAM-INF") for ln in lines):
        for i, ln in enumerate(lines):
            if ln.startswith("#EXT-X-STREAM-INF") and i + 1 < len(lines):
                return hls_segments(urljoin(m3u8_url, lines[i + 1]), headers)
    init = None
    segs: list[Segment] = []
    t = 0.0
    dur = None
    for ln in lines:
        if ln.startswith("#EXT-X-MAP"):
            m = re.search(r'URI="([^"]+)"', ln)
            if m:
                init = urljoin(m3u8_url, m.group(1))
        elif ln.startswith("#EXTINF:"):
            dur = float(ln.split(":", 1)[1].split(",")[0])
        elif not ln.startswith("#") and dur is not None:
            segs.append(Segment(t, dur, urljoin(m3u8_url, ln)))
            t += dur
            dur = None
    if not segs:
        raise RuntimeError("La lista m3u8 no tiene trozos de video.")
    return init, segs


def download_hls_range(m3u8_url: str, out_path: Path, start: float = 0.0,
                       end: float | None = None, headers: dict | None = None,
                       workers: int = 12) -> tuple[Path, float]:
    """Descarga los trozos que cubren [start, end] y los une en un archivo.

    Devuelve (archivo, segundo del stream donde empieza el archivo).
    """
    init, segs = hls_segments(m3u8_url, headers)
    end = segs[-1].start + segs[-1].duration if end is None else end
    chosen = [s for s in segs if s.start + s.duration > start and s.start < end]
    if not chosen:
        raise RuntimeError(f"No hay video entre {start:.0f}s y {end:.0f}s.")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    def fetch(seg: Segment) -> bytes:
        return _get(seg.uri, headers)

    with out_path.open("wb") as f:
        if init:
            f.write(_get(init, headers))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for data in pool.map(fetch, chosen):  # map mantiene el orden
                f.write(data)
    return out_path, chosen[0].start
