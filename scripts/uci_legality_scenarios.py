#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from cpw_variability.pl_codegen import derive_variant, run_build

MOVE_RE = re.compile(r"^info string legalmove ([a-h][1-8][a-h][1-8][qrbn]?)$")
SCORE_RE = re.compile(r"^info depth (-?\d+) score cp (-?\d+)\b")


@dataclass
class ScenarioResult:
    name: str
    passed: bool
    details: str


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


def parse_legalmoves(lines: list[str]) -> list[str]:
    moves: list[str] = []
    for line in lines:
        match = MOVE_RE.match(line.strip())
        if match:
            moves.append(match.group(1))
    return moves


def parse_last_score(lines: list[str]) -> tuple[int, int]:
    for line in reversed(lines):
        match = SCORE_RE.match(line.strip())
        if match:
            return int(match.group(1)), int(match.group(2))
    raise ValueError("No 'info depth ... score cp ...' line found")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def scenario_castling(engine_bin: Path) -> ScenarioResult:
    base = "r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1"
    attacked_f1 = "4kr2/8/8/8/8/8/8/4K2R w K - 0 1"
    try:
        lines = run_engine(engine_bin, ["uci", "isready", f"position fen {base}", "legalmoves", "quit"])
        moves = parse_legalmoves(lines)
        require("e1g1" in moves, "Expected kingside castling e1g1 in initial castling-rights position")
        require("e1c1" in moves, "Expected queenside castling e1c1 in initial castling-rights position")

        lines = run_engine(
            engine_bin,
            ["uci", "isready", f"position fen {base} moves h1h2 h8h7 h2h1 h7h8", "legalmoves", "quit"],
        )
        moves = parse_legalmoves(lines)
        require("e1g1" not in moves, "Kingside castling should disappear after rook h1 moves")
        require("e1c1" in moves, "Queenside castling should remain after h-rook move")

        lines = run_engine(
            engine_bin,
            ["uci", "isready", f"position fen {base} moves e1f1 h8h7 f1e1 h7h8", "legalmoves", "quit"],
        )
        moves = parse_legalmoves(lines)
        require("e1g1" not in moves and "e1c1" not in moves, "Both castling sides should disappear after king move")

        lines = run_engine(engine_bin, ["uci", "isready", f"position fen {attacked_f1}", "legalmoves", "quit"])
        moves = parse_legalmoves(lines)
        require("e1g1" not in moves, "Kingside castling must be illegal if f1 is attacked")
        return ScenarioResult("castling", True, "rights update + attacked-path checks passed")
    except Exception as exc:
        return ScenarioResult("castling", False, str(exc))


def scenario_en_passant(engine_bin: Path) -> ScenarioResult:
    ep_fen = "4k3/8/8/3pP3/8/8/8/4K3 w - d6 0 1"
    try:
        lines = run_engine(engine_bin, ["uci", "isready", f"position fen {ep_fen}", "legalmoves", "quit"])
        moves = parse_legalmoves(lines)
        require("e5d6" in moves, "Expected en-passant capture e5d6 when ep square is d6")

        lines = run_engine(
            engine_bin,
            ["uci", "isready", f"position fen {ep_fen} moves e1f1 e8f8", "legalmoves", "quit"],
        )
        moves = parse_legalmoves(lines)
        require("e5d6" not in moves, "En-passant right must expire after an intervening move")
        return ScenarioResult("en_passant", True, "availability + expiry checks passed")
    except Exception as exc:
        return ScenarioResult("en_passant", False, str(exc))


def scenario_threefold(engine_bin: Path) -> ScenarioResult:
    try:
        lines = run_engine(
            engine_bin,
            [
                "uci",
                "isready",
                "position startpos moves g1f3 g8f6 f3g1 f6g8 g1f3 g8f6 f3g1 f6g8",
                "go depth 3",
                "quit",
            ],
        )
        depth, score = parse_last_score(lines)
        require(depth == 0 and score == 0, f"Expected repetition draw (depth=0, score=0), got depth={depth}, score={score}")
        return ScenarioResult("threefold_repetition", True, "draw short-circuit at root passed")
    except Exception as exc:
        return ScenarioResult("threefold_repetition", False, str(exc))


def scenario_fifty_move(engine_bin: Path) -> ScenarioResult:
    fen = "8/8/8/8/8/8/4k3/7K w - - 100 1"
    try:
        lines = run_engine(engine_bin, ["uci", "isready", f"position fen {fen}", "go depth 2", "quit"])
        depth, score = parse_last_score(lines)
        require(depth == 0 and score == 0, f"Expected 50-move draw (depth=0, score=0), got depth={depth}, score={score}")
        return ScenarioResult("fifty_move_rule", True, "draw short-circuit at root passed")
    except Exception as exc:
        return ScenarioResult("fifty_move_rule", False, str(exc))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run tournament-legality scenario pack on a derived C UCI variant")
    parser.add_argument("--feature-model", default="outputs/feature_model.json")
    parser.add_argument("--config", default="c_engine_pl/variants/bitboards_alpha.json")
    parser.add_argument("--header-out", default="c_engine_pl/include/generated/variant_config.h")
    parser.add_argument("--manifest-out", default="c_engine_pl/include/generated/variant_manifest.json")
    parser.add_argument("--makefile", default="c_engine_pl/Makefile")
    parser.add_argument("--engine-bin", default="c_engine_pl/build/engine_pl")
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

    engine_bin = Path(args.engine_bin)
    scenarios = [
        scenario_castling(engine_bin),
        scenario_en_passant(engine_bin),
        scenario_threefold(engine_bin),
        scenario_fifty_move(engine_bin),
    ]
    payload = {
        "engine": str(engine_bin),
        "passed": [s.name for s in scenarios if s.passed],
        "failed": [{"name": s.name, "details": s.details} for s in scenarios if not s.passed],
    }
    print(json.dumps({"scenarios": payload}, indent=2))
    return 0 if not payload["failed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
