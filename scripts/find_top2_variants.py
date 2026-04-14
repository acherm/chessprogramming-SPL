#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import random
import shutil
import subprocess
from pathlib import Path

import chess
import chess.pgn

from cpw_variability.pl_codegen import derive_variant, load_model_index, run_build, validate_selection

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

OPENING_LINES_UCI: tuple[tuple[str, ...], ...] = (
    ("e2e4", "e7e5", "g1f3", "b8c6", "f1b5", "a7a6", "b5a4", "g8f6"),
    ("e2e4", "c7c5", "g1f3", "d7d6", "d2d4", "c5d4", "f3d4", "g8f6"),
    ("d2d4", "g8f6", "c2c4", "e7e6", "g1f3", "d7d5", "b1c3", "f8e7"),
    ("c2c4", "e7e5", "b1c3", "g8f6", "g1f3", "b8c6", "d2d4", "e5d4"),
    ("e2e4", "e7e6", "d2d4", "d7d5", "b1c3", "g8f6", "c1g5", "f8b4"),
    ("g1f3", "g8f6", "g2g3", "g7g6", "f1g2", "f8g7", "e1g1", "e8g8"),
)


def choose_random_valid_selection(model, rng: random.Random, optional_prob: float, max_attempts: int) -> set[str]:
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

        for name in MANDATORY_OPTION_NAMES:
            opt = options_by_name.get(name)
            if opt is not None:
                selected.add(opt.id)

        for group_id in REQUIRED_GROUPS:
            group_opts = required_group_options[group_id]
            if not group_opts:
                continue
            selected.add(rng.choice(group_opts).id)

        for option in options:
            if option.id in selected:
                continue
            if option.id in board_primary_ids:
                continue
            if rng.random() < optional_prob:
                selected.add(option.id)

        errors = validate_selection(model, selected, enforce_tournament_legality=True)
        if not errors:
            return selected

    raise RuntimeError(f"Failed to generate valid selection after {max_attempts} attempts")


def write_openings_pgn(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for idx, line in enumerate(OPENING_LINES_UCI, start=1):
            board = chess.Board()
            game = chess.pgn.Game()
            game.headers["Event"] = f"Search Opening {idx}"
            game.headers["Result"] = "*"
            node = game
            for uci in line:
                move = chess.Move.from_uci(uci)
                if move not in board.legal_moves:
                    raise ValueError(f"Illegal opening move {uci} in line {idx}")
                node = node.add_variation(move)
                board.push(move)
            exporter = chess.pgn.StringExporter(headers=True, variations=False, comments=False)
            handle.write(game.accept(exporter))
            handle.write("\n\n")


def run_cutechess(cmd: list[str], log_path: Path) -> None:
    completed = subprocess.run(cmd, capture_output=True, text=True, check=True)
    log_path.write_text(completed.stdout + ("\n" + completed.stderr if completed.stderr else ""), encoding="utf-8")


def parse_candidate_score(pgn_path: Path, candidate_name: str, opponent_elos: dict[str, int]) -> tuple[float, int, float]:
    points = 0.0
    games = 0
    opponent_sum = 0.0

    with pgn_path.open("r", encoding="utf-8", errors="replace") as handle:
        while True:
            game = chess.pgn.read_game(handle)
            if game is None:
                break
            white = game.headers.get("White", "")
            black = game.headers.get("Black", "")
            result = game.headers.get("Result", "*")
            if result not in {"1-0", "0-1", "1/2-1/2"}:
                continue
            if white != candidate_name and black != candidate_name:
                continue

            games += 1
            if white == candidate_name:
                opponent = black
                if result == "1-0":
                    points += 1.0
                elif result == "1/2-1/2":
                    points += 0.5
            else:
                opponent = white
                if result == "0-1":
                    points += 1.0
                elif result == "1/2-1/2":
                    points += 0.5

            opponent_sum += opponent_elos.get(opponent, 1500)

    if games == 0:
        return 0.0, 0, float("-inf")

    score = points / games
    avg_opp = opponent_sum / games

    # Approximate performance rating from score percentage.
    if score <= 0.0:
        perf = avg_opp - 800.0
    elif score >= 1.0:
        perf = avg_opp + 800.0
    else:
        perf = avg_opp + 400.0 * math.log10(score / (1.0 - score))

    return points, games, perf


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Search top-2 feature configurations by Elo proxy and run a full tournament")
    parser.add_argument("--feature-model", default="outputs/feature_model.json")
    parser.add_argument("--seed", type=int, default=20260305)
    parser.add_argument("--candidates", type=int, default=12)
    parser.add_argument("--optional-prob", type=float, default=0.35)
    parser.add_argument("--max-attempts", type=int, default=3000)

    parser.add_argument("--makefile", default="c_engine_pl/Makefile")
    parser.add_argument("--engine-bin", default="c_engine_pl/build/engine_pl")
    parser.add_argument("--header-out", default="c_engine_pl/include/generated/variant_config.h")
    parser.add_argument("--manifest-out", default="c_engine_pl/include/generated/variant_manifest.json")

    parser.add_argument("--stockfish-bin", default="stockfish")

    parser.add_argument("--search-depth", type=int, default=3)
    parser.add_argument("--final-depth", type=int, default=4)
    parser.add_argument("--final-rounds", type=int, default=2)
    parser.add_argument("--final-games-per-encounter", type=int, default=2)
    parser.add_argument("--concurrency", type=int, default=2)

    parser.add_argument("--out-dir", default="outputs/best_variant_search")
    parser.add_argument("--final-out-dir", default="outputs/proper_elo_tournament_best2")
    return parser


def main() -> int:
    args = build_parser().parse_args()

    rng = random.Random(args.seed)
    model = load_model_index(Path(args.feature_model))

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    cfg_dir = out_dir / "candidate_configs"
    bin_dir = out_dir / "candidate_bins"
    pgn_dir = out_dir / "candidate_pgn"
    log_dir = out_dir / "candidate_logs"
    openings = out_dir / "openings_search.pgn"
    ranking_csv = out_dir / "candidate_ranking.csv"
    selection_json = out_dir / "best2_selection.json"

    cfg_dir.mkdir(parents=True, exist_ok=True)
    bin_dir.mkdir(parents=True, exist_ok=True)
    pgn_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)

    write_openings_pgn(openings)

    sf_bin = shutil.which(args.stockfish_bin)
    if sf_bin is None:
        raise FileNotFoundError(f"stockfish not found: {args.stockfish_bin}")
    sf_bin_path = Path(sf_bin).resolve()

    sf_anchors = {
        "sf1320": 1320,
        "sf1800": 1800,
    }

    rows: list[dict[str, object]] = []
    seen: set[tuple[str, ...]] = set()

    while len(rows) < args.candidates:
        selected_ids = choose_random_valid_selection(model, rng, args.optional_prob, args.max_attempts)
        key = tuple(sorted(selected_ids))
        if key in seen:
            continue
        seen.add(key)

        idx = len(rows) + 1
        cand_name = f"candidate_{idx:02d}"
        selected_options = [model.options_by_id[oid] for oid in key]
        selected_names = [o.name for o in sorted(selected_options, key=lambda x: x.name.lower())]

        cfg_path = cfg_dir / f"{cand_name}.json"
        cfg_path.write_text(json.dumps({"name": cand_name, "selected_options": selected_names}, indent=2), encoding="utf-8")

        report = derive_variant(
            feature_model_path=Path(args.feature_model),
            config_path=cfg_path,
            header_out=Path(args.header_out),
            manifest_out=Path(args.manifest_out),
            enforce_tournament_legality=True,
        )
        run_build(Path(args.makefile))

        cand_bin = bin_dir / cand_name
        shutil.copy2(Path(args.engine_bin), cand_bin)
        cand_bin.chmod(0o755)

        pgn_path = pgn_dir / f"{cand_name}.pgn"
        log_path = log_dir / f"{cand_name}.log"

        cmd = [
            "cutechess-cli",
            "-engine", f"name={cand_name}", f"cmd={cand_bin}", "proto=uci",
            "-engine", f"name=sf1320", f"cmd={sf_bin_path}", "proto=uci", "option.Skill Level=1", "option.UCI_LimitStrength=true", "option.UCI_Elo=1320",
            "-engine", f"name=sf1800", f"cmd={sf_bin_path}", "proto=uci", "option.Skill Level=6", "option.UCI_LimitStrength=true", "option.UCI_Elo=1800",
            "-each", f"depth={args.search_depth}", "tc=inf",
            "-tournament", "gauntlet",
            "-rounds", "1",
            "-games", "2",
            "-concurrency", str(args.concurrency),
            "-maxmoves", "120",
            "-draw", "movenumber=25", "movecount=8", "score=20",
            "-resign", "movecount=4", "score=900",
            "-openings", f"file={openings}", "format=pgn", "order=random", "policy=encounter", "plies=8",
            "-repeat",
            "-srand", str(args.seed + idx),
            "-pgnout", str(pgn_path), "min",
            "-recover",
        ]
        run_cutechess(cmd, log_path)

        points, games, perf = parse_candidate_score(pgn_path, cand_name, sf_anchors)
        score_pct = (points / games * 100.0) if games > 0 else 0.0

        row = {
            "candidate": cand_name,
            "config_path": str(cfg_path),
            "binary_path": str(cand_bin),
            "selected_feature_count": report.get("selected_count", 0),
            "selected_features": "|".join(report.get("selected_features", [])),
            "games": games,
            "points": round(points, 3),
            "score_pct": round(score_pct, 3),
            "performance_elo": round(perf, 1),
            "pgn": str(pgn_path),
            "log": str(log_path),
        }
        rows.append(row)
        print(json.dumps({"candidate": cand_name, "score_pct": row["score_pct"], "perf": row["performance_elo"]}))

    rows.sort(key=lambda r: (-float(r["points"]), -float(r["performance_elo"]), r["candidate"]))

    with ranking_csv.open("w", newline="", encoding="utf-8") as handle:
        fieldnames = [
            "candidate",
            "config_path",
            "binary_path",
            "selected_feature_count",
            "selected_features",
            "games",
            "points",
            "score_pct",
            "performance_elo",
            "pgn",
            "log",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    best2 = rows[:2]
    selection_json.write_text(json.dumps({"best2": best2}, indent=2), encoding="utf-8")

    final_cmd = [
        "python3",
        "scripts/proper_elo_tournament.py",
        "--feature-model", args.feature_model,
        "--variant-config", best2[0]["config_path"],
        "--variant-config", best2[1]["config_path"],
        "--seed", str(args.seed),
        "--depth", str(args.final_depth),
        "--rounds", str(args.final_rounds),
        "--games-per-encounter", str(args.final_games_per_encounter),
        "--concurrency", str(args.concurrency),
        "--out-dir", args.final_out_dir,
    ]
    subprocess.run(final_cmd, check=True)

    print(
        json.dumps(
            {
                "candidates": len(rows),
                "ranking_csv": str(ranking_csv),
                "best2_selection": str(selection_json),
                "final_out_dir": args.final_out_dir,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
