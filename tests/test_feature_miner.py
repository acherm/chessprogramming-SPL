from __future__ import annotations

from cpw_variability.feature_miner import FeatureCandidate, canonicalize_candidates


def test_canonicalization_merges_alpha_beta_synonyms():
    candidates = [
        FeatureCandidate(
            name="Alpha-Beta",
            source_url="https://www.chessprogramming.org/Alpha-Beta",
            source_title="Alpha-Beta",
            snippet="Alpha-Beta is a minimax search algorithm.",
            rule_id="heading_match",
        ),
        FeatureCandidate(
            name="alpha beta",
            source_url="https://www.chessprogramming.org/Alpha-Beta",
            source_title="Alpha-Beta",
            snippet="alpha beta search is dominant in classic engines.",
            rule_id="bold_term",
        ),
    ]

    canonical = canonicalize_candidates(candidates)
    assert len(canonical) == 1
    assert canonical[0].canonical_key == "alpha-beta"
    assert "Alpha-Beta" in canonical[0].aliases
    assert "alpha beta" in canonical[0].aliases
