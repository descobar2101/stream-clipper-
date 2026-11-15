"""Combina audio + chat en una puntuación por segundo y elige los mejores momentos."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class Highlight:
    peak: float   # segundo del momento más intenso
    start: float  # inicio del clip
    end: float    # fin del clip
    score: float


def _smooth(x: np.ndarray, window: int) -> np.ndarray:
    if window <= 1 or len(x) == 0:
        return x.astype(np.float32)
    kernel = np.ones(window, dtype=np.float32) / window
    return np.convolve(x, kernel, mode="same")


def _rolling_median(x: np.ndarray, window: int) -> np.ndarray:
    """Mediana local aproximada (por bloques) para comparar cada momento
    con lo 'normal' de esa parte del stream, no con el stream entero."""
    if len(x) == 0:
        return x
    step = max(window // 4, 1)
    centers = np.arange(0, len(x), step)
    meds = np.array([
        np.median(x[max(0, c - window // 2): c + window // 2 + 1]) for c in centers
    ])
    return np.interp(np.arange(len(x)), centers, meds).astype(np.float32)


def _robust_z(x: np.ndarray, baseline_window: int = 300) -> np.ndarray:
    base = _rolling_median(x, baseline_window)
    dev = x - base
    mad = np.median(np.abs(dev - np.median(dev))) + 1e-6
    return np.clip(dev / (1.4826 * mad), -5, 10)


def score_timeline(audio_db: np.ndarray, chat: np.ndarray | None,
                   chat_delay: int = 6, audio_weight: float = 1.0,
                   chat_weight: float = 1.2) -> np.ndarray:
    n = len(audio_db)
    audio_z = _robust_z(_smooth(audio_db, 3))
    score = audio_weight * audio_z

    if chat is not None and chat.sum() > 0:
        chat = np.resize(chat, n) if len(chat) != n else chat
        # El chat reacciona unos segundos DESPUÉS del momento: lo adelantamos.
        shifted = np.zeros(n, dtype=np.float32)
        if chat_delay > 0:
            shifted[: n - chat_delay] = chat[chat_delay:]
        else:
            shifted = chat.astype(np.float32)
        chat_z = _robust_z(_smooth(shifted, 8))
        score = score + chat_weight * chat_z

    # Suavizamos para premiar momentos sostenidos, no un ruido de 1 segundo.
    return _smooth(score, 5)


def pick_highlights(score: np.ndarray, num_clips: int, clip_length: float,
                    pre_roll: float | None = None, min_gap: float | None = None,
                    min_score: float = 1.0) -> list[Highlight]:
    """Elige los N picos más altos sin que los clips se pisen entre sí."""
    duration = len(score)
    if pre_roll is None:
        pre_roll = clip_length * 0.65  # la mayor parte del clip es ANTES del pico (contexto)
    if min_gap is None:
        min_gap = clip_length * 1.5

    order = np.argsort(score)[::-1]
    chosen: list[Highlight] = []
    for idx in order:
        s = float(score[idx])
        if s < min_score or len(chosen) >= num_clips:
            break
        if any(abs(idx - h.peak) < min_gap for h in chosen):
            continue
        start = max(0.0, idx - pre_roll)
        end = min(float(duration), start + clip_length)
        start = max(0.0, end - clip_length)
        chosen.append(Highlight(peak=float(idx), start=start, end=end, score=s))

    return sorted(chosen, key=lambda h: h.start)
