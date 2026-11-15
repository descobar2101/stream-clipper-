"""Actividad del chat: cuando el chat explota (muchos mensajes, "KEKW",
"POG", "jajaja", "CLIP IT"...) casi siempre pasó algo bueno."""
from __future__ import annotations

import re

import numpy as np

HYPE_PATTERNS = [
    r"\bkekw\b", r"\blul\b", r"\blmao+\b", r"\bpog+(ers|champ)?\b", r"\bomegalul\b",
    r"\bclip\b", r"\bw+\b", r"\bno way\b", r"\bwtf\b", r"\bomg\b",
    r"\bja(ja)+\b", r"\bjsjs\w*\b", r"\bxd+\b", r"\bhaha+\b", r"\bnooo+\b",
    r"\bque\b.*\bpaso\b", r"\blocura\b", r"\bgod\b", r"\binsane\b", r"\b5head\b",
    r"\bmonkas\b", r"\bpepelaugh\b", r"\bicant\b", r"\baware\b", r"[!?]{3,}",
]
_HYPE_RE = re.compile("|".join(HYPE_PATTERNS), re.IGNORECASE)


def chat_activity(url: str, duration: int, max_messages: int = 400_000) -> np.ndarray | None:
    """Devuelve un array (1 valor por segundo) con la 'intensidad' del chat.

    Usa chat-downloader (Twitch VODs, YouTube). Si no hay chat disponible
    devuelve None y la herramienta usa solo el audio.
    """
    try:
        from chat_downloader import ChatDownloader  # type: ignore
    except ImportError:
        print("  [chat] chat-downloader no está instalado; se usa solo el audio.")
        return None

    activity = np.zeros(max(duration, 1), dtype=np.float32)
    count = 0
    try:
        chat = ChatDownloader().get_chat(url)
        for msg in chat:
            t = msg.get("time_in_seconds")
            if t is None or t < 0:
                continue
            sec = int(t)
            if sec >= len(activity):
                continue
            text = msg.get("message") or ""
            # 1 punto por mensaje + bonus si es un mensaje de "hype"
            activity[sec] += 1.0 + (1.5 if _HYPE_RE.search(text) else 0.0)
            count += 1
            if count >= max_messages:
                break
    except Exception as exc:  # el chat es opcional: nunca debe romper la herramienta
        print(f"  [chat] No se pudo leer el chat ({type(exc).__name__}: {exc}). Se usa solo el audio.")
        return None

    if count == 0:
        print("  [chat] El stream no tiene chat disponible. Se usa solo el audio.")
        return None
    print(f"  [chat] {count} mensajes leídos.")
    return activity
