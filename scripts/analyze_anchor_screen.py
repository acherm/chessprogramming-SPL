#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import math
import statistics
from collections import defaultdict
from pathlib import Path

from pillow_plot_utils import draw_rotated_text, draw_text, new_canvas, rgba, save_png


CONTROL_ORDER = [
    "phase3_full_eval",
    "phase2_10x12_ab_pvs_id",
    "strong_variant_02",
    "phase1_minimax",
]


def load_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def parse_match_score(token: str) -> tuple[float, int]:
    score_s, games_s = token.split("/")
    return float(score_s), int(games_s)


def screen_band(score_pct: float) -> str:
    if score_pct > 50.0:
        return "survivor"
    if score_pct > 0.0:
        return "positive"
    return "zero"


def png_geometry(base_width: int, base_height: int, target_width: int) -> tuple[float, int, int]:
    scale = max(0.5, float(target_width) / float(base_width))
    return scale, int(round(base_width * scale)), int(round(base_height * scale))


def corr(xs: list[float], ys: list[float]) -> float:
    if not xs or not ys or len(xs) != len(ys):
        return 0.0
    mx = statistics.mean(xs)
    my = statistics.mean(ys)
    numerator = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    denominator = math.sqrt(sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys))
    return numerator / denominator if denominator else 0.0


def take_diverse(rows: list[dict[str, object]], count: int, *, descending_score: bool) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str, str], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        key = (str(row["board_family"]), str(row["search_tier"]), str(row["eval_tier"]))
        grouped[key].append(row)

    for key in grouped:
        grouped[key].sort(
            key=lambda row: (
                -float(row["score_pct"]) if descending_score else float(row["score_pct"]),
                float(row["perft6_sec"]),
                str(row["variant_name"]),
            )
        )

    selected: list[dict[str, object]] = []
    keys = list(grouped)
    while len(selected) < count and keys:
        next_keys: list[tuple[str, str, str]] = []
        for key in keys:
            bucket = grouped[key]
            if not bucket:
                continue
            selected.append(bucket.pop(0))
            if bucket:
                next_keys.append(key)
            if len(selected) >= count:
                break
        keys = next_keys
    return selected[:count]


def recommend_stage2_subset(rows: list[dict[str, object]], count: int) -> list[dict[str, object]]:
    rows_by_name = {str(row["variant_name"]): row for row in rows}
    selected: list[dict[str, object]] = []
    selected_names: set[str] = set()

    for name in CONTROL_ORDER:
        row = rows_by_name.get(name)
        if row is None:
            continue
        picked = dict(row)
        picked["stage2_reason"] = "control"
        selected.append(picked)
        selected_names.add(name)
        if len(selected) >= count:
            return selected[:count]

    survivors = [
        row for row in rows
        if str(row["screen_band"]) == "survivor" and str(row["variant_name"]) not in selected_names
    ]
    for row in take_diverse(survivors, len(survivors), descending_score=True):
        picked = dict(row)
        picked["stage2_reason"] = "survivor"
        selected.append(picked)
        selected_names.add(str(row["variant_name"]))
        if len(selected) >= count:
            return selected[:count]

    remaining = count - len(selected)
    positives = [
        row for row in rows
        if str(row["screen_band"]) == "positive" and str(row["variant_name"]) not in selected_names
    ]
    zeros = [
        row for row in rows
        if str(row["screen_band"]) == "zero" and str(row["variant_name"]) not in selected_names
    ]

    positive_target = min(len(positives), max(0, math.ceil(remaining * 0.6)))
    zero_target = min(len(zeros), remaining - positive_target)
    if zero_target < min(4, len(zeros)) and positive_target > 0:
        shift = min(positive_target, min(4, len(zeros)) - zero_target)
        positive_target -= shift
        zero_target += shift

    for row in take_diverse(positives, positive_target, descending_score=True):
        picked = dict(row)
        picked["stage2_reason"] = "positive_diverse"
        selected.append(picked)
        selected_names.add(str(row["variant_name"]))

    remaining = count - len(selected)
    zeros = [row for row in zeros if str(row["variant_name"]) not in selected_names]
    for row in take_diverse(zeros, remaining, descending_score=False):
        picked = dict(row)
        picked["stage2_reason"] = "zero_diverse"
        selected.append(picked)
        selected_names.add(str(row["variant_name"]))

    if len(selected) < count:
        leftovers = [row for row in rows if str(row["variant_name"]) not in selected_names]
        leftovers.sort(key=lambda row: (-float(row["score_pct"]), float(row["perft6_sec"]), str(row["variant_name"])))
        for row in leftovers[: count - len(selected)]:
            picked = dict(row)
            picked["stage2_reason"] = "fill"
            selected.append(picked)
            selected_names.add(str(row["variant_name"]))

    return selected[:count]


def write_score_ladder_png(
    rows: list[dict[str, object]],
    anchors: dict[str, float],
    out_path: Path,
    *,
    target_width: int,
) -> None:
    ranked = sorted(rows, key=lambda row: (-float(row["score_pct"]), str(row["variant_name"])))
    base_width = 1200
    base_row_h = 22
    base_height = 90 + base_row_h * len(ranked)
    scale, width, height = png_geometry(base_width, base_height, target_width)
    image, draw = new_canvas(width, height, "#ffffff")

    margin_left = 280 * scale
    margin_right = 40 * scale
    plot_w = width - margin_left - margin_right
    row_h = base_row_h * scale
    band_colors = {
        "survivor": "#2E8B57",
        "positive": "#F4A261",
        "zero": "#D1495B",
    }

    draw_text(draw, (width / 2, 26 * scale), "Anchor-Screen Score Ladder (50 Variants)", size=int(20 * scale), fill="#1A202C", bold=True, anchor="mm")
    for pct in range(0, 101, 20):
        x = margin_left + (pct / 100.0) * plot_w
        draw.line((x, 42 * scale, x, height - 24 * scale), fill=rgba("#E2E8F0"), width=max(1, int(2 * scale)))
        draw_text(draw, (x, height - 6 * scale), f"{pct}%", size=int(11 * scale), fill="#4A5568", anchor="ms")

    for anchor_name, value in anchors.items():
        x = margin_left + (value / 100.0) * plot_w
        draw.line((x, 42 * scale, x, height - 24 * scale), fill=rgba("#4A5568"), width=max(1, int(2 * scale)))
        draw_text(draw, (x, 36 * scale), f"{anchor_name} {value:.1f}%", size=int(11 * scale), fill="#2D3748", bold=True, anchor="ms")

    for idx, row in enumerate(ranked):
        y = 48 * scale + idx * row_h
        value = float(row["score_pct"])
        bar_w = (value / 100.0) * plot_w
        color = band_colors[str(row["screen_band"])]
        label = str(row["variant_name"])
        draw_text(draw, (12 * scale, y + 7 * scale), label, size=int(11 * scale), fill="#1A202C", anchor="lm")
        draw.rounded_rectangle(
            (margin_left, y, margin_left + max(1.0, bar_w), y + 14 * scale),
            radius=max(3, int(4 * scale)),
            fill=rgba(color),
        )
        draw_text(draw, (margin_left + bar_w + 8 * scale, y + 7 * scale), f"{value:.1f}%", size=int(11 * scale), fill="#2D3748", anchor="lm")

    save_png(image, out_path)


def write_anchor_heatmap_png(rows: list[dict[str, object]], out_path: Path, *, target_width: int) -> None:
    ranked = sorted(rows, key=lambda row: (-float(row["score_pct"]), str(row["variant_name"])))
    anchors = ["sf2500", "sf2000", "sf1500"]
    base_cell_w = 130
    base_cell_h = 24
    base_margin_left = 280
    base_margin_top = 74
    base_width = base_margin_left + len(anchors) * base_cell_w + 30
    base_height = base_margin_top + len(ranked) * base_cell_h + 30
    scale, width, height = png_geometry(base_width, base_height, target_width)
    image, draw = new_canvas(width, height, "#ffffff")

    cell_w = base_cell_w * scale
    cell_h = base_cell_h * scale
    margin_left = base_margin_left * scale
    margin_top = base_margin_top * scale

    def fill(pct: float) -> tuple[int, int, int, int]:
        pct = max(0.0, min(1.0, pct))
        red = int(233 - pct * 150)
        green = int(98 + pct * 126)
        blue = int(106 - pct * 42)
        return (red, green, blue, 255)

    draw_text(draw, (width / 2, 28 * scale), "Variant x Anchor Matchup Heatmap", size=int(20 * scale), fill="#1A202C", bold=True, anchor="mm")
    for idx, anchor in enumerate(anchors):
        x = margin_left + idx * cell_w + cell_w / 2
        draw_text(draw, (x, 56 * scale), anchor, size=int(12 * scale), fill="#2D3748", bold=True, anchor="mm")

    for row_idx, row in enumerate(ranked):
        y = margin_top + row_idx * cell_h
        draw_text(draw, (margin_left - 10 * scale, y + cell_h / 2), str(row["variant_name"]), size=int(11 * scale), fill="#1A202C", anchor="rm")
        for col_idx, anchor in enumerate(anchors):
            x = margin_left + col_idx * cell_w
            score = float(row[f"{anchor}_score"])
            games_count = int(row[f"{anchor}_games"])
            pct = score / games_count if games_count else 0.0
            draw.rounded_rectangle(
                (x, y, x + cell_w, y + cell_h),
                radius=max(4, int(4 * scale)),
                fill=fill(pct),
                outline=rgba("#FFFFFF"),
                width=max(1, int(2 * scale)),
            )
            draw_text(draw, (x + cell_w / 2, y + cell_h / 2), f"{score:.1f}/{games_count}", size=int(10 * scale), fill="#111827", bold=True, anchor="mm")

    save_png(image, out_path)


def write_score_vs_perft_png(rows: list[dict[str, object]], out_path: Path, *, target_width: int) -> None:
    base_width = 980
    base_height = 620
    scale, width, height = png_geometry(base_width, base_height, target_width)
    image, draw = new_canvas(width, height, "#ffffff")

    margin_left = 80 * scale
    margin_right = 170 * scale
    margin_top = 42 * scale
    margin_bottom = 64 * scale
    plot_w = width - margin_left - margin_right
    plot_h = height - margin_top - margin_bottom
    colors = {
        "Bitboards": "#2E86DE",
        "0x88": "#FF8C42",
        "Mailbox": "#3FA34D",
        "10x12 Board": "#D94E41",
        "unknown": "#7F8C8D",
    }

    xs = [float(row["perft6_sec"]) for row in rows]
    x_min = min(xs)
    x_max = max(xs)
    if x_min == x_max:
        x_min -= 1.0
        x_max += 1.0

    def map_x(value: float) -> float:
        return margin_left + (value - x_min) / (x_max - x_min) * plot_w

    def map_y(value: float) -> float:
        return margin_top + plot_h - value / 100.0 * plot_h

    draw_text(draw, (width / 2, 24 * scale), "Anchor-Screen Score vs Perft-6 Runtime", size=int(20 * scale), fill="#1A202C", bold=True, anchor="mm")
    for pct in range(0, 101, 20):
        y = map_y(float(pct))
        draw.line((margin_left, y, margin_left + plot_w, y), fill=rgba("#E2E8F0"), width=max(1, int(2 * scale)))
        draw_text(draw, (margin_left - 10 * scale, y), f"{pct}%", size=int(11 * scale), fill="#4A5568", anchor="rm")
    for step in range(6):
        value = x_min + (x_max - x_min) * step / 5.0
        x = map_x(value)
        draw.line((x, margin_top, x, margin_top + plot_h), fill=rgba("#EEF2F7"), width=max(1, int(2 * scale)))
        draw_text(draw, (x, height - 16 * scale), f"{value:.1f}s", size=int(11 * scale), fill="#4A5568", anchor="mm")
    draw.line((margin_left, margin_top + plot_h, margin_left + plot_w, margin_top + plot_h), fill=rgba("#2D3748"), width=max(2, int(3 * scale)))
    draw.line((margin_left, margin_top, margin_left, margin_top + plot_h), fill=rgba("#2D3748"), width=max(2, int(3 * scale)))
    draw_text(draw, (margin_left + plot_w / 2, height - 4 * scale), "Perft-6 Runtime (s)", size=int(14 * scale), fill="#2D3748", bold=True, anchor="ms")
    draw_rotated_text(image, (18 * scale, margin_top + plot_h / 2), "Anchor-Screen Score", size=int(14 * scale), fill="#2D3748", bold=True, angle=90, anchor="mm")

    label_names = {str(row["variant_name"]) for row in sorted(rows, key=lambda row: -float(row["score_pct"]))[:6]}
    label_names.update({"phase3_full_eval", "phase2_10x12_ab_pvs_id", "strong_variant_02", "phase1_minimax"})

    for row in rows:
        x = map_x(float(row["perft6_sec"]))
        y = map_y(float(row["score_pct"]))
        color = colors.get(str(row["board_family"]), colors["unknown"])
        radius = 5 * scale if str(row["variant_name"]) in CONTROL_ORDER else 4 * scale
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=rgba(color), outline=rgba("#1F2933"), width=max(1, int(2 * scale)))
        if str(row["variant_name"]) in label_names:
            draw_text(draw, (x + 8 * scale, y - 8 * scale), str(row["variant_name"]), size=int(11 * scale), fill="#1A202C", anchor="lm")

    legend_y = 66 * scale
    legend_x = width - 148 * scale
    for idx, label in enumerate(["Bitboards", "0x88", "Mailbox", "10x12 Board"]):
        y = legend_y + idx * 20 * scale
        radius = 5 * scale
        draw.ellipse((legend_x - radius, y - radius, legend_x + radius, y + radius), fill=rgba(colors[label]), outline=rgba("#1F2933"), width=max(1, int(2 * scale)))
        draw_text(draw, (legend_x + 12 * scale, y), label, size=int(12 * scale), fill="#2D3748", anchor="lm")

    save_png(image, out_path)


def write_band_bar_png(rows: list[dict[str, object]], out_path: Path, *, target_width: int) -> None:
    order = ["survivor", "positive", "zero"]
    labels = {
        "survivor": "Score > 50%",
        "positive": "0 < Score <= 50%",
        "zero": "Score = 0",
    }
    colors = {
        "survivor": "#2E8B57",
        "positive": "#F4A261",
        "zero": "#D1495B",
    }
    counts = {band: sum(1 for row in rows if str(row["screen_band"]) == band) for band in order}
    total = len(rows)

    base_width = 860
    base_height = 460
    scale, width, height = png_geometry(base_width, base_height, target_width)
    image, draw = new_canvas(width, height, "#ffffff")
    margin_left = 90 * scale
    margin_right = 30 * scale
    margin_top = 44 * scale
    margin_bottom = 96 * scale
    plot_w = width - margin_left - margin_right
    plot_h = height - margin_top - margin_bottom
    max_value = max(counts.values()) if counts else 1

    draw_text(draw, (width / 2, 24 * scale), "Screen Outcome Bands", size=int(20 * scale), fill="#1A202C", bold=True, anchor="mm")
    for step in range(6):
        value = max_value * step / 5.0
        y = margin_top + plot_h - (value / max_value * plot_h if max_value > 0 else 0.0)
        draw.line((margin_left, y, margin_left + plot_w, y), fill=rgba("#E2E8F0"), width=max(1, int(2 * scale)))
        draw_text(draw, (margin_left - 8 * scale, y), f"{int(round(value))}", size=int(11 * scale), fill="#4A5568", anchor="rm")

    gap = plot_w / len(order)
    bar_w = gap * 0.58
    for idx, band in enumerate(order):
        x = margin_left + idx * gap + (gap - bar_w) / 2
        value = counts[band]
        bar_h = 0.0 if max_value == 0 else value / max_value * plot_h
        y = margin_top + plot_h - bar_h
        draw.rounded_rectangle((x, y, x + bar_w, y + bar_h), radius=max(4, int(5 * scale)), fill=rgba(colors[band]))
        draw_text(draw, (x + bar_w / 2, y - 8 * scale), f"{value}", size=int(12 * scale), fill="#1A202C", bold=True, anchor="mm")
        draw_text(draw, (x + bar_w / 2, y - 26 * scale), f"{100.0 * value / total:.1f}%", size=int(11 * scale), fill="#4A5568", anchor="mm")
        draw_text(draw, (x + bar_w / 2, height - 48 * scale), labels[band], size=int(11 * scale), fill="#2D3748", anchor="mm")

    save_png(image, out_path)


def write_mean_score_bar_png(rows: list[dict[str, object]], key: str, title: str, out_path: Path, *, target_width: int) -> None:
    grouped: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        grouped[str(row[key])].append(float(row["score_pct"]))
    stats = sorted((name, sum(values) / len(values), statistics.median(values), len(values)) for name, values in grouped.items())
    if not stats:
        return

    base_width = 940
    base_height = 480
    scale, width, height = png_geometry(base_width, base_height, target_width)
    image, draw = new_canvas(width, height, "#ffffff")
    margin_left = 80 * scale
    margin_right = 30 * scale
    margin_top = 44 * scale
    margin_bottom = 104 * scale
    plot_w = width - margin_left - margin_right
    plot_h = height - margin_top - margin_bottom
    max_value = max(mean for _, mean, _, _ in stats)
    palette = ["#4C78A8", "#F58518", "#54A24B", "#E45756", "#72B7B2", "#B279A2", "#9D755D"]

    draw_text(draw, (width / 2, 24 * scale), title, size=int(20 * scale), fill="#1A202C", bold=True, anchor="mm")
    for step in range(6):
        value = max_value * step / 5.0 if max_value else 0.0
        y = margin_top + plot_h - (value / max_value * plot_h if max_value > 0 else 0.0)
        draw.line((margin_left, y, margin_left + plot_w, y), fill=rgba("#E2E8F0"), width=max(1, int(2 * scale)))
        draw_text(draw, (margin_left - 8 * scale, y), f"{value:.1f}", size=int(11 * scale), fill="#4A5568", anchor="rm")

    gap = plot_w / len(stats)
    bar_w = gap * 0.58
    for idx, (name, mean_value, median_value, count) in enumerate(stats):
        x = margin_left + idx * gap + (gap - bar_w) / 2
        bar_h = 0.0 if max_value == 0 else mean_value / max_value * plot_h
        y = margin_top + plot_h - bar_h
        draw.rounded_rectangle((x, y, x + bar_w, y + bar_h), radius=max(4, int(5 * scale)), fill=rgba(palette[idx % len(palette)]))
        draw_text(draw, (x + bar_w / 2, y - 8 * scale), f"{mean_value:.1f}", size=int(11 * scale), fill="#1A202C", bold=True, anchor="mm")
        draw_text(draw, (x + bar_w / 2, height - 50 * scale), name, size=int(11 * scale), fill="#2D3748", anchor="mm")
        draw_text(draw, (x + bar_w / 2, height - 32 * scale), f"n={count}, med={median_value:.1f}", size=int(10 * scale), fill="#4A5568", anchor="mm")

    save_png(image, out_path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze an anchor-only strength screen and emit report + PNG plots")
    parser.add_argument("--standings", required=True)
    parser.add_argument("--strength-buckets", required=True)
    parser.add_argument("--perft-screen", required=True)
    parser.add_argument("--summary-json", default="")
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--png-width", type=int, default=2400)
    parser.add_argument("--stage2-count", type=int, default=16)
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    plots_dir = out_dir / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)

    standings = load_rows(Path(args.standings))
    bucket_rows = load_rows(Path(args.strength_buckets))
    perft_rows = load_rows(Path(args.perft_screen))
    perft_by_name = {row["variant_name"]: row for row in perft_rows}
    bucket_by_name = {row["variant_name"]: row for row in bucket_rows}

    anchors = {row["player"]: float(row["score_pct"]) for row in standings if row["kind"] == "stockfish"}
    variants = [row for row in standings if row["kind"] == "variant"]

    merged_rows: list[dict[str, object]] = []
    for row in variants:
        name = row["player"]
        perft = perft_by_name[name]
        matchup = bucket_by_name[name]
        sf1500_score, sf1500_games = parse_match_score(matchup["vs_sf1500"])
        sf2000_score, sf2000_games = parse_match_score(matchup["vs_sf2000"])
        sf2500_score, sf2500_games = parse_match_score(matchup["vs_sf2500"])
        score_pct = float(row["score_pct"])
        merged_rows.append(
            {
                "variant_name": name,
                "config_path": perft["config_path"],
                "source_kind": perft["source_kind"],
                "score_pct": score_pct,
                "score": float(row["score"]),
                "games": int(row["games"]),
                "wins": int(row["wins"]),
                "draws": int(row["draws"]),
                "losses": int(row["losses"]),
                "screen_band": screen_band(score_pct),
                "board_family": perft["board_family"],
                "search_tier": perft["search_tier"],
                "eval_tier": perft["eval_tier"],
                "stratum": perft["stratum"],
                "selected_feature_count": int(perft["selected_feature_count"]),
                "perft6_sec": float(perft["perft_sec"]),
                "sf1500_score": sf1500_score,
                "sf1500_games": sf1500_games,
                "sf1500_pct": round(100.0 * sf1500_score / sf1500_games, 1) if sf1500_games else 0.0,
                "sf2000_score": sf2000_score,
                "sf2000_games": sf2000_games,
                "sf2000_pct": round(100.0 * sf2000_score / sf2000_games, 1) if sf2000_games else 0.0,
                "sf2500_score": sf2500_score,
                "sf2500_games": sf2500_games,
                "sf2500_pct": round(100.0 * sf2500_score / sf2500_games, 1) if sf2500_games else 0.0,
            }
        )

    merged_rows.sort(key=lambda row: (-float(row["score_pct"]), str(row["variant_name"])))
    write_csv(out_dir / "paper_variant_summary.csv", merged_rows)

    xs = [float(row["perft6_sec"]) for row in merged_rows]
    ys = [float(row["score_pct"]) for row in merged_rows]
    perft_corr = corr(xs, ys)

    zero_count = sum(1 for row in merged_rows if str(row["screen_band"]) == "zero")
    positive_count = sum(1 for row in merged_rows if str(row["screen_band"]) == "positive")
    survivor_count = sum(1 for row in merged_rows if str(row["screen_band"]) == "survivor")

    beat_counts: dict[str, int] = {}
    draw_counts: dict[str, int] = {}
    for anchor in ("sf1500", "sf2000", "sf2500"):
        beat_counts[anchor] = sum(1 for row in merged_rows if float(row[f"{anchor}_score"]) > int(row[f"{anchor}_games"]) / 2)
        draw_counts[anchor] = sum(
            1
            for row in merged_rows
            if int(row[f"{anchor}_games"]) > 0 and float(row[f"{anchor}_score"]) == int(row[f"{anchor}_games"]) / 2
        )

    board_stats: list[dict[str, object]] = []
    search_stats: list[dict[str, object]] = []
    eval_stats: list[dict[str, object]] = []
    for key, target in [
        ("board_family", board_stats),
        ("search_tier", search_stats),
        ("eval_tier", eval_stats),
    ]:
        grouped: dict[str, list[float]] = defaultdict(list)
        for row in merged_rows:
            grouped[str(row[key])].append(float(row["score_pct"]))
        for name, values in sorted(grouped.items()):
            target.append(
                {
                    key: name,
                    "count": len(values),
                    "mean_score_pct": round(sum(values) / len(values), 3),
                    "median_score_pct": round(statistics.median(values), 3),
                    "max_score_pct": round(max(values), 3),
                }
            )
    write_csv(out_dir / "board_family_score_stats.csv", board_stats)
    write_csv(out_dir / "search_tier_score_stats.csv", search_stats)
    write_csv(out_dir / "eval_tier_score_stats.csv", eval_stats)

    stage2_subset = recommend_stage2_subset(merged_rows, args.stage2_count)
    write_csv(out_dir / f"stage2_round_robin_subset_{args.stage2_count}.csv", stage2_subset)

    # 53 players total in this stage: 50 variants + 3 anchors.
    total_players = len(standings)
    full_round_robin_games = total_players * (total_players - 1) // 2 * 2 * 2
    screening_games = sum(int(row["games"]) for row in merged_rows)
    game_reduction_pct = 100.0 * (1.0 - screening_games / full_round_robin_games)

    write_score_ladder_png(merged_rows, anchors, plots_dir / "anchor_screen_score_ladder.png", target_width=args.png_width)
    write_anchor_heatmap_png(merged_rows, plots_dir / "anchor_matchup_heatmap.png", target_width=args.png_width)
    write_score_vs_perft_png(merged_rows, plots_dir / "score_vs_perft6.png", target_width=args.png_width)
    write_band_bar_png(merged_rows, plots_dir / "screen_outcome_bands.png", target_width=args.png_width)
    write_mean_score_bar_png(merged_rows, "search_tier", "Mean Anchor-Screen Score by Search Tier", plots_dir / "score_by_search_tier.png", target_width=args.png_width)
    write_mean_score_bar_png(merged_rows, "board_family", "Mean Anchor-Screen Score by Board Family", plots_dir / "score_by_board_family.png", target_width=args.png_width)

    top_rows = merged_rows[:10]
    zero_rows = [row for row in merged_rows if float(row["score_pct"]) == 0.0]

    report_lines = [
        "# N'=50 Anchor-Screen Analysis",
        "",
        "## Design Setup",
        "",
        "- screened population: `50` variants selected from the perft-6 stratified pool (`4` fixed controls + `46` sampled variants)",
        "- anchors: `sf1500`, `sf2000`, `sf2500`",
        "- time control: `10+0.1`",
        "- schedule: each variant plays `4` games against each anchor (`12` games total per variant), for `600` games overall",
        "",
        "## Rationale",
        "",
        f"- A full `53`-player round-robin at the same `rounds=2`, `games-per-encounter=2` setting would require `{full_round_robin_games}` games.",
        f"- The anchor-only screen uses `{screening_games}` games instead, a reduction of `{game_reduction_pct:.1f}%`.",
        "- This stage is intentionally a harsh screening phase: it is designed to prune clearly weak variants, keep a compact set of promising survivors, and retain some diverse weak/mid representatives for a later full round-robin.",
        "",
        "## Key Findings",
        "",
        f"- Only `{survivor_count}/50` variants scored above `50%` against the anchor ensemble.",
        f"- `{positive_count}/50` variants scored at least one point but stayed at or below `50%` overall.",
        f"- `{zero_count}/50` variants collapsed to `0/12` against the anchor trio.",
        f"- Against individual anchors: `{beat_counts['sf1500']}` variants beat `sf1500`, `{beat_counts['sf2000']}` beat `sf2000`, `{beat_counts['sf2500']}` beat `sf2500`; `{draw_counts['sf2500']}` variants drew `sf2500` head-to-head.",
        f"- Perft-6 runtime remains a weak proxy for strength in this stage (`r = {perft_corr:.3f}`).",
        "- Search-tier signal is strong in this sample: every `alpha_beta` variant scored `0`, while the `pvs_id` family had the highest mean score.",
        "",
        "## Interpretation",
        "",
        "- The screen clearly separates a tiny top tier, a small positive middle, and a large collapsed weak tail.",
        "- The surviving top tier is architecturally diverse rather than monolithic: the three best variants come from `Bitboards/pvs_id/rich_eval`, `10x12 Board/pvs_id/pst_eval`, and `0x88/minimax/structural_eval` respectively.",
        "- The result is useful for selection, not Elo calibration: twelve games per variant are enough to identify obviously weak and obviously promising candidates, but not enough to fully resolve the positive middle.",
        "",
        "## Top Variants",
        "",
    ]
    for row in top_rows[:8]:
        report_lines.append(
            f"- `{row['variant_name']}`: `{row['score']}/{row['games']}` (`{row['score_pct']:.1f}%`), "
            f"`sf1500={row['sf1500_score']}/{row['sf1500_games']}`, "
            f"`sf2000={row['sf2000_score']}/{row['sf2000_games']}`, "
            f"`sf2500={row['sf2500_score']}/{row['sf2500_games']}`, "
            f"`{row['board_family']}`, `{row['search_tier']}`, `{row['eval_tier']}`, `perft6={row['perft6_sec']:.3f}s`"
        )

    report_lines.extend(["", "## Weak Tail", ""])
    report_lines.append(f"- zero-score variants: `{zero_count}`")
    for row in zero_rows[:10]:
        report_lines.append(
            f"- `{row['variant_name']}`: `{row['board_family']}`, `{row['search_tier']}`, `{row['eval_tier']}`, `perft6={row['perft6_sec']:.3f}s`"
        )

    report_lines.extend(
        [
            "",
            "## Recommended Stage 2",
            "",
            f"- recommended subset size: `{args.stage2_count}` variants plus the same three anchors",
            f"- estimated full round-robin cost for that stage: `{(args.stage2_count + 3) * (args.stage2_count + 2) // 2 * 2 * 2}` games",
            f"- prepared subset file: `stage2_round_robin_subset_{args.stage2_count}.csv`",
            "- selection rule: keep the four controls, include all non-control survivors, then add diverse positive-middle variants and a few diverse zero-score weak variants so the later round-robin can still expose internal structure among the weak tail.",
            "",
            "## Figure Set",
            "",
            "- `plots/anchor_screen_score_ladder.png`: overall sorted ladder with anchor reference lines.",
            "- `plots/anchor_matchup_heatmap.png`: direct scores against `sf1500`, `sf2000`, `sf2500`.",
            "- `plots/score_vs_perft6.png`: anchor-screen score vs perft-6 runtime.",
            "- `plots/screen_outcome_bands.png`: survivor / positive / zero counts.",
            "- `plots/score_by_search_tier.png`: mean score by search tier.",
            "- `plots/score_by_board_family.png`: mean score by board family.",
        ]
    )

    (out_dir / "paper_report.md").write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
