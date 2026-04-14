from __future__ import annotations

from pathlib import Path

from cpw_variability.config import resolve_paths
from cpw_variability.setup_model import build_setup_feature_model


def test_setup_feature_model_structure():
    paths = resolve_paths(root=Path.cwd())
    result = build_setup_feature_model(paths)

    by_name = {feature.name: feature for feature in result.features}

    assert "EngineSetup" in by_name
    assert by_name["Search Budget"].kind == "xor"
    assert by_name["Fixed Depth"].parent_id == "setup_search_budget"
    assert by_name["Fixed Depth"].kind == "xor"
    assert by_name["Clock Managed"].runtime_flag == "go wtime/btime[/winc/binc/movestogo]"
    assert by_name["Own Book Enabled"].runtime_flag == "setoption name OwnBook value true"
    assert by_name["Ponder Enabled"].runtime_flag == "setoption name Ponder value true"

    constraint_pairs = {(constraint.left_feature_id, constraint.right_feature_id, constraint.kind) for constraint in result.constraints}
    assert ("setup_book_custom_file", "setup_book_enabled", "requires") in constraint_pairs
    assert ("setup_increment_aware", "setup_clock_managed", "requires") in constraint_pairs


def test_setup_recommendations_distinguish_variant_strength():
    paths = resolve_paths(root=Path.cwd())
    result = build_setup_feature_model(paths)
    rows = {row.variant_name: row for row in result.variant_recommendations}

    assert "phase1_minimax" in rows
    assert "phase3_negamax_ab_id_pruning_full_eval" in rows

    assert rows["phase1_minimax"].analysis_mode == "FixedDepth"
    assert "depth 3-4" in rows["phase1_minimax"].analysis_budget
    assert rows["phase1_minimax"].match_mode == "FixedMoveTime"

    assert "depth 12-20" in rows["phase3_negamax_ab_id_pruning_full_eval"].analysis_budget
    assert rows["phase3_negamax_ab_id_pruning_full_eval"].match_mode in {"ClockManaged", "FixedMoveTime"}


def test_setup_feature_recommendations_cover_runtime_features():
    paths = resolve_paths(root=Path.cwd())
    result = build_setup_feature_model(paths)
    rows = {row.feature_name: row for row in result.feature_recommendations}

    assert rows["Opening Book"].setup_impact == "primary"
    assert "Enable in match play" in rows["Opening Book"].runtime_policy
    assert rows["Pondering"].preferred_match_mode == "ClockManaged"
    assert rows["Time Management"].preferred_match_mode == "ClockManaged"
