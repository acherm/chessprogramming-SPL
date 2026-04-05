from __future__ import annotations

import argparse
import csv
import json
import time
from pathlib import Path

import chess
import chess.engine
import chess.pgn


STATS_KEYS = [
    "tt_probe",
    "tt_hit",
    "tt_cut",
    "tt_store",
    "eval",
    "eval_cache_hit",
    "movegen",
    "attack",
    "beta_cut",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a direct UCI match against a Stockfish Elo anchor.")
    parser.add_argument("--engine-bin", required=True, help="Path to the variant engine binary.")
    parser.add_argument("--variant-name", required=True, help="Label used in outputs.")
    parser.add_argument("--out-dir", required=True, help="Output directory.")
    parser.add_argument("--stockfish-bin", default="/opt/homebrew/bin/stockfish")
    parser.add_argument("--stockfish-elo", type=int, default=2500)
    parser.add_argument("--stockfish-skill", type=int, default=20)
    parser.add_argument("--movetime-ms", type=int, default=2000)
    parser.add_argument("--opening-pgn", default="outputs/proper_elo_tournament_strong_v1/openings.pgn")
    parser.add_argument("--opening-count", type=int, default=2)
    parser.add_argument("--opening-plies", type=int, default=8)
    parser.add_argument("--max-fullmoves", type=int, default=80)
    parser.add_argument("--engine-timeout-sec", type=float, default=20.0)
    return parser.parse_args()


def load_openings(path: Path, opening_count: int, opening_plies: int) -> list[dict[str, str]]:
    openings: list[dict[str, str]] = []
    with path.open(encoding="utf-8") as handle:
        while len(openings) < opening_count:
            game = chess.pgn.read_game(handle)
            if game is None:
                break
            board = game.board()
            moves: list[str] = []
            for idx, move in enumerate(game.mainline_moves()):
                if idx >= opening_plies:
                    break
                moves.append(move.uci())
                board.push(move)
            openings.append(
                {
                    "opening_index": str(len(openings) + 1),
                    "fen": board.fen(),
                    "opening_moves_uci": " ".join(moves),
                }
            )
    if len(openings) < opening_count:
        raise RuntimeError(f"not enough openings in {path}")
    return openings


def role_name(role: str, variant_name: str, stockfish_name: str) -> str:
    return variant_name if role == "variant" else stockfish_name


def result_for_winner(winner_role: str | None) -> str:
    if winner_role is None:
        return "1/2-1/2"
    return "1-0" if winner_role == "white" else "0-1"


def parse_stats_string(stats_string: object) -> dict[str, int]:
    parsed = {key: 0 for key in STATS_KEYS}
    if not isinstance(stats_string, str):
        return parsed
    for token in stats_string.split():
        if "=" not in token:
            continue
        key, value = token.split("=", 1)
        if key in parsed:
            try:
                parsed[key] = int(value)
            except ValueError:
                parsed[key] = 0
    return parsed


def init_variant_totals() -> dict[str, float]:
    totals: dict[str, float] = {
        "variant_move_count": 0,
        "variant_depth_sum": 0.0,
        "variant_depth_max": 0,
        "variant_nodes_total": 0,
    }
    for key in STATS_KEYS:
        totals[f"variant_{key}_total"] = 0
    return totals


def merge_variant_stats(target: dict[str, float], info: chess.engine.InfoDict) -> None:
    depth = info.get("depth")
    if isinstance(depth, int):
        target["variant_move_count"] += 1
        target["variant_depth_sum"] += depth
        if depth > target["variant_depth_max"]:
            target["variant_depth_max"] = depth

    nodes = info.get("nodes")
    if isinstance(nodes, int):
        target["variant_nodes_total"] += nodes

    parsed = parse_stats_string(info.get("string"))
    for key, value in parsed.items():
        target[f"variant_{key}_total"] += value


def run_game(
    spec: dict[str, str],
    game_no: int,
    args: argparse.Namespace,
    variant_name: str,
    stockfish_name: str,
) -> tuple[dict[str, object], chess.pgn.Game]:
    variant = chess.engine.SimpleEngine.popen_uci(args.engine_bin, timeout=args.engine_timeout_sec)
    stockfish = chess.engine.SimpleEngine.popen_uci(args.stockfish_bin, timeout=args.engine_timeout_sec)
    stockfish.configure(
        {
            "Skill Level": args.stockfish_skill,
            "UCI_LimitStrength": True,
            "UCI_Elo": args.stockfish_elo,
            "Threads": 1,
            "Hash": 64,
        }
    )

    board = chess.Board(spec["fen"])
    game = chess.pgn.Game()
    game.headers["Event"] = f"{variant_name} vs {stockfish_name}"
    game.headers["Site"] = "local-uci"
    game.headers["Round"] = str(game_no)
    game.headers["White"] = role_name(spec["white_role"], variant_name, stockfish_name)
    game.headers["Black"] = role_name(spec["black_role"], variant_name, stockfish_name)
    game.headers["SetUp"] = "1"
    game.headers["FEN"] = spec["fen"]
    game.headers["OpeningIndex"] = spec["opening_index"]
    game.headers["OpeningMoves"] = spec["opening_moves_uci"]

    node = game
    variant_depths: list[int] = []
    stockfish_depths: list[int] = []
    variant_totals = init_variant_totals()
    termination = "normal"
    winner_role: str | None = None
    illegal = False
    start = time.time()

    try:
        for _ in range(args.max_fullmoves * 2):
            turn_role = spec["white_role"] if board.turn == chess.WHITE else spec["black_role"]
            engine = variant if turn_role == "variant" else stockfish
            try:
                result = engine.play(
                    board,
                    chess.engine.Limit(time=args.movetime_ms / 1000.0),
                    info=chess.engine.INFO_ALL,
                )
            except Exception as exc:  # pragma: no cover - external engine failure path
                termination = f"engine_exception:{turn_role}:{type(exc).__name__}"
                winner_role = "black" if board.turn == chess.WHITE else "white"
                break

            move = result.move
            if move is None or move not in board.legal_moves:
                termination = f"illegal_move:{turn_role}"
                illegal = True
                winner_role = "black" if board.turn == chess.WHITE else "white"
                break

            depth = result.info.get("depth")
            if isinstance(depth, int):
                if turn_role == "variant":
                    variant_depths.append(depth)
                else:
                    stockfish_depths.append(depth)

            if turn_role == "variant":
                merge_variant_stats(variant_totals, result.info)

            node = node.add_variation(move)
            board.push(move)

            outcome = board.outcome(claim_draw=True)
            if outcome is not None:
                termination = outcome.termination.name.lower()
                if outcome.winner is None:
                    winner_role = None
                else:
                    winner_role = "white" if outcome.winner else "black"
                break
        else:
            termination = "move_cap"
            winner_role = None
    finally:
        variant.quit()
        stockfish.quit()

    result_code = result_for_winner(winner_role)
    game.headers["Result"] = result_code
    game.headers["Termination"] = termination

    variant_score = 0.5 if result_code == "1/2-1/2" else 0.0
    if result_code == "1-0" and spec["white_role"] == "variant":
        variant_score = 1.0
    elif result_code == "0-1" and spec["black_role"] == "variant":
        variant_score = 1.0

    row: dict[str, object] = {
        "game": game_no,
        "opening_index": spec["opening_index"],
        "white": role_name(spec["white_role"], variant_name, stockfish_name),
        "black": role_name(spec["black_role"], variant_name, stockfish_name),
        "result": result_code,
        "termination": termination,
        "variant_score": variant_score,
        "variant_color": "white" if spec["white_role"] == "variant" else "black",
        "illegal": illegal,
        "elapsed_sec": round(time.time() - start, 3),
        "variant_avg_depth": round(sum(variant_depths) / len(variant_depths), 2) if variant_depths else 0.0,
        "variant_max_depth": max(variant_depths) if variant_depths else 0,
        "stockfish_avg_depth": round(sum(stockfish_depths) / len(stockfish_depths), 2) if stockfish_depths else 0.0,
        "stockfish_max_depth": max(stockfish_depths) if stockfish_depths else 0,
        "ply_count": board.ply(),
        "variant_move_count": int(variant_totals["variant_move_count"]),
        "variant_nodes_total": int(variant_totals["variant_nodes_total"]),
    }
    for key in STATS_KEYS:
        row[f"variant_{key}_total"] = int(variant_totals[f"variant_{key}_total"])

    return row, game


def write_outputs(rows: list[dict[str, object]], games: list[chess.pgn.Game], args: argparse.Namespace, variant_name: str, stockfish_name: str) -> None:
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    with (out_dir / "games.pgn").open("w", encoding="utf-8") as handle:
        for game in games:
            print(game, file=handle, end="\n\n")

    with (out_dir / "games.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    score = sum(float(row["variant_score"]) for row in rows)
    wins = sum(1 for row in rows if float(row["variant_score"]) == 1.0)
    draws = sum(1 for row in rows if float(row["variant_score"]) == 0.5)
    losses = len(rows) - wins - draws
    white_games = sum(1 for row in rows if row["variant_color"] == "white")
    white_wins = sum(1 for row in rows if row["variant_color"] == "white" and float(row["variant_score"]) == 1.0)
    black_games = sum(1 for row in rows if row["variant_color"] == "black")
    black_wins = sum(1 for row in rows if row["variant_color"] == "black" and float(row["variant_score"]) == 1.0)
    illegal_count = sum(1 for row in rows if bool(row["illegal"]))
    move_cap_draws = sum(1 for row in rows if row["termination"] == "move_cap")
    variant_depths = [float(row["variant_avg_depth"]) for row in rows if float(row["variant_avg_depth"]) > 0]
    stockfish_depths = [float(row["stockfish_avg_depth"]) for row in rows if float(row["stockfish_avg_depth"]) > 0]

    totals = {key: sum(int(row[f"variant_{key}_total"]) for row in rows) for key in STATS_KEYS}
    total_variant_moves = sum(int(row["variant_move_count"]) for row in rows)
    total_variant_nodes = sum(int(row["variant_nodes_total"]) for row in rows)

    observability = {
        **totals,
        "variant_moves_total": total_variant_moves,
        "variant_nodes_total": total_variant_nodes,
        "tt_hit_rate": round(totals["tt_hit"] / totals["tt_probe"], 4) if totals["tt_probe"] else 0.0,
        "tt_cut_rate": round(totals["tt_cut"] / totals["tt_probe"], 4) if totals["tt_probe"] else 0.0,
        "eval_cache_hit_rate": round(totals["eval_cache_hit"] / totals["eval"], 4) if totals["eval"] else 0.0,
        "attack_per_node": round(totals["attack"] / total_variant_nodes, 4) if total_variant_nodes else 0.0,
        "movegen_per_node": round(totals["movegen"] / total_variant_nodes, 4) if total_variant_nodes else 0.0,
    }

    summary = {
        "variant": variant_name,
        "opponent": stockfish_name,
        "setup": {
            "runner": "python-chess UCI referee",
            "movetime_ms": args.movetime_ms,
            "opening_plies": args.opening_plies,
            "opening_count": args.opening_count,
            "games": len(rows),
            "max_fullmoves": args.max_fullmoves,
            "stockfish_options": {
                "Skill Level": args.stockfish_skill,
                "UCI_LimitStrength": True,
                "UCI_Elo": args.stockfish_elo,
                "Threads": 1,
                "Hash": 64,
            },
        },
        "result": {
            "wins": wins,
            "losses": losses,
            "draws": draws,
            "score": score,
            "games": len(rows),
            "score_pct": round(100.0 * score / len(rows), 1),
            "white_games": white_games,
            "white_wins": white_wins,
            "black_games": black_games,
            "black_wins": black_wins,
            "illegal_count": illegal_count,
            "move_cap_draws": move_cap_draws,
        },
        "depth": {
            "variant_avg_depth_across_games": round(sum(variant_depths) / len(variant_depths), 2) if variant_depths else 0.0,
            "variant_max_depth_seen": max((int(row["variant_max_depth"]) for row in rows), default=0),
            "stockfish_avg_depth_across_games": round(sum(stockfish_depths) / len(stockfish_depths), 2) if stockfish_depths else 0.0,
            "stockfish_max_depth_seen": max((int(row["stockfish_max_depth"]) for row in rows), default=0),
        },
        "observability": observability,
    }

    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    with (out_dir / "summary.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "variant",
                "games",
                "wins",
                "losses",
                "draws",
                "score",
                "score_pct",
                "white_wins",
                "black_wins",
                "illegal_count",
                "move_cap_draws",
                "variant_avg_depth_across_games",
                "variant_max_depth_seen",
                "stockfish_avg_depth_across_games",
                "stockfish_max_depth_seen",
                "tt_probe",
                "tt_hit",
                "tt_cut",
                "tt_store",
                "eval",
                "eval_cache_hit",
                "movegen",
                "attack",
                "beta_cut",
                "variant_moves_total",
                "variant_nodes_total",
                "tt_hit_rate",
                "tt_cut_rate",
                "eval_cache_hit_rate",
                "attack_per_node",
                "movegen_per_node",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "variant": variant_name,
                "games": len(rows),
                "wins": wins,
                "losses": losses,
                "draws": draws,
                "score": score,
                "score_pct": round(100.0 * score / len(rows), 1),
                "white_wins": white_wins,
                "black_wins": black_wins,
                "illegal_count": illegal_count,
                "move_cap_draws": move_cap_draws,
                "variant_avg_depth_across_games": summary["depth"]["variant_avg_depth_across_games"],
                "variant_max_depth_seen": summary["depth"]["variant_max_depth_seen"],
                "stockfish_avg_depth_across_games": summary["depth"]["stockfish_avg_depth_across_games"],
                "stockfish_max_depth_seen": summary["depth"]["stockfish_max_depth_seen"],
                **observability,
            }
        )

    report = f"""# {variant_name} vs {stockfish_name}

## Setup
- Variant: `{variant_name}`
- Opponent: `{stockfish_name}`
- Move time: `{args.movetime_ms} ms` per move
- Games: `{len(rows)}`
- Opening seeds: `{args.opening_count}` with color swap

## Result
- Score: `{score}/{len(rows)}` ({round(100.0 * score / len(rows), 1)}%)
- Record: `{wins}W {draws}D {losses}L`
- Illegal moves: `{illegal_count}`

## Depth
- Variant average depth across games: `{summary["depth"]["variant_avg_depth_across_games"]}`
- Variant max depth seen: `{summary["depth"]["variant_max_depth_seen"]}`
- Stockfish average depth across games: `{summary["depth"]["stockfish_avg_depth_across_games"]}`
- Stockfish max depth seen: `{summary["depth"]["stockfish_max_depth_seen"]}`

## TT / Search Observability
- TT probes / hits / cutoffs / stores: `{observability["tt_probe"]}` / `{observability["tt_hit"]}` / `{observability["tt_cut"]}` / `{observability["tt_store"]}`
- TT hit rate: `{observability["tt_hit_rate"]}`
- TT cutoff rate: `{observability["tt_cut_rate"]}`
- Eval calls / eval cache hits: `{observability["eval"]}` / `{observability["eval_cache_hit"]}`
- Eval cache hit rate: `{observability["eval_cache_hit_rate"]}`
- Movegen total: `{observability["movegen"]}`
- Attack total: `{observability["attack"]}`
- Attack per node: `{observability["attack_per_node"]}`
- Movegen per node: `{observability["movegen_per_node"]}`
"""
    (out_dir / "report.md").write_text(report, encoding="utf-8")


def main() -> None:
    args = parse_args()
    variant_name = args.variant_name
    stockfish_name = f"stockfish_{args.stockfish_elo}"
    openings = load_openings(Path(args.opening_pgn), args.opening_count, args.opening_plies)

    schedule: list[dict[str, str]] = []
    for opening in openings:
        schedule.append(opening | {"white_role": "variant", "black_role": "stockfish"})
        schedule.append(opening | {"white_role": "stockfish", "black_role": "variant"})

    rows: list[dict[str, object]] = []
    games: list[chess.pgn.Game] = []
    for idx, spec in enumerate(schedule, start=1):
        row, game = run_game(spec, idx, args, variant_name, stockfish_name)
        rows.append(row)
        games.append(game)
        print(json.dumps(row), flush=True)

    write_outputs(rows, games, args, variant_name, stockfish_name)


if __name__ == "__main__":
    main()
