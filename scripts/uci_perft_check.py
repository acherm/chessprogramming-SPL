#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

from cpw_variability.pl_codegen import derive_variant, run_build

PERFT_RE = re.compile(r"^info string perft depth (\d+) nodes (\d+)$")
STARTPOS_EXPECTED = {
    1: 20,
    2: 400,
    3: 8902,
    4: 197281,
    5: 4865609,
}


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
    results: dict[int, int] = {}
    for line in lines:
        match = PERFT_RE.match(line)
        if not match:
            continue
        depth = int(match.group(1))
        nodes = int(match.group(2))
        results[depth] = nodes
    return results


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Derive a variant and validate perft counts from start position")
    parser.add_argument("--feature-model", default="outputs/feature_model.json")
    parser.add_argument("--config", default="c_engine_pl/variants/bitboards_alpha.json")
    parser.add_argument("--header-out", default="c_engine_pl/include/generated/variant_config.h")
    parser.add_argument("--manifest-out", default="c_engine_pl/include/generated/variant_manifest.json")
    parser.add_argument("--makefile", default="c_engine_pl/Makefile")
    parser.add_argument("--engine-bin", default="c_engine_pl/build/engine_pl")
    parser.add_argument("--max-depth", type=int, default=4, choices=(1, 2, 3, 4, 5))
    parser.add_argument("--skip-derive", action="store_true")
    parser.add_argument("--skip-build", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()

    if not args.skip_derive:
        report = derive_variant(
            feature_model_path=Path(args.feature_model),
            config_path=Path(args.config),
            header_out=Path(args.header_out),
            manifest_out=Path(args.manifest_out),
        )
        print(json.dumps({"derive": report}, indent=2))

    if not args.skip_build:
        run_build(Path(args.makefile))
        print(json.dumps({"build": "ok"}, indent=2))

    commands = ["uci", "isready", "position startpos"]
    for depth in range(1, args.max_depth + 1):
        commands.append(f"perft {depth}")
    commands.append("quit")

    lines = run_engine(Path(args.engine_bin), commands)
    found = parse_perft(lines)

    expected = {depth: STARTPOS_EXPECTED[depth] for depth in range(1, args.max_depth + 1)}
    mismatches = []
    for depth, expected_nodes in expected.items():
        got = found.get(depth)
        if got != expected_nodes:
            mismatches.append(
                {
                    "depth": depth,
                    "expected": expected_nodes,
                    "got": got,
                }
            )

    print(
        json.dumps(
            {
                "perft": {
                    "position": "startpos",
                    "expected": expected,
                    "got": found,
                    "mismatches": mismatches,
                }
            },
            indent=2,
        )
    )

    return 0 if not mismatches else 1


if __name__ == "__main__":
    raise SystemExit(main())
