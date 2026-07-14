"""U24/U54: streamed speech — first audio before the whole reply is synthesized.

The reply is split into sentence chunks; chunk N+1 is synthesized WHILE chunk N
plays on the robot. First audio starts after one short TTS call instead of one
long one, which is where most of the perceived latency lived.

Pure asyncio + injected callables, so the pipelining is unit-testable without
a robot or a TTS provider.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Awaitable, Callable

_SENTENCE_END = re.compile(r"(?<=[.!?…])\s+")


def split_speech_chunks(text: str, min_chars: int = 60, max_chunks: int = 6) -> list[str]:
    """Sentence-boundary chunks, merged until ≥ min_chars so TTS calls stay
    worthwhile. The tail is capped at max_chunks (last chunk absorbs the rest)."""
    text = (text or "").strip()
    if not text:
        return []
    sentences = [s.strip() for s in _SENTENCE_END.split(text) if s.strip()]
    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        current = f"{current} {sentence}".strip()
        if len(current) >= min_chars:
            chunks.append(current)
            current = ""
    if current:
        chunks.append(current)
    if len(chunks) > max_chunks:
        chunks[max_chunks - 1:] = [" ".join(chunks[max_chunks - 1:])]
    return chunks


async def stream_speech(
    text: str,
    synthesize: Callable[[str], Awaitable[str]],
    speak: Callable[[str, str], Awaitable[None]],
    min_chars: int = 60,
) -> int:
    """Speak ``text`` in pipelined chunks; returns the number of chunks spoken.

    ``synthesize(chunk) -> audio_b64`` runs one step ahead of
    ``speak(chunk, audio_b64)`` so the robot never waits for TTS after the
    first chunk.
    """
    chunks = split_speech_chunks(text, min_chars=min_chars)
    if not chunks:
        return 0
    next_audio: asyncio.Task[str] = asyncio.create_task(synthesize(chunks[0]))
    for i, chunk in enumerate(chunks):
        audio = await next_audio
        if i + 1 < len(chunks):
            next_audio = asyncio.create_task(synthesize(chunks[i + 1]))
        await speak(chunk, audio)
    return len(chunks)
