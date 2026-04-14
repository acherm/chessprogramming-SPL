from __future__ import annotations

from cpw_variability.feature_miner import (
    FeatureCandidate,
    augment_with_core_features,
    canonicalize_candidates,
    filter_noise_features,
)
from cpw_variability.models import FeatureNode, PageDocument, TraceRecord


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


def test_noise_filter_removes_edit_people_and_navigation_items():
    leaves = [
        FeatureNode(id="f1", name="1995[edit]", parent_id="board_representation"),
        FeatureNode(id="f2", name="References[edit]", parent_id="board_representation"),
        FeatureNode(id="f3", name="Robert Hyatt", parent_id="board_representation"),
        FeatureNode(id="f4", name="index.php", parent_id="board_representation"),
        FeatureNode(id="f5", name="Main Page", parent_id="board_representation"),
        FeatureNode(id="f6", name="Bitboards", parent_id="board_representation"),
    ]
    traces = [
        TraceRecord(
            id="t1",
            feature_id="f1",
            source_url="u",
            source_title="s",
            snippet="sn",
            confidence=0.5,
            rule_id="heading_match",
        ),
        TraceRecord(
            id="t6",
            feature_id="f6",
            source_url="u",
            source_title="s",
            snippet="sn",
            confidence=0.9,
            rule_id="heading_match",
        ),
    ]

    filtered_leaves, filtered_traces, removed = filter_noise_features(leaves, traces)
    names = {leaf.name for leaf in filtered_leaves}

    assert names == {"Bitboards"}
    assert len(filtered_traces) == 1
    assert "Robert Hyatt" in removed
    assert "Main Page" in removed


def test_core_feature_augmentation_adds_0x88_and_bitboards():
    pages = [
        PageDocument(
            title="0x88",
            url="https://www.chessprogramming.org/0x88",
            source_type="html",
            retrieved_at="2026-01-01T00:00:00+00:00",
            content_hash="h1",
            text="0x88 is a board representation used in chess engines.",
            headings=["0x88"],
            links=["Board Representation"],
            bold_terms=["0x88"],
            categories=["Board Representation"],
            page_type="technique",
        ),
        PageDocument(
            title="Bitboards",
            url="https://www.chessprogramming.org/Bitboards",
            source_type="html",
            retrieved_at="2026-01-01T00:00:00+00:00",
            content_hash="h2",
            text="Bitboards represent board occupancy and accelerate move generation.",
            headings=["Bitboards"],
            links=["Move Generation"],
            bold_terms=["Bitboards"],
            categories=["Board Representation"],
            page_type="technique",
        ),
    ]

    base_leaves: list[FeatureNode] = []
    base_traces: list[TraceRecord] = []
    augmented_leaves, augmented_traces, warnings = augment_with_core_features(base_leaves, base_traces, pages)

    names = {leaf.name for leaf in augmented_leaves}
    assert "0x88" in names
    assert "Bitboards" in names
    assert any(trace.rule_id == "core_feature_match" for trace in augmented_traces)
    assert not [warning for warning in warnings if "Core feature '0x88'" in warning]
    assert not [warning for warning in warnings if "Core feature 'Bitboards'" in warning]
