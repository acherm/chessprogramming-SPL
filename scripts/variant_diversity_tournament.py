#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

import chess
import chess.pgn

from cpw_variability.pl_codegen import derive_variant, run_build

OPENING_LINES_UCI: tuple[tuple[str, ...], ...] = (
    ("e2e4", "e7e5", "g1f3", "b8c6", "f1b5", "a7a6", "b5a4", "g8f6"),
    ("e2e4", "c7c5", "g1f3", "d7d6", "d2d4", "c5d4", "f3d4", "g8f6"),
    ("e2e4", "e7e6", "d2d4", "d7d5", "b1c3", "g8f6", "c1g5", "f8b4"),
    ("d2d4", "d7d5", "c2c4", "e7e6", "b1c3", "g8f6", "c1g5", "f8e7"),
    ("d2d4", "g8f6", "c2c4", "g7g6", "b1c3", "f8g7", "e2e4", "d7d6"),
    ("c2c4", "e7e5", "b1c3", "g8f6", "g1f3", "b8c6", "d2d4", "e5d4"),
    ("g1f3", "d7d5", "d2d4", "g8f6", "c2c4", "e7e6", "b1c3", "f8e7"),
    ("e2e4", "c7c6", "d2d4", "d7d5", "b1c3", "d5e4", "c3e4", "b8d7"),
)


@dataclass
class Player:
    name: str
    kind: str
    cmd: Path
    config_path: Path | None
    selected_features: list[str]
    selected_feature_count: int
    uci_options: list[str]
    anchor_elo: float | None = None


def parse_stockfish_profile(spec: str) -> tuple[str, int, int]:
    parts = [part.strip() for part in spec.split(":")]
    if len(parts) != 3:
        raise ValueError(
            f"Invalid --stockfish-profile '{spec}'. Expected format: name:skill:elo "
            "(example: sf1800:6:1800)"
        )
    name, skill_s, elo_s = parts
    if not name:
        raise ValueError(f"Invalid --stockfish-profile '{spec}': empty profile name")
    return name, int(skill_s), int(elo_s)


def resolve_engine_path(token: str) -> Path:
    path = Path(token).expanduser()
    if path.exists():
        return path.resolve()
    resolved = shutil.which(token)
    if resolved is not None:
        return Path(resolved).resolve()
    raise FileNotFoundError(f"Engine executable not found: {token}")


def load_variant_config_paths(explicit_paths: list[str], csv_path: str) -> list[Path]:
    ordered: list[Path] = []
    seen: set[Path] = set()

    def add_path(raw: str) -> None:
        path = Path(raw)
        if path in seen:
            return
        seen.add(path)
        ordered.append(path)

    for item in explicit_paths:
        add_path(item)

    if csv_path:
        with Path(csv_path).open("r", encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                config_path = str(row.get("config_path", "")).strip()
                if config_path:
                    add_path(config_path)

    return ordered


def write_openings_pgn(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for idx, line in enumerate(OPENING_LINES_UCI, start=1):
            board = chess.Board()
            game = chess.pgn.Game()
            game.headers["Event"] = f"Diversity Opening {idx}"
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


def build_variant_players(
    feature_model: Path,
    config_paths: list[Path],
    makefile: Path,
    engine_bin: Path,
    header_out: Path,
    manifest_out: Path,
    bin_dir: Path,
) -> list[Player]:
    players: list[Player] = []
    used_names: set[str] = set()
    bin_dir.mkdir(parents=True, exist_ok=True)

    for idx, config_path in enumerate(config_paths, start=1):
        if not config_path.exists():
            raise FileNotFoundError(f"Variant config not found: {config_path}")

        report = derive_variant(
            feature_model_path=feature_model,
            config_path=config_path,
            header_out=header_out,
            manifest_out=manifest_out,
            enforce_tournament_legality=True,
        )
        run_build(makefile)

        base_name = str(report.get("variant") or config_path.stem)
        player_name = base_name
        if player_name in used_names:
            player_name = f"{base_name}_{idx:02d}"
        used_names.add(player_name)

        binary_path = bin_dir / player_name
        shutil.copy2(engine_bin, binary_path)
        binary_path.chmod(0o755)

        players.append(
            Player(
                name=player_name,
                kind="variant",
                cmd=binary_path,
                config_path=config_path,
                selected_features=list(report.get("selected_features", [])),
                selected_feature_count=int(report.get("selected_count", 0)),
                uci_options=[],
            )
        )
    return players


def build_stockfish_players(stockfish_bin: Path, profiles: list[str]) -> list[Player]:
    players: list[Player] = []
    for spec in profiles:
        name, skill, elo = parse_stockfish_profile(spec)
        players.append(
            Player(
                name=name,
                kind="stockfish",
                cmd=stockfish_bin,
                config_path=None,
                selected_features=["Stockfish", f"Skill Level={skill}", f"UCI_Elo={elo}", "UCI_LimitStrength=true"],
                selected_feature_count=4,
                uci_options=[
                    f"option.Skill Level={skill}",
                    "option.UCI_LimitStrength=true",
                    f"option.UCI_Elo={elo}",
                ],
                anchor_elo=float(elo),
            )
        )
    return players


def build_search_spec(
    *,
    depth: int | None,
    tc: str,
    st: float | None,
    nodes: int | None,
) -> tuple[list[str], str]:
    if tc:
        return [f"tc={tc}"], f"time control {tc}"
    if st is not None:
        return [f"st={st:g}"], f"fixed move time {st:g}s"
    if nodes is not None:
        return [f"nodes={nodes}"], f"node limit {nodes}"
    chosen_depth = depth if depth is not None else 3
    return [f"depth={chosen_depth}", "tc=inf"], f"search depth {chosen_depth}"


def run_cutechess_tournament(
    players: list[Player],
    openings_pgn: Path,
    output_pgn: Path,
    log_path: Path,
    search_spec: list[str],
    rounds: int,
    games_per_encounter: int,
    concurrency: int,
    maxmoves: int,
    draw_movenumber: int,
    draw_movecount: int,
    draw_score: int,
    resign_movecount: int,
    resign_score: int,
    seed: int,
) -> list[str]:
    cmd = build_cutechess_command(
        players=players,
        openings_pgn=openings_pgn,
        output_pgn=output_pgn,
        search_spec=search_spec,
        rounds=rounds,
        games_per_encounter=games_per_encounter,
        concurrency=concurrency,
        maxmoves=maxmoves,
        draw_movenumber=draw_movenumber,
        draw_movecount=draw_movecount,
        draw_score=draw_score,
        resign_movecount=resign_movecount,
        resign_score=resign_score,
        seed=seed,
    )
    completed = subprocess.run(cmd, capture_output=True, text=True, check=True)
    log_path.write_text(completed.stdout + ("\n" + completed.stderr if completed.stderr else ""), encoding="utf-8")
    return cmd


def build_cutechess_command(
    *,
    players: list[Player],
    openings_pgn: Path,
    output_pgn: Path,
    search_spec: list[str],
    rounds: int,
    games_per_encounter: int,
    concurrency: int,
    maxmoves: int,
    draw_movenumber: int,
    draw_movecount: int,
    draw_score: int,
    resign_movecount: int,
    resign_score: int,
    seed: int,
) -> list[str]:
    cmd: list[str] = ["cutechess-cli"]

    for player in players:
        cmd.extend(["-engine", f"name={player.name}", f"cmd={player.cmd}", "proto=uci"])
        cmd.extend(player.uci_options)

    cmd.extend(["-each", *search_spec])
    cmd.extend(["-tournament", "round-robin"])
    cmd.extend(["-rounds", str(rounds), "-games", str(games_per_encounter)])
    cmd.extend(["-concurrency", str(concurrency)])
    cmd.extend(["-maxmoves", str(maxmoves)])
    cmd.extend(["-draw", f"movenumber={draw_movenumber}", f"movecount={draw_movecount}", f"score={draw_score}"])
    cmd.extend(["-resign", f"movecount={resign_movecount}", f"score={resign_score}"])
    cmd.extend(["-openings", f"file={openings_pgn}", "format=pgn", "order=random", "policy=encounter", "plies=8"])
    cmd.append("-repeat")
    cmd.extend(["-srand", str(seed)])
    cmd.extend(["-pgnout", str(output_pgn), "min"])
    cmd.append("-recover")
    return cmd


def run_anchor_only_tournament(
    players: list[Player],
    openings_pgn: Path,
    output_pgn: Path,
    log_path: Path,
    search_spec: list[str],
    rounds: int,
    games_per_encounter: int,
    concurrency: int,
    match_jobs: int,
    maxmoves: int,
    draw_movenumber: int,
    draw_movecount: int,
    draw_score: int,
    resign_movecount: int,
    resign_score: int,
    seed: int,
) -> list[list[str]]:
    variants = [player for player in players if player.kind == "variant"]
    anchors = [player for player in players if player.kind == "stockfish"]
    if not variants:
        raise ValueError("anchors_only mode requires at least one variant player")
    if not anchors:
        raise ValueError("anchors_only mode requires at least one stockfish anchor")

    matches_dir = output_pgn.parent / "anchor_matches"
    matches_dir.mkdir(parents=True, exist_ok=True)
    per_match_concurrency = max(1, concurrency // max(1, match_jobs))

    tasks: list[tuple[Player, Player, Path, Path, int]] = []
    for variant_index, variant in enumerate(variants):
        for anchor_index, anchor in enumerate(anchors):
            pair_seed = seed + variant_index * 1000 + anchor_index * 17
            stem = f"{variant.name}__vs__{anchor.name}"
            tasks.append(
                (
                    variant,
                    anchor,
                    matches_dir / f"{stem}.pgn",
                    matches_dir / f"{stem}.log",
                    pair_seed,
                )
            )

    commands: list[list[str]] = []

    def run_pair(task: tuple[Player, Player, Path, Path, int]) -> tuple[Path, list[str]]:
        variant, anchor, pair_pgn, pair_log, pair_seed = task
        cmd = build_cutechess_command(
            players=[variant, anchor],
            openings_pgn=openings_pgn,
            output_pgn=pair_pgn,
            search_spec=search_spec,
            rounds=rounds,
            games_per_encounter=games_per_encounter,
            concurrency=per_match_concurrency,
            maxmoves=maxmoves,
            draw_movenumber=draw_movenumber,
            draw_movecount=draw_movecount,
            draw_score=draw_score,
            resign_movecount=resign_movecount,
            resign_score=resign_score,
            seed=pair_seed,
        )
        completed = subprocess.run(cmd, capture_output=True, text=True, check=True)
        pair_log.write_text(completed.stdout + ("\n" + completed.stderr if completed.stderr else ""), encoding="utf-8")
        return pair_pgn, cmd

    ordered_pgns: dict[Path, list[str]] = {}
    with ThreadPoolExecutor(max_workers=max(1, match_jobs)) as executor:
        future_map = {executor.submit(run_pair, task): task for task in tasks}
        for future in as_completed(future_map):
            pair_pgn, cmd = future.result()
            ordered_pgns[pair_pgn] = cmd

    aggregate_parts: list[str] = []
    for pair_pgn in sorted(ordered_pgns):
        commands.append(ordered_pgns[pair_pgn])
        aggregate_parts.append(pair_pgn.read_text(encoding="utf-8", errors="replace").strip())
    output_pgn.write_text("\n\n".join(part for part in aggregate_parts if part) + "\n", encoding="utf-8")

    log_lines = [
        "# Anchor-only tournament logs",
        "",
        f"- variant players: {len(variants)}",
        f"- stockfish anchors: {len(anchors)}",
        f"- pairwise matches: {len(tasks)}",
        f"- outer match jobs: {max(1, match_jobs)}",
        f"- cutechess concurrency per match: {per_match_concurrency}",
        "",
    ]
    for pair_pgn in sorted(ordered_pgns):
        pair_log = pair_pgn.with_suffix(".log")
        log_lines.append(f"## {pair_pgn.stem}")
        log_lines.append("")
        log_lines.append(pair_log.read_text(encoding="utf-8", errors="replace"))
        log_lines.append("")
    log_path.write_text("\n".join(log_lines), encoding="utf-8")
    return commands


def parse_result_to_white_score(result: str) -> float:
    if result == "1-0":
        return 1.0
    if result == "0-1":
        return 0.0
    if result == "1/2-1/2":
        return 0.5
    raise ValueError(f"Unsupported result token: {result}")


def parse_games_from_pgn(pgn_path: Path) -> list[dict[str, object]]:
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
                    "white_score": parse_result_to_white_score(result),
                }
            )
    return rows


def compute_standings(players: list[Player], games: list[dict[str, object]]) -> list[dict[str, object]]:
    table = {
        player.name: {
            "player": player.name,
            "kind": player.kind,
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
        result = str(game["result"])
        table[white]["games"] += 1
        table[black]["games"] += 1

        if result == "1-0":
            table[white]["wins"] += 1
            table[black]["losses"] += 1
            table[white]["score"] += 1.0
        elif result == "0-1":
            table[black]["wins"] += 1
            table[white]["losses"] += 1
            table[black]["score"] += 1.0
        else:
            table[white]["draws"] += 1
            table[black]["draws"] += 1
            table[white]["score"] += 0.5
            table[black]["score"] += 0.5

    for row in table.values():
        games_count = int(row["games"])
        row["score_pct"] = round(float(row["score"]) / games_count * 100.0, 1) if games_count > 0 else 0.0

    return sorted(table.values(), key=lambda r: (-float(r["score"]), -int(r["wins"]), int(r["losses"]), str(r["player"])))


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def compute_anchor_matchups(
    players: list[Player],
    games: list[dict[str, object]],
) -> dict[str, dict[str, tuple[float, int]]]:
    anchor_names = {player.name for player in players if player.kind == "stockfish"}
    matchups: dict[str, dict[str, list[float | int]]] = defaultdict(lambda: defaultdict(lambda: [0.0, 0]))

    for game in games:
        white = str(game["white"])
        black = str(game["black"])
        result = str(game["result"])
        if (white in anchor_names) == (black in anchor_names):
            continue

        if white in anchor_names:
            anchor_name = white
            variant_name = black
            variant_score = 0.0 if result == "1-0" else 0.5 if result == "1/2-1/2" else 1.0
        else:
            anchor_name = black
            variant_name = white
            variant_score = 1.0 if result == "1-0" else 0.5 if result == "1/2-1/2" else 0.0

        matchups[variant_name][anchor_name][0] += variant_score
        matchups[variant_name][anchor_name][1] += 1

    frozen: dict[str, dict[str, tuple[float, int]]] = {}
    for variant_name, anchor_rows in matchups.items():
        frozen[variant_name] = {
            anchor_name: (float(score), int(games_count))
            for anchor_name, (score, games_count) in anchor_rows.items()
        }
    return frozen


def build_strength_buckets(
    players: list[Player],
    standings: list[dict[str, object]],
    games: list[dict[str, object]],
) -> list[dict[str, object]]:
    anchor_rows = [row for row in standings if row["kind"] == "stockfish"]
    if not anchor_rows:
        return []

    anchor_scores = {str(row["player"]): float(row["score_pct"]) for row in anchor_rows}
    strongest_non_top_anchor = max(
        (score for name, score in anchor_scores.items() if name != "sf2500"),
        default=max(anchor_scores.values()),
    )
    weakest_anchor = min(anchor_scores.values())
    anchor_matchups = compute_anchor_matchups(players, games)
    player_by_name = {player.name: player for player in players}

    bucket_rows: list[dict[str, object]] = []
    for row in standings:
        if row["kind"] != "variant":
            continue

        score_pct = float(row["score_pct"])
        if score_pct > strongest_non_top_anchor:
            bucket = "strong"
        elif score_pct >= weakest_anchor:
            bucket = "mid"
        else:
            bucket = "weak"

        matchup = anchor_matchups.get(str(row["player"]), {})
        player = player_by_name[str(row["player"])]
        bucket_row: dict[str, object] = {
            "bucket": bucket,
            "variant_name": row["player"],
            "config_path": str(player.config_path) if player.config_path else "",
            "score_pct": row["score_pct"],
            "score": row["score"],
            "games": row["games"],
            "wins": row["wins"],
            "draws": row["draws"],
            "losses": row["losses"],
        }
        for anchor_name in sorted(anchor_scores):
            score, games_count = matchup.get(anchor_name, (0.0, 0))
            bucket_row[f"vs_{anchor_name}"] = f"{score}/{games_count}"
        bucket_rows.append(bucket_row)

    return bucket_rows


def write_score_ladder(path: Path, standings: list[dict[str, object]]) -> None:
    width = 980
    height = 80 + 22 * len(standings)
    margin_left = 240
    margin_right = 40
    plot_w = width - margin_left - margin_right
    max_pct = 100.0
    colors = {"variant": "#4c78a8", "stockfish": "#e45756"}

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<style>text{font-family:Menlo,Consolas,monospace;font-size:12px;fill:#222}.grid{stroke:#ddd;stroke-width:1}</style>',
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="#fff"/>',
        f'<text x="{width/2:.1f}" y="24" text-anchor="middle">Anchored Diversity Tournament Score Ladder</text>',
    ]

    for step in range(6):
        pct = step * 20
        x = margin_left + (pct / max_pct) * plot_w
        lines.append(f'<line class="grid" x1="{x:.1f}" y1="40" x2="{x:.1f}" y2="{height - 24}"/>')
        lines.append(f'<text x="{x:.1f}" y="{height - 6}" text-anchor="middle">{pct}%</text>')

    for idx, row in enumerate(standings):
        y = 42 + idx * 22
        pct = float(row["score_pct"])
        bar_w = (pct / max_pct) * plot_w
        color = colors.get(str(row["kind"]), "#7f7f7f")
        lines.append(f'<text x="10" y="{y + 12:.1f}">{row["player"]}</text>')
        lines.append(f'<rect x="{margin_left}" y="{y - 2:.1f}" width="{bar_w:.1f}" height="14" fill="{color}"/>')
        lines.append(f'<text x="{margin_left + bar_w + 8:.1f}" y="{y + 10:.1f}">{pct:.1f}%</text>')

    lines.append("</svg>")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_report(
    path: Path,
    players: list[Player],
    standings: list[dict[str, object]],
    strength_buckets: list[dict[str, object]],
    search_label: str,
    args: argparse.Namespace,
) -> None:
    lines = [
        "# Variant Diversity Tournament",
        "",
        "## Setup",
        "",
        f"- variant players: `{sum(1 for p in players if p.kind == 'variant')}`",
        f"- stockfish players: `{sum(1 for p in players if p.kind == 'stockfish')}`",
        f"- search mode: `{search_label}`",
        f"- pairing mode: `{args.pairing_mode}`",
        f"- rounds: `{args.rounds}`",
        f"- games per encounter: `{args.games_per_encounter}`",
        "",
        "## Standings",
        "",
    ]
    for row in standings[: min(len(standings), 12)]:
        lines.append(
            f"- `{row['player']}` ({row['kind']}): `{row['score']}/{row['games']}` ({row['score_pct']}%)"
        )

    if strength_buckets:
        lines.extend(["", "## Strength Buckets", ""])
        for bucket in ("strong", "mid", "weak"):
            bucket_rows = [row for row in strength_buckets if row["bucket"] == bucket]
            if not bucket_rows:
                continue
            lines.append(f"- `{bucket}`: " + ", ".join(f"`{row['variant_name']}`" for row in bucket_rows))

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a low-cost diversity tournament on explicit variant configs")
    parser.add_argument("--feature-model", default="outputs/feature_model.json")
    parser.add_argument("--variant-config", action="append", default=[], help="Path to a variant config JSON. Can be repeated.")
    parser.add_argument("--variant-config-csv", default="", help="CSV file with a config_path column, for example a prepared shortlist.")
    parser.add_argument("--makefile", default="c_engine_pl/Makefile")
    parser.add_argument("--engine-bin", default="c_engine_pl/build/engine_pl")
    parser.add_argument("--header-out", default="c_engine_pl/include/generated/variant_config.h")
    parser.add_argument("--manifest-out", default="c_engine_pl/include/generated/variant_manifest.json")
    parser.add_argument("--stockfish-bin", default="stockfish")
    parser.add_argument("--stockfish-profile", action="append", default=[])
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--depth", type=int, default=None, help="Fixed search depth. Default when no time control is provided.")
    mode_group.add_argument("--tc", default="", help="Cutechess time control, for example 10+0.1 or 40/60+0.6.")
    mode_group.add_argument("--st", type=float, default=None, help="Fixed move time in seconds.")
    mode_group.add_argument("--nodes", type=int, default=None, help="Fixed node limit per move.")
    parser.add_argument("--pairing-mode", choices=["full", "anchors_only"], default="full")
    parser.add_argument("--rounds", type=int, default=1)
    parser.add_argument("--games-per-encounter", type=int, default=2)
    parser.add_argument("--concurrency", type=int, default=2)
    parser.add_argument("--match-jobs", type=int, default=1, help="Number of pairwise cutechess matches to run in parallel in anchors_only mode.")
    parser.add_argument("--maxmoves", type=int, default=140)
    parser.add_argument("--draw-movenumber", type=int, default=30)
    parser.add_argument("--draw-movecount", type=int, default=8)
    parser.add_argument("--draw-score", type=int, default=20)
    parser.add_argument("--resign-movecount", type=int, default=4)
    parser.add_argument("--resign-score", type=int, default=900)
    parser.add_argument("--seed", type=int, default=20260409)
    parser.add_argument("--out-dir", default="outputs/variant_diversity_tournament")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    config_paths = load_variant_config_paths(args.variant_config, args.variant_config_csv)
    if len(config_paths) < 2:
        raise ValueError("Provide at least 2 variant configs via --variant-config and/or --variant-config-csv")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    bin_dir = out_dir / "variant_bins"
    openings_pgn = out_dir / "openings.pgn"
    pgn_out = out_dir / "games.pgn"
    log_out = out_dir / "cutechess.log"
    standings_csv = out_dir / "standings.csv"
    games_csv = out_dir / "games.csv"
    buckets_csv = out_dir / "strength_buckets.csv"
    ladder_svg = out_dir / "score_ladder.svg"
    summary_json = out_dir / "summary.json"
    report_md = out_dir / "report.md"

    players = build_variant_players(
        feature_model=Path(args.feature_model),
        config_paths=config_paths,
        makefile=Path(args.makefile),
        engine_bin=Path(args.engine_bin),
        header_out=Path(args.header_out),
        manifest_out=Path(args.manifest_out),
        bin_dir=bin_dir,
    )
    if args.stockfish_profile:
        players.extend(build_stockfish_players(resolve_engine_path(args.stockfish_bin), args.stockfish_profile))

    search_spec, search_label = build_search_spec(
        depth=args.depth,
        tc=args.tc,
        st=args.st,
        nodes=args.nodes,
    )

    write_openings_pgn(openings_pgn)
    if args.pairing_mode == "anchors_only":
        if not args.stockfish_profile:
            raise ValueError("anchors_only mode requires at least one --stockfish-profile")
        cmd = run_anchor_only_tournament(
            players=players,
            openings_pgn=openings_pgn,
            output_pgn=pgn_out,
            log_path=log_out,
            search_spec=search_spec,
            rounds=args.rounds,
            games_per_encounter=args.games_per_encounter,
            concurrency=args.concurrency,
            match_jobs=args.match_jobs,
            maxmoves=args.maxmoves,
            draw_movenumber=args.draw_movenumber,
            draw_movecount=args.draw_movecount,
            draw_score=args.draw_score,
            resign_movecount=args.resign_movecount,
            resign_score=args.resign_score,
            seed=args.seed,
        )
    else:
        cmd = run_cutechess_tournament(
            players=players,
            openings_pgn=openings_pgn,
            output_pgn=pgn_out,
            log_path=log_out,
            search_spec=search_spec,
            rounds=args.rounds,
            games_per_encounter=args.games_per_encounter,
            concurrency=args.concurrency,
            maxmoves=args.maxmoves,
            draw_movenumber=args.draw_movenumber,
            draw_movecount=args.draw_movecount,
            draw_score=args.draw_score,
            resign_movecount=args.resign_movecount,
            resign_score=args.resign_score,
            seed=args.seed,
        )

    games = parse_games_from_pgn(pgn_out)
    standings = compute_standings(players, games)
    strength_buckets = build_strength_buckets(players, standings, games)
    write_csv(standings_csv, standings)
    write_csv(games_csv, games)
    write_csv(buckets_csv, strength_buckets)
    write_score_ladder(ladder_svg, standings)
    write_report(report_md, players, standings, strength_buckets, search_label, args)

    summary = {
        "players": [
            {
                "name": player.name,
                "kind": player.kind,
                "cmd": str(player.cmd),
                "config_path": str(player.config_path) if player.config_path else "",
                "selected_feature_count": player.selected_feature_count,
                "selected_features": player.selected_features,
                "uci_options": player.uci_options,
                "anchor_elo": player.anchor_elo,
            }
            for player in players
        ],
        "params": {
            "search_mode": search_label,
            "depth": args.depth,
            "tc": args.tc,
            "st": args.st,
            "nodes": args.nodes,
            "rounds": args.rounds,
            "games_per_encounter": args.games_per_encounter,
            "concurrency": args.concurrency,
            "pairing_mode": args.pairing_mode,
            "match_jobs": args.match_jobs,
            "seed": args.seed,
        },
        "cutechess_command": cmd,
        "game_count": len(games),
        "standings": standings,
        "strength_buckets": strength_buckets,
    }
    summary_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
