from __future__ import annotations

from xml.etree import ElementTree as ET

from cpw_variability.constraints import build_cross_tree_constraints
from cpw_variability.config import resolve_paths
from cpw_variability.exporters import export_featureide_xml
from cpw_variability.models import FeatureNode


def test_build_cross_tree_constraints_from_feature_set():
    features = [
        FeatureNode(id="search", name="Search", parent_id="root", variation_role="group", configurable=False, variability_stage="none"),
        FeatureNode(id="board", name="BoardRepresentation", parent_id="root", variation_role="group", configurable=False, variability_stage="none"),
        FeatureNode(id="feat_magic_bitboards", name="Magic Bitboards", parent_id="move_generation"),
        FeatureNode(id="feat_bitboards", name="Bitboards", parent_id="board"),
        FeatureNode(id="feat_mailbox", name="Mailbox", parent_id="board"),
        FeatureNode(id="feat_minimax", name="Minimax", parent_id="search"),
        FeatureNode(id="feat_negamax", name="Negamax", parent_id="search"),
        FeatureNode(id="feat_alpha_beta", name="Alpha-Beta", parent_id="search"),
        FeatureNode(id="feat_pvs", name="Principal Variation Search", parent_id="search"),
        FeatureNode(id="feat_eval", name="Evaluation", parent_id="evaluation"),
        FeatureNode(id="feat_passed", name="Passed Pawn", parent_id="evaluation"),
        FeatureNode(id="feat_tapered", name="Tapered Eval", parent_id="evaluation"),
        FeatureNode(id="feat_king_activity", name="King Activity", parent_id="evaluation"),
    ]

    constraints, warnings = build_cross_tree_constraints(features)
    assert warnings
    assert constraints
    kinds = {constraint.kind for constraint in constraints}
    assert "requires" in kinds
    assert "excludes" in kinds

    index_by_id = {feature.id: feature for feature in features}
    edge_names = {
        (index_by_id[constraint.left_feature_id].name, index_by_id[constraint.right_feature_id].name, constraint.kind)
        for constraint in constraints
    }
    assert ("Magic Bitboards", "Bitboards", "requires") in edge_names
    assert ("Minimax", "Negamax", "excludes") in edge_names
    assert ("Bitboards", "Mailbox", "excludes") in edge_names
    assert ("Passed Pawn", "Evaluation", "requires") in edge_names
    assert ("King Activity", "Tapered Eval", "requires") in edge_names


def test_featureide_constraints_export(tmp_path):
    features = [
        FeatureNode(id="root", name="ChessEngineProductLine", parent_id=None, variation_role="root", configurable=False, variability_stage="none"),
        FeatureNode(id="search", name="Search", parent_id="root", variation_role="group", configurable=False, variability_stage="none"),
        FeatureNode(id="board", name="BoardRepresentation", parent_id="root", variation_role="group", configurable=False, variability_stage="none"),
        FeatureNode(id="feat_magic_bitboards", name="Magic Bitboards", parent_id="search"),
        FeatureNode(id="feat_bitboards", name="Bitboards", parent_id="board"),
        FeatureNode(id="feat_mailbox", name="Mailbox", parent_id="board"),
    ]
    constraints, _ = build_cross_tree_constraints(features)
    paths = resolve_paths(root=tmp_path)

    export_featureide_xml(paths.feature_model_featureide_path, features, constraints)

    tree = ET.parse(paths.feature_model_featureide_path)
    root = tree.getroot()
    constraints_node = root.find("constraints")
    assert constraints_node is not None

    rules = constraints_node.findall("rule")
    assert rules
    assert any(rule.find("imp") is not None for rule in rules)
    assert any(rule.find("not") is not None for rule in rules)
