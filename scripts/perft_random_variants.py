#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import random
import re
import subprocess
import time
from pathlib import Path

from cpw_variability.pl_codegen import (
    derive_variant,
    load_model_index,
    run_build,
    validate_selection,
)

PERFT_RE = re.compile(r"^info string perft depth (\d+) nodes (\d+)$")
STARTPOS_EXPECTED = {1: 20, 2: 400, 3: 8902, 4: 197281, 5: 4865609, 6: 119060324}
REQUIRED_GROUPS = ("board_representation", "search", "evaluation", "move_generation", "protocol")
MANDATORY_OPTION_NAMES = (
    "UCI",
    "Castling",
    "En Passant",
    "Threefold Repetition",
    "Fifty-Move Rule",
)
BOARD_PRIMARY_NAMES = ("Bitboards", "0x88", "Mailbox", "10x12 Board")


def run_engine(engine_bin: Path, commands: list[str]) -> list[str]:
    transcript = "\n".join(commands) + "\n"
    completed = subprocess.run(
        [str(engine_bin)],
        input=transcript,
        capture_output=True,
        text=True,
        check=True,
    )
    normalized = completed.stdout.replace("\\n", "\n")
    return [line.strip() for line in normalized.splitlines() if line.strip()]


def parse_perft(lines: list[str]) -> dict[int, int]:
    result: dict[int, int] = {}
    for line in lines:
        match = PERFT_RE.match(line)
        if match is None:
            continue
        depth = int(match.group(1))
        nodes = int(match.group(2))
        result[depth] = nodes
    return result


def derive_forbidden_option_ids(model, excluded_option_names: set[str]) -> set[str]:
    forbidden = {
        option.id
        for option in model.options_by_id.values()
        if option.name in excluded_option_names
    }

    changed = True
    while changed:
        changed = False
        for rule in model.constraints:
            if rule.kind != "requires":
                continue
            if rule.right_feature_id in forbidden and rule.left_feature_id in model.options_by_id and rule.left_feature_id not in forbidden:
                forbidden.add(rule.left_feature_id)
                changed = True
    return forbidden


def choose_random_valid_selection(
    model,
    rng: random.Random,
    optional_prob: float,
    max_attempts: int,
    mandatory_option_names: tuple[str, ...],
    forbidden_option_ids: set[str],
    enforce_tournament_legality: bool,
) -> set[str]:
    options = list(model.options_by_id.values())
    options_by_name = {option.name: option for option in options}

    required_group_options: dict[str, list] = {}
    for group_id in REQUIRED_GROUPS:
        required_group_options[group_id] = [opt for opt in options if opt.parent_id == group_id]

    board_primary_ids = {
        options_by_name[name].id
        for name in BOARD_PRIMARY_NAMES
        if name in options_by_name
    }

    for _ in range(max_attempts):
        selected: set[str] = set()

        for name in mandatory_option_names:
            opt = options_by_name.get(name)
            if opt is not None and opt.id not in forbidden_option_ids:
                selected.add(opt.id)

        for group_id in REQUIRED_GROUPS:
            group_opts = [opt for opt in required_group_options[group_id] if opt.id not in forbidden_option_ids]
            if not group_opts:
                continue
            selected.add(rng.choice(group_opts).id)

        for option in options:
            if option.id in selected:
                continue
            if option.id in forbidden_option_ids:
                continue
            if option.id in board_primary_ids:
                continue
            if rng.random() < optional_prob:
                selected.add(option.id)

        errors = validate_selection(model, selected, enforce_tournament_legality=enforce_tournament_legality)
        if not errors:
            return selected

    raise RuntimeError(f"Failed to generate a valid selection after {max_attempts} attempts")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate random valid variants and benchmark perft")
    parser.add_argument("--feature-model", default="outputs/feature_model.json")
    parser.add_argument("--count", type=int, default=5)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--optional-prob", type=float, default=0.35)
    parser.add_argument("--max-attempts", type=int, default=2000)
    parser.add_argument("--max-depth", type=int, default=4, choices=(1, 2, 3, 4, 5, 6))
    parser.add_argument("--exclude-option", action="append", default=[], help="Feature name to exclude (can be repeated)")
    parser.add_argument("--require-option", action="append", default=[], help="Feature name to require (can be repeated)")
    parser.add_argument("--without-castling", action="store_true", help="Shortcut for --exclude-option Castling")
    parser.add_argument(
        "--allow-non-tournament-legality",
        action="store_true",
        help="Disable mandatory tournament-legality option validation",
    )
    parser.add_argument("--makefile", default="c_engine_pl/Makefile")
    parser.add_argument("--engine-bin", default="c_engine_pl/build/engine_pl")
    parser.add_argument("--header-out", default="c_engine_pl/include/generated/variant_config.h")
    parser.add_argument("--manifest-out", default="c_engine_pl/include/generated/variant_manifest.json")
    parser.add_argument("--out-csv", default="outputs/perft_random_variants.csv")
    parser.add_argument("--out-json", default="outputs/perft_random_variants.json")
    parser.add_argument("--out-config-dir", default="outputs/random_variant_configs")
    return parser


def main() -> int:
    args = build_parser().parse_args()

    if args.count <= 0:
        raise ValueError("--count must be > 0")

    model_path = Path(args.feature_model)
    model = load_model_index(model_path)
    rng = random.Random(args.seed)
    excluded_option_names = set(args.exclude_option)
    if args.without_castling:
        excluded_option_names.add("Castling")

    mandatory_option_names = tuple(
        sorted(set([name for name in MANDATORY_OPTION_NAMES if name not in excluded_option_names] + args.require_option))
    )
    enforce_tournament_legality = not args.allow_non_tournament_legality
    forbidden_option_ids = derive_forbidden_option_ids(model, excluded_option_names)

    out_config_dir = Path(args.out_config_dir)
    out_config_dir.mkdir(parents=True, exist_ok=True)

    csv_path = Path(args.out_csv)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    json_path = Path(args.out_json)
    json_path.parent.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, object]] = []
    seen_configs: set[tuple[str, ...]] = set()

    while len(rows) < args.count:
        selected_ids = choose_random_valid_selection(
            model,
            rng,
            args.optional_prob,
            args.max_attempts,
            mandatory_option_names=mandatory_option_names,
            forbidden_option_ids=forbidden_option_ids,
            enforce_tournament_legality=enforce_tournament_legality,
        )
        key = tuple(sorted(selected_ids))
        if key in seen_configs:
            continue
        seen_configs.add(key)

        idx = len(rows) + 1
        variant_name = f"random_variant_{idx:02d}"
        selected_options = [model.options_by_id[option_id] for option_id in key]
        selected_names = [option.name for option in sorted(selected_options, key=lambda item: item.name.lower())]

        config_path = out_config_dir / f"{variant_name}.json"
        config_payload = {
            "name": variant_name,
            "selected_options": selected_names,
        }
        config_path.write_text(json.dumps(config_payload, indent=2), encoding="utf-8")

        t0 = time.perf_counter()
        report = derive_variant(
            feature_model_path=model_path,
            config_path=config_path,
            header_out=Path(args.header_out),
            manifest_out=Path(args.manifest_out),
            enforce_tournament_legality=enforce_tournament_legality,
        )
        run_build(Path(args.makefile))
        t1 = time.perf_counter()

        commands = ["uci", "isready", "position startpos"]
        for depth in range(1, args.max_depth + 1):
            commands.append(f"perft {depth}")
        commands.append("quit")
        lines = run_engine(Path(args.engine_bin), commands)
        t2 = time.perf_counter()

        got = parse_perft(lines)
        pass_all = True
        for depth in range(1, args.max_depth + 1):
            expected = STARTPOS_EXPECTED[depth]
            if got.get(depth) != expected:
                pass_all = False
                break

        row = {
            "variant": variant_name,
            "selected_feature_count": report["selected_count"],
            "selected_features": "|".join(report["selected_features"]),
            "perft_d1": got.get(1, ""),
            "perft_d2": got.get(2, ""),
            "perft_d3": got.get(3, ""),
            "perft_d4": got.get(4, ""),
            "perft_d5": got.get(5, ""),
            "perft_d6": got.get(6, ""),
            "pass": "PASS" if pass_all else "FAIL",
            "derive_build_sec": round(t1 - t0, 3),
            "perft_sec": round(t2 - t1, 3),
            "total_sec": round(t2 - t0, 3),
            "config_path": str(config_path),
        }
        rows.append(row)
        print(json.dumps({"progress": f"{len(rows)}/{args.count}", "variant": variant_name, "pass": row["pass"]}))

    fieldnames = [
        "variant",
        "selected_feature_count",
        "selected_features",
        "perft_d1",
        "perft_d2",
        "perft_d3",
        "perft_d4",
        "perft_d5",
        "perft_d6",
        "pass",
        "derive_build_sec",
        "perft_sec",
        "total_sec",
        "config_path",
    ]

    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    payload = {
        "seed": args.seed,
        "count": args.count,
        "max_depth": args.max_depth,
        "excluded_options": sorted(excluded_option_names),
        "forbidden_option_ids": sorted(forbidden_option_ids),
        "enforce_tournament_legality": enforce_tournament_legality,
        "rows": rows,
        "expected": {depth: STARTPOS_EXPECTED[depth] for depth in range(1, args.max_depth + 1)},
    }
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print(json.dumps({"csv": str(csv_path), "json": str(json_path), "rows": len(rows)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
