from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from .exporters import export_feature_model_json, export_featureide_xml
from .models import ConstraintRule, FeatureNode, TraceRecord
from .pl_codegen import load_model_index, resolve_selected_option_ids, validate_selection


@dataclass
class VariantSetupRecommendation:
    variant_name: str
    backend_class: str
    search_profile: str
    analysis_mode: str
    analysis_budget: str
    match_mode: str
    match_budget: str
    book_policy: str
    ponder_policy: str
    notes: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass
class FeatureSetupRecommendation:
    feature_name: str
    setup_impact: str
    preferred_analysis_mode: str
    preferred_analysis_budget: str
    preferred_match_mode: str
    runtime_policy: str
    notes: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass
class SetupBuildResult:
    features: list[FeatureNode]
    traces: list[TraceRecord]
    constraints: list[ConstraintRule]
    variant_recommendations: list[VariantSetupRecommendation]
    feature_recommendations: list[FeatureSetupRecommendation]
    meta: dict[str, object]
    warnings: list[str]


def _setup_output_paths(paths) -> dict[str, Path]:
    outputs_dir = paths.outputs_dir
    return {
        "json": outputs_dir / "setup_feature_model.json",
        "featureide": outputs_dir / "setup_feature_model.featureide.xml",
        "variant_csv": outputs_dir / "setup_recommendations_by_variant.csv",
        "variant_md": outputs_dir / "setup_recommendations_by_variant.md",
        "feature_csv": outputs_dir / "setup_recommendations_by_feature.csv",
        "feature_md": outputs_dir / "setup_recommendations_by_feature.md",
        "report": outputs_dir / "setup_recommendations_report.md",
    }


def _setup_trace(feature_id: str, source_path: Path, title: str, snippet: str) -> TraceRecord:
    return TraceRecord(
        id=f"setup_trace_{feature_id}",
        feature_id=feature_id,
        source_url=str(source_path),
        source_title=title,
        snippet=snippet,
        confidence=0.95,
        rule_id="runtime_setup_spec",
    )


def build_setup_feature_model(paths) -> SetupBuildResult:
    root_id = "engine_setup"
    features = [
        FeatureNode(
            id=root_id,
            name="EngineSetup",
            parent_id=None,
            kind="mandatory",
            description="Runtime and operational setup variability layered on top of a derived engine variant.",
            variation_role="root",
            variability_stage="none",
            configurable=False,
        ),
        FeatureNode(
            id="setup_search_budget",
            name="Search Budget",
            parent_id=root_id,
            kind="xor",
            description="Primary runtime search-limit mode.",
            variation_role="group",
            variability_stage="none",
            configurable=False,
        ),
        FeatureNode(
            id="setup_fixed_depth",
            name="Fixed Depth",
            parent_id="setup_search_budget",
            kind="xor",
            description="Use an exact search depth and disable time cutoffs.",
            variation_role="option",
            variability_stage="runtime",
            runtime_flag="go depth N",
        ),
        FeatureNode(
            id="setup_depth_shallow",
            name="Shallow Depth",
            parent_id="setup_fixed_depth",
            kind="optional",
            description="Small depth budget, typically depth 2-4.",
            variation_role="option",
            variability_stage="runtime",
            runtime_flag="depth 2-4",
        ),
        FeatureNode(
            id="setup_depth_medium",
            name="Medium Depth",
            parent_id="setup_fixed_depth",
            kind="optional",
            description="Moderate depth budget, typically depth 5-8.",
            variation_role="option",
            variability_stage="runtime",
            runtime_flag="depth 5-8",
        ),
        FeatureNode(
            id="setup_depth_deep",
            name="Deep Depth",
            parent_id="setup_fixed_depth",
            kind="optional",
            description="Deep analysis budget, typically depth 9+.",
            variation_role="option",
            variability_stage="runtime",
            runtime_flag="depth 9+",
        ),
        FeatureNode(
            id="setup_fixed_movetime",
            name="Fixed MoveTime",
            parent_id="setup_search_budget",
            kind="xor",
            description="Allocate a fixed exact movetime to each search.",
            variation_role="option",
            variability_stage="runtime",
            runtime_flag="go movetime <ms>",
        ),
        FeatureNode(
            id="setup_movetime_short",
            name="Short MoveTime",
            parent_id="setup_fixed_movetime",
            kind="optional",
            description="Short per-move budget, typically 50-250 ms.",
            variation_role="option",
            variability_stage="runtime",
            runtime_flag="movetime 50-250",
        ),
        FeatureNode(
            id="setup_movetime_medium",
            name="Medium MoveTime",
            parent_id="setup_fixed_movetime",
            kind="optional",
            description="Medium per-move budget, typically 300-1000 ms.",
            variation_role="option",
            variability_stage="runtime",
            runtime_flag="movetime 300-1000",
        ),
        FeatureNode(
            id="setup_movetime_long",
            name="Long MoveTime",
            parent_id="setup_fixed_movetime",
            kind="optional",
            description="Long per-move budget, typically 1500 ms or more.",
            variation_role="option",
            variability_stage="runtime",
            runtime_flag="movetime 1500+",
        ),
        FeatureNode(
            id="setup_clock_managed",
            name="Clock Managed",
            parent_id="setup_search_budget",
            kind="optional",
            description="Let the engine derive the budget from UCI clock information.",
            variation_role="option",
            variability_stage="runtime",
            runtime_flag="go wtime/btime[/winc/binc/movestogo]",
        ),
        FeatureNode(
            id="setup_increment_aware",
            name="Increment Aware",
            parent_id="setup_clock_managed",
            kind="optional",
            description="Budget calculation considers increment terms.",
            variation_role="option",
            variability_stage="runtime",
            runtime_flag="winc/binc",
        ),
        FeatureNode(
            id="setup_movestogo_aware",
            name="Moves-To-Go Aware",
            parent_id="setup_clock_managed",
            kind="optional",
            description="Budget calculation considers remaining moves to the time control.",
            variation_role="option",
            variability_stage="runtime",
            runtime_flag="movestogo",
        ),
        FeatureNode(
            id="setup_book_control",
            name="Opening Book Control",
            parent_id=root_id,
            kind="xor",
            description="Runtime control of opening-book usage.",
            variation_role="group",
            variability_stage="none",
            configurable=False,
        ),
        FeatureNode(
            id="setup_book_disabled",
            name="Own Book Disabled",
            parent_id="setup_book_control",
            kind="optional",
            description="Disable the engine opening book at runtime.",
            variation_role="option",
            variability_stage="runtime",
            runtime_flag="setoption name OwnBook value false",
        ),
        FeatureNode(
            id="setup_book_enabled",
            name="Own Book Enabled",
            parent_id="setup_book_control",
            kind="xor",
            description="Enable the engine opening book at runtime.",
            variation_role="option",
            variability_stage="runtime",
            runtime_flag="setoption name OwnBook value true",
        ),
        FeatureNode(
            id="setup_book_default_file",
            name="Default Book File",
            parent_id="setup_book_enabled",
            kind="optional",
            description="Use the built-in default opening-book file.",
            variation_role="option",
            variability_stage="runtime",
            runtime_flag="BookFile=c_engine_pl/books/default_openings.txt",
        ),
        FeatureNode(
            id="setup_book_custom_file",
            name="Custom Book File",
            parent_id="setup_book_enabled",
            kind="optional",
            description="Use an explicitly selected external opening-book file.",
            variation_role="option",
            variability_stage="runtime",
            runtime_flag="setoption name BookFile value <path>",
        ),
        FeatureNode(
            id="setup_ponder_control",
            name="Ponder Control",
            parent_id=root_id,
            kind="xor",
            description="Runtime control of pondering.",
            variation_role="group",
            variability_stage="none",
            configurable=False,
        ),
        FeatureNode(
            id="setup_ponder_disabled",
            name="Ponder Disabled",
            parent_id="setup_ponder_control",
            kind="optional",
            description="Disable pondering and use only normal go commands.",
            variation_role="option",
            variability_stage="runtime",
            runtime_flag="setoption name Ponder value false",
        ),
        FeatureNode(
            id="setup_ponder_enabled",
            name="Ponder Enabled",
            parent_id="setup_ponder_control",
            kind="optional",
            description="Enable asynchronous go ponder / ponderhit handling.",
            variation_role="option",
            variability_stage="runtime",
            runtime_flag="setoption name Ponder value true",
        ),
    ]

    constraints = [
        ConstraintRule(
            id="setup_requires_shallow_fixed_depth",
            kind="requires",
            left_feature_id="setup_depth_shallow",
            right_feature_id="setup_fixed_depth",
            rationale="Depth bands refine fixed-depth search.",
            source="setup_catalog",
        ),
        ConstraintRule(
            id="setup_requires_medium_fixed_depth",
            kind="requires",
            left_feature_id="setup_depth_medium",
            right_feature_id="setup_fixed_depth",
            rationale="Depth bands refine fixed-depth search.",
            source="setup_catalog",
        ),
        ConstraintRule(
            id="setup_requires_deep_fixed_depth",
            kind="requires",
            left_feature_id="setup_depth_deep",
            right_feature_id="setup_fixed_depth",
            rationale="Depth bands refine fixed-depth search.",
            source="setup_catalog",
        ),
        ConstraintRule(
            id="setup_requires_short_movetime",
            kind="requires",
            left_feature_id="setup_movetime_short",
            right_feature_id="setup_fixed_movetime",
            rationale="Move-time bands refine fixed movetime.",
            source="setup_catalog",
        ),
        ConstraintRule(
            id="setup_requires_medium_movetime",
            kind="requires",
            left_feature_id="setup_movetime_medium",
            right_feature_id="setup_fixed_movetime",
            rationale="Move-time bands refine fixed movetime.",
            source="setup_catalog",
        ),
        ConstraintRule(
            id="setup_requires_long_movetime",
            kind="requires",
            left_feature_id="setup_movetime_long",
            right_feature_id="setup_fixed_movetime",
            rationale="Move-time bands refine fixed movetime.",
            source="setup_catalog",
        ),
        ConstraintRule(
            id="setup_requires_custom_book",
            kind="requires",
            left_feature_id="setup_book_custom_file",
            right_feature_id="setup_book_enabled",
            rationale="A custom book file only makes sense if the engine book is enabled.",
            source="setup_catalog",
        ),
        ConstraintRule(
            id="setup_requires_default_book",
            kind="requires",
            left_feature_id="setup_book_default_file",
            right_feature_id="setup_book_enabled",
            rationale="The default book file only makes sense if the engine book is enabled.",
            source="setup_catalog",
        ),
        ConstraintRule(
            id="setup_requires_increment_clock",
            kind="requires",
            left_feature_id="setup_increment_aware",
            right_feature_id="setup_clock_managed",
            rationale="Increment awareness refines clock-managed search.",
            source="setup_catalog",
        ),
        ConstraintRule(
            id="setup_requires_movestogo_clock",
            kind="requires",
            left_feature_id="setup_movestogo_aware",
            right_feature_id="setup_clock_managed",
            rationale="Moves-to-go awareness refines clock-managed search.",
            source="setup_catalog",
        ),
    ]

    uci_path = paths.root / "c_engine_pl" / "src" / "uci.c"
    search_path = paths.root / "c_engine_pl" / "src" / "search.c"
    engine_path = paths.root / "c_engine_pl" / "src" / "engine.c"
    traces = [
        _setup_trace("setup_fixed_depth", uci_path, "UCI go depth", "Depth-only mode returns -1 and disables time cutoffs."),
        _setup_trace("setup_depth_shallow", uci_path, "UCI go depth", "Shallow depth is a low fixed-depth budget such as depth 2-4."),
        _setup_trace("setup_depth_medium", uci_path, "UCI go depth", "Medium depth is a moderate fixed-depth budget such as depth 5-8."),
        _setup_trace("setup_depth_deep", uci_path, "UCI go depth", "Deep depth represents deeper fixed-depth analysis budgets."),
        _setup_trace("setup_fixed_movetime", uci_path, "UCI movetime", "Explicit movetime is parsed and marked exact."),
        _setup_trace("setup_movetime_short", uci_path, "UCI movetime", "Short movetime corresponds to very small exact budgets."),
        _setup_trace("setup_movetime_medium", uci_path, "UCI movetime", "Medium movetime corresponds to moderate exact per-move budgets."),
        _setup_trace("setup_movetime_long", uci_path, "UCI movetime", "Long movetime corresponds to large exact per-move budgets."),
        _setup_trace("setup_clock_managed", search_path, "Search deadlines", "Clock-managed search derives soft and hard deadlines from runtime clock data."),
        _setup_trace("setup_increment_aware", uci_path, "UCI increment parsing", "Budget allocation considers winc/binc when present."),
        _setup_trace("setup_movestogo_aware", uci_path, "UCI movestogo parsing", "Budget allocation considers movestogo when present."),
        _setup_trace("setup_book_disabled", engine_path, "OwnBook option", "The engine exposes OwnBook to disable the book at runtime."),
        _setup_trace("setup_book_enabled", engine_path, "OwnBook option", "The engine exposes OwnBook to enable the book at runtime."),
        _setup_trace("setup_book_default_file", engine_path, "BookFile option", "The engine advertises the default book file path."),
        _setup_trace("setup_book_custom_file", uci_path, "BookFile option", "The engine accepts a runtime BookFile path through setoption."),
        _setup_trace("setup_ponder_disabled", engine_path, "Ponder option", "The engine exposes Ponder to disable pondering at runtime."),
        _setup_trace("setup_ponder_enabled", uci_path, "Ponder option", "The engine supports go ponder, ponderhit, and stop."),
    ]

    variant_recommendations, feature_recommendations, warnings = build_setup_recommendations(
        paths,
        feature_model_path=paths.feature_model_json_path,
        variants_dir=paths.root / "c_engine_pl" / "variants",
    )

    meta = {
        "model_perspective": "runtime_setup_layer",
        "goal": "Model runtime and harness variability layered on top of a compile-time engine variant.",
        "abstraction_note": "Numeric UCI parameters are abstracted into categorical setup bands so they fit a feature-model style representation.",
        "scope_limit": "Only setup variability backed by the current engine implementation is modeled. Threads and Hash are intentionally excluded because they are not exposed as real engine options here.",
        "variant_recommendations": len(variant_recommendations),
        "feature_recommendations": len(feature_recommendations),
    }

    return SetupBuildResult(
        features=features,
        traces=traces,
        constraints=constraints,
        variant_recommendations=variant_recommendations,
        feature_recommendations=feature_recommendations,
        meta=meta,
        warnings=warnings,
    )


def _load_variant_tokens(config_path: Path) -> tuple[str, list[str]]:
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    return str(payload.get("name", config_path.stem)), [str(item) for item in payload.get("selected_options", [])]


def _backend_class(selected: set[str]) -> str:
    if "Magic Bitboards" in selected:
        return "MagicBitboards"
    if "Bitboards" in selected:
        return "Bitboards"
    if "Mailbox" in selected:
        return "Mailbox"
    if "0x88" in selected:
        return "0x88"
    if "10x12 Board" in selected:
        return "10x12"
    return "Unknown"


def _search_profile(selected: set[str]) -> str:
    if "Minimax" in selected and "Alpha-Beta" not in selected:
        return "Minimax"
    if "Minimax" in selected and "Alpha-Beta" in selected and "Iterative Deepening" in selected:
        return "Minimax+AlphaBeta+ID"
    if "Minimax" in selected and "Alpha-Beta" in selected:
        return "Minimax+AlphaBeta"
    if "Negamax" in selected and "Alpha-Beta" not in selected:
        return "Negamax"
    if "Negamax" in selected and "Alpha-Beta" in selected and "Principal Variation Search" in selected and "Iterative Deepening" in selected:
        return "Negamax+AlphaBeta+PVS+ID"
    if "Negamax" in selected and "Alpha-Beta" in selected and "Iterative Deepening" in selected:
        return "Negamax+AlphaBeta+ID"
    if "Negamax" in selected and "Alpha-Beta" in selected:
        return "Negamax+AlphaBeta"
    return "Search"


def _budget_score(selected: set[str]) -> int:
    score = 0
    if "Minimax" in selected:
        score -= 4
    if "Alpha-Beta" in selected:
        score += 4
    if "Principal Variation Search" in selected:
        score += 1
    if "Iterative Deepening" in selected:
        score += 1
    if "Transposition Table" in selected:
        score += 1
    if "Hash Move" in selected:
        score += 1
    if "Killer Heuristic" in selected:
        score += 1
    if "History Heuristic" in selected:
        score += 1
    pruning_hits = sum(
        1
        for name in (
            "Null Move Pruning",
            "Late Move Reductions",
            "Futility Pruning",
            "Razoring",
            "Delta Pruning",
        )
        if name in selected
    )
    if pruning_hits >= 2:
        score += 2
    elif pruning_hits == 1:
        score += 1
    if "Bitboards" in selected:
        score += 1
    if "Magic Bitboards" in selected:
        score += 1
    return score


def _budget_tier(score: int) -> str:
    if score <= 0:
        return "shallow"
    if score <= 4:
        return "moderate"
    if score <= 8:
        return "deep"
    return "very_deep"


def _analysis_budget_for_tier(tier: str) -> tuple[str, str]:
    if tier == "shallow":
        return "FixedDepth", "depth 3-4 (target 4)"
    if tier == "moderate":
        return "FixedDepth", "depth 5-8 (target 6)"
    if tier == "deep":
        return "FixedDepth", "depth 9-12 (target 10)"
    return "FixedDepth", "depth 12-20 (target 14)"


def _match_budget_for_tier(tier: str, has_time_management: bool) -> tuple[str, str]:
    if has_time_management:
        if tier in {"deep", "very_deep"}:
            return "ClockManaged", "120+1 with increment and movestogo when available"
        if tier == "moderate":
            return "ClockManaged", "10+0.1 with increment-aware allocation"
        return "FixedMoveTime", "100-250 ms/move"

    if tier == "shallow":
        return "FixedMoveTime", "100-250 ms/move"
    if tier == "moderate":
        return "FixedMoveTime", "250-500 ms/move"
    if tier == "deep":
        return "FixedMoveTime", "750-1000 ms/move"
    return "FixedMoveTime", "1500-2000 ms/move"


def _book_policy(selected: set[str]) -> str:
    if "Opening Book" not in selected:
        return "unsupported"
    return "match: enable default book; analysis/perft: disable"


def _ponder_policy(selected: set[str], match_mode: str) -> str:
    if "Pondering" not in selected:
        return "unsupported"
    if match_mode == "ClockManaged":
        return "match: enable if GUI sends go ponder/ponderhit; analysis/perft: disable"
    return "available but usually keep disabled outside long time-control GUI play"


def _variant_notes(selected: set[str], tier: str, match_mode: str) -> str:
    notes: list[str] = []
    if "Time Management" not in selected and match_mode == "FixedMoveTime":
        notes.append("No dedicated Time Management feature is selected, so fixed movetime is the safer operational default.")
    if "Time Management" in selected and match_mode == "ClockManaged":
        notes.append("Clock-managed play is justified because the variant includes explicit time-allocation logic.")
    if "Opening Book" in selected:
        notes.append("Opening book should stay off for perft and analysis to avoid masking search behavior.")
    if "Pondering" in selected:
        notes.append("Pondering depends on GUI cooperation and is not relevant for perft.")
    if tier == "very_deep":
        notes.append("This stack is deep enough that larger depth targets are meaningful for single-variant analysis.")
    return " ".join(notes)


def build_setup_recommendations(paths, feature_model_path: Path, variants_dir: Path) -> tuple[list[VariantSetupRecommendation], list[FeatureSetupRecommendation], list[str]]:
    model = load_model_index(feature_model_path)
    warnings: list[str] = []
    variant_rows: list[VariantSetupRecommendation] = []

    for config_path in sorted(variants_dir.glob("*.json")):
        variant_name, tokens = _load_variant_tokens(config_path)
        selected_ids, resolve_errors = resolve_selected_option_ids(model, tokens)
        validation_errors = validate_selection(model, selected_ids)
        if resolve_errors or validation_errors:
            warnings.append(
                f"Skipped variant '{variant_name}' while building setup recommendations: {'; '.join(resolve_errors + validation_errors)}"
            )
            continue

        selected_names = {model.options_by_id[feature_id].name for feature_id in selected_ids if feature_id in model.options_by_id}
        score = _budget_score(selected_names)
        tier = _budget_tier(score)
        analysis_mode, analysis_budget = _analysis_budget_for_tier(tier)
        match_mode, match_budget = _match_budget_for_tier(tier, "Time Management" in selected_names)

        variant_rows.append(
            VariantSetupRecommendation(
                variant_name=variant_name,
                backend_class=_backend_class(selected_names),
                search_profile=_search_profile(selected_names),
                analysis_mode=analysis_mode,
                analysis_budget=analysis_budget,
                match_mode=match_mode,
                match_budget=match_budget,
                book_policy=_book_policy(selected_names),
                ponder_policy=_ponder_policy(selected_names, match_mode),
                notes=_variant_notes(selected_names, tier, match_mode),
            )
        )

    feature_rows = [
        _feature_setup_recommendation(feature)
        for feature in sorted(model.options_by_id.values(), key=lambda item: item.name.lower())
    ]

    return variant_rows, feature_rows, warnings


def _feature_setup_recommendation(feature: FeatureNode) -> FeatureSetupRecommendation:
    name = feature.name

    if name == "Minimax":
        return FeatureSetupRecommendation(
            feature_name=name,
            setup_impact="primary",
            preferred_analysis_mode="FixedDepth",
            preferred_analysis_budget="ShallowDepth (3-4)",
            preferred_match_mode="FixedMoveTime",
            runtime_policy="Avoid deep fixed-depth tournaments; prefer small exact budgets.",
            notes="Tree growth is explosive without alpha-beta pruning, so setup must stay conservative.",
        )
    if name == "Negamax":
        return FeatureSetupRecommendation(
            feature_name=name,
            setup_impact="primary",
            preferred_analysis_mode="FixedDepth",
            preferred_analysis_budget="MediumDepth (5-8) unless refined by Alpha-Beta/PVS/TT",
            preferred_match_mode="FixedMoveTime",
            runtime_policy="Negamax alone does not justify aggressive time controls.",
            notes="Search-core symmetry helps, but setup strength really increases once alpha-beta and ordering features are present.",
        )
    if name in {"Alpha-Beta", "Principal Variation Search", "Iterative Deepening"}:
        return FeatureSetupRecommendation(
            feature_name=name,
            setup_impact="primary",
            preferred_analysis_mode="FixedDepth",
            preferred_analysis_budget="Deeper depth bands become meaningful (9+ when stacked together)",
            preferred_match_mode="ClockManaged" if name == "Iterative Deepening" else "FixedMoveTime or ClockManaged",
            runtime_policy="These features pay off more under time-based or deeper fixed-depth setups.",
            notes="They are search-strength multipliers and should move the setup toward deeper or time-aware operation.",
        )
    if name in {"Null Move Pruning", "Late Move Reductions", "Futility Pruning", "Razoring", "Delta Pruning"}:
        return FeatureSetupRecommendation(
            feature_name=name,
            setup_impact="conditional",
            preferred_analysis_mode="FixedDepth",
            preferred_analysis_budget="DeepDepth (9+) once the base search stack is stable",
            preferred_match_mode="FixedMoveTime or ClockManaged",
            runtime_policy="Do not rely on these to compensate for weak base search settings.",
            notes="Selective pruning is most useful when the surrounding alpha-beta, TT, and move-ordering infrastructure is already strong.",
        )
    if name in {"Transposition Table", "Hash Move", "Zobrist Hashing", "Replacement Schemes", "Pawn Hash Table", "Move Ordering", "Killer Heuristic", "History Heuristic", "Static Exchange Evaluation"}:
        return FeatureSetupRecommendation(
            feature_name=name,
            setup_impact="conditional",
            preferred_analysis_mode="FixedDepth or FixedMoveTime",
            preferred_analysis_budget="MediumDepth to DeepDepth depending on the rest of the stack",
            preferred_match_mode="FixedMoveTime or ClockManaged",
            runtime_policy="These features become more valuable as the search budget grows.",
            notes="They are setup-sensitive because their practical benefit appears more clearly at larger search budgets.",
        )
    if name in {"Bitboards", "Magic Bitboards"}:
        return FeatureSetupRecommendation(
            feature_name=name,
            setup_impact="conditional",
            preferred_analysis_mode="FixedDepth",
            preferred_analysis_budget="DeepDepth is realistic on these faster backends",
            preferred_match_mode="FixedMoveTime or ClockManaged",
            runtime_policy="Faster backends justify larger depth targets.",
            notes="Backend speed affects how ambitious the runtime budget can be.",
        )
    if name in {"0x88", "Mailbox", "10x12 Board"}:
        return FeatureSetupRecommendation(
            feature_name=name,
            setup_impact="conditional",
            preferred_analysis_mode="FixedDepth",
            preferred_analysis_budget="MediumDepth by default",
            preferred_match_mode="FixedMoveTime",
            runtime_policy="Use more conservative depth targets than the faster bitboard backends.",
            notes="These representations are valid, but the current implementation is not the fastest one for large depth targets.",
        )
    if name == "Opening Book":
        return FeatureSetupRecommendation(
            feature_name=name,
            setup_impact="primary",
            preferred_analysis_mode="FixedDepth or FixedMoveTime",
            preferred_analysis_budget="Disable during analysis/perft",
            preferred_match_mode="FixedMoveTime or ClockManaged",
            runtime_policy="Enable in match play, usually with the default book first; disable in perft and search analysis.",
            notes="Book usage is a runtime operational choice layered on top of the compile-time Opening Book feature.",
        )
    if name == "Pondering":
        return FeatureSetupRecommendation(
            feature_name=name,
            setup_impact="primary",
            preferred_analysis_mode="FixedDepth or FixedMoveTime",
            preferred_analysis_budget="Disable during one-shot analysis and perft",
            preferred_match_mode="ClockManaged",
            runtime_policy="Enable only when the GUI supports go ponder / ponderhit and the time control is long enough.",
            notes="Pondering is runtime-visible but only useful in end-to-end GUI match contexts.",
        )
    if name == "Time Management":
        return FeatureSetupRecommendation(
            feature_name=name,
            setup_impact="primary",
            preferred_analysis_mode="FixedMoveTime or ClockManaged",
            preferred_analysis_budget="Medium to long exact budgets or full clock-managed play",
            preferred_match_mode="ClockManaged",
            runtime_policy="Prefer real time controls with increment and movestogo when available.",
            notes="This is the main feature that justifies using clock-derived budgets instead of exact movetime.",
        )

    return FeatureSetupRecommendation(
        feature_name=name,
        setup_impact="none",
        preferred_analysis_mode="Inherit variant profile",
        preferred_analysis_budget="No direct setup-specific change",
        preferred_match_mode="Inherit variant profile",
        runtime_policy="No direct runtime setup knob beyond the surrounding variant profile.",
        notes="This feature mainly changes engine behavior internally rather than introducing a separate setup policy.",
    )


def _write_csv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _write_markdown(path: Path, rows: list[dict[str, str]], headers: list[str], legend: str | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(row.get(header, "")) for header in headers) + " |")
    if legend:
        lines.extend(["", legend])
    path.write_text("\n".join(lines), encoding="utf-8")


def export_setup_outputs(paths, result: SetupBuildResult) -> dict[str, Path]:
    output_paths = _setup_output_paths(paths)
    export_feature_model_json(
        output_paths["json"],
        result.features,
        result.traces,
        result.constraints,
        result.meta,
    )
    export_featureide_xml(output_paths["featureide"], result.features, result.constraints)

    variant_rows = [row.to_dict() for row in result.variant_recommendations]
    feature_rows = [row.to_dict() for row in result.feature_recommendations]

    variant_fields = [
        "variant_name",
        "backend_class",
        "search_profile",
        "analysis_mode",
        "analysis_budget",
        "match_mode",
        "match_budget",
        "book_policy",
        "ponder_policy",
        "notes",
    ]
    feature_fields = [
        "feature_name",
        "setup_impact",
        "preferred_analysis_mode",
        "preferred_analysis_budget",
        "preferred_match_mode",
        "runtime_policy",
        "notes",
    ]

    _write_csv(output_paths["variant_csv"], variant_rows, variant_fields)
    _write_markdown(output_paths["variant_md"], variant_rows, variant_fields)
    _write_csv(output_paths["feature_csv"], feature_rows, feature_fields)
    _write_markdown(output_paths["feature_md"], feature_rows, feature_fields)

    report_lines = [
        "# Setup Variability Report",
        "",
        "## Scope",
        "- This setup model captures runtime and harness choices layered on top of a compile-time engine variant.",
        "- It intentionally models only implemented variability: search budget, opening-book control, and pondering control.",
        "- It intentionally excludes fictive runtime knobs such as `Threads` and `Hash`, because the engine does not expose them as real setup options here.",
        "",
        "## Counts",
        f"- setup features: {len(result.features)}",
        f"- setup constraints: {len(result.constraints)}",
        f"- variant recommendations: {len(result.variant_recommendations)}",
        f"- feature recommendations: {len(result.feature_recommendations)}",
        "",
        "## Warnings",
    ]
    if result.warnings:
        for warning in result.warnings:
            report_lines.append(f"- {warning}")
    else:
        report_lines.append("- None")
    output_paths["report"].write_text("\n".join(report_lines), encoding="utf-8")

    return output_paths
