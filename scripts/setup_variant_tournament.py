#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import random
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

import chess
import chess.pgn

from cpw_variability.pl_codegen import derive_variant, run_build


BEST_VARIANT = "phase3_full_eval"
WORST_VARIANT = "phase1_minimax"
DEFAULT_SEED = 20260404
OPENING_LINES_UCI: tuple[tuple[str, ...], ...] = (
    ("e2e4", "e7e5", "g1f3", "b8c6", "f1b5", "a7a6", "b5a4", "g8f6"),
    ("e2e4", "c7c5", "g1f3", "d7d6", "d2d4", "c5d4", "f3d4", "g8f6"),
    ("d2d4", "d7d5", "c2c4", "e7e6", "b1c3", "g8f6", "c1g5", "f8e7"),
    ("d2d4", "g8f6", "c2c4", "g7g6", "b1c3", "f8g7", "e2e4", "d7d6"),
    ("c2c4", "e7e5", "b1c3", "g8f6", "g1f3", "b8c6", "d2d4", "e5d4"),
    ("g1f3", "d7d5", "d2d4", "g8f6", "c2c4", "e7e6", "b1c3", "f8e7"),
)


@dataclass
class PlayerSpec:
    role: str
    variant_name: str
    config_path: Path
    binary_path: Path
    match_mode: str
    match_budget: str
    cutechess_engine_args: list[str]
    setup_summary: str
    book_policy: str
    ponder_policy: str


def _load_setup_rows(path: Path) -> dict[str, dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return {row["variant_name"]: row for row in csv.DictReader(handle)}


def _choose_random_variant(variants_dir: Path, seed: int) -> Path:
    configs = [
        path
        for path in sorted(variants_dir.glob("*.json"))
        if path.stem not in {BEST_VARIANT, WORST_VARIANT, "invalid_excludes"}
    ]
    if not configs:
        raise ValueError("No candidate random variants found")
    rng = random.Random(seed)
    return rng.choice(configs)


def _perft_commands(max_depth: int) -> str:
    commands = ["uci", "isready", "position startpos"]
    for depth in range(1, max_depth + 1):
        commands.append(f"perft {depth}")
    commands.append("quit")
    return "\n".join(commands) + "\n"


def _parse_perft(stdout: str) -> dict[int, int]:
    results: dict[int, int] = {}
    for raw_line in stdout.replace("\\n", "\n").splitlines():
        line = raw_line.strip()
        prefix = "info string perft depth "
        if not line.startswith(prefix):
            continue
        remainder = line[len(prefix):]
        parts = remainder.split()
        if len(parts) >= 3 and parts[1] == "nodes":
            try:
                results[int(parts[0])] = int(parts[2])
            except ValueError:
                continue
    return results


def _derive_build_copy(
    feature_model: Path,
    config_path: Path,
    header_out: Path,
    manifest_out: Path,
    makefile: Path,
    engine_bin: Path,
    dest_bin: Path,
) -> dict[str, object]:
    report = derive_variant(
        feature_model_path=feature_model,
        config_path=config_path,
        header_out=header_out,
        manifest_out=manifest_out,
        enforce_tournament_legality=True,
    )
    run_build(makefile)
    dest_bin.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(engine_bin, dest_bin)
    dest_bin.chmod(0o755)
    return report


def _run_perft(engine_bin: Path, max_depth: int) -> dict[str, object]:
    completed = subprocess.run(
        [str(engine_bin)],
        input=_perft_commands(max_depth),
        capture_output=True,
        text=True,
        check=True,
    )
    got = _parse_perft(completed.stdout)
    expected = {1: 20, 2: 400, 3: 8902, 4: 197281, 5: 4865609}
    expected = {depth: expected[depth] for depth in range(1, max_depth + 1)}
    return {
        "expected": expected,
        "got": got,
        "pass": all(got.get(depth) == expected[depth] for depth in expected),
    }


def _write_openings_pgn(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for idx, line in enumerate(OPENING_LINES_UCI, start=1):
            board = chess.Board()
            game = chess.pgn.Game()
            game.headers["Event"] = f"Setup Opening {idx}"
            game.headers["Site"] = "Local"
            game.headers["Round"] = str(idx)
            game.headers["White"] = "OpeningWhite"
            game.headers["Black"] = "OpeningBlack"
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


def _budget_to_engine_args(
    row: dict[str, str],
    selected_features: list[str],
    repo_root: Path,
    setup_kind: str,
) -> tuple[list[str], str]:
    args: list[str] = ["proto=uci", "restart=on"]
    if setup_kind == "analysis":
        mode = row["analysis_mode"]
        budget = row["analysis_budget"]
    else:
        mode = row["match_mode"]
        budget = row["match_budget"]
    setup_parts: list[str] = [f"{mode}:{budget}"]

    if mode == "FixedMoveTime":
        if "1500-2000" in budget:
            args.append("st=2.0")
            setup_parts.append("st=2.0")
        elif "750-1000" in budget:
            args.append("st=1.0")
            setup_parts.append("st=1.0")
        elif "250-500" in budget:
            args.append("st=0.5")
            setup_parts.append("st=0.5")
        else:
            args.append("st=0.25")
            setup_parts.append("st=0.25")
    elif mode == "ClockManaged":
        if "120+1" in budget:
            args.append("tc=120+1")
            setup_parts.append("tc=120+1")
        else:
            args.append("tc=10+0.1")
            setup_parts.append("tc=10+0.1")
    elif mode == "FixedDepth":
        if setup_kind == "analysis":
            if "12-20" in budget:
                args.append("depth=6")
                setup_parts.append("depth=6")
            elif "9-12" in budget:
                args.append("depth=5")
                setup_parts.append("depth=5")
            elif "5-8" in budget:
                args.append("depth=4")
                setup_parts.append("depth=4")
            else:
                args.append("depth=3")
                setup_parts.append("depth=3")
        else:
            if "12-20" in budget:
                args.append("depth=14")
                setup_parts.append("depth=14")
            elif "9-12" in budget:
                args.append("depth=10")
                setup_parts.append("depth=10")
            elif "5-8" in budget:
                args.append("depth=6")
                setup_parts.append("depth=6")
            else:
                args.append("depth=4")
                setup_parts.append("depth=4")

    if "Opening Book" in selected_features and row["book_policy"].startswith("match: enable default book"):
        default_book = repo_root / "c_engine_pl" / "books" / "default_openings.txt"
        args.extend(
            [
                "option.OwnBook=true",
                f"option.BookFile={default_book}",
            ]
        )
        setup_parts.append("OwnBook=true")

    if "Pondering" in selected_features and row["ponder_policy"].startswith("match: enable"):
        args.extend(["ponder", "option.Ponder=true"])
        setup_parts.append("ponder=true")

    return args, ", ".join(setup_parts)


def _parse_games(pgn_path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    with pgn_path.open("r", encoding="utf-8", errors="replace") as handle:
        while True:
            game = chess.pgn.read_game(handle)
            if game is None:
                break
            result = game.headers.get("Result", "*")
            if result not in {"1-0", "0-1", "1/2-1/2"}:
                continue
            rows.append(
                {
                    "white": game.headers.get("White", ""),
                    "black": game.headers.get("Black", ""),
                    "result": result,
                    "termination": game.headers.get("Termination", ""),
                }
            )
    return rows


def _score_for_color(result: str) -> tuple[float, float]:
    if result == "1-0":
        return 1.0, 0.0
    if result == "0-1":
        return 0.0, 1.0
    return 0.5, 0.5


def _compute_standings(players: list[PlayerSpec], games: list[dict[str, object]]) -> list[dict[str, object]]:
    table = {
        player.role: {
            "role": player.role,
            "variant_name": player.variant_name,
            "match_mode": player.match_mode,
            "match_budget": player.match_budget,
            "setup_summary": player.setup_summary,
            "games": 0,
            "wins": 0,
            "draws": 0,
            "losses": 0,
            "score": 0.0,
            "score_pct": 0.0,
        }
        for player in players
    }
    for game in games:
        white = str(game["white"])
        black = str(game["black"])
        white_score, black_score = _score_for_color(str(game["result"]))
        table[white]["games"] += 1
        table[black]["games"] += 1
        table[white]["score"] += white_score
        table[black]["score"] += black_score
        if white_score == 1.0:
            table[white]["wins"] += 1
            table[black]["losses"] += 1
        elif black_score == 1.0:
            table[black]["wins"] += 1
            table[white]["losses"] += 1
        else:
            table[white]["draws"] += 1
            table[black]["draws"] += 1

    standings = list(table.values())
    for row in standings:
        games_count = int(row["games"])
        row["score_pct"] = round((float(row["score"]) / games_count * 100.0), 1) if games_count else 0.0

    standings.sort(key=lambda item: (-float(item["score"]), -int(item["wins"]), int(item["losses"]), item["role"]))
    return standings


def _write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a best-setup tournament for best/worst/random engine variants")
    parser.add_argument("--feature-model", default="outputs/feature_model.json")
    parser.add_argument("--setup-recommendations", default="outputs/setup_recommendations_by_variant.csv")
    parser.add_argument("--variants-dir", default="c_engine_pl/variants")
    parser.add_argument("--makefile", default="c_engine_pl/Makefile")
    parser.add_argument("--engine-bin", default="c_engine_pl/build/engine_pl")
    parser.add_argument("--header-out", default="c_engine_pl/include/generated/variant_config.h")
    parser.add_argument("--manifest-out", default="c_engine_pl/include/generated/variant_manifest.json")
    parser.add_argument("--out-dir", default="outputs/setup_variant_tournament_best_worst_random")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--rounds", type=int, default=1)
    parser.add_argument("--games-per-encounter", type=int, default=2)
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--maxmoves", type=int, default=100)
    parser.add_argument("--perft-depth", type=int, default=5, choices=(1, 2, 3, 4, 5))
    parser.add_argument("--setup-kind", choices=("match", "analysis"), default="match")
    parser.add_argument("--use-openings", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    feature_model = (repo_root / args.feature_model).resolve()
    recommendations_path = (repo_root / args.setup_recommendations).resolve()
    variants_dir = (repo_root / args.variants_dir).resolve()
    makefile = (repo_root / args.makefile).resolve()
    engine_bin = (repo_root / args.engine_bin).resolve()
    header_out = (repo_root / args.header_out).resolve()
    manifest_out = (repo_root / args.manifest_out).resolve()
    out_dir = (repo_root / args.out_dir).resolve()

    out_dir.mkdir(parents=True, exist_ok=True)
    bins_dir = out_dir / "variant_bins"
    perft_dir = out_dir / "perft"
    log_path = out_dir / "cutechess.log"
    pgn_path = out_dir / "games.pgn"
    openings_path = out_dir / "openings.pgn"
    summary_path = out_dir / "summary.json"
    standings_path = out_dir / "standings.csv"
    players_path = out_dir / "players.csv"
    games_path = out_dir / "games.csv"
    perft_path = out_dir / "perft.csv"
    report_path = out_dir / "report.md"

    setup_rows = _load_setup_rows(recommendations_path)
    random_config = _choose_random_variant(variants_dir, seed=args.seed)
    variant_configs = [
        ("best", (variants_dir / f"{BEST_VARIANT}.json").resolve()),
        ("worst", (variants_dir / f"{WORST_VARIANT}.json").resolve()),
        ("random", random_config.resolve()),
    ]

    players: list[PlayerSpec] = []
    perft_rows: list[dict[str, object]] = []

    for role, config_path in variant_configs:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
        variant_name = str(payload.get("name", config_path.stem))
        setup_row = setup_rows[variant_name]
        binary_path = bins_dir / f"{role}_{variant_name}"
        derive_report = _derive_build_copy(
            feature_model=feature_model,
            config_path=config_path,
            header_out=header_out,
            manifest_out=manifest_out,
            makefile=makefile,
            engine_bin=engine_bin,
            dest_bin=binary_path,
        )
        perft_result = _run_perft(binary_path, args.perft_depth)
        perft_rows.append(
            {
                "role": role,
                "variant_name": variant_name,
                "binary": str(binary_path),
                "perft_depth": args.perft_depth,
                "pass": perft_result["pass"],
                "expected": json.dumps(perft_result["expected"], sort_keys=True),
                "got": json.dumps(perft_result["got"], sort_keys=True),
            }
        )
        engine_args, setup_summary = _budget_to_engine_args(
            setup_row,
            list(derive_report["selected_features"]),
            repo_root,
            args.setup_kind,
        )
        players.append(
            PlayerSpec(
                role=role,
                variant_name=variant_name,
                config_path=config_path,
                binary_path=binary_path,
                match_mode=setup_row["match_mode"],
                match_budget=setup_row["match_budget"],
                cutechess_engine_args=engine_args,
                setup_summary=setup_summary,
                book_policy=setup_row["book_policy"],
                ponder_policy=setup_row["ponder_policy"],
            )
        )

    # Restore the default working build after copying the tournament players.
    _derive_build_copy(
        feature_model=feature_model,
        config_path=(variants_dir / f"{BEST_VARIANT}.json").resolve(),
        header_out=header_out,
        manifest_out=manifest_out,
        makefile=makefile,
        engine_bin=engine_bin,
        dest_bin=out_dir / "restored_default_engine",
    )

    if args.use_openings:
        _write_openings_pgn(openings_path)

    cmd: list[str] = ["cutechess-cli"]
    for player in players:
        cmd.extend(
            [
                "-engine",
                f"name={player.role}",
                f"cmd={player.binary_path}",
                *player.cutechess_engine_args,
            ]
        )
    if args.setup_kind == "analysis":
        cmd.extend(["-each", "tc=inf"])
    cmd.extend(
        [
            "-variant",
            "standard",
            "-tournament",
            "round-robin",
            "-games",
            str(args.games_per_encounter),
            "-rounds",
            str(args.rounds),
            "-concurrency",
            str(args.concurrency),
            "-maxmoves",
            str(args.maxmoves),
            "-draw",
            "movenumber=30",
            "movecount=8",
            "score=20",
            "-resign",
            "movecount=4",
            "score=900",
            "-repeat",
            "-srand",
            str(args.seed),
            "-pgnout",
            str(pgn_path),
            "min",
            "-recover",
        ]
    )
    if args.use_openings:
        cmd.extend(["-openings", f"file={openings_path}", "format=pgn", "order=random", "policy=encounter", "plies=8"])

    completed = subprocess.run(cmd, capture_output=True, text=True, check=True)
    log_path.write_text(completed.stdout + ("\n" + completed.stderr if completed.stderr else ""), encoding="utf-8")

    games = _parse_games(pgn_path)
    standings = _compute_standings(players, games)

    player_rows = [asdict(player) for player in players]
    for row in player_rows:
        row["config_path"] = str(row["config_path"])
        row["binary_path"] = str(row["binary_path"])
        row["cutechess_engine_args"] = " ".join(row["cutechess_engine_args"])

    _write_csv(
        players_path,
        player_rows,
        [
            "role",
            "variant_name",
            "config_path",
            "binary_path",
            "match_mode",
            "match_budget",
            "cutechess_engine_args",
            "setup_summary",
            "book_policy",
            "ponder_policy",
        ],
    )
    _write_csv(
        games_path,
        games,
        ["white", "black", "result", "termination"],
    )
    _write_csv(
        standings_path,
        standings,
        ["role", "variant_name", "match_mode", "match_budget", "setup_summary", "games", "wins", "draws", "losses", "score", "score_pct"],
    )
    _write_csv(
        perft_path,
        perft_rows,
        ["role", "variant_name", "binary", "perft_depth", "pass", "expected", "got"],
    )

    summary = {
        "roles": {
            "best": BEST_VARIANT,
            "worst": WORST_VARIANT,
            "random": random_config.stem,
        },
        "seed": args.seed,
        "params": {
            "setup_kind": args.setup_kind,
            "rounds": args.rounds,
            "games_per_encounter": args.games_per_encounter,
            "concurrency": args.concurrency,
            "maxmoves": args.maxmoves,
            "perft_depth": args.perft_depth,
            "use_openings": args.use_openings,
        },
        "players": player_rows,
        "perft": perft_rows,
        "game_count": len(games),
        "standings": standings,
        "cutechess_command": [str(item) for item in cmd],
        "artifacts": {
            "players_csv": str(players_path),
            "standings_csv": str(standings_path),
            "games_csv": str(games_path),
            "perft_csv": str(perft_path),
            "pgn": str(pgn_path),
            "log": str(log_path),
            "openings_pgn": str(openings_path) if args.use_openings else "",
        },
    }
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    illegal_markers = [
        token
        for token in ("Illegal move", "failed_to_apply_move", "disconnects")
        if token in log_path.read_text(encoding="utf-8", errors="replace")
    ]
    report_lines = [
        "# Setup Tournament Report",
        "",
        "This tournament compares three `(variant, setup)` pairs rather than three variants under equal external conditions.",
        "It is therefore a best-operating-point comparison, not a controlled Elo comparison.",
        "",
        "## Players",
    ]
    for player in players:
        report_lines.append(
            f"- `{player.role}`: `{player.variant_name}` with setup `{player.setup_summary}`"
        )
    report_lines.extend(
        [
            "",
            "## Integrity",
            f"- perft rows: {len(perft_rows)}",
            f"- all perft passed: {all(bool(row['pass']) for row in perft_rows)}",
            f"- illegal markers in cutechess log: {illegal_markers}",
            "",
            "## Standings",
        ]
    )
    for row in standings:
        report_lines.append(
            f"- `{row['role']}` / `{row['variant_name']}`: {row['score']}/{row['games']} ({row['score_pct']}%)"
        )
    report_path.write_text("\n".join(report_lines), encoding="utf-8")

    print(json.dumps({"summary_json": str(summary_path), "game_count": len(games), "random_variant": random_config.stem}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
