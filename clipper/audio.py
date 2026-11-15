"""Análisis de volumen: encuentra los momentos donde el audio sube de golpe
(gritos, risas, explosiones, reacciones fuertes)."""
from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np

SAMPLE_RATE = 8000  # suficiente para medir volumen y muy rápido


def loudness_per_second(media: Path) -> np.ndarray:
    """Devuelve el volumen (en dB) de cada segundo del archivo."""
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-i", str(media),
        "-vn", "-ac", "1", "-ar", str(SAMPLE_RATE),
        "-f", "s16le", "-",
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    chunk = SAMPLE_RATE * 2  # 1 segundo de audio int16
    values: list[float] = []
    assert proc.stdout is not None
    buf = b""
    while True:
        data = proc.stdout.read(chunk * 60)
        if not data:
            break
        buf += data
        n_full = len(buf) // chunk
        if n_full:
            arr = np.frombuffer(buf[: n_full * chunk], dtype=np.int16)
            arr = arr.reshape(n_full, SAMPLE_RATE).astype(np.float32)
            rms = np.sqrt(np.mean(arr ** 2, axis=1)) + 1e-6
            values.extend((20 * np.log10(rms / 32768.0)).tolist())
            buf = buf[n_full * chunk:]
    proc.wait()
    if proc.returncode != 0:
        raise RuntimeError("ffmpeg no pudo leer el audio.")
    return np.array(values, dtype=np.float32)
