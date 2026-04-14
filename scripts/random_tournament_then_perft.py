#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import itertools
import json
import random
import re
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

import chess

from cpw_variability.pl_codegen import derive_variant, load_model_index, run_build, validate_selection

PERFT_RE = re.compile(r"^info string perft depth (\d+) nodes (\d+)$")
BESTMOVE_RE = re.compile(r"^bestmove\s+([^\s]+)")
SCORE_CP_RE = re.compile(r"\bscore cp (-?\d+)\b")
SCORE_MATE_RE = re.compile(r"\bscore mate (-?\d+)\b")
NODES_SEARCHED_RE = re.compile(r"^Nodes searched:\s*(\d+)$", re.IGNORECASE)
STOCKFISH_ELO_MIN_RE = re.compile(r"^option name UCI_Elo type spin default -?\d+ min (-?\d+) max -?\d+$")
STOCKFISH_ELO_RANGE_RE = re.compile(r"^option name UCI_Elo type spin default -?\d+ min (-?\d+) max (-?\d+)$")

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


@dataclass
class Player:
    name: str
    binary_path: Path
    selected_features: list[str]
    selected_feature_count: int
    config_path: Path | None = None
    uci_options: list[str] = field(default_factory=list)
    perft_mode: str = "cpw"


def resolve_engine_path(token: str) -> Path:
    path = Path(token).expanduser()
    if path.exists():
        return path.resolve()

    resolved = shutil.which(token)
    if resolved is not None:
        return Path(resolved).resolve()

    raise FileNotFoundError(f"Engine executable not found: {token}")


def run_engine(engine_bin: Path, commands: list[str], timeout_sec: float = 15.0) -> list[str]:
    transcript = "\n".join(commands) + "\n"
    completed = subprocess.run(
        [str(engine_bin)],
        input=transcript,
        capture_output=True,
        text=True,
        timeout=timeout_sec,
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


def parse_bestmove_and_score(lines: list[str]) -> tuple[str | None, int | None, int | None]:
    bestmove = None
    score_cp = None
    score_mate = None

    for line in lines:
        cp_match = SCORE_CP_RE.search(line)
        if cp_match is not None:
            score_cp = int(cp_match.group(1))
        mate_match = SCORE_MATE_RE.search(line)
        if mate_match is not None:
            score_mate = int(mate_match.group(1))

    for line in reversed(lines):
        match = BESTMOVE_RE.match(line)
        if match is not None:
            bestmove = match.group(1)
            break

    return bestmove, score_cp, score_mate


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


def build_uci_commands(player: Player, history: list[str], action_commands: list[str]) -> list[str]:
    commands = ["uci"]
    commands.extend(player.uci_options)
    commands.append("isready")
    position = "position startpos"
    if history:
        position += " moves " + " ".join(history)
    commands.append(position)
    commands.extend(action_commands)
    commands.append("quit")
    return commands


def query_bestmove(player: Player, history: list[str], depth: int, movetime_ms: int) -> tuple[str | None, int | None, int | None]:
    commands = build_uci_commands(player, history, [f"go depth {depth} movetime {movetime_ms}"])
    lines = run_engine(player.binary_path, commands)
    return parse_bestmove_and_score(lines)


def discover_stockfish_min_elo(stockfish_bin: Path) -> int | None:
    lines = run_engine(stockfish_bin, ["uci", "quit"], timeout_sec=10.0)
    for line in lines:
        match = STOCKFISH_ELO_MIN_RE.match(line)
        if match is not None:
            return int(match.group(1))
    return None


def discover_stockfish_elo_range(stockfish_bin: Path) -> tuple[int | None, int | None]:
    lines = run_engine(stockfish_bin, ["uci", "quit"], timeout_sec=10.0)
    for line in lines:
        match = STOCKFISH_ELO_RANGE_RE.match(line)
        if match is not None:
            return int(match.group(1)), int(match.group(2))
    return None, None


def parse_stockfish_profile(spec: str) -> tuple[str, int, int]:
    parts = [part.strip() for part in spec.split(":")]
    if len(parts) != 3:
        raise ValueError(
            f"Invalid --stockfish-profile '{spec}'. Expected format: name:skill:elo "
            "(example: strong:6:1800)"
        )
    name, skill_s, elo_s = parts
    if not name:
        raise ValueError(f"Invalid --stockfish-profile '{spec}': empty profile name")
    try:
        skill = int(skill_s)
        elo = int(elo_s)
    except ValueError as exc:
        raise ValueError(
            f"Invalid --stockfish-profile '{spec}'. Skill and elo must be integers."
        ) from exc
    return name, skill, elo


def play_game(
    white: Player,
    black: Player,
    game_id: str,
    go_depth: int,
    movetime_ms: int,
    max_plies: int,
) -> dict[str, object]:
    board = chess.Board()
    history: list[str] = []

    for _ in range(max_plies):
        if board.is_game_over(claim_draw=True):
            outcome = board.outcome(claim_draw=True)
            if outcome is None:
                result = "1/2-1/2"
                termination = "draw"
            else:
                result = outcome.result()
                termination = outcome.termination.name.lower()
            return {
                "game_id": game_id,
                "white": white.name,
                "black": black.name,
                "result": result,
                "termination": termination,
                "plies": len(history),
                "moves": " ".join(history),
                "last_bestmove": "",
                "last_score_cp": "",
                "last_score_mate": "",
            }

        engine = white if board.turn == chess.WHITE else black
        bestmove, score_cp, score_mate = query_bestmove(engine, history, depth=go_depth, movetime_ms=movetime_ms)

        if bestmove is None or bestmove in {"0000", "(none)"}:
            result = "0-1" if board.turn == chess.WHITE else "1-0"
            return {
                "game_id": game_id,
                "white": white.name,
                "black": black.name,
                "result": result,
                "termination": "no_bestmove_with_legal_moves",
                "plies": len(history),
                "moves": " ".join(history),
                "last_bestmove": bestmove or "",
                "last_score_cp": "" if score_cp is None else score_cp,
                "last_score_mate": "" if score_mate is None else score_mate,
            }

        try:
            move = chess.Move.from_uci(bestmove)
        except ValueError:
            result = "0-1" if board.turn == chess.WHITE else "1-0"
            return {
                "game_id": game_id,
                "white": white.name,
                "black": black.name,
                "result": result,
                "termination": "invalid_bestmove_format",
                "plies": len(history),
                "moves": " ".join(history),
                "last_bestmove": bestmove,
                "last_score_cp": "" if score_cp is None else score_cp,
                "last_score_mate": "" if score_mate is None else score_mate,
            }

        if move not in board.legal_moves:
            result = "0-1" if board.turn == chess.WHITE else "1-0"
            return {
                "game_id": game_id,
                "white": white.name,
                "black": black.name,
                "result": result,
                "termination": "illegal_bestmove",
                "plies": len(history),
                "moves": " ".join(history),
                "last_bestmove": bestmove,
                "last_score_cp": "" if score_cp is None else score_cp,
                "last_score_mate": "" if score_mate is None else score_mate,
            }

        board.push(move)
        history.append(bestmove)

    return {
        "game_id": game_id,
        "white": white.name,
        "black": black.name,
        "result": "1/2-1/2",
        "termination": "max_plies",
        "plies": len(history),
        "moves": " ".join(history),
        "last_bestmove": "",
        "last_score_cp": "",
        "last_score_mate": "",
    }


def update_standings(standings: dict[str, dict[str, float]], game: dict[str, object]) -> None:
    white = str(game["white"])
    black = str(game["black"])
    result = str(game["result"])

    if result == "1-0":
        standings[white]["points"] += 1.0
        standings[white]["wins"] += 1
        standings[black]["losses"] += 1
    elif result == "0-1":
        standings[black]["points"] += 1.0
        standings[black]["wins"] += 1
        standings[white]["losses"] += 1
    else:
        standings[white]["points"] += 0.5
        standings[black]["points"] += 0.5
        standings[white]["draws"] += 1
        standings[black]["draws"] += 1


def parse_stockfish_nodes(lines: list[str]) -> int | None:
    for line in reversed(lines):
        match = NODES_SEARCHED_RE.match(line)
        if match is not None:
            return int(match.group(1))
    return None


def run_perft_check(player: Player, max_depth: int) -> tuple[dict[int, int], bool, float]:
    t0 = time.perf_counter()
    got: dict[int, int] = {}

    if player.perft_mode == "cpw":
        commands = build_uci_commands(player, [], [f"perft {depth}" for depth in range(1, max_depth + 1)])
        lines = run_engine(player.binary_path, commands, timeout_sec=max(20.0, 5.0 * max_depth))
        got = parse_perft(lines)
    elif player.perft_mode == "stockfish_go_perft":
        for depth in range(1, max_depth + 1):
            commands = build_uci_commands(player, [], [f"go perft {depth}"])
            lines = run_engine(player.binary_path, commands, timeout_sec=max(20.0, 5.0 * depth))
            nodes = parse_stockfish_nodes(lines)
            if nodes is not None:
                got[depth] = nodes
    else:
        raise ValueError(f"Unknown perft mode: {player.perft_mode}")

    elapsed = time.perf_counter() - t0
    passed = True
    for depth in range(1, max_depth + 1):
        if got.get(depth) != STARTPOS_EXPECTED[depth]:
            passed = False
            break

    return got, passed, elapsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Sample random variants, run small tournament, then run perft checks")
    parser.add_argument("--feature-model", default="outputs/feature_model.json")
    parser.add_argument("--count", type=int, default=3)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--optional-prob", type=float, default=0.35)
    parser.add_argument("--max-attempts", type=int, default=2000)
    parser.add_argument("--go-depth", type=int, default=3)
    parser.add_argument("--movetime-ms", type=int, default=80)
    parser.add_argument("--max-plies", type=int, default=100)
    parser.add_argument("--perft-depth", type=int, default=4, choices=(1, 2, 3, 4, 5, 6))
    parser.add_argument("--makefile", default="c_engine_pl/Makefile")
    parser.add_argument("--engine-bin", default="c_engine_pl/build/engine_pl")
    parser.add_argument("--header-out", default="c_engine_pl/include/generated/variant_config.h")
    parser.add_argument("--manifest-out", default="c_engine_pl/include/generated/variant_manifest.json")
    parser.add_argument("--out-config-dir", default="outputs/tournament_variant_configs")
    parser.add_argument("--out-bin-dir", default="outputs/tournament_variant_bins")
    parser.add_argument("--out-matches-csv", default="outputs/tournament_matches.csv")
    parser.add_argument("--out-standings-csv", default="outputs/tournament_standings.csv")
    parser.add_argument("--out-perft-csv", default="outputs/tournament_perft.csv")
    parser.add_argument("--out-json", default="outputs/tournament_run.json")
    parser.add_argument("--include-stockfish", action="store_true")
    parser.add_argument("--stockfish-bin", default="stockfish")
    parser.add_argument("--stockfish-skill", type=int, default=1)
    parser.add_argument("--stockfish-elo", type=int, default=None, help="If omitted, uses Stockfish minimum UCI_Elo")
    parser.add_argument(
        "--stockfish-profile",
        action="append",
        default=[],
        help=(
            "Additional Stockfish player profile in format name:skill:elo, "
            "can be repeated (example: --stockfish-profile strong:6:1800)"
        ),
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.count < 2:
        raise ValueError("--count must be >= 2")

    model = load_model_index(Path(args.feature_model))
    rng = random.Random(args.seed)

    config_dir = Path(args.out_config_dir)
    bin_dir = Path(args.out_bin_dir)
    config_dir.mkdir(parents=True, exist_ok=True)
    bin_dir.mkdir(parents=True, exist_ok=True)

    players: list[Player] = []
    seen_configs: set[tuple[str, ...]] = set()

    while len(players) < args.count:
        selected_ids = choose_random_valid_selection(
            model,
            rng,
            optional_prob=args.optional_prob,
            max_attempts=args.max_attempts,
        )
        key = tuple(sorted(selected_ids))
        if key in seen_configs:
            continue
        seen_configs.add(key)

        idx = len(players) + 1
        variant_name = f"tour_variant_{idx:02d}"
        selected_options = [model.options_by_id[option_id] for option_id in key]
        selected_names = [option.name for option in sorted(selected_options, key=lambda item: item.name.lower())]

        config_path = config_dir / f"{variant_name}.json"
        config_payload = {
            "name": variant_name,
            "selected_options": selected_names,
        }
        config_path.write_text(json.dumps(config_payload, indent=2), encoding="utf-8")

        derive_variant(
            feature_model_path=Path(args.feature_model),
            config_path=config_path,
            header_out=Path(args.header_out),
            manifest_out=Path(args.manifest_out),
            enforce_tournament_legality=True,
        )
        run_build(Path(args.makefile))

        binary_path = bin_dir / variant_name
        shutil.copy2(Path(args.engine_bin), binary_path)
        binary_path.chmod(0o755)

        players.append(
            Player(
                name=variant_name,
                config_path=config_path,
                binary_path=binary_path,
                selected_features=selected_names,
                selected_feature_count=len(selected_names),
                perft_mode="cpw",
            )
        )
        print(json.dumps({"derived": variant_name, "selected_features": len(selected_names)}))

    if args.include_stockfish or args.stockfish_profile:
        stockfish_bin = resolve_engine_path(args.stockfish_bin)
        min_elo, max_elo = discover_stockfish_elo_range(stockfish_bin)
        if min_elo is None:
            min_elo = discover_stockfish_min_elo(stockfish_bin)
        if min_elo is None:
            min_elo = 1320
        if max_elo is None:
            max_elo = 3200

        def clamp_elo(elo_value: int) -> int:
            if elo_value < min_elo:
                return min_elo
            if elo_value > max_elo:
                return max_elo
            return elo_value

        profile_specs: list[tuple[str, int, int]] = []
        if args.include_stockfish:
            base_elo = args.stockfish_elo if args.stockfish_elo is not None else min_elo
            profile_specs.append(("base", args.stockfish_skill, base_elo))

        for spec in args.stockfish_profile:
            profile_specs.append(parse_stockfish_profile(spec))

        used_names: set[str] = {player.name for player in players}
        for profile_name, skill, elo in profile_specs:
            final_elo = clamp_elo(elo)
            sf_options = [
                f"setoption name Skill Level value {skill}",
                "setoption name UCI_LimitStrength value true",
                f"setoption name UCI_Elo value {final_elo}",
            ]
            sf_name = f"stockfish_{profile_name}_s{skill}_elo{final_elo}"
            if sf_name in used_names:
                raise ValueError(f"Duplicate player name generated: {sf_name}")
            used_names.add(sf_name)

            sf_features = [
                "Stockfish",
                f"Profile={profile_name}",
                f"Skill Level={skill}",
                "UCI_LimitStrength=true",
                f"UCI_Elo={final_elo}",
            ]
            players.append(
                Player(
                    name=sf_name,
                    binary_path=stockfish_bin,
                    selected_features=sf_features,
                    selected_feature_count=len(sf_features),
                    config_path=None,
                    uci_options=sf_options,
                    perft_mode="stockfish_go_perft",
                )
            )
            print(
                json.dumps(
                    {
                        "added_external": sf_name,
                        "binary": str(stockfish_bin),
                        "uci_options": sf_options,
                    }
                )
            )

    matches: list[dict[str, object]] = []
    standings = {
        player.name: {"variant": player.name, "points": 0.0, "wins": 0, "draws": 0, "losses": 0}
        for player in players
    }

    game_counter = 1
    for left, right in itertools.combinations(players, 2):
        for white, black in ((left, right), (right, left)):
            game_id = f"g{game_counter:02d}"
            t0 = time.perf_counter()
            game = play_game(
                white,
                black,
                game_id=game_id,
                go_depth=args.go_depth,
                movetime_ms=args.movetime_ms,
                max_plies=args.max_plies,
            )
            game["duration_sec"] = round(time.perf_counter() - t0, 3)
            matches.append(game)
            update_standings(standings, game)
            print(json.dumps({"game": game_id, "result": game["result"], "termination": game["termination"]}))
            game_counter += 1

    matches_csv_path = Path(args.out_matches_csv)
    matches_csv_path.parent.mkdir(parents=True, exist_ok=True)
    with matches_csv_path.open("w", newline="", encoding="utf-8") as handle:
        fieldnames = [
            "game_id",
            "white",
            "black",
            "result",
            "termination",
            "plies",
            "duration_sec",
            "last_bestmove",
            "last_score_cp",
            "last_score_mate",
            "moves",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(matches)

    standings_rows = sorted(
        standings.values(),
        key=lambda item: (-item["points"], -item["wins"], item["losses"], item["variant"]),
    )

    standings_csv_path = Path(args.out_standings_csv)
    standings_csv_path.parent.mkdir(parents=True, exist_ok=True)
    with standings_csv_path.open("w", newline="", encoding="utf-8") as handle:
        fieldnames = ["variant", "points", "wins", "draws", "losses"]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(standings_rows)

    perft_rows: list[dict[str, object]] = []
    for player in players:
        got, passed, elapsed = run_perft_check(player, args.perft_depth)
        row = {
            "variant": player.name,
            "selected_feature_count": player.selected_feature_count,
            "selected_features": "|".join(player.selected_features),
            "pass": "PASS" if passed else "FAIL",
            "perft_sec": round(elapsed, 3),
            "config_path": "" if player.config_path is None else str(player.config_path),
            "binary_path": str(player.binary_path),
        }
        for depth in range(1, 7):
            row[f"perft_d{depth}"] = got.get(depth, "")
        perft_rows.append(row)

    perft_csv_path = Path(args.out_perft_csv)
    perft_csv_path.parent.mkdir(parents=True, exist_ok=True)
    with perft_csv_path.open("w", newline="", encoding="utf-8") as handle:
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
            "perft_sec",
            "config_path",
            "binary_path",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(perft_rows)

    payload = {
        "seed": args.seed,
        "variant_count": args.count,
        "include_stockfish": args.include_stockfish,
        "go_depth": args.go_depth,
        "movetime_ms": args.movetime_ms,
        "max_plies": args.max_plies,
        "perft_depth": args.perft_depth,
        "players": [
            {
                "name": player.name,
                "config_path": "" if player.config_path is None else str(player.config_path),
                "binary_path": str(player.binary_path),
                "selected_feature_count": player.selected_feature_count,
                "selected_features": player.selected_features,
                "uci_options": player.uci_options,
            }
            for player in players
        ],
        "standings": standings_rows,
        "matches": matches,
        "perft": perft_rows,
        "expected_perft": {depth: STARTPOS_EXPECTED[depth] for depth in range(1, args.perft_depth + 1)},
    }

    out_json_path = Path(args.out_json)
    out_json_path.parent.mkdir(parents=True, exist_ok=True)
    out_json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print(
        json.dumps(
            {
                "players": len(players),
                "matches_csv": str(matches_csv_path),
                "standings_csv": str(standings_csv_path),
                "perft_csv": str(perft_csv_path),
                "json": str(out_json_path),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
