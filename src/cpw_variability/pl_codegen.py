from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .models import ConstraintRule, FeatureNode


@dataclass
class ModelIndex:
    features_by_id: dict[str, FeatureNode]
    groups_by_id: dict[str, FeatureNode]
    options_by_id: dict[str, FeatureNode]
    options_by_name: dict[str, FeatureNode]
    options_by_flag: dict[str, FeatureNode]
    constraints: list[ConstraintRule]


def _normalize_token(token: str) -> str:
    return " ".join(token.strip().lower().split())


def load_model_index(feature_model_path: Path) -> ModelIndex:
    payload = json.loads(feature_model_path.read_text(encoding="utf-8"))
    features = [FeatureNode(**item) for item in payload.get("features", [])]
    constraints = [ConstraintRule(**item) for item in payload.get("constraints", [])]

    features_by_id = {feature.id: feature for feature in features}
    groups_by_id = {feature.id: feature for feature in features if feature.variation_role == "group"}
    options_by_id = {
        feature.id: feature
        for feature in features
        if feature.variation_role == "option" and feature.configurable
    }

    options_by_name: dict[str, FeatureNode] = {}
    for option in options_by_id.values():
        options_by_name[_normalize_token(option.name)] = option
        for alias in option.aliases:
            options_by_name[_normalize_token(alias)] = option

    options_by_flag = {option.compile_flag: option for option in options_by_id.values() if option.compile_flag}

    return ModelIndex(
        features_by_id=features_by_id,
        groups_by_id=groups_by_id,
        options_by_id=options_by_id,
        options_by_name=options_by_name,
        options_by_flag=options_by_flag,
        constraints=constraints,
    )


def resolve_selected_option_ids(model: ModelIndex, selected_tokens: Iterable[str]) -> tuple[set[str], list[str]]:
    selected_ids: set[str] = set()
    errors: list[str] = []

    for token in selected_tokens:
        raw = token.strip()
        if not raw:
            continue

        if raw in model.options_by_id:
            selected_ids.add(raw)
            continue

        if raw in model.options_by_flag:
            selected_ids.add(model.options_by_flag[raw].id)
            continue

        normalized = _normalize_token(raw)
        if normalized in model.options_by_name:
            selected_ids.add(model.options_by_name[normalized].id)
            continue

        errors.append(f"Unknown option token: '{raw}'")

    return selected_ids, errors


def _validate_required_variation_points(
    model: ModelIndex,
    selected_ids: set[str],
    enforce_tournament_legality: bool = True,
) -> list[str]:
    errors: list[str] = []

    required_groups = ["board_representation", "search", "evaluation", "move_generation", "protocol"]
    for group_id in required_groups:
        if group_id not in model.groups_by_id:
            continue
        in_group = [option for option in model.options_by_id.values() if option.parent_id == group_id]
        if not in_group:
            continue
        if not any(option.id in selected_ids for option in in_group):
            errors.append(f"Missing required variation point selection for group '{model.groups_by_id[group_id].name}'")

    # Mandatory options for this product-line implementation profile.
    required_options = [
        ("UCI", "Feature 'UCI' must be selected for this C engine product line"),
        ("Move Generation", "Feature 'Move Generation' is mandatory for executable chess engine variants"),
    ]
    if enforce_tournament_legality:
        required_options.extend(
            [
                ("Castling", "Feature 'Castling' must be selected for tournament legality"),
                ("En Passant", "Feature 'En Passant' must be selected for tournament legality"),
                ("Threefold Repetition", "Feature 'Threefold Repetition' must be selected for tournament legality"),
                ("Fifty-Move Rule", "Feature 'Fifty-Move Rule' must be selected for tournament legality"),
            ]
        )
    for option_name, message in required_options:
        option = next((candidate for candidate in model.options_by_id.values() if candidate.name == option_name), None)
        if option is not None and option.id not in selected_ids:
            errors.append(message)

    # Primary board representation: exactly one of these core alternatives.
    board_alternatives = [
        "Bitboards",
        "0x88",
        "Mailbox",
        "10x12 Board",
    ]
    board_ids = {
        option.id
        for option in model.options_by_id.values()
        if option.name in board_alternatives
    }
    selected_board = board_ids & selected_ids
    if len(selected_board) != 1:
        errors.append("Select exactly one primary board representation: Bitboards | 0x88 | Mailbox | 10x12 Board")

    return errors


def _validate_constraints(model: ModelIndex, selected_ids: set[str]) -> list[str]:
    errors: list[str] = []

    for rule in model.constraints:
        left_selected = rule.left_feature_id in selected_ids
        right_selected = rule.right_feature_id in selected_ids

        if rule.kind == "requires" and left_selected and not right_selected:
            left_name = model.features_by_id[rule.left_feature_id].name if rule.left_feature_id in model.features_by_id else rule.left_feature_id
            right_name = model.features_by_id[rule.right_feature_id].name if rule.right_feature_id in model.features_by_id else rule.right_feature_id
            errors.append(f"Constraint violation: '{left_name}' requires '{right_name}'")

        if rule.kind == "excludes" and left_selected and right_selected:
            left_name = model.features_by_id[rule.left_feature_id].name if rule.left_feature_id in model.features_by_id else rule.left_feature_id
            right_name = model.features_by_id[rule.right_feature_id].name if rule.right_feature_id in model.features_by_id else rule.right_feature_id
            errors.append(f"Constraint violation: '{left_name}' excludes '{right_name}'")

    return errors


def validate_selection(
    model: ModelIndex,
    selected_ids: set[str],
    enforce_tournament_legality: bool = True,
) -> list[str]:
    errors: list[str] = []
    errors.extend(_validate_required_variation_points(model, selected_ids, enforce_tournament_legality=enforce_tournament_legality))
    errors.extend(_validate_constraints(model, selected_ids))
    return errors


def _header_preamble(name: str) -> str:
    guard = "C_ENGINE_PL_VARIANT_CONFIG_H"
    return (
        f"#ifndef {guard}\n"
        f"#define {guard}\n\n"
        f"#define PL_VARIANT_NAME \"{name}\"\n\n"
    )


def _header_footer() -> str:
    return "\n#endif\n"


def generate_variant_header(
    model: ModelIndex,
    selected_ids: set[str],
    variant_name: str,
    out_path: Path,
) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)

    options = list(model.options_by_id.values())
    options.sort(key=lambda option: option.compile_flag)

    lines: list[str] = [_header_preamble(variant_name)]
    lines.append("/* Compile-time feature toggles derived from feature_model.json */")

    for option in options:
        if not option.compile_flag:
            continue
        value = 1 if option.id in selected_ids else 0
        lines.append(f"#define {option.compile_flag} {value}")

    selected_options = [model.options_by_id[option_id] for option_id in sorted(selected_ids)]
    lines.append("")
    lines.append(f"#define PL_SELECTED_OPTION_COUNT {len(selected_options)}")

    if selected_options:
        lines.append("static const char *PL_SELECTED_OPTION_NAMES[PL_SELECTED_OPTION_COUNT] = {")
        for option in sorted(selected_options, key=lambda item: item.name.lower()):
            lines.append(f"    \"{option.name}\",")
        lines.append("};")
    else:
        lines.append("static const char *PL_SELECTED_OPTION_NAMES[1] = { \"(none)\" };")

    lines.append(_header_footer())
    out_path.write_text("\n".join(lines), encoding="utf-8")


def write_variant_manifest(
    model: ModelIndex,
    selected_ids: set[str],
    variant_name: str,
    out_path: Path,
) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    selected_options = [model.options_by_id[option_id] for option_id in sorted(selected_ids)]
    payload = {
        "variant": variant_name,
        "selected_feature_ids": sorted(selected_ids),
        "selected_feature_names": [option.name for option in sorted(selected_options, key=lambda item: item.name.lower())],
        "selected_compile_flags": [
            option.compile_flag
            for option in sorted(selected_options, key=lambda item: item.compile_flag)
            if option.compile_flag
        ],
    }
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def derive_variant(
    feature_model_path: Path,
    config_path: Path,
    header_out: Path,
    manifest_out: Path,
    enforce_tournament_legality: bool = True,
) -> dict:
    model = load_model_index(feature_model_path)
    config = json.loads(config_path.read_text(encoding="utf-8"))

    variant_name = config.get("name") or config_path.stem
    tokens = config.get("selected_options", [])
    if not isinstance(tokens, list):
        raise ValueError("Config field 'selected_options' must be a list")

    selected_ids, resolve_errors = resolve_selected_option_ids(model, [str(token) for token in tokens])
    validation_errors = validate_selection(
        model,
        selected_ids,
        enforce_tournament_legality=enforce_tournament_legality,
    )

    errors = resolve_errors + validation_errors
    if errors:
        raise ValueError("\n".join(errors))

    generate_variant_header(model, selected_ids, variant_name, header_out)
    write_variant_manifest(model, selected_ids, variant_name, manifest_out)

    selected_options = [model.options_by_id[option_id] for option_id in sorted(selected_ids)]
    return {
        "variant": variant_name,
        "selected_count": len(selected_options),
        "selected_features": [option.name for option in sorted(selected_options, key=lambda item: item.name.lower())],
        "header": str(header_out),
        "manifest": str(manifest_out),
    }


def run_build(makefile: Path) -> None:
    subprocess.run(["make", "-f", str(makefile), "clean", "all"], check=True)


def run_smoke(engine_bin: Path) -> str:
    commands = "uci\nisready\nposition startpos moves e2e4 e7e5\ngo movetime 20\nquit\n"
    completed = subprocess.run(
        [str(engine_bin)],
        input=commands,
        capture_output=True,
        text=True,
        check=True,
    )

    stdout = completed.stdout
    if "uciok" not in stdout or "readyok" not in stdout or "bestmove" not in stdout:
        raise ValueError("Smoke test failed: missing expected UCI tokens in engine output")
    return stdout
