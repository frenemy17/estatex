"""Pytest for state-machine transitions and scoring rubric."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from server import ALLOWED_TRANSITIONS, Qualification, _fallback_score, classify_score


def test_transitions_map_has_all_terminal_states():
    for s in ("NEW", "CALLING", "IN_CONVERSATION", "QUALIFIED", "HOT", "NURTURE", "BOOKED"):
        assert s in ALLOWED_TRANSITIONS


def test_new_can_only_go_to_calling_or_nurture():
    assert ALLOWED_TRANSITIONS["NEW"] == {"CALLING", "NURTURE"}


def test_booked_is_semi_terminal():
    # Booked leads may only be moved to NURTURE (post-appointment nurture)
    assert ALLOWED_TRANSITIONS["BOOKED"] == {"NURTURE"}


def test_illegal_transitions_are_not_in_map():
    # NEW -> BOOKED must never be allowed
    assert "BOOKED" not in ALLOWED_TRANSITIONS["NEW"]
    # BOOKED -> HOT must never be allowed
    assert "HOT" not in ALLOWED_TRANSITIONS["BOOKED"]


@pytest.mark.parametrize(
    "q,expected_min",
    [
        (Qualification(intent="buy family home", budget="$1.2M", timeline="30 days", financing="pre-approved", area="Downtown"), 85),
        (Qualification(intent="buy", budget="$650k", timeline="2 months", financing="pre-approved", area="East Village"), 70),
        (Qualification(intent="rent", budget="unsure", timeline="6+ months", financing="renting", area="undecided"), 0),
    ],
)
def test_scoring_bands(q, expected_min):
    assert _fallback_score(q) >= expected_min


def test_classify_score_thresholds():
    assert classify_score(95) == "HOT"
    assert classify_score(75) == "QUALIFIED"
    assert classify_score(50) == "NURTURE"
    assert classify_score(20) == "NURTURE"
