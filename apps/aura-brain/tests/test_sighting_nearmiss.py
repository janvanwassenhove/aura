"""U277: why a face you have taught turns up as a stranger.

Reported as: "ik had dit gedaan maar bij unknown visitors kwam ik er ook op —
ik ga er vanuit dat hier een mindere mate van zekerheid is en zo bij kan
dragen tot trainen als ik hier tag met de juiste persoon."

Both halves of that reading are right, and neither was visible. A face lands
in unknown visitors when its best match scores below RECOGNITION_THRESHOLD —
a different angle, worse light, further away. `identify()` computes that
near-miss and the old listing threw it away, so a face taught ten minutes ago
appeared as a stranger with no hint why, and no way to tell "this is you at a
bad angle" from "this is genuinely someone else".
"""

from __future__ import annotations

import os

import pytest
from shared_schemas.knowledge import crypto
from shared_schemas.knowledge.recognition import EmbeddingMatcher


@pytest.fixture()
def matcher():
    omk = crypto.derive_omk("test-passphrase", b"0123456789abcdef")
    return EmbeddingMatcher(omk)


def test_closest_reports_the_near_miss_that_identify_hides(matcher) -> None:
    """identify() answers "nobody" below the bar — right for recognition,
    useless for explaining it."""
    matcher.enroll("jan", [1.0, 0.0, 0.0])

    # Same person, worse angle: similar but under the 0.4 bar.
    off_angle = [0.3, 0.95, 0.0]

    who, score = matcher.identify(off_angle)
    assert who is None, "below the bar he is not recognised — unchanged"

    near, near_score = matcher.closest(off_angle)
    assert near == "jan", "but WHO it nearly was is the whole answer"
    assert 0.0 < near_score < matcher.threshold


def test_the_threshold_is_readable_so_a_score_means_something(matcher) -> None:
    assert matcher.threshold == float(os.environ.get("RECOGNITION_THRESHOLD", "0.4"))


def test_closest_on_an_empty_gallery_names_nobody(matcher) -> None:
    near, score = matcher.closest([1.0, 0.0, 0.0])
    assert near is None and score == 0.0


def test_tagging_grows_the_sample_count(matcher) -> None:
    """The owner's reading of the feature, as a test: tagging trains it."""
    matcher.enroll("jan", [1.0, 0.0, 0.0])
    assert matcher.sample_count("jan") == 1

    # The off-angle shot that had landed in unknown visitors.
    matcher.enroll("jan", [0.3, 0.95, 0.0])
    assert matcher.sample_count("jan") == 2

    # ...and now that angle IS him — which is the point of tagging.
    who, _ = matcher.identify([0.3, 0.95, 0.0])
    assert who == "jan"
