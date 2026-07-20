"""U18: face-embedding matcher (no camera) — match known, reject strangers,
embeddings encrypted at rest. Plus the PersonRecognized event."""

from __future__ import annotations

from shared_schemas.events import PersonRecognized
from shared_schemas.knowledge import EmbeddingMatcher

_OMK = b"k" * 32


def test_matches_known_person() -> None:
    m = EmbeddingMatcher(_OMK, threshold=0.9)
    m.enroll("jan", [1.0, 0.0, 0.0])
    m.enroll("ada", [0.0, 1.0, 0.0])

    pid, score = m.identify([0.98, 0.05, 0.0])  # close to jan
    assert pid == "jan"
    assert score > 0.9


def test_stranger_is_rejected() -> None:
    m = EmbeddingMatcher(_OMK, threshold=0.9)
    m.enroll("jan", [1.0, 0.0, 0.0])

    pid, score = m.identify([0.0, 0.0, 1.0])  # orthogonal — nobody
    assert pid is None
    assert score < 0.9


def test_embeddings_encrypted_at_rest() -> None:
    m = EmbeddingMatcher(_OMK)
    m.enroll("jan", [0.123456, 0.654321])
    blob = m._enrolled["jan"]
    assert b"0.123456" not in blob  # ciphertext, not the raw vector
    # A different OMK cannot read it.
    import pytest
    from cryptography.exceptions import InvalidTag
    other = EmbeddingMatcher(b"x" * 32)
    other._enrolled = dict(m._enrolled)
    with pytest.raises(InvalidTag):
        other.identify([0.123456, 0.654321])


def test_forget_removes_enrollment() -> None:
    m = EmbeddingMatcher(_OMK)
    m.enroll("jan", [1.0, 0.0])
    m.forget("jan")
    assert m.enrolled_ids() == []
    assert m.identify([1.0, 0.0]) == (None, 0.0)


def test_person_recognized_event_shape() -> None:
    known = PersonRecognized(session_id="s", person_id="jan", display_name="Jan",
                             confidence=0.95, known=True)
    stranger = PersonRecognized(session_id="s")
    assert known.known is True and known.person_id == "jan"
    assert stranger.known is False and stranger.person_id is None
