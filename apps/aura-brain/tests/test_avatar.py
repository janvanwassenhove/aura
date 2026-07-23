"""U204: person avatars — encode, upload, and the teach/change behaviour."""

from __future__ import annotations

import base64
import io

import pytest
from aura_brain.avatar import avatar_from_data_uri, avatar_from_image_bytes


def _png(width: int = 300, height: int = 200, colour=(120, 30, 200)) -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (width, height), colour).save(buf, format="PNG")
    return buf.getvalue()


def test_encodes_to_a_small_square_jpeg_data_uri() -> None:
    from PIL import Image

    uri = avatar_from_image_bytes(_png(400, 250))
    assert uri is not None
    assert uri.startswith("data:image/jpeg;base64,")
    raw = base64.b64decode(uri.split(",", 1)[1])
    img = Image.open(io.BytesIO(raw))
    assert img.size == (128, 128)          # cropped square, downscaled
    assert len(raw) < 30_000               # small enough to store per-person


def test_a_wide_image_is_centre_cropped_not_squashed() -> None:
    from PIL import Image

    uri = avatar_from_image_bytes(_png(600, 100))
    img = Image.open(io.BytesIO(base64.b64decode(uri.split(",", 1)[1])))
    assert img.size == (128, 128)          # square, from a 6:1 source


def test_junk_bytes_are_rejected_not_stored() -> None:
    assert avatar_from_image_bytes(b"not an image") is None
    assert avatar_from_image_bytes(b"") is None


def test_an_oversized_upload_is_refused_before_decoding() -> None:
    assert avatar_from_image_bytes(b"\x89PNG" + b"\x00" * 9_000_000) is None


def test_data_uri_upload_is_re_encoded_to_jpeg() -> None:
    png_uri = "data:image/png;base64," + base64.b64encode(_png()).decode()
    out = avatar_from_data_uri(png_uri)
    assert out is not None and out.startswith("data:image/jpeg;base64,")   # normalised


@pytest.mark.parametrize("bad", [
    "", "not a data uri", "data:text/plain;base64,aGk=",         # not an image
    "data:image/png,rawnotbase64", "data:image/png;base64,%%%",  # bad base64
])
def test_bad_data_uris_are_refused(bad) -> None:
    assert avatar_from_data_uri(bad) is None
