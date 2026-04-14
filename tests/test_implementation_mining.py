from __future__ import annotations

from cpw_variability.model_builder import build_feature_model


NOISE_TOKENS = [
    "[edit]",
    "references",
    "external links",
    "main page",
    "index.php",
    "up one level",
]


def test_model_is_implementation_oriented(sample_pages):
    result = build_feature_model(sample_pages, depth=3, target_features=200)

    root = next(feature for feature in result.features if feature.parent_id is None)
    assert root.id == "chess_engine_product_line"
    assert root.variation_role == "root"

    groups = [feature for feature in result.features if feature.variation_role == "group"]
    assert groups
    assert any(group.id == "board_representation" and group.kind == "xor" for group in groups)

    options = [feature for feature in result.features if feature.variation_role == "option"]
    assert options
    assert all(feature.compile_flag for feature in options)

    option_names = {feature.name for feature in options}
    assert "Alpha-Beta" in option_names
    assert "Minimax" in option_names
    assert "Magic Bitboards" in option_names
    assert "Passed Pawn" in option_names
    assert "Bishop Pair" in option_names
    assert "King Shelter" in option_names

    for option in options:
        lowered = option.name.lower()
        assert not any(token in lowered for token in NOISE_TOKENS)


def test_model_meta_declares_product_line_goal(sample_pages):
    result = build_feature_model(sample_pages, depth=3, target_features=200)

    assert result.meta["model_perspective"] == "implementation_product_line"
    assert "configuration" in result.meta["configuration_goal"]
    assert "compile_time_first" in result.meta["primary_variability_strategy"]
    assert "commonality" in result.meta["taxonomy_note"]


def test_depth_one_emits_structural_model_only(sample_pages):
    result = build_feature_model(sample_pages, depth=1, target_features=200)

    roots = [feature for feature in result.features if feature.parent_id is None]
    groups = [feature for feature in result.features if feature.variation_role == "group"]
    options = [feature for feature in result.features if feature.variation_role == "option"]

    assert len(roots) == 1
    assert groups
    assert not options
    assert result.constraints == []


def test_depth_four_adds_intermediate_groups(sample_pages):
    result = build_feature_model(sample_pages, depth=4, target_features=200)

    options = [feature for feature in result.features if feature.variation_role == "option"]
    groups = [feature for feature in result.features if feature.variation_role == "group"]
    by_name = {feature.name: feature for feature in result.features}

    assert options
    assert any(group.name == "Pawn Structure" and group.parent_id == "evaluation" for group in groups)
    assert any(group.name == "Piece Coordination" and group.parent_id == "evaluation" for group in groups)
    assert any(group.name == "King Terms" and group.parent_id == "evaluation" for group in groups)
    assert any(group.name == "Ordering Heuristics" and group.parent_id == by_name["Move Ordering"].id for group in groups)
    assert any(group.name == "TT Support" and group.parent_id == "transposition_table" for group in groups)
    assert by_name["Move Ordering"].parent_id == "search"
    assert any(feature.name == "Passed Pawn" and feature.parent_id != "evaluation" for feature in options)
    assert any(feature.name == "King Pressure" and feature.parent_id != "evaluation" for feature in options)
    assert any(feature.name == "Hash Move" and feature.parent_id == "search_ordering_heuristics" for feature in options)


def test_depth_five_adds_binding_layer(sample_pages):
    result = build_feature_model(sample_pages, depth=5, target_features=200)

    options = [feature for feature in result.features if feature.variation_role == "option"]
    bindings = [feature for feature in result.features if feature.variation_role == "binding"]

    assert options
    assert bindings
    assert all(binding.parent_id for binding in bindings)

    option_ids = {feature.id for feature in options}
    assert all(binding.parent_id in option_ids for binding in bindings)
    assert any(binding.name.startswith("CompileFlag ") for binding in bindings)
