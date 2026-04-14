#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import random
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
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

# Curated opening suite (UCI moves). Each line is 8 plies to diversify starts.
OPENING_LINES_UCI: tuple[tuple[str, ...], ...] = (
    ("e2e4", "e7e5", "g1f3", "b8c6", "f1b5", "a7a6", "b5a4", "g8f6"),
    ("e2e4", "e7e5", "g1f3", "b8c6", "f1c4", "f8c5", "c2c3", "g8f6"),
    ("e2e4", "c7c5", "g1f3", "d7d6", "d2d4", "c5d4", "f3d4", "g8f6"),
    ("e2e4", "c7c5", "g1f3", "b8c6", "d2d4", "c5d4", "f3d4", "g7g6"),
    ("e2e4", "e7e6", "d2d4", "d7d5", "b1c3", "g8f6", "c1g5", "f8b4"),
    ("d2d4", "d7d5", "c2c4", "e7e6", "b1c3", "g8f6", "c1g5", "f8e7"),
    ("d2d4", "g8f6", "c2c4", "g7g6", "b1c3", "f8g7", "e2e4", "d7d6"),
    ("d2d4", "g8f6", "c2c4", "e7e6", "g1f3", "d7d5", "b1c3", "f8e7"),
    ("c2c4", "e7e5", "b1c3", "g8f6", "g1f3", "b8c6", "d2d4", "e5d4"),
    ("g1f3", "d7d5", "d2d4", "g8f6", "c2c4", "e7e6", "b1c3", "f8e7"),
    ("e2e4", "c7c6", "d2d4", "d7d5", "b1c3", "d5e4", "c3e4", "b8d7"),
    ("e2e4", "d7d5", "e4d5", "d8d5", "b1c3", "d5a5", "d2d4", "c7c6"),
    ("d2d4", "f7f5", "c2c4", "g8f6", "b1c3", "e7e6", "g2g3", "f8b4"),
    ("e2e4", "g7g6", "d2d4", "f8g7", "b1c3", "d7d6", "c1e3", "g8f6"),
    ("c2c4", "c7c5", "b1c3", "b8c6", "g1f3", "g8f6", "d2d4", "c5d4"),
    ("e2e4", "e7e5", "g1f3", "g8f6", "f3e5", "d7d6", "e5f3", "f6e4"),
    ("d2d4", "d7d5", "g1f3", "g8f6", "c2c4", "c7c6", "b1c3", "e7e6"),
    ("g1f3", "g8f6", "g2g3", "g7g6", "f1g2", "f8g7", "e1g1", "e8g8"),
    ("d2d4", "g8f6", "c2c4", "c7c5", "d4d5", "e7e6", "b1c3", "e6d5"),
    ("e2e4", "c7c5", "g1f3", "e7e6", "d2d4", "c5d4", "f3d4", "a7a6"),
)

DEFAULT_STOCKFISH_PROFILES: tuple[tuple[str, int, int], ...] = (
    ("stockfish_1320", 1, 1320),
    ("stockfish_1800", 6, 1800),
    ("stockfish_2150", 10, 2150),
    ("stockfish_2500", 20, 2500),
)


@dataclass
class Player:
    name: str
    kind: str  # variant | stockfish
    cmd: Path
    selected_features: list[str]
    selected_feature_count: int
    config_path: Path | None
    uci_options: list[str]
    anchor_elo: float | None


def _expected_score(rating_a: float, rating_b: float) -> float:
    return 1.0 / (1.0 + math.pow(10.0, (rating_b - rating_a) / 400.0))


def _parse_result_to_white_score(result: str) -> float:
    if result == "1-0":
        return 1.0
    if result == "0-1":
        return 0.0
    if result == "1/2-1/2":
        return 0.5
    raise ValueError(f"Unsupported result token: {result}")


def parse_stockfish_profile(spec: str) -> tuple[str, int, int]:
    parts = [part.strip() for part in spec.split(":")]
    if len(parts) != 3:
        raise ValueError(
            f"Invalid --stockfish-profile '{spec}'. Expected format: name:skill:elo "
            "(example: sf2000:10:2000)"
        )
    name, skill_s, elo_s = parts
    if not name:
        raise ValueError(f"Invalid --stockfish-profile '{spec}': empty profile name")
    return name, int(skill_s), int(elo_s)


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
    chosen_depth = depth if depth is not None else 4
    return [f"depth={chosen_depth}", "tc=inf"], f"search depth {chosen_depth}"


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


def build_variant_players(
    feature_model: Path,
    count: int,
    seed: int | None,
    optional_prob: float,
    max_attempts: int,
    makefile: Path,
    engine_bin: Path,
    header_out: Path,
    manifest_out: Path,
    config_dir: Path,
    bin_dir: Path,
) -> list[Player]:
    model = load_model_index(feature_model)
    rng = random.Random(seed)

    config_dir.mkdir(parents=True, exist_ok=True)
    bin_dir.mkdir(parents=True, exist_ok=True)

    players: list[Player] = []
    seen_configs: set[tuple[str, ...]] = set()

    while len(players) < count:
        selected_ids = choose_random_valid_selection(model, rng, optional_prob=optional_prob, max_attempts=max_attempts)
        key = tuple(sorted(selected_ids))
        if key in seen_configs:
            continue
        seen_configs.add(key)

        idx = len(players) + 1
        variant_name = f"elo_variant_{idx:02d}"

        selected_options = [model.options_by_id[option_id] for option_id in key]
        selected_names = [option.name for option in sorted(selected_options, key=lambda item: item.name.lower())]

        config_path = config_dir / f"{variant_name}.json"
        config_path.write_text(
            json.dumps({"name": variant_name, "selected_options": selected_names}, indent=2),
            encoding="utf-8",
        )

        derive_variant(
            feature_model_path=feature_model,
            config_path=config_path,
            header_out=header_out,
            manifest_out=manifest_out,
            enforce_tournament_legality=True,
        )
        run_build(makefile)

        binary_path = bin_dir / variant_name
        shutil.copy2(engine_bin, binary_path)
        binary_path.chmod(0o755)

        players.append(
            Player(
                name=variant_name,
                kind="variant",
                cmd=binary_path,
                selected_features=selected_names,
                selected_feature_count=len(selected_names),
                config_path=config_path,
                uci_options=[],
                anchor_elo=None,
            )
        )
        print(json.dumps({"derived_variant": variant_name, "selected_features": len(selected_names)}))

    return players


def build_variant_players_from_configs(
    feature_model: Path,
    config_paths: list[Path],
    makefile: Path,
    engine_bin: Path,
    header_out: Path,
    manifest_out: Path,
    bin_dir: Path,
) -> list[Player]:
    bin_dir.mkdir(parents=True, exist_ok=True)

    players: list[Player] = []
    used_names: set[str] = set()
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
        variant_name = base_name
        if variant_name in used_names:
            variant_name = f"{base_name}_{idx:02d}"
        used_names.add(variant_name)
        binary_path = bin_dir / variant_name
        shutil.copy2(engine_bin, binary_path)
        binary_path.chmod(0o755)

        players.append(
            Player(
                name=variant_name,
                kind="variant",
                cmd=binary_path,
                selected_features=list(report.get("selected_features", [])),
                selected_feature_count=int(report.get("selected_count", 0)),
                config_path=config_path,
                uci_options=[],
                anchor_elo=None,
            )
        )
        print(
            json.dumps(
                {
                    "derived_variant": variant_name,
                    "config": str(config_path),
                    "selected_features": int(report.get("selected_count", 0)),
                }
            )
        )

    return players


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


def build_stockfish_players(stockfish_bin: Path, profiles: list[str]) -> list[Player]:
    players: list[Player] = []
    profile_rows = profiles or [f"{name}:{skill}:{elo}" for name, skill, elo in DEFAULT_STOCKFISH_PROFILES]
    for spec in profile_rows:
        name, skill, elo = parse_stockfish_profile(spec)
        opts = [
            f"option.Skill Level={skill}",
            "option.UCI_LimitStrength=true",
            f"option.UCI_Elo={elo}",
        ]
        players.append(
            Player(
                name=name,
                kind="stockfish",
                cmd=stockfish_bin,
                selected_features=["Stockfish", f"Skill Level={skill}", f"UCI_Elo={elo}", "UCI_LimitStrength=true"],
                selected_feature_count=4,
                config_path=None,
                uci_options=opts,
                anchor_elo=float(elo),
            )
        )
    return players


def load_anchor_players_from_csv(csv_path: str) -> list[Player]:
    if not csv_path:
        return []

    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"Anchor CSV not found: {path}")

    players: list[Player] = []
    used_names: set[str] = set()
    with path.open("r", encoding="utf-8", newline="") as handle:
        for idx, row in enumerate(csv.DictReader(handle), start=1):
            raw_name = str(row.get("name", "")).strip()
            raw_cmd = str(row.get("cmd", "")).strip()
            raw_elo = str(row.get("elo", "")).strip()
            if not raw_name or not raw_cmd or not raw_elo:
                raise ValueError(
                    f"Invalid anchor row #{idx} in {path}: expected non-empty name, cmd, elo columns"
                )

            name = raw_name
            if name in used_names:
                name = f"{raw_name}_{idx:02d}"
            used_names.add(name)

            cmd = resolve_engine_path(raw_cmd)
            elo = float(raw_elo)
            uci_options_raw = str(row.get("uci_options", "")).strip()
            selected_features_raw = str(row.get("selected_features", "")).strip()
            uci_options = [part.strip() for part in uci_options_raw.split("|") if part.strip()]
            selected_features = [part.strip() for part in selected_features_raw.split("|") if part.strip()]
            if not selected_features:
                selected_features = ["External Anchor"]

            players.append(
                Player(
                    name=name,
                    kind="anchor",
                    cmd=cmd,
                    selected_features=selected_features + [f"Published Elo={elo:g}"],
                    selected_feature_count=len(selected_features) + 1,
                    config_path=None,
                    uci_options=uci_options,
                    anchor_elo=elo,
                )
            )
    return players


def write_openings_pgn(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for idx, line in enumerate(OPENING_LINES_UCI, start=1):
            board = chess.Board()
            game = chess.pgn.Game()
            game.headers["Event"] = f"CPW Opening {idx}"
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
    log_path.parent.mkdir(parents=True, exist_ok=True)
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


def parse_games_from_pgn(pgn_path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    with pgn_path.open("r", encoding="utf-8", errors="replace") as handle:
        while True:
            game = chess.pgn.read_game(handle)
            if game is None:
                break
            white = game.headers.get("White", "")
            black = game.headers.get("Black", "")
            result = game.headers.get("Result", "*")
            termination = game.headers.get("Termination", "")
            if result not in {"1-0", "0-1", "1/2-1/2"}:
                continue
            rows.append(
                {
                    "white": white,
                    "black": black,
                    "result": result,
                    "termination": termination,
                    "white_score": _parse_result_to_white_score(result),
                }
            )
    return rows


def compute_standings(players: list[Player], games: list[dict[str, object]]) -> list[dict[str, object]]:
    table = {
        p.name: {
            "player": p.name,
            "kind": p.kind,
            "games": 0,
            "wins": 0,
            "draws": 0,
            "losses": 0,
            "score": 0.0,
            "score_pct": 0.0,
        }
        for p in players
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
        row["score_pct"] = (float(row["score"]) / games_count * 100.0) if games_count > 0 else 0.0

    return sorted(
        table.values(),
        key=lambda r: (-float(r["score"]), -int(r["wins"]), int(r["losses"]), str(r["player"])),
    )


def estimate_elo_anchored(players: list[Player], games: list[dict[str, object]]) -> list[dict[str, object]]:
    anchors = {p.name: float(p.anchor_elo) for p in players if p.anchor_elo is not None}
    unknown = [p.name for p in players if p.anchor_elo is None]

    if not unknown:
        return []

    anchor_mean = sum(anchors.values()) / len(anchors) if anchors else 1800.0
    ratings = {name: anchor_mean for name in unknown}

    k = math.log(10.0) / 400.0
    k2 = k * k

    for _ in range(200):
        max_step = 0.0
        for target in unknown:
            grad = 0.0
            hess = 0.0

            for game in games:
                white = str(game["white"])
                black = str(game["black"])
                s_white = float(game["white_score"])

                if white == target:
                    ra = ratings[target]
                    rb = anchors.get(black, ratings.get(black, anchor_mean))
                    exp = _expected_score(ra, rb)
                    grad += k * (s_white - exp)
                    hess -= k2 * exp * (1.0 - exp)
                elif black == target:
                    rb = ratings[target]
                    ra = anchors.get(white, ratings.get(white, anchor_mean))
                    s_black = 1.0 - s_white
                    exp = _expected_score(rb, ra)
                    grad += k * (s_black - exp)
                    hess -= k2 * exp * (1.0 - exp)

            if hess == 0.0:
                continue

            step = -grad / hess
            if step > 64.0:
                step = 64.0
            elif step < -64.0:
                step = -64.0

            ratings[target] += step
            max_step = max(max_step, abs(step))

        if max_step < 1e-3:
            break

    # Approximate standard error from observed Hessian diagonal at optimum.
    stderr: dict[str, float] = {}
    for target in unknown:
        fisher_diag = 0.0
        for game in games:
            white = str(game["white"])
            black = str(game["black"])
            if white == target:
                ra = ratings[target]
                rb = anchors.get(black, ratings.get(black, anchor_mean))
                exp = _expected_score(ra, rb)
                fisher_diag += k2 * exp * (1.0 - exp)
            elif black == target:
                rb = ratings[target]
                ra = anchors.get(white, ratings.get(white, anchor_mean))
                exp = _expected_score(rb, ra)
                fisher_diag += k2 * exp * (1.0 - exp)

        stderr[target] = math.sqrt(1.0 / fisher_diag) if fisher_diag > 0.0 else float("inf")

    rows: list[dict[str, object]] = []
    for player in players:
        if player.name in anchors:
            rows.append(
                {
                    "player": player.name,
                    "kind": player.kind,
                    "elo_estimate": round(anchors[player.name], 1),
                    "elo_ci95": "",
                    "elo_source": "anchor_stockfish",
                }
            )
        else:
            ci = 1.96 * stderr[player.name]
            rows.append(
                {
                    "player": player.name,
                    "kind": player.kind,
                    "elo_estimate": round(ratings[player.name], 1),
                    "elo_ci95": round(ci, 1),
                    "elo_source": "mle_anchored_logistic",
                }
            )

    return sorted(rows, key=lambda r: (-float(r["elo_estimate"]), str(r["player"])))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a proper Elo tournament: 3 random variants + 4 Stockfish calibration players")
    parser.add_argument("--feature-model", default="outputs/feature_model.json")
    parser.add_argument("--variant-count", type=int, default=3)
    parser.add_argument(
        "--variant-config",
        action="append",
        default=[],
        help=(
            "Path to an existing variant config JSON (can be repeated). "
            "If provided, these configs are used instead of random variant search."
        ),
    )
    parser.add_argument(
        "--variant-config-csv",
        default="",
        help="CSV file with a config_path column, for example a prepared shortlist.",
    )
    parser.add_argument("--seed", type=int, default=20260305)
    parser.add_argument("--optional-prob", type=float, default=0.35)
    parser.add_argument("--max-attempts", type=int, default=3000)

    parser.add_argument("--makefile", default="c_engine_pl/Makefile")
    parser.add_argument("--engine-bin", default="c_engine_pl/build/engine_pl")
    parser.add_argument("--header-out", default="c_engine_pl/include/generated/variant_config.h")
    parser.add_argument("--manifest-out", default="c_engine_pl/include/generated/variant_manifest.json")

    parser.add_argument("--stockfish-bin", default="stockfish")
    parser.add_argument("--stockfish-profile", action="append", default=[])
    parser.add_argument(
        "--anchor-spec-csv",
        default="",
        help=(
            "CSV file describing external anchor engines with published ratings. "
            "Expected columns: name,cmd,elo,uci_options,selected_features. "
            "Multi-value fields use '|' separators."
        ),
    )
    parser.add_argument("--pairing-mode", choices=["full", "anchors_only"], default="full")
    parser.add_argument("--match-jobs", type=int, default=1, help="Number of pairwise cutechess matches to run in parallel in anchors_only mode.")

    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--depth", type=int, default=None, help="Fixed search depth. Default when no time control is provided.")
    mode_group.add_argument("--tc", default="", help="Cutechess time control, for example 10+0.1 or 40/60+0.6.")
    mode_group.add_argument("--st", type=float, default=None, help="Fixed move time in seconds.")
    mode_group.add_argument("--nodes", type=int, default=None, help="Fixed node limit per move.")
    parser.add_argument("--rounds", type=int, default=2)
    parser.add_argument("--games-per-encounter", type=int, default=2)
    parser.add_argument("--concurrency", type=int, default=2)
    parser.add_argument("--maxmoves", type=int, default=140)

    parser.add_argument("--draw-movenumber", type=int, default=30)
    parser.add_argument("--draw-movecount", type=int, default=8)
    parser.add_argument("--draw-score", type=int, default=20)
    parser.add_argument("--resign-movecount", type=int, default=4)
    parser.add_argument("--resign-score", type=int, default=900)

    parser.add_argument("--out-dir", default="outputs/proper_elo_tournament")
    return parser


def main() -> int:
    args = build_parser().parse_args()

    feature_model = Path(args.feature_model)
    makefile = Path(args.makefile)
    engine_bin = Path(args.engine_bin)
    header_out = Path(args.header_out)
    manifest_out = Path(args.manifest_out)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    config_dir = out_dir / "variant_configs"
    bin_dir = out_dir / "variant_bins"
    openings_pgn = out_dir / "openings.pgn"
    pgn_out = out_dir / "games.pgn"
    log_out = out_dir / "cutechess.log"
    standings_csv = out_dir / "standings.csv"
    elo_csv = out_dir / "elo_estimates.csv"
    games_csv = out_dir / "games.csv"
    summary_json = out_dir / "summary.json"

    config_paths = load_variant_config_paths(args.variant_config, args.variant_config_csv)

    if config_paths:
        variant_players = build_variant_players_from_configs(
            feature_model=feature_model,
            config_paths=config_paths,
            makefile=makefile,
            engine_bin=engine_bin,
            header_out=header_out,
            manifest_out=manifest_out,
            bin_dir=bin_dir,
        )
    else:
        variant_players = build_variant_players(
            feature_model=feature_model,
            count=args.variant_count,
            seed=args.seed,
            optional_prob=args.optional_prob,
            max_attempts=args.max_attempts,
            makefile=makefile,
            engine_bin=engine_bin,
            header_out=header_out,
            manifest_out=manifest_out,
            config_dir=config_dir,
            bin_dir=bin_dir,
        )

    stockfish_bin = resolve_engine_path(args.stockfish_bin)
    stockfish_players = build_stockfish_players(stockfish_bin, args.stockfish_profile)
    external_anchor_players = load_anchor_players_from_csv(args.anchor_spec_csv)

    players = variant_players + stockfish_players + external_anchor_players
    write_openings_pgn(openings_pgn)
    search_spec, search_label = build_search_spec(
        depth=args.depth,
        tc=args.tc,
        st=args.st,
        nodes=args.nodes,
    )

    if args.pairing_mode == "anchors_only":
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
    elo_rows = estimate_elo_anchored(players, games)

    with games_csv.open("w", newline="", encoding="utf-8") as handle:
        fieldnames = ["white", "black", "result", "termination", "white_score"]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(games)

    with standings_csv.open("w", newline="", encoding="utf-8") as handle:
        fieldnames = ["player", "kind", "games", "wins", "draws", "losses", "score", "score_pct"]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(standings)

    with elo_csv.open("w", newline="", encoding="utf-8") as handle:
        fieldnames = ["player", "kind", "elo_estimate", "elo_ci95", "elo_source"]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(elo_rows)

    payload = {
        "players": [
            {
                "name": p.name,
                "kind": p.kind,
                "cmd": str(p.cmd),
                "selected_feature_count": p.selected_feature_count,
                "selected_features": p.selected_features,
                "config_path": "" if p.config_path is None else str(p.config_path),
                "uci_options": p.uci_options,
                "anchor_elo": p.anchor_elo,
            }
            for p in players
        ],
        "params": {
            "variant_count": len(variant_players),
            "variant_configs": [str(p.config_path) for p in variant_players if p.config_path is not None],
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
            "maxmoves": args.maxmoves,
            "draw_movenumber": args.draw_movenumber,
            "draw_movecount": args.draw_movecount,
            "draw_score": args.draw_score,
            "resign_movecount": args.resign_movecount,
            "resign_score": args.resign_score,
            "seed": args.seed,
        },
        "cutechess_command": cmd,
        "game_count": len(games),
        "standings": standings,
        "elo_estimates": elo_rows,
        "artifacts": {
            "openings_pgn": str(openings_pgn),
            "pgn": str(pgn_out),
            "log": str(log_out),
            "games_csv": str(games_csv),
            "standings_csv": str(standings_csv),
            "elo_csv": str(elo_csv),
        },
    }
    summary_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print(
        json.dumps(
            {
                "players": len(players),
                "games": len(games),
                "standings_csv": str(standings_csv),
                "elo_csv": str(elo_csv),
                "summary_json": str(summary_json),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
