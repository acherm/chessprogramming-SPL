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

    for option in options:
        lowered = option.name.lower()
        assert not any(token in lowered for token in NOISE_TOKENS)


def test_model_meta_declares_product_line_goal(sample_pages):
    result = build_feature_model(sample_pages, depth=3, target_features=200)

    assert result.meta["model_perspective"] == "implementation_product_line"
    assert "configuration" in result.meta["configuration_goal"]
    assert "compile_time_first" in result.meta["primary_variability_strategy"]


def test_depth_one_emits_structural_model_only(sample_pages):
    result = build_feature_model(sample_pages, depth=1, target_features=200)

    roots = [feature for feature in result.features if feature.parent_id is None]
    groups = [feature for feature in result.features if feature.variation_role == "group"]
    options = [feature for feature in result.features if feature.variation_role == "option"]

    assert len(roots) == 1
    assert groups
    assert not options
    assert result.constraints == []


def test_depth_four_adds_binding_layer(sample_pages):
    result = build_feature_model(sample_pages, depth=4, target_features=200)

    options = [feature for feature in result.features if feature.variation_role == "option"]
    bindings = [feature for feature in result.features if feature.variation_role == "binding"]

    assert options
    assert bindings
    assert all(binding.parent_id for binding in bindings)

    option_ids = {feature.id for feature in options}
    assert all(binding.parent_id in option_ids for binding in bindings)
    assert any(binding.name.startswith("CompileFlag ") for binding in bindings)
