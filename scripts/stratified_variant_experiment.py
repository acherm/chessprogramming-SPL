#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import random
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

import chess

from cpw_variability.pl_codegen import (
    derive_variant,
    load_model_index,
    resolve_selected_option_ids,
    run_build,
    run_smoke,
    validate_selection,
)

PERFT_RE = re.compile(r"^info string perft depth (\d+) nodes (\d+)$")
BESTMOVE_RE = re.compile(r"^bestmove\s+([^\s]+)")
STARTPOS_EXPECTED = {1: 20, 2: 400, 3: 8902, 4: 197281, 5: 4865609, 6: 119060324}

REQUIRED_GROUPS = ("board_representation", "search", "evaluation", "move_generation", "protocol")
MANDATORY_OPTION_NAMES = (
    "UCI",
    "Move Generation",
    "Castling",
    "En Passant",
    "Threefold Repetition",
    "Fifty-Move Rule",
)
BOARD_PRIMARY_NAMES = ("Bitboards", "0x88", "Mailbox", "10x12 Board")
SEARCH_CORE_NAMES = ("Minimax", "Negamax")
SAFE_ALWAYS_ON_OPTION_NAMES = ("Evaluation", "FEN")

SEARCH_ADVANCED = {
    "Aspiration Windows",
    "Null Move Pruning",
    "Late Move Reductions",
    "Futility Pruning",
    "Razoring",
    "Delta Pruning",
    "Killer Heuristic",
    "History Heuristic",
}
EVAL_STRUCTURAL = {
    "Passed Pawn",
    "Isolated Pawn",
    "Doubled Pawn",
    "Connected Pawn",
}
EVAL_RICH = {
    "Pawn Hash Table",
    "Bishop Pair",
    "Rook on Open File",
    "Rook Semi-Open File",
    "Mobility",
    "King Pressure",
    "King Shelter",
    "Tapered Eval",
    "King Activity",
    "Static Exchange Evaluation",
}

CONTROL_SPECS = (
    ("worst_preset", "c_engine_pl/variants/phase1_minimax.json"),
    ("reference_random", "c_engine_pl/variants/phase2_10x12_ab_pvs_id.json"),
    ("best_preset", "c_engine_pl/variants/phase3_full_eval.json"),
    ("best_empirical", "outputs/improved_variants/strong_variant_02.json"),
)

ABLATION_FAMILIES = {
    "search_core_ladder": [
        "c_engine_pl/variants/phase1_minimax.json",
        "c_engine_pl/variants/phase1_negamax.json",
        "c_engine_pl/variants/phase1_negamax_ab.json",
        "c_engine_pl/variants/phase1_negamax_ab_pvs_id.json",
    ],
    "board_backend_family": [
        "c_engine_pl/variants/phase2_bitboards_ab_pvs_id.json",
        "c_engine_pl/variants/phase2_magic_bitboards_ab_pvs_id.json",
        "c_engine_pl/variants/phase2_0x88_ab_pvs_id.json",
        "c_engine_pl/variants/phase2_mailbox_piece_lists_ab_pvs_id.json",
        "c_engine_pl/variants/phase2_10x12_ab_pvs_id.json",
    ],
    "evaluation_ladder": [
        "c_engine_pl/variants/phase3_material_only.json",
        "c_engine_pl/variants/phase3_pst_pawn.json",
        "c_engine_pl/variants/phase3_full_eval.json",
    ],
    "search_refinement_pair": [
        "c_engine_pl/variants/phase3_full_eval.json",
        "c_engine_pl/variants/phase3_negamax_ab_id_pruning_full_eval.json",
    ],
}

CORRECTNESS_PROBES: tuple[tuple[str, str], ...] = (
    ("startpos", "position startpos"),
    ("castle_tension", "position fen r3k2r/pppq1ppp/2n1bn2/3pp3/3PP3/2N1BN2/PPP2PPP/R2Q1RK1 w kq - 0 9"),
    ("en_passant_window", "position fen rnbqkbnr/pppp1ppp/8/4p3/3PPp2/8/PPP3PP/RNBQKBNR b KQkq d3 0 3"),
    ("promotion_race", "position fen 8/P7/2k5/8/8/8/7p/2K5 w - - 0 1"),
)


@dataclass
class VariantSpec:
    variant_name: str
    source_kind: str
    role: str
    config_path: Path
    selected_ids: tuple[str, ...]
    selected_features: list[str]
    selected_feature_count: int
    board_family: str
    search_tier: str
    eval_tier: str
    feature_count_bin: str
    stratum: str


def feature_count_bin(count: int) -> str:
    if count <= 20:
        return "low"
    if count <= 30:
        return "medium"
    return "high"


def classify_variant(selected_features: list[str]) -> tuple[str, str, str]:
    feature_set = set(selected_features)

    board = "unknown"
    for name in BOARD_PRIMARY_NAMES:
        if name in feature_set:
            board = name
            break

    if "Minimax" in feature_set:
        search_tier = "minimax"
    elif "Negamax" in feature_set and "Alpha-Beta" not in feature_set:
        search_tier = "negamax"
    elif "Alpha-Beta" in feature_set and not ({"Principal Variation Search", "Iterative Deepening"} & feature_set):
        search_tier = "alpha_beta"
    elif feature_set & SEARCH_ADVANCED:
        search_tier = "pruning_full"
    elif {"Principal Variation Search", "Iterative Deepening"} & feature_set:
        search_tier = "pvs_id"
    else:
        search_tier = "search_misc"

    if feature_set & EVAL_RICH:
        eval_tier = "rich_eval"
    elif feature_set & EVAL_STRUCTURAL:
        eval_tier = "structural_eval"
    elif "Piece-Square Tables" in feature_set:
        eval_tier = "pst_eval"
    elif "Evaluation" in feature_set:
        eval_tier = "material_eval"
    else:
        eval_tier = "eval_misc"

    return board, search_tier, eval_tier


def choose_random_valid_selection(model, rng: random.Random, optional_prob: float, max_attempts: int) -> set[str]:
    options = list(model.options_by_id.values())
    options_by_name = {option.name: option for option in options}

    board_primary_ids = {
        options_by_name[name].id
        for name in BOARD_PRIMARY_NAMES
        if name in options_by_name
    }
    search_core_ids = {
        options_by_name[name].id
        for name in SEARCH_CORE_NAMES
        if name in options_by_name
    }
    requires_map: dict[str, set[str]] = {}
    excludes_map: dict[str, set[str]] = {}
    for rule in model.constraints:
        if rule.kind == "requires":
            requires_map.setdefault(rule.left_feature_id, set()).add(rule.right_feature_id)
        elif rule.kind == "excludes":
            excludes_map.setdefault(rule.left_feature_id, set()).add(rule.right_feature_id)
            excludes_map.setdefault(rule.right_feature_id, set()).add(rule.left_feature_id)

    def require_closure(feature_id: str) -> set[str]:
        closure: set[str] = set()
        stack = [feature_id]
        while stack:
            current = stack.pop()
            for req in requires_map.get(current, set()):
                if req in closure:
                    continue
                closure.add(req)
                stack.append(req)
        return closure

    def can_add(selected: set[str], additions: set[str], board_id: str, search_id: str) -> bool:
        future = selected | additions
        other_board_ids = board_primary_ids - {board_id}
        other_search_ids = search_core_ids - {search_id}
        if future & other_board_ids:
            return False
        if future & other_search_ids:
            return False
        for feature_id in additions:
            if excludes_map.get(feature_id, set()) & future:
                return False
        for feature_id in selected:
            if excludes_map.get(feature_id, set()) & additions:
                return False
        return True

    for _ in range(max_attempts):
        selected: set[str] = set()

        for name in MANDATORY_OPTION_NAMES + SAFE_ALWAYS_ON_OPTION_NAMES:
            opt = options_by_name.get(name)
            if opt is not None:
                selected.add(opt.id)

        board_choices = [options_by_name[name].id for name in BOARD_PRIMARY_NAMES if name in options_by_name]
        if board_choices:
            chosen_board = rng.choice(board_choices)
            selected.add(chosen_board)
        else:
            chosen_board = ""

        search_choices = [options_by_name[name].id for name in SEARCH_CORE_NAMES if name in options_by_name]
        if search_choices:
            chosen_search = rng.choice(search_choices)
            selected.add(chosen_search)
        else:
            chosen_search = ""

        expanded = set(selected)
        for feature_id in list(selected):
            expanded |= require_closure(feature_id)
        selected = expanded
        if chosen_board and chosen_board not in selected:
            selected.add(chosen_board)
        if chosen_search and chosen_search not in selected:
            selected.add(chosen_search)

        option_order = list(options)
        rng.shuffle(option_order)
        for option in option_order:
            if option.id in selected:
                continue
            if option.id in board_primary_ids:
                continue
            if option.id in search_core_ids:
                continue
            if rng.random() < optional_prob:
                additions = {option.id} | require_closure(option.id)
                if can_add(selected, additions, chosen_board, chosen_search):
                    selected |= additions

        errors = validate_selection(model, selected, enforce_tournament_legality=True)
        if not errors:
            return selected

    raise RuntimeError(f"Failed to generate valid selection after {max_attempts} attempts")


def load_variant_from_config(model, config_path: Path, role: str, source_kind: str) -> VariantSpec:
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    selected_ids, resolve_errors = resolve_selected_option_ids(model, [str(token) for token in payload.get("selected_options", [])])
    validation_errors = validate_selection(model, selected_ids, enforce_tournament_legality=True)
    errors = resolve_errors + validation_errors
    if errors:
        raise ValueError(f"Invalid control/ablation config {config_path}: {'; '.join(errors)}")

    selected_options = [model.options_by_id[option_id] for option_id in sorted(selected_ids)]
    selected_features = [option.name for option in sorted(selected_options, key=lambda item: item.name.lower())]
    board, search_tier, eval_tier = classify_variant(selected_features)
    variant_name = str(payload.get("name") or config_path.stem)
    count = len(selected_features)
    return VariantSpec(
        variant_name=variant_name,
        source_kind=source_kind,
        role=role,
        config_path=config_path,
        selected_ids=tuple(sorted(selected_ids)),
        selected_features=selected_features,
        selected_feature_count=count,
        board_family=board,
        search_tier=search_tier,
        eval_tier=eval_tier,
        feature_count_bin=feature_count_bin(count),
        stratum=f"{board}__{search_tier}__{eval_tier}",
    )


def build_candidate_spec(model, selected_ids: set[str], config_path: Path, variant_name: str) -> VariantSpec:
    selected_options = [model.options_by_id[option_id] for option_id in sorted(selected_ids)]
    selected_features = [option.name for option in sorted(selected_options, key=lambda item: item.name.lower())]
    board, search_tier, eval_tier = classify_variant(selected_features)
    count = len(selected_features)
    return VariantSpec(
        variant_name=variant_name,
        source_kind="random_sample",
        role="sampled",
        config_path=config_path,
        selected_ids=tuple(sorted(selected_ids)),
        selected_features=selected_features,
        selected_feature_count=count,
        board_family=board,
        search_tier=search_tier,
        eval_tier=eval_tier,
        feature_count_bin=feature_count_bin(count),
        stratum=f"{board}__{search_tier}__{eval_tier}",
    )


def collect_controls(model, workspace: Path) -> list[VariantSpec]:
    controls: list[VariantSpec] = []
    for role, relative_path in CONTROL_SPECS:
        config_path = workspace / relative_path
        if not config_path.exists():
            continue
        controls.append(load_variant_from_config(model, config_path, role=role, source_kind="control"))
    return controls


def collect_ablations(model, workspace: Path) -> list[VariantSpec]:
    rows: list[VariantSpec] = []
    for family, relative_paths in ABLATION_FAMILIES.items():
        for relative_path in relative_paths:
            config_path = workspace / relative_path
            if not config_path.exists():
                continue
            rows.append(load_variant_from_config(model, config_path, role=family, source_kind="ablation"))
    return rows


def sample_stratified_variants(
    model,
    rng: random.Random,
    out_dir: Path,
    count: int,
    optional_prob: float,
    max_attempts: int,
    pool_multiplier: int,
    excluded_ids: set[tuple[str, ...]],
) -> tuple[list[VariantSpec], list[VariantSpec]]:
    pool_target = max(count * pool_multiplier, count + 12)
    pool_dir = out_dir / "pool_configs"
    sample_dir = out_dir / "sample_configs"
    pool_dir.mkdir(parents=True, exist_ok=True)
    sample_dir.mkdir(parents=True, exist_ok=True)

    pool_specs: list[VariantSpec] = []
    seen = set(excluded_ids)
    draw_budget = pool_target * max(10, max_attempts)
    attempts = 0

    while len(pool_specs) < pool_target and attempts < draw_budget:
        attempts += 1
        selected_ids = choose_random_valid_selection(model, rng, optional_prob=optional_prob, max_attempts=max_attempts)
        key = tuple(sorted(selected_ids))
        if key in seen:
            continue
        seen.add(key)

        variant_name = f"pool_variant_{len(pool_specs) + 1:03d}"
        config_path = pool_dir / f"{variant_name}.json"
        selected_options = [model.options_by_id[option_id] for option_id in key]
        selected_names = [option.name for option in sorted(selected_options, key=lambda item: item.name.lower())]
        config_path.write_text(
            json.dumps({"name": variant_name, "selected_options": selected_names}, indent=2),
            encoding="utf-8",
        )
        pool_specs.append(build_candidate_spec(model, selected_ids, config_path, variant_name))

    if len(pool_specs) < count:
        raise RuntimeError(
            f"Only generated {len(pool_specs)} unique legal candidates for a requested sample of {count}. "
            "Increase --pool-multiplier or reduce --count."
        )

    grouped: dict[str, list[VariantSpec]] = {}
    for spec in pool_specs:
        grouped.setdefault(spec.stratum, []).append(spec)

    group_order = list(grouped)
    rng.shuffle(group_order)
    for specs in grouped.values():
        rng.shuffle(specs)

    selected: list[VariantSpec] = []
    while len(selected) < count and group_order:
        next_round: list[str] = []
        for stratum in group_order:
            bucket = grouped[stratum]
            if not bucket:
                continue
            selected.append(bucket.pop())
            if bucket:
                next_round.append(stratum)
            if len(selected) >= count:
                break
        group_order = next_round

    final_specs: list[VariantSpec] = []
    for idx, spec in enumerate(selected, start=1):
        variant_name = f"stratified_variant_{idx:02d}"
        config_path = sample_dir / f"{variant_name}.json"
        config_path.write_text(
            json.dumps({"name": variant_name, "selected_options": spec.selected_features}, indent=2),
            encoding="utf-8",
        )
        final_specs.append(
            VariantSpec(
                variant_name=variant_name,
                source_kind=spec.source_kind,
                role=spec.role,
                config_path=config_path,
                selected_ids=spec.selected_ids,
                selected_features=spec.selected_features,
                selected_feature_count=spec.selected_feature_count,
                board_family=spec.board_family,
                search_tier=spec.search_tier,
                eval_tier=spec.eval_tier,
                feature_count_bin=spec.feature_count_bin,
                stratum=spec.stratum,
            )
        )

    return pool_specs, final_specs


def run_engine(engine_bin: Path, commands: list[str], timeout_sec: float = 60.0) -> list[str]:
    transcript = "\n".join(commands) + "\n"
    completed = subprocess.run(
        [str(engine_bin)],
        input=transcript,
        capture_output=True,
        text=True,
        timeout=timeout_sec,
        check=True,
    )
    return [line.strip() for line in completed.stdout.replace("\\n", "\n").splitlines() if line.strip()]


def parse_perft(lines: list[str]) -> dict[int, int]:
    result: dict[int, int] = {}
    for line in lines:
        match = PERFT_RE.match(line)
        if match is None:
            continue
        result[int(match.group(1))] = int(match.group(2))
    return result


def parse_bestmove(lines: list[str]) -> str | None:
    for line in reversed(lines):
        match = BESTMOVE_RE.match(line)
        if match is not None:
            return match.group(1)
    return None


def run_correctness_probes(engine_bin: Path, probe_depth: int) -> tuple[list[dict[str, object]], bool]:
    rows: list[dict[str, object]] = []
    all_passed = True

    for probe_name, position_cmd in CORRECTNESS_PROBES:
        lines = run_engine(engine_bin, ["uci", "isready", position_cmd, f"go depth {probe_depth}", "quit"])
        bestmove = parse_bestmove(lines)

        board = chess.Board() if position_cmd == "position startpos" else None
        if board is None:
            fen = position_cmd.split("position fen ", 1)[1]
            board = chess.Board(fen)

        legal = False
        error = ""
        if bestmove is None or bestmove == "(none)":
            error = "missing_bestmove"
        else:
            try:
                move = chess.Move.from_uci(bestmove)
                legal = move in board.legal_moves
                if not legal:
                    error = "illegal_bestmove"
            except ValueError:
                error = "unparseable_bestmove"

        if not legal:
            all_passed = False

        rows.append(
            {
                "probe": probe_name,
                "position": position_cmd,
                "bestmove": bestmove or "",
                "legal": "PASS" if legal else "FAIL",
                "error": error,
            }
        )

    return rows, all_passed


def build_and_perft_variant(
    spec: VariantSpec,
    feature_model: Path,
    makefile: Path,
    engine_bin: Path,
    header_out: Path,
    manifest_out: Path,
    out_bin_dir: Path,
    perft_depth: int,
    correctness_depth: int,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    started = time.perf_counter()
    report = derive_variant(
        feature_model_path=feature_model,
        config_path=spec.config_path,
        header_out=header_out,
        manifest_out=manifest_out,
        enforce_tournament_legality=True,
    )
    run_build(makefile)
    build_done = time.perf_counter()

    out_bin_dir.mkdir(parents=True, exist_ok=True)
    binary_path = out_bin_dir / spec.variant_name
    shutil.copy2(engine_bin, binary_path)
    binary_path.chmod(0o755)

    smoke_ok = True
    smoke_error = ""
    try:
        run_smoke(binary_path)
    except Exception as exc:  # pragma: no cover - external engine failure path
        smoke_ok = False
        smoke_error = type(exc).__name__

    commands = ["uci", "isready", "position startpos"]
    for depth in range(1, perft_depth + 1):
        commands.append(f"perft {depth}")
    commands.append("quit")
    lines = run_engine(binary_path, commands)
    perft_done = time.perf_counter()

    perft = parse_perft(lines)
    passed = all(perft.get(depth) == STARTPOS_EXPECTED[depth] for depth in range(1, perft_depth + 1))
    correctness_rows, correctness_pass = run_correctness_probes(binary_path, probe_depth=correctness_depth)
    finished = time.perf_counter()

    row: dict[str, object] = {
        "variant_name": spec.variant_name,
        "source_kind": spec.source_kind,
        "role": spec.role,
        "config_path": str(spec.config_path),
        "binary_path": str(binary_path),
        "selected_feature_count": spec.selected_feature_count,
        "selected_features": "|".join(spec.selected_features),
        "board_family": spec.board_family,
        "search_tier": spec.search_tier,
        "eval_tier": spec.eval_tier,
        "feature_count_bin": spec.feature_count_bin,
        "stratum": spec.stratum,
        "derive_build_sec": round(build_done - started, 3),
        "perft_sec": round(perft_done - build_done, 3),
        "correctness_sec": round(finished - perft_done, 3),
        "total_sec": round(finished - started, 3),
        "uci_smoke": "PASS" if smoke_ok else "FAIL",
        "uci_smoke_error": smoke_error,
        "perft_pass": "PASS" if passed else "FAIL",
        "correctness_pass": "PASS" if correctness_pass else "FAIL",
        "screen_pass": "PASS" if smoke_ok and passed and correctness_pass else "FAIL",
        "derive_selected_count": int(report.get("selected_count", spec.selected_feature_count)),
    }
    for depth in range(1, perft_depth + 1):
        row[f"perft_d{depth}"] = perft.get(depth, "")
    for probe_row in correctness_rows:
        probe_row.update(
            {
                "variant_name": spec.variant_name,
                "source_kind": spec.source_kind,
                "role": spec.role,
                "board_family": spec.board_family,
                "search_tier": spec.search_tier,
                "eval_tier": spec.eval_tier,
            }
        )
    return row, correctness_rows


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def spec_to_row(spec: VariantSpec) -> dict[str, object]:
    return {
        "variant_name": spec.variant_name,
        "source_kind": spec.source_kind,
        "role": spec.role,
        "config_path": str(spec.config_path),
        "selected_feature_count": spec.selected_feature_count,
        "selected_features": "|".join(spec.selected_features),
        "board_family": spec.board_family,
        "search_tier": spec.search_tier,
        "eval_tier": spec.eval_tier,
        "feature_count_bin": spec.feature_count_bin,
        "stratum": spec.stratum,
    }


def shortlist_rows(
    controls: list[VariantSpec],
    sample_specs: list[VariantSpec],
    perft_rows: list[dict[str, object]],
    shortlist_count: int,
) -> list[dict[str, object]]:
    if shortlist_count <= 0:
        return []

    perft_by_name = {str(row["variant_name"]): row for row in perft_rows}
    selected_names: set[str] = set()
    shortlist: list[dict[str, object]] = []

    for spec in controls:
        row = dict(spec_to_row(spec))
        if spec.variant_name in perft_by_name:
            row.update(perft_by_name[spec.variant_name])
        row["shortlist_reason"] = "fixed_control"
        shortlist.append(row)
        selected_names.add(spec.variant_name)

    candidates: list[dict[str, object]] = []
    for spec in sample_specs:
        row = perft_by_name.get(spec.variant_name)
        if row is None:
            continue
        if row.get("screen_pass") != "PASS":
            continue
        candidates.append(row)

    if not candidates or len(shortlist) >= shortlist_count:
        return shortlist[:shortlist_count]

    perft_values = sorted(float(row["perft_sec"]) for row in candidates)
    low_cut = perft_values[max(0, len(perft_values) // 3 - 1)]
    high_cut = perft_values[min(len(perft_values) - 1, (2 * len(perft_values)) // 3)]

    for row in candidates:
        sec = float(row["perft_sec"])
        if sec <= low_cut:
            row["_perft_band"] = "fast"
        elif sec >= high_cut:
            row["_perft_band"] = "slow"
        else:
            row["_perft_band"] = "mid"

    grouped: dict[tuple[str, str], list[dict[str, object]]] = {}
    for row in sorted(candidates, key=lambda r: (r["stratum"], float(r["perft_sec"]), str(r["variant_name"]))):
        grouped.setdefault((str(row["stratum"]), str(row["_perft_band"])), []).append(row)

    keys = list(grouped)
    round_index = 0
    while len(shortlist) < shortlist_count and keys:
        next_keys: list[tuple[str, str]] = []
        for key in keys:
            bucket = grouped[key]
            if not bucket:
                continue
            row = bucket.pop(0)
            if row["variant_name"] in selected_names:
                if bucket:
                    next_keys.append(key)
                continue
            row = dict(row)
            row["shortlist_reason"] = f"stratified_{key[1]}"
            shortlist.append(row)
            selected_names.add(str(row["variant_name"]))
            if bucket:
                next_keys.append(key)
            if len(shortlist) >= shortlist_count:
                break
        keys = next_keys
        round_index += 1
        if round_index > shortlist_count * 4:
            break

    return shortlist[:shortlist_count]


def svg_escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def write_perft_scatter_svg(rows: list[dict[str, object]], out_path: Path) -> None:
    usable = [row for row in rows if row.get("perft_sec") not in {"", None} and row.get("selected_feature_count") not in {"", None}]
    if not usable:
        return

    width = 920
    height = 540
    margin_left = 70
    margin_right = 30
    margin_top = 35
    margin_bottom = 60
    plot_w = width - margin_left - margin_right
    plot_h = height - margin_top - margin_bottom

    colors = {
        "Bitboards": "#1f77b4",
        "0x88": "#ff7f0e",
        "Mailbox": "#2ca02c",
        "10x12 Board": "#d62728",
        "unknown": "#7f7f7f",
    }

    xs = [int(row["selected_feature_count"]) for row in usable]
    ys = [float(row["perft_sec"]) for row in usable]
    x_min = min(xs)
    x_max = max(xs)
    y_min = min(ys)
    y_max = max(ys)
    if x_min == x_max:
        x_min -= 1
        x_max += 1
    if y_min == y_max:
        y_min = max(0.0, y_min - 1.0)
        y_max += 1.0

    def map_x(value: int) -> float:
        return margin_left + (value - x_min) / (x_max - x_min) * plot_w

    def map_y(value: float) -> float:
        return margin_top + plot_h - (value - y_min) / (y_max - y_min) * plot_h

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<style>text{font-family:Menlo,Consolas,monospace;font-size:12px;fill:#222} .axis{stroke:#333;stroke-width:1} .grid{stroke:#ddd;stroke-width:1} .label{font-size:11px}</style>',
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="#fffaf0"/>',
    ]

    for step in range(6):
        x_value = x_min + (x_max - x_min) * step / 5.0
        x_pos = map_x(x_value)
        lines.append(f'<line class="grid" x1="{x_pos:.1f}" y1="{margin_top}" x2="{x_pos:.1f}" y2="{margin_top + plot_h}"/>')
        lines.append(f'<text class="label" x="{x_pos:.1f}" y="{height - 22}" text-anchor="middle">{int(round(x_value))}</text>')

    for step in range(6):
        y_value = y_min + (y_max - y_min) * step / 5.0
        y_pos = map_y(y_value)
        lines.append(f'<line class="grid" x1="{margin_left}" y1="{y_pos:.1f}" x2="{margin_left + plot_w}" y2="{y_pos:.1f}"/>')
        lines.append(f'<text class="label" x="{margin_left - 10}" y="{y_pos + 4:.1f}" text-anchor="end">{y_value:.2f}</text>')

    lines.append(f'<line class="axis" x1="{margin_left}" y1="{margin_top + plot_h}" x2="{margin_left + plot_w}" y2="{margin_top + plot_h}"/>')
    lines.append(f'<line class="axis" x1="{margin_left}" y1="{margin_top}" x2="{margin_left}" y2="{margin_top + plot_h}"/>')
    lines.append(f'<text x="{width / 2:.1f}" y="{height - 8}" text-anchor="middle">Selected Feature Count</text>')
    lines.append(f'<text x="18" y="{height / 2:.1f}" text-anchor="middle" transform="rotate(-90 18 {height / 2:.1f})">Perft Time (s)</text>')
    lines.append(f'<text x="{width / 2:.1f}" y="20" text-anchor="middle">Perft Diversity Screen</text>')

    label_rows = [row for row in usable if row["source_kind"] == "control"][:6]
    for row in usable:
        cx = map_x(int(row["selected_feature_count"]))
        cy = map_y(float(row["perft_sec"]))
        color = colors.get(str(row["board_family"]), colors["unknown"])
        radius = 6 if row["source_kind"] == "control" else 4
        stroke = "#000" if row["source_kind"] == "control" else "none"
        lines.append(
            f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{radius}" fill="{color}" stroke="{stroke}" stroke-width="1">'
            f'<title>{svg_escape(str(row["variant_name"]))}: {svg_escape(str(row["stratum"]))}, perft={row["perft_sec"]}s</title>'
            f"</circle>"
        )

    for row in label_rows:
        cx = map_x(int(row["selected_feature_count"]))
        cy = map_y(float(row["perft_sec"]))
        lines.append(
            f'<text class="label" x="{cx + 8:.1f}" y="{cy - 8:.1f}">{svg_escape(str(row["variant_name"]))}</text>'
        )

    legend_x = width - 180
    legend_y = 50
    lines.append(f'<rect x="{legend_x - 12}" y="{legend_y - 22}" width="170" height="120" fill="#ffffff" stroke="#ddd"/>')
    lines.append(f'<text x="{legend_x}" y="{legend_y}" text-anchor="start">Board Family</text>')
    for idx, board in enumerate(("Bitboards", "0x88", "Mailbox", "10x12 Board")):
        y = legend_y + 20 + idx * 22
        lines.append(f'<circle cx="{legend_x}" cy="{y}" r="5" fill="{colors[board]}"/>')
        lines.append(f'<text x="{legend_x + 12}" y="{y + 4}">{svg_escape(board)}</text>')

    lines.append("</svg>")
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_board_bar_svg(rows: list[dict[str, object]], out_path: Path) -> None:
    grouped: dict[str, list[float]] = {}
    for row in rows:
        if row.get("perft_sec") in {"", None}:
            continue
        grouped.setdefault(str(row["board_family"]), []).append(float(row["perft_sec"]))
    if not grouped:
        return

    stats = [(board, sum(values) / len(values)) for board, values in grouped.items()]
    stats.sort(key=lambda item: item[0])
    max_value = max(value for _, value in stats)

    width = 760
    height = 420
    margin_left = 70
    margin_right = 30
    margin_top = 40
    margin_bottom = 70
    plot_w = width - margin_left - margin_right
    plot_h = height - margin_top - margin_bottom

    colors = {
        "Bitboards": "#1f77b4",
        "0x88": "#ff7f0e",
        "Mailbox": "#2ca02c",
        "10x12 Board": "#d62728",
        "unknown": "#7f7f7f",
    }

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<style>text{font-family:Menlo,Consolas,monospace;font-size:12px;fill:#222} .axis{stroke:#333;stroke-width:1} .grid{stroke:#ddd;stroke-width:1} .label{font-size:11px}</style>',
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="#f7fbff"/>',
        f'<text x="{width / 2:.1f}" y="22" text-anchor="middle">Mean Perft Time by Board Family</text>',
    ]

    for step in range(6):
        value = max_value * step / 5.0
        y = margin_top + plot_h - (value / max_value * plot_h if max_value > 0 else 0.0)
        lines.append(f'<line class="grid" x1="{margin_left}" y1="{y:.1f}" x2="{margin_left + plot_w}" y2="{y:.1f}"/>')
        lines.append(f'<text class="label" x="{margin_left - 8}" y="{y + 4:.1f}" text-anchor="end">{value:.2f}</text>')

    bar_w = plot_w / max(len(stats), 1) * 0.6
    gap = plot_w / max(len(stats), 1)
    for idx, (board, value) in enumerate(stats):
        x = margin_left + idx * gap + (gap - bar_w) / 2.0
        bar_h = 0.0 if max_value == 0 else value / max_value * plot_h
        y = margin_top + plot_h - bar_h
        lines.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{bar_h:.1f}" fill="{colors.get(board, colors["unknown"])}">'
            f'<title>{svg_escape(board)}: {value:.3f}s</title></rect>'
        )
        lines.append(f'<text class="label" x="{x + bar_w / 2:.1f}" y="{height - 35}" text-anchor="middle">{svg_escape(board)}</text>')
        lines.append(f'<text class="label" x="{x + bar_w / 2:.1f}" y="{y - 6:.1f}" text-anchor="middle">{value:.2f}</text>')

    lines.append(f'<line class="axis" x1="{margin_left}" y1="{margin_top + plot_h}" x2="{margin_left + plot_w}" y2="{margin_top + plot_h}"/>')
    lines.append(f'<line class="axis" x1="{margin_left}" y1="{margin_top}" x2="{margin_left}" y2="{margin_top + plot_h}"/>')
    lines.append(f'<text x="{width / 2:.1f}" y="{height - 8}" text-anchor="middle">Board Family</text>')
    lines.append(f'<text x="18" y="{height / 2:.1f}" text-anchor="middle" transform="rotate(-90 18 {height / 2:.1f})">Mean Perft Time (s)</text>')
    lines.append("</svg>")
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_elo_command(config_paths: list[Path], out_dir: Path, depth: int, rounds: int, games: int) -> str:
    parts = ["PYTHONPATH=src", "python3", "scripts/proper_elo_tournament.py"]
    for config_path in config_paths:
        parts.extend(["--variant-config", str(config_path)])
    parts.extend(
        [
            "--depth",
            str(depth),
            "--rounds",
            str(rounds),
            "--games-per-encounter",
            str(games),
            "--out-dir",
            str(out_dir),
        ]
    )
    return " ".join(parts)


def build_diversity_tournament_command(
    config_paths: list[Path],
    out_dir: Path,
    depth: int,
    rounds: int,
    games: int,
    stockfish_profiles: tuple[str, ...] = (),
) -> str:
    parts = ["PYTHONPATH=src", "python3", "scripts/variant_diversity_tournament.py"]
    for config_path in config_paths:
        parts.extend(["--variant-config", str(config_path)])
    for profile in stockfish_profiles:
        parts.extend(["--stockfish-profile", profile])
    parts.extend(
        [
            "--depth",
            str(depth),
            "--rounds",
            str(rounds),
            "--games-per-encounter",
            str(games),
            "--out-dir",
            str(out_dir),
        ]
    )
    return " ".join(parts)


def write_report(
    out_path: Path,
    controls: list[VariantSpec],
    samples: list[VariantSpec],
    ablations: list[VariantSpec],
    perft_rows: list[dict[str, object]],
    correctness_rows: list[dict[str, object]],
    shortlist: list[dict[str, object]],
    args: argparse.Namespace,
) -> None:
    stratum_counts: dict[str, int] = {}
    board_counts: dict[str, int] = {}
    search_counts: dict[str, int] = {}
    eval_counts: dict[str, int] = {}
    for spec in samples:
        stratum_counts[spec.stratum] = stratum_counts.get(spec.stratum, 0) + 1
        board_counts[spec.board_family] = board_counts.get(spec.board_family, 0) + 1
        search_counts[spec.search_tier] = search_counts.get(spec.search_tier, 0) + 1
        eval_counts[spec.eval_tier] = eval_counts.get(spec.eval_tier, 0) + 1

    lines = [
        "# Stratified Variant Experiment Plan",
        "",
        "## Goal",
        "",
        "- Draw a diverse legal sample of random variants.",
        "- Keep fixed controls for the presumed worst, canonical random, and best presets.",
        "- Screen everything for legality/perft first.",
        "- Then reuse the existing anchored Elo harness on the screened pool or a selected shortlist.",
        "",
        "## Fixed Controls",
        "",
    ]
    for spec in controls:
        lines.append(f"- `{spec.role}`: `{spec.variant_name}` -> `{spec.config_path}`")

    lines.extend(
        [
            "",
            "## Random Sample",
            "",
            f"- requested random variants: `{args.count}`",
            f"- selected random variants: `{len(samples)}`",
            f"- observed strata: `{len(stratum_counts)}`",
            "",
            "### Coverage by Board",
            "",
        ]
    )
    for board, value in sorted(board_counts.items()):
        lines.append(f"- `{board}`: `{value}`")

    lines.extend(["", "### Coverage by Search Tier", ""])
    for tier, value in sorted(search_counts.items()):
        lines.append(f"- `{tier}`: `{value}`")

    lines.extend(["", "### Coverage by Eval Tier", ""])
    for tier, value in sorted(eval_counts.items()):
        lines.append(f"- `{tier}`: `{value}`")

    if perft_rows:
        passed = sum(1 for row in perft_rows if row["perft_pass"] == "PASS")
        correctness_passed = sum(1 for row in perft_rows if row.get("correctness_pass") == "PASS")
        screen_passed = sum(1 for row in perft_rows if row.get("screen_pass") == "PASS")
        lines.extend(
            [
                "",
                "## Correctness and Perft Screen",
                "",
                f"- variants screened: `{len(perft_rows)}`",
                f"- passed perft: `{passed}/{len(perft_rows)}`",
                f"- passed correctness probes: `{correctness_passed}/{len(perft_rows)}`",
                f"- passed full screen: `{screen_passed}/{len(perft_rows)}`",
                f"- depth used: `{args.perft_depth}`",
                f"- probe depth used: `{args.correctness_depth}`",
                f"- scatter plot: `{args.out_dir}/plots/perft_vs_feature_count.svg`",
                f"- board bar plot: `{args.out_dir}/plots/perft_by_board.svg`",
            ]
        )

        probe_failures = [row for row in correctness_rows if row.get("legal") != "PASS"]
        if probe_failures:
            lines.extend(["", "### Probe Failures", ""])
            for row in probe_failures[:12]:
                lines.append(
                    f"- `{row['variant_name']}` / `{row['probe']}`: `{row['error']}` (`{row['bestmove']}`)"
                )

    lines.extend(
        [
            "",
            "## Elo Reuse Plan",
            "",
            "- Quick screen: run anchors on the controls plus the full stratified pool with a shallow budget to bracket obvious weak/strong regions.",
            "- Full estimation: run `scripts/proper_elo_tournament.py` on a shortlist chosen for both strength and diversity, not only on the top perft performers.",
            "",
            "Suggested quick anchored tournament command:",
            "",
            "```bash",
            build_elo_command(
                [spec.config_path for spec in controls + samples],
                Path(args.out_dir) / "elo_screen",
                depth=3,
                rounds=1,
                games=2,
            ),
            "```",
            "",
            "Suggested full anchored tournament command on the fixed controls only:",
            "",
            "```bash",
            build_elo_command(
                [spec.config_path for spec in controls],
                Path(args.out_dir) / "elo_controls",
                depth=4,
                rounds=2,
                games=2,
            ),
            "```",
            "",
            "## Controlled Ablations",
            "",
            "- Feature-family ablations reuse existing committed configs rather than inventing new ladders.",
            "- Commonality is separated by comparing archived before/after outputs on the same feature profile.",
            "",
            "### Families",
            "",
        ]
    )
    by_role: dict[str, list[str]] = {}
    for spec in ablations:
        by_role.setdefault(spec.role, []).append(f"`{spec.variant_name}`")
    for role, names in sorted(by_role.items()):
        lines.append(f"- `{role}`: {', '.join(names)}")

    lines.extend(
        [
            "",
            "### Commonality Comparison Inputs",
            "",
            "- `outputs/commonality_opt_baseline_before.json`",
            "- `outputs/commonality_opt_round3_comparison.csv`",
            "- `outputs/sf2500_best_variant_st2_4g/summary.json`",
            "- `outputs/sf2500_after_commonality_opt_clean/summary.json`",
            "",
            "## Plot Set",
            "",
            "- `perft_vs_feature_count.svg`: fast diversity view for the screened pool.",
            "- `perft_by_board.svg`: board-family throughput differences.",
            "- After Elo: plot `anchored_elo` vs `perft_sec`, color by `board_family`, shape by `search_tier`, and label the fixed controls.",
            "- For the ablations: use ladder plots for search, board, evaluation, and commonality before/after.",
        ]
    )
    if shortlist:
        lines.extend(
            [
                "",
                "## N'=20 Game Diversity Stage",
                "",
                f"- shortlist target: `{args.shortlist_count}`",
                f"- shortlist size prepared: `{len(shortlist)}`",
                "- fixed controls remain in the shortlist",
                "- remaining slots are filled from screen-passing random variants using stratified structural coverage plus fast/mid/slow perft bands",
                "",
                "Suggested internal diversity tournament:",
                "",
                "```bash",
                build_diversity_tournament_command(
                    [Path(str(row["config_path"])) for row in shortlist],
                    Path(args.out_dir) / "game_diversity_round_robin",
                    depth=3,
                    rounds=1,
                    games=2,
                ),
                "```",
                "",
                "Suggested anchor-flavored diversity tournament:",
                "",
                "```bash",
                build_diversity_tournament_command(
                    [Path(str(row["config_path"])) for row in shortlist],
                    Path(args.out_dir) / "game_diversity_with_anchors",
                    depth=3,
                    rounds=1,
                    games=2,
                    stockfish_profiles=("sf1320:1:1320", "sf1800:6:1800"),
                ),
                "```",
            ]
        )
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prepare a stratified random-variant experiment on top of the existing repo scripts")
    parser.add_argument("--feature-model", default="outputs/feature_model.json")
    parser.add_argument("--count", type=int, default=100)
    parser.add_argument("--seed", type=int, default=20260409)
    parser.add_argument("--optional-prob", type=float, default=0.35)
    parser.add_argument("--max-attempts", type=int, default=3000)
    parser.add_argument("--pool-multiplier", type=int, default=8)
    parser.add_argument("--out-dir", default="outputs/stratified_variant_experiment")
    parser.add_argument("--build-perft", action="store_true", help="Also derive/build and run start-position perft on controls + sample")
    parser.add_argument("--perft-depth", type=int, default=5, choices=(1, 2, 3, 4, 5, 6))
    parser.add_argument("--correctness-depth", type=int, default=2)
    parser.add_argument("--shortlist-count", type=int, default=20)
    parser.add_argument("--makefile", default="c_engine_pl/Makefile")
    parser.add_argument("--engine-bin", default="c_engine_pl/build/engine_pl")
    parser.add_argument("--header-out", default="c_engine_pl/include/generated/variant_config.h")
    parser.add_argument("--manifest-out", default="c_engine_pl/include/generated/variant_manifest.json")
    return parser


def main() -> int:
    args = build_parser().parse_args()

    if args.count <= 0:
        raise ValueError("--count must be > 0")

    workspace = Path.cwd()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    feature_model = Path(args.feature_model)
    model = load_model_index(feature_model)
    rng = random.Random(args.seed)

    controls = collect_controls(model, workspace)
    ablations = collect_ablations(model, workspace)
    excluded_ids = {spec.selected_ids for spec in controls}

    pool_specs, sample_specs = sample_stratified_variants(
        model=model,
        rng=rng,
        out_dir=out_dir,
        count=args.count,
        optional_prob=args.optional_prob,
        max_attempts=args.max_attempts,
        pool_multiplier=args.pool_multiplier,
        excluded_ids=excluded_ids,
    )

    manifest_fields = [
        "variant_name",
        "source_kind",
        "role",
        "config_path",
        "selected_feature_count",
        "selected_features",
        "board_family",
        "search_tier",
        "eval_tier",
        "feature_count_bin",
        "stratum",
    ]
    write_csv(out_dir / "pool_manifest.csv", [spec_to_row(spec) for spec in pool_specs], manifest_fields)
    write_csv(out_dir / "sample_manifest.csv", [spec_to_row(spec) for spec in sample_specs], manifest_fields)
    write_csv(out_dir / "controls_manifest.csv", [spec_to_row(spec) for spec in controls], manifest_fields)
    write_csv(out_dir / "ablation_manifest.csv", [spec_to_row(spec) for spec in ablations], manifest_fields)

    perft_rows: list[dict[str, object]] = []
    correctness_rows: list[dict[str, object]] = []
    if args.build_perft:
        out_bin_dir = out_dir / "variant_bins"
        for spec in controls + sample_specs:
            row, probe_rows = build_and_perft_variant(
                spec=spec,
                feature_model=feature_model,
                makefile=Path(args.makefile),
                engine_bin=Path(args.engine_bin),
                header_out=Path(args.header_out),
                manifest_out=Path(args.manifest_out),
                out_bin_dir=out_bin_dir,
                perft_depth=args.perft_depth,
                correctness_depth=args.correctness_depth,
            )
            perft_rows.append(row)
            correctness_rows.extend(probe_rows)
        perft_fields = [
            "variant_name",
            "source_kind",
            "role",
            "config_path",
            "binary_path",
            "selected_feature_count",
            "selected_features",
            "board_family",
            "search_tier",
            "eval_tier",
            "feature_count_bin",
            "stratum",
            "derive_build_sec",
            "perft_sec",
            "correctness_sec",
            "total_sec",
            "uci_smoke",
            "uci_smoke_error",
            "perft_pass",
            "correctness_pass",
            "screen_pass",
            "derive_selected_count",
        ] + [f"perft_d{depth}" for depth in range(1, args.perft_depth + 1)]
        write_csv(out_dir / "perft_screen.csv", perft_rows, perft_fields)
        probe_fields = [
            "variant_name",
            "source_kind",
            "role",
            "board_family",
            "search_tier",
            "eval_tier",
            "probe",
            "position",
            "bestmove",
            "legal",
            "error",
        ]
        write_csv(out_dir / "correctness_probes.csv", correctness_rows, probe_fields)
        plots_dir = out_dir / "plots"
        plots_dir.mkdir(parents=True, exist_ok=True)
        write_perft_scatter_svg(perft_rows, plots_dir / "perft_vs_feature_count.svg")
        write_board_bar_svg(perft_rows, plots_dir / "perft_by_board.svg")

    shortlist = shortlist_rows(controls, sample_specs, perft_rows, shortlist_count=args.shortlist_count) if perft_rows else []
    if shortlist:
        shortlist_fields = [
            "variant_name",
            "source_kind",
            "role",
            "config_path",
            "selected_feature_count",
            "selected_features",
            "board_family",
            "search_tier",
            "eval_tier",
            "feature_count_bin",
            "stratum",
            "perft_sec",
            "_perft_band",
            "screen_pass",
            "shortlist_reason",
        ]
        write_csv(out_dir / "game_shortlist.csv", shortlist, shortlist_fields)

    write_report(out_dir / "report.md", controls, sample_specs, ablations, perft_rows, correctness_rows, shortlist, args)

    summary = {
        "controls": [spec_to_row(spec) for spec in controls],
        "samples": [spec_to_row(spec) for spec in sample_specs],
        "ablations": [spec_to_row(spec) for spec in ablations],
        "perft_screened": bool(args.build_perft),
        "perft_rows": perft_rows,
        "correctness_rows": correctness_rows,
        "game_shortlist": shortlist,
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
