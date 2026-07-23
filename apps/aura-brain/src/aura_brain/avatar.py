"""U204: turn a photo into a small, storable avatar icon.

A person's avatar is a `data:image/jpeg;base64,...` URI — small enough to live
in their encrypted knowledge bundle beside the facts, and to hand straight to
an <img> in the console. Two sources feed it: a frame from the face-teach
flow, or an image the owner uploads. Both land here so the size/shape rules
live in one place.
"""

from __future__ import annotations

import base64
import io
import logging

logger = logging.getLogger(__name__)

_AVATAR_PX = 128          # square side; a list-icon never needs more
_MAX_INPUT_BYTES = 8_000_000   # reject a huge upload before decoding it


def _to_square_jpeg(raw: bytes) -> bytes | None:
    """Center-crop to a square and shrink to a small JPEG. None on bad input."""
    try:
        from PIL import Image

        img = Image.open(io.BytesIO(raw)).convert("RGB")
        w, h = img.size
        side = min(w, h)
        left, top = (w - side) // 2, (h - side) // 2
        img = img.crop((left, top, left + side, top + side))
        img = img.resize((_AVATAR_PX, _AVATAR_PX), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=82)
        return buf.getvalue()
    except Exception as exc:  # noqa: BLE001 — any decode failure = "not an image"
        logger.debug("avatar encode failed: %s", exc)
        return None


def avatar_from_image_bytes(raw: bytes) -> str | None:
    """Build a data-URI avatar from raw image bytes (camera frame or upload)."""
    if not raw or len(raw) > _MAX_INPUT_BYTES:
        return None
    small = _to_square_jpeg(raw)
    if small is None:
        return None
    return "data:image/jpeg;base64," + base64.b64encode(small).decode("ascii")


def avatar_from_data_uri(data_uri: str) -> str | None:
    """Normalise an uploaded `data:image/...;base64,...` string into an avatar.

    Re-encoding rather than trusting the upload bounds the size and strips
    whatever the source format was (PNG/webp/…) down to one small JPEG.
    """
    if not isinstance(data_uri, str) or "," not in data_uri:
        return None
    header, _, b64 = data_uri.partition(",")
    if "base64" not in header.lower() or not header.lower().startswith("data:image"):
        return None
    try:
        raw = base64.b64decode(b64, validate=True)
    except (ValueError, base64.binascii.Error):
        return None
    return avatar_from_image_bytes(raw)
