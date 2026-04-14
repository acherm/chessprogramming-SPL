#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import statistics
import subprocess
import sys
from pathlib import Path

from pillow_plot_utils import draw_dashed_line, draw_text, new_canvas, rgba, save_png


DEFAULT_STOCKFISH_PROFILES: tuple[str, ...] = (
    "sf2400:20:2400",
    "sf2450:20:2450",
    "sf2500:20:2500",
    "sf2550:20:2550",
    "sf2600:20:2600",
    "sf2650:20:2650",
    "sf2700:20:2700",
    "sf2800:20:2800",
)


def parse_stockfish_profile(spec: str) -> tuple[str, int, int]:
    parts = [part.strip() for part in spec.split(":")]
    if len(parts) != 3:
        raise ValueError(
            f"Invalid --stockfish-profile '{spec}'. Expected format: name:skill:elo "
            "(example: sf2500:20:2500)"
        )
    name, skill_s, elo_s = parts
    if not name:
        raise ValueError(f"Invalid --stockfish-profile '{spec}': empty profile name")
    return name, int(skill_s), int(elo_s)


def load_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def select_best_variant(standings_csv: Path, summary_json: Path, explicit_name: str) -> tuple[str, Path]:
    standings = load_csv_rows(standings_csv)
    summary = json.loads(summary_json.read_text(encoding="utf-8"))
    config_by_name = {
        str(player["name"]): Path(str(player["config_path"]))
        for player in summary["players"]
        if str(player["kind"]) == "variant" and str(player.get("config_path", "")).strip()
    }

    chosen_name = explicit_name.strip()
    if not chosen_name:
        for row in standings:
            if row["kind"] == "variant":
                chosen_name = row["player"]
                break

    if not chosen_name:
        raise ValueError("Could not identify a best variant from the source tournament standings")
    if chosen_name not in config_by_name:
        raise ValueError(f"Best variant '{chosen_name}' does not have a config_path in {summary_json}")

    return chosen_name, config_by_name[chosen_name]


def build_run_command(
    *,
    variant_config: Path,
    stockfish_profiles: list[str],
    anchor_spec_csv: str,
    tc: str,
    st: float | None,
    nodes: int | None,
    rounds: int,
    games_per_encounter: int,
    concurrency: int,
    match_jobs: int,
    out_dir: Path,
    seed: int,
) -> list[str]:
    script_path = Path(__file__).with_name("proper_elo_tournament.py")
    cmd: list[str] = [
        sys.executable,
        str(script_path),
        "--variant-config",
        str(variant_config),
        "--pairing-mode",
        "anchors_only",
        "--rounds",
        str(rounds),
        "--games-per-encounter",
        str(games_per_encounter),
        "--concurrency",
        str(concurrency),
        "--match-jobs",
        str(match_jobs),
        "--seed",
        str(seed),
        "--out-dir",
        str(out_dir / "tournament"),
    ]
    if anchor_spec_csv:
        cmd.extend(["--anchor-spec-csv", anchor_spec_csv])
    for spec in stockfish_profiles:
        cmd.extend(["--stockfish-profile", spec])
    if tc:
        cmd.extend(["--tc", tc])
    elif st is not None:
        cmd.extend(["--st", f"{st:g}"])
    elif nodes is not None:
        cmd.extend(["--nodes", str(nodes)])
    return cmd


def parse_anchor_scores(games_csv: Path, variant_name: str, stockfish_profiles: list[str]) -> list[dict[str, object]]:
    anchor_elo = {name: elo for name, _skill, elo in (parse_stockfish_profile(spec) for spec in stockfish_profiles)}
    totals: dict[str, list[float | int]] = {name: [0.0, 0] for name in anchor_elo}
    for row in load_csv_rows(games_csv):
        white = row["white"]
        black = row["black"]
        if white == variant_name and black in totals:
            score = 1.0 if row["result"] == "1-0" else 0.5 if row["result"] == "1/2-1/2" else 0.0
        elif black == variant_name and white in totals:
            score = 0.0 if row["result"] == "1-0" else 0.5 if row["result"] == "1/2-1/2" else 1.0
            black = white
        else:
            continue
        totals[black][0] += score
        totals[black][1] += 1

    rows: list[dict[str, object]] = []
    for anchor_name, elo in sorted(anchor_elo.items(), key=lambda item: item[1]):
        score = float(totals[anchor_name][0])
        games = int(totals[anchor_name][1])
        score_pct = (score / games * 100.0) if games else 0.0
        p = score / games if games else 0.0
        se = math.sqrt(max(0.0, p * (1.0 - p) / games)) if games else 0.0
        ci95 = 1.96 * se
        rows.append(
            {
                "anchor_name": anchor_name,
                "anchor_elo": elo,
                "score": round(score, 3),
                "games": games,
                "score_pct": round(score_pct, 1),
                "score_frac": p,
                "score_ci95_lo": max(0.0, p - ci95),
                "score_ci95_hi": min(1.0, p + ci95),
            }
        )
    return rows


def load_anchor_rows_from_csv(csv_path: str) -> list[dict[str, object]]:
    if not csv_path:
        return []
    rows: list[dict[str, object]] = []
    for row in load_csv_rows(Path(csv_path)):
        rows.append(
            {
                "anchor_name": str(row["name"]).strip(),
                "anchor_elo": float(row["elo"]),
            }
        )
    return rows


def parse_anchor_scores_from_any_source(
    games_csv: Path,
    variant_name: str,
    stockfish_profiles: list[str],
    anchor_spec_csv: str,
) -> list[dict[str, object]]:
    anchor_rows = [
        {"anchor_name": name, "anchor_elo": elo}
        for name, _skill, elo in (parse_stockfish_profile(spec) for spec in stockfish_profiles)
    ]
    anchor_rows.extend(load_anchor_rows_from_csv(anchor_spec_csv))
    anchor_elo = {str(row["anchor_name"]): float(row["anchor_elo"]) for row in anchor_rows}
    totals: dict[str, list[float | int]] = {name: [0.0, 0] for name in anchor_elo}
    for row in load_csv_rows(games_csv):
        white = row["white"]
        black = row["black"]
        if white == variant_name and black in totals:
            score = 1.0 if row["result"] == "1-0" else 0.5 if row["result"] == "1/2-1/2" else 0.0
            anchor_name = black
        elif black == variant_name and white in totals:
            score = 0.0 if row["result"] == "1-0" else 0.5 if row["result"] == "1/2-1/2" else 1.0
            anchor_name = white
        else:
            continue
        totals[anchor_name][0] += score
        totals[anchor_name][1] += 1

    rows: list[dict[str, object]] = []
    for anchor_name, elo in sorted(anchor_elo.items(), key=lambda item: item[1]):
        score = float(totals[anchor_name][0])
        games = int(totals[anchor_name][1])
        score_pct = (score / games * 100.0) if games else 0.0
        p = score / games if games else 0.0
        se = math.sqrt(max(0.0, p * (1.0 - p) / games)) if games else 0.0
        ci95 = 1.96 * se
        rows.append(
            {
                "anchor_name": anchor_name,
                "anchor_elo": elo,
                "score": round(score, 3),
                "games": games,
                "score_pct": round(score_pct, 1),
                "score_frac": p,
                "score_ci95_lo": max(0.0, p - ci95),
                "score_ci95_hi": min(1.0, p + ci95),
            }
        )
    return rows


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def estimate_summary(elo_csv: Path, variant_name: str) -> tuple[float, float]:
    for row in load_csv_rows(elo_csv):
        if row["player"] == variant_name:
            return float(row["elo_estimate"]), float(row["elo_ci95"] or 0.0)
    raise ValueError(f"Variant '{variant_name}' not found in {elo_csv}")


def sanitize_estimate_for_plot(anchor_rows: list[dict[str, object]], estimate_elo: float, estimate_ci95: float) -> tuple[float, float, bool]:
    anchor_elos = [float(row["anchor_elo"]) for row in anchor_rows]
    anchor_min = min(anchor_elos)
    anchor_max = max(anchor_elos)
    unstable = (
        not math.isfinite(estimate_elo)
        or not math.isfinite(estimate_ci95)
        or estimate_ci95 > 600.0
        or estimate_elo < anchor_min - 400.0
        or estimate_elo > anchor_max + 400.0
    )
    if unstable:
        clipped = estimate_elo if math.isfinite(estimate_elo) else statistics.mean(anchor_elos)
        clipped = min(max(clipped, anchor_min - 200.0), anchor_max + 200.0)
        return clipped, 0.0, True
    return estimate_elo, estimate_ci95, False


def render_score_curve_plot(
    out_path: Path,
    *,
    variant_name: str,
    estimate_elo: float,
    estimate_ci95: float,
    anchor_rows: list[dict[str, object]],
) -> None:
    width = 2200
    height = 1400
    margin_left = 180
    margin_right = 360
    margin_top = 110
    margin_bottom = 160

    image, draw = new_canvas(width, height, "#ffffff")
    plot_left = margin_left
    plot_top = margin_top
    plot_right = width - margin_right
    plot_bottom = height - margin_bottom
    plot_width = plot_right - plot_left
    plot_height = plot_bottom - plot_top

    anchor_elos = [int(row["anchor_elo"]) for row in anchor_rows]
    plot_estimate, plot_ci95, estimate_unstable = sanitize_estimate_for_plot(anchor_rows, estimate_elo, estimate_ci95)
    min_elo = min(anchor_elos + [int(plot_estimate - plot_ci95)]) - 40
    max_elo = max(anchor_elos + [int(plot_estimate + plot_ci95)]) + 40

    def x_map(elo: float) -> float:
        return plot_left + (elo - min_elo) / max(1.0, max_elo - min_elo) * plot_width

    def y_map(score_frac: float) -> float:
        return plot_bottom - score_frac * plot_height

    draw.rectangle((plot_left, plot_top, plot_right, plot_bottom), outline=rgba("#222222"), width=2)
    for tick in range(0, 11):
        frac = tick / 10.0
        y = y_map(frac)
        draw.line((plot_left, y, plot_right, y), fill=rgba("#e3e6eb"), width=1)
        draw_text(draw, (plot_left - 18, y), f"{int(frac * 100)}%", size=28, anchor="ra")

    for elo_tick in range((min_elo // 50) * 50, ((max_elo + 49) // 50) * 50 + 1, 50):
        x = x_map(float(elo_tick))
        line_color = "#cfd4dc" if elo_tick % 100 == 0 else "#e7eaf0"
        draw.line((x, plot_top, x, plot_bottom), fill=rgba(line_color), width=1)
        if elo_tick % 100 == 0:
            draw_text(draw, (x, plot_bottom + 16), str(elo_tick), size=28, anchor="ma")

    draw_dashed_line(draw, (plot_left, y_map(0.5)), (plot_right, y_map(0.5)), fill="#8d99ae", width=3, dash=14, gap=10)
    draw_dashed_line(draw, (x_map(plot_estimate), plot_top), (x_map(plot_estimate), plot_bottom), fill="#1d3557", width=4, dash=16, gap=10)
    if plot_ci95 > 0.0:
        ci_left = x_map(plot_estimate - plot_ci95)
        ci_right = x_map(plot_estimate + plot_ci95)
        draw.rectangle((ci_left, plot_top, ci_right, plot_bottom), fill=rgba("#457b9d", 28), outline=None)

    curve_points: list[tuple[float, float]] = []
    for step in range(300):
        elo = min_elo + (max_elo - min_elo) * step / 299.0
        expected = 1.0 / (1.0 + math.pow(10.0, (elo - plot_estimate) / 400.0))
        curve_points.append((x_map(elo), y_map(expected)))
    draw.line(curve_points, fill=rgba("#1d3557"), width=6)

    for row in anchor_rows:
        x = x_map(float(row["anchor_elo"]))
        y = y_map(float(row["score_frac"]))
        y_lo = y_map(float(row["score_ci95_hi"]))
        y_hi = y_map(float(row["score_ci95_lo"]))
        draw.line((x, y_lo, x, y_hi), fill=rgba("#c1121f"), width=4)
        draw.line((x - 12, y_lo, x + 12, y_lo), fill=rgba("#c1121f"), width=4)
        draw.line((x - 12, y_hi, x + 12, y_hi), fill=rgba("#c1121f"), width=4)
        draw.ellipse((x - 11, y - 11, x + 11, y + 11), fill=rgba("#c1121f"), outline=rgba("#ffffff"), width=3)
        draw_text(draw, (x, y - 22), str(row["anchor_name"]), size=24, anchor="ms", fill="#7a1620")

    title = f"Best Variant Anchored Elo Assessment: {variant_name}"
    if estimate_unstable:
        subtitle = "Anchored logistic fit against Stockfish ladder; estimate unstable because the current pilot bracket is too narrow or one-sided"
    else:
        subtitle = f"Anchored logistic fit against Stockfish ladder, estimate {estimate_elo:.0f} +/- {estimate_ci95:.0f} Elo (95% CI)"
    draw_text(draw, (width / 2, 42), title, size=40, bold=True, anchor="ma")
    draw_text(draw, (width / 2, 78), subtitle, size=24, fill="#4a4f57", anchor="ma")

    draw_text(draw, ((plot_left + plot_right) / 2, height - 72), "Stockfish anchor Elo", size=32, bold=True, anchor="ma")
    draw_text(draw, (56, (plot_top + plot_bottom) / 2), "Variant score", size=32, bold=True, anchor="ma")

    legend_x = width - margin_right + 28
    legend_y = margin_top + 10
    draw_text(draw, (legend_x, legend_y), "Encoding", size=28, bold=True)
    draw.line((legend_x, legend_y + 46, legend_x + 92, legend_y + 46), fill=rgba("#1d3557"), width=6)
    draw_text(draw, (legend_x + 106, legend_y + 46), "Anchored logistic fit", size=24, anchor="lm")
    draw.ellipse((legend_x + 2, legend_y + 88 - 10, legend_x + 22, legend_y + 88 + 10), fill=rgba("#c1121f"))
    draw_text(draw, (legend_x + 106, legend_y + 88), "Observed score vs anchor", size=24, anchor="lm")
    draw.line((legend_x + 12, legend_y + 126, legend_x + 12, legend_y + 170), fill=rgba("#c1121f"), width=4)
    draw_text(draw, (legend_x + 106, legend_y + 148), "Approx. 95% score CI", size=24, anchor="lm")
    draw_dashed_line(draw, (legend_x, legend_y + 208), (legend_x + 92, legend_y + 208), fill="#8d99ae", width=3, dash=14, gap=10)
    draw_text(draw, (legend_x + 106, legend_y + 208), "50% score line", size=24, anchor="lm")
    draw_dashed_line(draw, (legend_x + 12, legend_y + 252), (legend_x + 12, legend_y + 324), fill="#1d3557", width=4, dash=16, gap=10)
    draw_text(draw, (legend_x + 106, legend_y + 288), "Estimated Elo", size=24, anchor="lm")

    note = "Local anchored Elo only: tied to this hardware, opening suite, and time control."
    draw_text(draw, (width / 2, height - 28), note, size=22, fill="#5d6470", anchor="ms")
    save_png(image, out_path)


def write_report(
    path: Path,
    *,
    source_summary_json: Path,
    source_standings_csv: Path,
    variant_name: str,
    variant_config: Path,
    stockfish_profiles: list[str],
    rounds: int,
    games_per_encounter: int,
    search_label: str,
    estimate_elo: float,
    estimate_ci95: float,
    anchor_rows: list[dict[str, object]],
    elo_csv: Path,
    plot_path: Path,
) -> None:
    total_games = sum(int(row["games"]) for row in anchor_rows)
    close_anchors = [
        row for row in anchor_rows if 0.25 <= float(row["score_frac"]) <= 0.75
    ]
    close_game_count = sum(int(row["games"]) for row in close_anchors)
    estimate_unstable = (
        not math.isfinite(estimate_elo)
        or not math.isfinite(estimate_ci95)
        or estimate_ci95 > 600.0
    )
    elo_low = estimate_elo - estimate_ci95 if not estimate_unstable else float("nan")
    elo_high = estimate_elo + estimate_ci95 if not estimate_unstable else float("nan")

    lines = [
        "# Best Variant Elo Assessment",
        "",
        "## Setup and Rationale",
        "",
        f"- Source tournament: `{source_summary_json}` with standings in `{source_standings_csv}`.",
        f"- Best non-anchor player selected from the `N'=50` realistic round-robin: `{variant_name}`.",
        f"- Fixed variant config: `{variant_config}`.",
        "- Goal: estimate the playing strength of the best discovered variant against a dense Stockfish ladder, rather than only ranking it inside the sampled population.",
        "- Method: anchor-only scheduling plus anchored logistic maximum-likelihood estimation. This concentrates the game budget on the variant-vs-anchor evidence that determines the Elo estimate.",
        f"- Search regime: {search_label}.",
        f"- Stockfish ladder: {', '.join(stockfish_profiles)}.",
        f"- Games per anchor: `{rounds * games_per_encounter}`. Total variant-vs-anchor games: `{total_games}`.",
        "",
        "## Main Result",
        "",
    ]
    if estimate_unstable:
        lines.append(
            f"- Anchored Elo estimate for `{variant_name}` is currently unstable (`{estimate_elo:.1f} +/- {estimate_ci95:.1f}` in the raw fit), which means the anchor ladder or game budget does not yet bracket the true score curve tightly enough."
        )
    else:
        lines.append(
            f"- Anchored Elo estimate for `{variant_name}`: `{estimate_elo:.1f} +/- {estimate_ci95:.1f}` Elo (95% CI), i.e. roughly `{elo_low:.0f}` to `{elo_high:.0f}`."
        )
    lines.extend(
        [
            f"- Informative games near the 50% score region: `{close_game_count}` across `{len(close_anchors)}` anchors.",
            f"- Detailed anchored estimates are in `{elo_csv}`.",
            "",
            "## Direct Scores Versus Anchors",
            "",
        ]
    )
    for row in anchor_rows:
        lines.append(
            f"- `{row['anchor_name']}` ({row['anchor_elo']}): {row['score']}/{row['games']} = {row['score_pct']}%"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- This is a local anchored Elo estimate, not a universal absolute rating. It is tied to the current machine, Stockfish build, opening suite, and time-control settings.",
            "- The estimate is much more defensible than the previous diversity tournaments because the game budget is concentrated on the best variant and on multiple anchors around and above the target skill region.",
            f"- Plot: `{plot_path}`.",
            "",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Assess the Elo of the best variant from the N'=50 tournament against a dense Stockfish ladder.")
    parser.add_argument("--source-summary-json", default="outputs/variant_diversity_tournament_n50_realistic_retry/summary.json")
    parser.add_argument("--source-standings-csv", default="outputs/variant_diversity_tournament_n50_realistic_retry/standings.csv")
    parser.add_argument("--variant-name", default="", help="Optional override for the selected best variant name.")
    parser.add_argument("--anchor-spec-csv", default="", help="Optional CSV of external anchor engines with published ratings.")
    parser.add_argument("--stockfish-profile", action="append", default=[])
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--tc", default="", help="Cutechess time control, for example 10+0.1 or 40/60+0.6.")
    mode_group.add_argument("--st", type=float, default=None, help="Fixed move time in seconds.")
    mode_group.add_argument("--nodes", type=int, default=None, help="Fixed node limit per move.")
    parser.add_argument("--rounds", type=int, default=12)
    parser.add_argument("--games-per-encounter", type=int, default=2)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--match-jobs", type=int, default=4)
    parser.add_argument("--seed", type=int, default=20260411)
    parser.add_argument("--out-dir", default="outputs/best_variant_elo_assessment")
    parser.add_argument("--skip-run", action="store_true", help="Only materialize the protocol and command, do not run the tournament.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    source_summary_json = Path(args.source_summary_json)
    source_standings_csv = Path(args.source_standings_csv)
    variant_name, variant_config = select_best_variant(source_standings_csv, source_summary_json, args.variant_name)
    stockfish_profiles = list(args.stockfish_profile)
    if not stockfish_profiles and not args.anchor_spec_csv:
        stockfish_profiles = list(DEFAULT_STOCKFISH_PROFILES)
    external_anchor_count = len(load_anchor_rows_from_csv(args.anchor_spec_csv))
    tc = args.tc
    if not tc and args.st is None and args.nodes is None:
        tc = "10+0.1"

    run_cmd = build_run_command(
        variant_config=variant_config,
        stockfish_profiles=stockfish_profiles,
        anchor_spec_csv=args.anchor_spec_csv,
        tc=tc,
        st=args.st,
        nodes=args.nodes,
        rounds=args.rounds,
        games_per_encounter=args.games_per_encounter,
        concurrency=args.concurrency,
        match_jobs=args.match_jobs,
        out_dir=out_dir,
        seed=args.seed,
    )

    shell_cmd = f"PYTHONPATH=src {' '.join(run_cmd)}"
    (out_dir / "run_command.txt").write_text(shell_cmd + "\n", encoding="utf-8")
    protocol = {
        "source_summary_json": str(source_summary_json),
        "source_standings_csv": str(source_standings_csv),
        "variant_name": variant_name,
        "variant_config": str(variant_config),
        "anchor_spec_csv": args.anchor_spec_csv,
        "stockfish_profiles": stockfish_profiles,
        "rounds": args.rounds,
        "games_per_encounter": args.games_per_encounter,
        "concurrency": args.concurrency,
        "match_jobs": args.match_jobs,
        "tc": tc,
        "st": args.st,
        "nodes": args.nodes,
        "planned_games": (len(stockfish_profiles) + external_anchor_count) * args.rounds * args.games_per_encounter,
        "run_command": run_cmd,
        "shell_command": shell_cmd,
    }
    (out_dir / "protocol.json").write_text(json.dumps(protocol, indent=2), encoding="utf-8")

    if not args.skip_run:
        env = os.environ.copy()
        env["PYTHONPATH"] = f"src{os.pathsep}{env['PYTHONPATH']}" if env.get("PYTHONPATH") else "src"
        subprocess.run(run_cmd, check=True, env=env)

    tournament_dir = out_dir / "tournament"
    games_csv = tournament_dir / "games.csv"
    elo_csv = tournament_dir / "elo_estimates.csv"
    if not games_csv.exists() or not elo_csv.exists():
        print(json.dumps({"prepared": True, "variant_name": variant_name, "protocol_json": str(out_dir / "protocol.json")}, indent=2))
        return 0

    anchor_rows = parse_anchor_scores_from_any_source(games_csv, variant_name, stockfish_profiles, args.anchor_spec_csv)
    write_csv(out_dir / "anchor_scores.csv", anchor_rows)
    estimate_elo, estimate_ci95 = estimate_summary(elo_csv, variant_name)

    plot_path = out_dir / "elo_score_curve.png"
    render_score_curve_plot(
        plot_path,
        variant_name=variant_name,
        estimate_elo=estimate_elo,
        estimate_ci95=estimate_ci95,
        anchor_rows=anchor_rows,
    )

    if tc:
        search_label = f"time control {tc}"
    elif args.st is not None:
        search_label = f"fixed move time {args.st:g}s"
    elif args.nodes is not None:
        search_label = f"node limit {args.nodes}"
    else:
        search_label = "default search settings"

    write_report(
        out_dir / "report.md",
        source_summary_json=source_summary_json,
        source_standings_csv=source_standings_csv,
        variant_name=variant_name,
        variant_config=variant_config,
        stockfish_profiles=stockfish_profiles,
        rounds=args.rounds,
        games_per_encounter=args.games_per_encounter,
        search_label=search_label,
        estimate_elo=estimate_elo,
        estimate_ci95=estimate_ci95,
        anchor_rows=anchor_rows,
        elo_csv=elo_csv,
        plot_path=plot_path,
    )

    payload = {
        "variant_name": variant_name,
        "variant_config": str(variant_config),
        "anchor_count": len(stockfish_profiles) + external_anchor_count,
        "planned_games": (len(stockfish_profiles) + external_anchor_count) * args.rounds * args.games_per_encounter,
        "estimate_elo": estimate_elo,
        "estimate_ci95": estimate_ci95,
        "protocol_json": str(out_dir / "protocol.json"),
        "report_md": str(out_dir / "report.md"),
        "plot_png": str(plot_path),
    }
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
