from __future__ import annotations

from cpw_variability.matrix_builder import detect_support_status


def test_tri_state_detection_positive_and_negative():
    positive = "This engine uses alpha-beta search with iterative deepening."
    status_pos, snippet_pos, _ = detect_support_status(positive, ["alpha-beta"])
    assert status_pos == "SUPPORTED"
    assert "alpha-beta" in snippet_pos.lower()

    negative = "This engine works without alpha-beta pruning in its search core."
    status_neg, snippet_neg, _ = detect_support_status(negative, ["alpha-beta"])
    assert status_neg == "UNSUPPORTED_EXPLICIT"
    assert "without" in snippet_neg.lower()

    unknown = "This engine is open source and active in tournaments."
    status_unknown, _, _ = detect_support_status(unknown, ["alpha-beta"])
    assert status_unknown == "UNKNOWN"
