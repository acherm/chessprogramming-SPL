#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path

from PIL import Image, ImageEnhance, ImageOps
from pillow_plot_utils import draw_dashed_line, draw_rotated_text, draw_text, new_canvas, rgba, save_png, text_bbox


def svg_escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def load_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def count_pgn_games(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("r", encoding="utf-8") as handle:
        return sum(1 for line in handle if line.startswith("[Event "))


def write_svg(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def compute_anchor_matchups(games: list[dict[str, str]], anchors: list[str]) -> dict[str, dict[str, tuple[float, int]]]:
    matchups: dict[str, dict[str, list[float | int]]] = defaultdict(lambda: defaultdict(lambda: [0.0, 0]))
    for row in games:
        white = row["white"]
        black = row["black"]
        result = row["result"]
        if (white in anchors) == (black in anchors):
            continue
        if white in anchors:
            anchor = white
            variant = black
            variant_score = 0.0 if result == "1-0" else 0.5 if result == "1/2-1/2" else 1.0
        else:
            anchor = black
            variant = white
            variant_score = 1.0 if result == "1-0" else 0.5 if result == "1/2-1/2" else 0.0
        matchups[variant][anchor][0] += variant_score
        matchups[variant][anchor][1] += 1
    frozen: dict[str, dict[str, tuple[float, int]]] = {}
    for variant_name, anchor_rows in matchups.items():
        frozen[variant_name] = {
            anchor_name: (float(score), int(games_count))
            for anchor_name, (score, games_count) in anchor_rows.items()
        }
    return frozen


def compute_bucket(score_pct: float, sf1500_pct: float, sf2000_pct: float) -> str:
    if score_pct > sf2000_pct:
        return "strong"
    if score_pct >= sf1500_pct:
        return "mid"
    return "weak"


def select_strength_scatter_labels(rows: list[dict[str, object]]) -> list[str]:
    if not rows:
        return []
    ordered_names: list[str] = []
    seen: set[str] = set()

    def add(name: str) -> None:
        if name not in seen:
            ordered_names.append(name)
            seen.add(name)

    controls = ["phase2_10x12_ab_pvs_id", "phase3_full_eval", "strong_variant_02", "phase1_minimax"]
    for name in controls:
        add(name)

    for row in rows[:2]:
        add(str(row["variant_name"]))
    for row in rows[-2:]:
        add(str(row["variant_name"]))

    fastest = min(rows, key=lambda row: float(row["perft6_sec"]))
    slowest = max(rows, key=lambda row: float(row["perft6_sec"]))
    add(str(fastest["variant_name"]))
    add(str(slowest["variant_name"]))

    return ordered_names


def select_strength_scatter_publication_labels(rows: list[dict[str, object]]) -> list[str]:
    if not rows:
        return []
    by_name = {str(row["variant_name"]): row for row in rows}
    ordered_names: list[str] = []
    seen: set[str] = set()

    def add(name: str) -> None:
        if name in by_name and name not in seen:
            ordered_names.append(name)
            seen.add(name)

    # Keep only the points that support the main interpretation:
    # best sampled variant, best controls, baseline weak control, and
    # one or two weak/performance outliers.
    for name in [
        "stratified_variant_28",
        "phase2_10x12_ab_pvs_id",
        "phase3_full_eval",
        "strong_variant_02",
        "phase1_minimax",
        "stratified_variant_98",
        "stratified_variant_10",
    ]:
        add(name)

    return ordered_names


def publication_short_label(name: str) -> str:
    mapping = {
        "phase1_minimax": "P1",
        "phase2_10x12_ab_pvs_id": "P2",
        "phase3_full_eval": "P3",
        "strong_variant_02": "SV2",
    }
    if name in mapping:
        return mapping[name]
    if name.startswith("stratified_variant_"):
        try:
            return f"V{int(name.rsplit('_', 1)[1])}"
        except ValueError:
            return name
    return name


def corr(xs: list[float], ys: list[float]) -> float:
    if not xs or not ys or len(xs) != len(ys):
        return 0.0
    mx = statistics.mean(xs)
    my = statistics.mean(ys)
    numerator = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    denominator = math.sqrt(sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys))
    return numerator / denominator if denominator else 0.0


def stack_label_positions(items: list[tuple[str, float]], *, top: float, bottom: float, gap: float) -> dict[str, float]:
    if not items:
        return {}
    placed: list[list[object]] = []
    for name, y in sorted(items, key=lambda item: item[1]):
        target_y = float(y)
        if placed:
            target_y = max(target_y, float(placed[-1][1]) + gap)
        else:
            target_y = max(target_y, top)
        placed.append([name, target_y])

    overflow = float(placed[-1][1]) - bottom
    if overflow > 0:
        for item in placed:
            item[1] = float(item[1]) - overflow
        if float(placed[0][1]) < top:
            shift = top - float(placed[0][1])
            for item in placed:
                item[1] = float(item[1]) + shift

    return {str(name): float(y) for name, y in placed}


def compute_pairwise_scores(games: list[dict[str, str]]) -> dict[str, dict[str, tuple[float, int]]]:
    totals: dict[str, dict[str, list[float | int]]] = defaultdict(lambda: defaultdict(lambda: [0.0, 0]))
    for row in games:
        white = row["white"]
        black = row["black"]
        white_score = float(row["white_score"])
        black_score = 1.0 - white_score
        totals[white][black][0] += white_score
        totals[white][black][1] += 1
        totals[black][white][0] += black_score
        totals[black][white][1] += 1

    frozen: dict[str, dict[str, tuple[float, int]]] = {}
    for player, row in totals.items():
        frozen[player] = {
            opponent: (float(score), int(games_count))
            for opponent, (score, games_count) in row.items()
        }
    return frozen


def write_group_stats_csv(rows: list[dict[str, object]], key: str, out_path: Path) -> None:
    grouped: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        grouped[str(row[key])].append(float(row["score_pct"]))

    stats_rows: list[dict[str, object]] = []
    for group_name, values in sorted(grouped.items()):
        stats_rows.append(
            {
                "group": group_name,
                "count": len(values),
                "mean_score_pct": round(statistics.mean(values), 2),
                "median_score_pct": round(statistics.median(values), 2),
                "min_score_pct": round(min(values), 2),
                "max_score_pct": round(max(values), 2),
            }
        )
    write_csv(out_path, stats_rows)


def select_bucket_representatives(rows: list[dict[str, object]], bucket: str) -> list[dict[str, object]]:
    bucket_rows = [row for row in rows if str(row["bucket"]) == bucket]
    if not bucket_rows:
        return []
    bucket_rows = sorted(bucket_rows, key=lambda row: (-float(row["score_pct"]), str(row["variant_name"])))
    if bucket == "strong":
        roles = ["top_strong", "median_strong", "lowest_strong"]
    elif bucket == "mid":
        roles = ["upper_mid", "median_mid", "lower_mid"]
    else:
        roles = ["boundary_weak", "median_weak", "extreme_weak"]

    targets = [0, len(bucket_rows) // 2, len(bucket_rows) - 1]
    selected: list[dict[str, object]] = []
    used_names: set[str] = set()
    used_signatures: set[tuple[str, str, str]] = set()
    for role, target_idx in zip(roles, targets):
        ranked_candidates: list[tuple[int, int, str, dict[str, object]]] = []
        for idx, row in enumerate(bucket_rows):
            name = str(row["variant_name"])
            if name in used_names:
                continue
            signature = (str(row["board_family"]), str(row["search_tier"]), str(row["eval_tier"]))
            diversity_penalty = 1 if signature in used_signatures else 0
            ranked_candidates.append((diversity_penalty, abs(idx - target_idx), name, row))
        if not ranked_candidates:
            continue
        _, _, _, chosen = min(ranked_candidates)
        picked = dict(chosen)
        picked["representative_role"] = role
        selected.append(picked)
        used_names.add(str(chosen["variant_name"]))
        used_signatures.add((str(chosen["board_family"]), str(chosen["search_tier"]), str(chosen["eval_tier"])))
    return selected


def write_grayscale_png(src: Path, dst: Path) -> None:
    image = Image.open(src).convert("RGB")
    gray = ImageOps.grayscale(image)
    gray = ImageOps.autocontrast(gray, cutoff=1)
    gray = ImageEnhance.Contrast(gray).enhance(1.15)
    gray = ImageEnhance.Sharpness(gray).enhance(1.05)
    dst.parent.mkdir(parents=True, exist_ok=True)
    gray.convert("RGB").save(dst, format="PNG", dpi=(300, 300), optimize=True)


def write_strength_vs_perft(
    rows: list[dict[str, object]],
    anchor_lines: dict[str, float],
    out_path: Path,
) -> None:
    width = 980
    height = 620
    margin_left = 80
    margin_right = 170
    margin_top = 40
    margin_bottom = 65
    plot_w = width - margin_left - margin_right
    plot_h = height - margin_top - margin_bottom

    colors = {
        "Bitboards": "#1f77b4",
        "0x88": "#ff7f0e",
        "Mailbox": "#2ca02c",
        "10x12 Board": "#d62728",
        "unknown": "#7f7f7f",
    }

    xs = [float(row["perft6_sec"]) for row in rows]
    ys = [float(row["score_pct"]) for row in rows]
    x_min = min(xs)
    x_max = max(xs)
    y_min = 0.0
    y_max = 100.0
    if x_min == x_max:
        x_min -= 1.0
        x_max += 1.0

    def map_x(value: float) -> float:
        return margin_left + (value - x_min) / (x_max - x_min) * plot_w

    def map_y(value: float) -> float:
        return margin_top + plot_h - (value - y_min) / (y_max - y_min) * plot_h

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<style>text{font-family:Menlo,Consolas,monospace;font-size:12px;fill:#222}.grid{stroke:#ddd;stroke-width:1}.axis{stroke:#333;stroke-width:1}.anchor{stroke:#999;stroke-width:1.2;stroke-dasharray:5 4}.label{font-size:11px}</style>',
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="#fff"/>',
        '<text x="490" y="22" text-anchor="middle">Realistic Strength vs Perft-6 Runtime</text>',
    ]

    for step in range(6):
        y_value = step * 20.0
        y = map_y(y_value)
        lines.append(f'<line class="grid" x1="{margin_left}" y1="{y:.1f}" x2="{margin_left + plot_w}" y2="{y:.1f}"/>')
        lines.append(f'<text x="{margin_left - 10}" y="{y + 4:.1f}" text-anchor="end">{y_value:.0f}%</text>')

    for step in range(6):
        x_value = x_min + (x_max - x_min) * step / 5.0
        x = map_x(x_value)
        lines.append(f'<line class="grid" x1="{x:.1f}" y1="{margin_top}" x2="{x:.1f}" y2="{margin_top + plot_h}"/>')
        lines.append(f'<text x="{x:.1f}" y="{height - 18}" text-anchor="middle">{x_value:.1f}s</text>')

    anchor_label_y = stack_label_positions(
        [(anchor_name, map_y(value)) for anchor_name, value in anchor_lines.items()],
        top=margin_top + 10.0,
        bottom=margin_top + 64.0,
        gap=18.0,
    )
    for anchor_name, value in anchor_lines.items():
        y = map_y(value)
        lines.append(f'<line class="anchor" x1="{margin_left}" y1="{y:.1f}" x2="{margin_left + plot_w}" y2="{y:.1f}"/>')
        box_y = anchor_label_y[anchor_name]
        box_x = margin_left + plot_w + 8.0
        label = f"{anchor_name}: {value:.1f}%"
        box_w = max(88.0, len(label) * 6.6 + 10.0)
        lines.append(f'<rect x="{box_x:.1f}" y="{box_y - 11:.1f}" width="{box_w:.1f}" height="16" rx="3" ry="3" fill="#ffffff" fill-opacity="0.92" stroke="#cbd5e0"/>')
        lines.append(f'<text class="label" x="{box_x + 5:.1f}" y="{box_y:.1f}">{svg_escape(label)}</text>')

    lines.append(f'<line class="axis" x1="{margin_left}" y1="{margin_top + plot_h}" x2="{margin_left + plot_w}" y2="{margin_top + plot_h}"/>')
    lines.append(f'<line class="axis" x1="{margin_left}" y1="{margin_top}" x2="{margin_left}" y2="{margin_top + plot_h}"/>')
    lines.append(f'<text x="{margin_left + plot_w/2:.1f}" y="{height - 2}" text-anchor="middle">Perft-6 Runtime (s)</text>')
    lines.append(f'<text x="18" y="{margin_top + plot_h/2:.1f}" text-anchor="middle" transform="rotate(-90 18 {margin_top + plot_h/2:.1f})">Tournament Score</text>')

    control_labels = {"phase1_minimax", "phase2_10x12_ab_pvs_id", "phase3_full_eval", "strong_variant_02"}
    label_names = set(select_strength_scatter_labels(rows))

    label_offsets = {
        "stratified_variant_28": (-112.0, -18.0),
        "phase2_10x12_ab_pvs_id": (12.0, 22.0),
        "phase3_full_eval": (12.0, -30.0),
        "strong_variant_02": (12.0, 12.0),
        "phase1_minimax": (12.0, -26.0),
    }

    for row in rows:
        x = map_x(float(row["perft6_sec"]))
        y = map_y(float(row["score_pct"]))
        color = colors.get(str(row["board_family"]), colors["unknown"])
        radius = 5 if row["variant_name"] in control_labels else 4
        lines.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{radius}" fill="{color}" stroke="#111" stroke-width="0.6">'
            f'<title>{svg_escape(str(row["variant_name"]))}: score={row["score_pct"]}% perft6={row["perft6_sec"]}s</title></circle>'
        )
        if row["variant_name"] in label_names:
            label = svg_escape(str(row["variant_name"]))
            dx, dy = label_offsets.get(str(row["variant_name"]), (8.0, -12.0 if y > margin_top + 20 else 16.0))
            tx = x + dx
            ty = y + dy
            label_w = max(48.0, len(str(row["variant_name"])) * 7.2)
            lines.append(f'<line x1="{x:.1f}" y1="{y:.1f}" x2="{tx:.1f}" y2="{ty - 5:.1f}" stroke="#94a3b8" stroke-width="1"/>')
            lines.append(f'<rect x="{tx - 4:.1f}" y="{ty - 11:.1f}" width="{label_w:.1f}" height="16" rx="3" ry="3" fill="#ffffff" fill-opacity="0.92" stroke="#cbd5e0"/>')
            lines.append(f'<text class="label" x="{tx:.1f}" y="{ty:.1f}">{label}</text>')

    legend_y = margin_top + plot_h - 82.0
    for idx, label in enumerate(["Bitboards", "0x88", "Mailbox", "10x12 Board"]):
        y = legend_y + idx * 18
        lines.append(f'<circle cx="{width - 150}" cy="{y}" r="5" fill="{colors[label]}" stroke="#111" stroke-width="0.6"/>')
        lines.append(f'<text x="{width - 138}" y="{y + 4:.1f}">{svg_escape(label)}</text>')

    lines.append("</svg>")
    write_svg(out_path, lines)


def write_anchor_heatmap(
    rows: list[dict[str, object]],
    anchors: list[str],
    out_path: Path,
) -> None:
    cell_w = 120
    cell_h = 24
    margin_left = 240
    margin_top = 70
    width = margin_left + len(anchors) * cell_w + 30
    height = margin_top + len(rows) * cell_h + 30

    def fill(pct: float) -> str:
        # red -> yellow -> green
        pct = max(0.0, min(1.0, pct))
        red = int(235 - pct * 150)
        green = int(96 + pct * 120)
        blue = int(96 - pct * 40)
        return f"rgb({red},{green},{blue})"

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<style>text{font-family:Menlo,Consolas,monospace;font-size:12px;fill:#222}.cell{stroke:#ddd;stroke-width:1}</style>',
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="#fff"/>',
        '<text x="430" y="24" text-anchor="middle">Anchor Matchup Heatmap</text>',
    ]

    for idx, anchor in enumerate(anchors):
        x = margin_left + idx * cell_w + cell_w / 2
        lines.append(f'<text x="{x:.1f}" y="52" text-anchor="middle">{svg_escape(anchor)}</text>')

    for row_idx, row in enumerate(rows):
        y = margin_top + row_idx * cell_h
        lines.append(f'<text x="{margin_left - 8}" y="{y + 16:.1f}" text-anchor="end">{svg_escape(str(row["variant_name"]))}</text>')
        for col_idx, anchor in enumerate(anchors):
            x = margin_left + col_idx * cell_w
            score = float(row[f"{anchor}_score"])
            games_count = int(row[f"{anchor}_games"])
            pct = score / games_count if games_count else 0.0
            lines.append(f'<rect class="cell" x="{x}" y="{y}" width="{cell_w}" height="{cell_h}" fill="{fill(pct)}"/>')
            lines.append(f'<text x="{x + cell_w/2:.1f}" y="{y + 16:.1f}" text-anchor="middle">{score:.1f}/{games_count}</text>')

    lines.append("</svg>")
    write_svg(out_path, lines)


def write_rank_shift(rows: list[dict[str, object]], out_path: Path) -> None:
    width = 980
    row_h = 22
    height = 80 + row_h * len(rows)
    margin_left = 290
    margin_right = 40
    plot_w = width - margin_left - margin_right
    max_abs = max(abs(float(row["delta_score_pct"])) for row in rows) if rows else 1.0

    def map_x(delta: float) -> float:
        return margin_left + plot_w / 2 + (delta / max_abs) * (plot_w / 2)

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<style>text{font-family:Menlo,Consolas,monospace;font-size:12px;fill:#222}.axis{stroke:#333;stroke-width:1}.grid{stroke:#ddd;stroke-width:1}</style>',
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="#fff"/>',
        '<text x="490" y="24" text-anchor="middle">Rank Shift: Shallow Depth-3 vs Realistic 10+0.1</text>',
    ]

    for step in range(-4, 5):
        delta = max_abs * step / 4
        x = map_x(delta)
        lines.append(f'<line class="grid" x1="{x:.1f}" y1="40" x2="{x:.1f}" y2="{height - 24}"/>')
        lines.append(f'<text x="{x:.1f}" y="{height - 6}" text-anchor="middle">{delta:.0f}</text>')

    zero_x = map_x(0.0)
    lines.append(f'<line class="axis" x1="{zero_x:.1f}" y1="40" x2="{zero_x:.1f}" y2="{height - 24}"/>')

    for idx, row in enumerate(rows):
        y = 42 + idx * row_h
        delta = float(row["delta_score_pct"])
        x0 = map_x(0.0)
        x1 = map_x(delta)
        bar_x = min(x0, x1)
        bar_w = abs(x1 - x0)
        color = "#4c78a8" if delta >= 0 else "#e45756"
        lines.append(f'<text x="10" y="{y + 12:.1f}">{svg_escape(str(row["variant_name"]))}</text>')
        lines.append(f'<rect x="{bar_x:.1f}" y="{y - 2:.1f}" width="{bar_w:.1f}" height="14" fill="{color}"/>')
        lines.append(f'<text x="{x1 + (8 if delta >= 0 else -8):.1f}" y="{y + 10:.1f}" text-anchor="{"start" if delta >= 0 else "end"}">{delta:+.1f}</text>')

    lines.append("</svg>")
    write_svg(out_path, lines)


def png_geometry(base_width: int, base_height: int, target_width: int) -> tuple[float, int, int]:
    scale = max(0.5, float(target_width) / float(base_width))
    return scale, int(round(base_width * scale)), int(round(base_height * scale))


def write_score_ladder_png(
    rows: list[dict[str, object]],
    out_path: Path,
    *,
    target_width: int,
    title: str,
) -> None:
    ranked = sorted(rows, key=lambda row: (-float(row["score_pct"]), str(row["name"])))
    base_width = 1120
    base_row_h = 22
    base_height = 96 + base_row_h * len(ranked)
    scale, width, height = png_geometry(base_width, base_height, target_width)
    image, draw = new_canvas(width, height, "#ffffff")

    margin_left = 280 * scale
    margin_right = 44 * scale
    plot_w = width - margin_left - margin_right
    row_h = base_row_h * scale
    kind_colors = {
        "stockfish": "#2D3748",
        "strong": "#2E8B57",
        "mid": "#4C78A8",
        "weak": "#D1495B",
        "unknown": "#7F8C8D",
    }

    draw_text(draw, (width / 2, 28 * scale), title, size=int(20 * scale), fill="#1A202C", bold=True, anchor="mm")
    for pct in range(0, 101, 20):
        x = margin_left + (pct / 100.0) * plot_w
        draw.line((x, 46 * scale, x, height - 24 * scale), fill=rgba("#E2E8F0"), width=max(1, int(2 * scale)))
        draw_text(draw, (x, height - 8 * scale), f"{pct}%", size=int(11 * scale), fill="#4A5568", anchor="ms")

    for idx, row in enumerate(ranked):
        y = 52 * scale + idx * row_h
        value = float(row["score_pct"])
        bar_w = plot_w * value / 100.0
        color_key = str(row.get("bucket") or row.get("kind") or "unknown")
        color = kind_colors.get(color_key, kind_colors["unknown"])
        draw_text(draw, (12 * scale, y + 7 * scale), str(row["name"]), size=int(11 * scale), fill="#1A202C", anchor="lm")
        draw.rounded_rectangle(
            (margin_left, y, margin_left + max(1.0, bar_w), y + 14 * scale),
            radius=max(3, int(4 * scale)),
            fill=rgba(color),
        )
        draw_text(draw, (margin_left + bar_w + 8 * scale, y + 7 * scale), f"{value:.1f}%", size=int(11 * scale), fill="#2D3748", anchor="lm")

    legend_items = [
        ("stockfish", "Stockfish anchors"),
        ("strong", "Variants above sf2000"),
        ("mid", "Variants between sf1500 and sf2000"),
        ("weak", "Variants below sf1500"),
    ]
    legend_x = width - 238 * scale
    legend_y = 58 * scale
    for idx, (key, label) in enumerate(legend_items):
        cy = legend_y + idx * 20 * scale
        r = 5 * scale
        draw.ellipse((legend_x - r, cy - r, legend_x + r, cy + r), fill=rgba(kind_colors[key]), outline=rgba("#1F2933"), width=max(1, int(2 * scale)))
        draw_text(draw, (legend_x + 12 * scale, cy), label, size=int(11 * scale), fill="#2D3748", anchor="lm")

    save_png(image, out_path)


def write_mean_score_bar_png(rows: list[dict[str, object]], key: str, title: str, out_path: Path, *, target_width: int) -> None:
    grouped: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        grouped[str(row[key])].append(float(row["score_pct"]))
    stats = sorted((name, statistics.mean(values), statistics.median(values), len(values)) for name, values in grouped.items())
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
    max_value = max(mean_value for _, mean_value, _, _ in stats)
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


def write_pairwise_heatmap_png(
    names: list[str],
    pairwise_scores: dict[str, dict[str, tuple[float, int]]],
    out_path: Path,
    *,
    target_width: int,
    title: str,
) -> None:
    if not names:
        return
    base_cell_w = 68
    base_cell_h = 30
    base_margin_left = 220
    base_margin_top = 170
    base_width = base_margin_left + len(names) * base_cell_w + 30
    base_height = base_margin_top + len(names) * base_cell_h + 30
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

    draw_text(draw, (width / 2, 28 * scale), title, size=int(20 * scale), fill="#1A202C", bold=True, anchor="mm")
    draw_text(draw, (width / 2, 52 * scale), "Cell value = row player score percentage against column player", size=int(11 * scale), fill="#4A5568", anchor="mm")

    for idx, name in enumerate(names):
        x = margin_left + idx * cell_w + cell_w / 2
        draw_rotated_text(image, (x, 138 * scale), name, size=int(11 * scale), fill="#2D3748", angle=90, anchor="mm")
        y = margin_top + idx * cell_h + cell_h / 2
        draw_text(draw, (margin_left - 10 * scale, y), name, size=int(11 * scale), fill="#1A202C", anchor="rm")

    for row_idx, name in enumerate(names):
        y = margin_top + row_idx * cell_h
        for col_idx, opponent in enumerate(names):
            x = margin_left + col_idx * cell_w
            if name == opponent:
                draw.rounded_rectangle(
                    (x, y, x + cell_w, y + cell_h),
                    radius=max(4, int(4 * scale)),
                    fill=rgba("#EDF2F7"),
                    outline=rgba("#FFFFFF"),
                    width=max(1, int(2 * scale)),
                )
                draw_text(draw, (x + cell_w / 2, y + cell_h / 2), "—", size=int(12 * scale), fill="#4A5568", anchor="mm")
                continue
            score, games_count = pairwise_scores.get(name, {}).get(opponent, (0.0, 0))
            pct = score / games_count if games_count else 0.0
            draw.rounded_rectangle(
                (x, y, x + cell_w, y + cell_h),
                radius=max(4, int(4 * scale)),
                fill=fill(pct),
                outline=rgba("#FFFFFF"),
                width=max(1, int(2 * scale)),
            )
            label = f"{100.0 * pct:.0f}%" if games_count else "n/a"
            draw_text(draw, (x + cell_w / 2, y + cell_h / 2), label, size=int(10 * scale), fill="#111827", bold=True, anchor="mm")

    save_png(image, out_path)


def write_strength_vs_perft_png(
    rows: list[dict[str, object]],
    anchor_lines: dict[str, float],
    out_path: Path,
    *,
    target_width: int,
) -> None:
    base_width = 980
    base_height = 620
    scale, width, height = png_geometry(base_width, base_height, target_width)
    image, draw = new_canvas(width, height, "#ffffff")

    margin_left = 80 * scale
    margin_right = 170 * scale
    margin_top = 40 * scale
    margin_bottom = 65 * scale
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

    for step in range(6):
        y_value = step * 20.0
        y = map_y(y_value)
        draw.line((margin_left, y, margin_left + plot_w, y), fill=rgba("#D9DEE7"), width=max(1, int(2 * scale)))
        draw_text(draw, (margin_left - 12 * scale, y), f"{y_value:.0f}%", size=int(12 * scale), fill="#4A5568", anchor="rm")

    for step in range(6):
        x_value = x_min + (x_max - x_min) * step / 5.0
        x = map_x(x_value)
        draw.line((x, margin_top, x, margin_top + plot_h), fill=rgba("#EEF1F5"), width=max(1, int(2 * scale)))
        draw_text(draw, (x, height - 18 * scale), f"{x_value:.1f}s", size=int(12 * scale), fill="#4A5568", anchor="mm")

    anchor_label_y = stack_label_positions(
        [(anchor_name, map_y(value)) for anchor_name, value in anchor_lines.items()],
        top=margin_top + 12 * scale,
        bottom=margin_top + 70 * scale,
        gap=20 * scale,
    )
    for anchor_name, value in anchor_lines.items():
        y = map_y(value)
        draw_dashed_line(
            draw,
            (margin_left, y),
            (margin_left + plot_w, y),
            fill="#A0AEC0",
            width=max(1, int(2 * scale)),
            dash=max(8, int(12 * scale)),
            gap=max(6, int(8 * scale)),
        )
        label = f"{anchor_name}: {value:.1f}%"
        box_y = anchor_label_y[anchor_name]
        font_size = int(12 * scale)
        text_box = text_bbox(draw, label, size=font_size, anchor="la")
        text_w = text_box[2] - text_box[0]
        text_h = text_box[3] - text_box[1]
        box_x = margin_left + plot_w + 10 * scale
        pad_x = 5 * scale
        pad_y = 3 * scale
        draw.rounded_rectangle(
            (box_x, box_y - text_h / 2 - pad_y, box_x + text_w + pad_x * 2, box_y + text_h / 2 + pad_y),
            radius=max(3, int(4 * scale)),
            fill=rgba("#FFFFFF", 235),
            outline=rgba("#CBD5E0"),
            width=max(1, int(1 * scale)),
        )
        draw_text(draw, (box_x + pad_x, box_y), label, size=font_size, fill="#4A5568", anchor="lm")

    draw.line((margin_left, margin_top + plot_h, margin_left + plot_w, margin_top + plot_h), fill=rgba("#2D3748"), width=max(2, int(3 * scale)))
    draw.line((margin_left, margin_top, margin_left, margin_top + plot_h), fill=rgba("#2D3748"), width=max(2, int(3 * scale)))

    draw_text(draw, (width / 2, 22 * scale), "Realistic Strength vs Perft-6 Runtime", size=int(19 * scale), fill="#1A202C", bold=True, anchor="mm")
    draw_text(draw, (margin_left + plot_w / 2, height - 12 * scale), "Perft-6 Runtime (s)", size=int(14 * scale), fill="#2D3748", bold=True, anchor="mm")
    draw_rotated_text(image, (20 * scale, margin_top + plot_h / 2), "Tournament Score", size=int(14 * scale), fill="#2D3748", bold=True, angle=90, anchor="mm")

    control_labels = {"phase1_minimax", "phase2_10x12_ab_pvs_id", "phase3_full_eval", "strong_variant_02"}
    label_names = set(select_strength_scatter_labels(rows))

    label_offsets = {
        "stratified_variant_28": (-112 * scale, -18 * scale),
        "phase2_10x12_ab_pvs_id": (12 * scale, 22 * scale),
        "phase3_full_eval": (12 * scale, -30 * scale),
        "strong_variant_02": (12 * scale, 12 * scale),
        "phase1_minimax": (12 * scale, -26 * scale),
    }

    for row in rows:
        x = map_x(float(row["perft6_sec"]))
        y = map_y(float(row["score_pct"]))
        color = colors.get(str(row["board_family"]), colors["unknown"])
        radius = 6 * scale if row["variant_name"] in control_labels else 5 * scale
        fill_alpha = 255 if row["variant_name"] in control_labels else 196
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=rgba(color, fill_alpha), outline=rgba("#1F2933"), width=max(1, int(2 * scale)))
        if row["variant_name"] in label_names:
            label = str(row["variant_name"])
            font_size = int(11 * scale)
            bbox = text_bbox(draw, label, size=font_size, anchor="la")
            text_w = bbox[2] - bbox[0]
            text_h = bbox[3] - bbox[1]
            dx, dy = label_offsets.get(str(row["variant_name"]), (10 * scale, -18 * scale if y > margin_top + 26 * scale else 10 * scale))
            tx = x + dx
            ty = y + dy
            pad_x = 4 * scale
            pad_y = 3 * scale
            draw.line((x, y, tx, ty + text_h / 2), fill=rgba("#94A3B8"), width=max(1, int(1 * scale)))
            draw.rounded_rectangle(
                (tx - pad_x, ty - pad_y, tx + text_w + pad_x, ty + text_h + pad_y),
                radius=max(3, int(4 * scale)),
                fill=rgba("#FFFFFF", 232),
                outline=rgba("#CBD5E0"),
                width=max(1, int(1 * scale)),
            )
            draw_text(draw, (tx, ty), label, size=font_size, fill="#1A202C", anchor="la")

    legend_y = margin_top + plot_h - 84 * scale
    legend_x = width - 150 * scale
    for idx, label in enumerate(["Bitboards", "0x88", "Mailbox", "10x12 Board"]):
        y = legend_y + idx * 20 * scale
        radius = 5 * scale
        draw.ellipse((legend_x - radius, y - radius, legend_x + radius, y + radius), fill=rgba(colors[label]), outline=rgba("#1F2933"), width=max(1, int(2 * scale)))
        draw_text(draw, (legend_x + 12 * scale, y), label, size=int(12 * scale), fill="#2D3748", anchor="lm")

    save_png(image, out_path)


def write_strength_vs_perft_publication_png(
    rows: list[dict[str, object]],
    anchor_lines: dict[str, float],
    out_path: Path,
    key_csv_path: Path,
    *,
    target_width: int,
) -> None:
    base_width = 1260
    base_height = 800
    scale, width, height = png_geometry(base_width, base_height, target_width)
    image, draw = new_canvas(width, height, "#ffffff")

    margin_left = 100 * scale
    margin_right = 360 * scale
    margin_top = 56 * scale
    margin_bottom = 78 * scale
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

    draw_text(draw, (width / 2, 28 * scale), "Realistic Strength vs Perft-6 Runtime", size=int(24 * scale), fill="#111827", bold=True, anchor="mm")
    draw_text(draw, (width / 2, 50 * scale), "Full round-robin, 50 variants + 3 anchors", size=int(12 * scale), fill="#4B5563", anchor="mm")

    for step in range(6):
        y_value = step * 20.0
        y = map_y(y_value)
        draw.line((margin_left, y, margin_left + plot_w, y), fill=rgba("#D6DCE5"), width=max(1, int(2 * scale)))
        draw_text(draw, (margin_left - 14 * scale, y), f"{y_value:.0f}%", size=int(14 * scale), fill="#4A5568", anchor="rm")

    for step in range(6):
        x_value = x_min + (x_max - x_min) * step / 5.0
        x = map_x(x_value)
        draw.line((x, margin_top, x, margin_top + plot_h), fill=rgba("#EEF2F7"), width=max(1, int(2 * scale)))
        draw_text(draw, (x, height - 22 * scale), f"{x_value:.1f}s", size=int(13 * scale), fill="#4A5568", anchor="mm")

    anchor_label_y = stack_label_positions(
        [(anchor_name, map_y(value)) for anchor_name, value in anchor_lines.items()],
        top=margin_top + 12 * scale,
        bottom=margin_top + 84 * scale,
        gap=24 * scale,
    )
    anchor_panel_x = margin_left + plot_w + 18 * scale
    for anchor_name, value in anchor_lines.items():
        y = map_y(value)
        draw_dashed_line(
            draw,
            (margin_left, y),
            (margin_left + plot_w, y),
            fill="#64748B",
            width=max(2, int(3 * scale)),
            dash=max(10, int(15 * scale)),
            gap=max(7, int(10 * scale)),
        )
        label = f"{anchor_name}: {value:.1f}%"
        box_y = anchor_label_y[anchor_name]
        font_size = int(13 * scale)
        bbox = text_bbox(draw, label, size=font_size, anchor="la")
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        pad_x = 7 * scale
        pad_y = 4 * scale
        draw.rounded_rectangle(
            (anchor_panel_x, box_y - text_h / 2 - pad_y, anchor_panel_x + text_w + pad_x * 2, box_y + text_h / 2 + pad_y),
            radius=max(4, int(5 * scale)),
            fill=rgba("#FFFFFF", 242),
            outline=rgba("#94A3B8"),
            width=max(1, int(1 * scale)),
        )
        draw_text(draw, (anchor_panel_x + pad_x, box_y), label, size=font_size, fill="#334155", bold=True, anchor="lm")

    draw.line((margin_left, margin_top + plot_h, margin_left + plot_w, margin_top + plot_h), fill=rgba("#1F2937"), width=max(2, int(3 * scale)))
    draw.line((margin_left, margin_top, margin_left, margin_top + plot_h), fill=rgba("#1F2937"), width=max(2, int(3 * scale)))
    draw_text(draw, (margin_left + plot_w / 2, height - 12 * scale), "Perft-6 Runtime (s)", size=int(16 * scale), fill="#1F2937", bold=True, anchor="mm")
    draw_rotated_text(image, (24 * scale, margin_top + plot_h / 2), "Tournament Score", size=int(16 * scale), fill="#1F2937", bold=True, angle=90, anchor="mm")

    control_labels = {"phase1_minimax", "phase2_10x12_ab_pvs_id", "phase3_full_eval", "strong_variant_02"}
    callout_names = select_strength_scatter_publication_labels(rows)
    callout_order = {name: idx + 1 for idx, name in enumerate(callout_names)}
    label_offsets = {
        "stratified_variant_28": (-32 * scale, -24 * scale),
        "phase2_10x12_ab_pvs_id": (18 * scale, 30 * scale),
        "phase3_full_eval": (18 * scale, -38 * scale),
        "strong_variant_02": (18 * scale, 16 * scale),
        "phase1_minimax": (18 * scale, -28 * scale),
        "stratified_variant_98": (-26 * scale, -14 * scale),
        "stratified_variant_10": (18 * scale, -16 * scale),
    }

    key_rows: list[dict[str, object]] = []
    for row in rows:
        x = map_x(float(row["perft6_sec"]))
        y = map_y(float(row["score_pct"]))
        color = colors.get(str(row["board_family"]), colors["unknown"])
        radius = 7 * scale if row["variant_name"] in control_labels else 5 * scale
        fill_alpha = 255 if row["variant_name"] in control_labels else 178
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=rgba(color, fill_alpha), outline=rgba("#1F2933"), width=max(1, int(2 * scale)))

        name = str(row["variant_name"])
        if name not in callout_order:
            continue
        badge_num = callout_order[name]
        dx, dy = label_offsets.get(name, (14 * scale, -20 * scale if y > margin_top + 30 * scale else 16 * scale))
        bx = x + dx
        by = y + dy
        badge_r = 10 * scale
        draw.line((x, y, bx, by), fill=rgba("#94A3B8"), width=max(1, int(2 * scale)))
        draw.ellipse((bx - badge_r, by - badge_r, bx + badge_r, by + badge_r), fill=rgba("#FFFFFF", 244), outline=rgba("#334155"), width=max(1, int(2 * scale)))
        draw_text(draw, (bx, by), str(badge_num), size=int(12 * scale), fill="#111827", bold=True, anchor="mm")
        key_rows.append(
            {
                "index": badge_num,
                "short_label": publication_short_label(name),
                "variant_name": name,
                "score_pct": float(row["score_pct"]),
                "perft6_sec": float(row["perft6_sec"]),
            }
        )

    key_rows.sort(key=lambda item: int(item["index"]))
    write_csv(key_csv_path, key_rows)

    key_panel_x = anchor_panel_x
    key_panel_y = margin_top + 168 * scale
    key_panel_w = width - key_panel_x - 22 * scale
    key_panel_h = max(168 * scale, len(key_rows) * 24 * scale + 38 * scale)
    draw.rounded_rectangle(
        (key_panel_x, key_panel_y, key_panel_x + key_panel_w, key_panel_y + key_panel_h),
        radius=max(5, int(6 * scale)),
        fill=rgba("#F8FAFC", 248),
        outline=rgba("#CBD5E1"),
        width=max(1, int(1 * scale)),
    )
    draw_text(draw, (key_panel_x + 12 * scale, key_panel_y + 14 * scale), "Labeled Engines", size=int(15 * scale), fill="#111827", bold=True, anchor="la")
    for idx, item in enumerate(key_rows):
        y = key_panel_y + 40 * scale + idx * 24 * scale
        badge_x = key_panel_x + 16 * scale
        badge_r = 9 * scale
        draw.ellipse((badge_x - badge_r, y - badge_r, badge_x + badge_r, y + badge_r), fill=rgba("#FFFFFF"), outline=rgba("#334155"), width=max(1, int(2 * scale)))
        draw_text(draw, (badge_x, y), str(item["index"]), size=int(11 * scale), fill="#111827", bold=True, anchor="mm")
        label = f"{item['short_label']}  {item['score_pct']:.1f}%"
        draw_text(draw, (badge_x + 18 * scale, y), label, size=int(12 * scale), fill="#1F2937", anchor="lm")

    legend_title_y = key_panel_y + key_panel_h + 18 * scale
    legend_y = legend_title_y + 28 * scale
    draw_text(draw, (key_panel_x, legend_title_y), "Board Family", size=int(14 * scale), fill="#111827", bold=True, anchor="la")
    for idx, label in enumerate(["Bitboards", "0x88", "Mailbox", "10x12 Board"]):
        y = legend_y + idx * 22 * scale
        radius = 6 * scale
        draw.ellipse((key_panel_x + radius, y - radius, key_panel_x + 3 * radius, y + radius), fill=rgba(colors[label]), outline=rgba("#1F2933"), width=max(1, int(2 * scale)))
        draw_text(draw, (key_panel_x + 28 * scale, y), label, size=int(12 * scale), fill="#2D3748", anchor="lm")

    save_png(image, out_path)


def write_anchor_heatmap_png(
    rows: list[dict[str, object]],
    anchors: list[str],
    out_path: Path,
    *,
    target_width: int,
) -> None:
    base_cell_w = 120
    base_cell_h = 24
    base_margin_left = 240
    base_margin_top = 70
    base_width = base_margin_left + len(anchors) * base_cell_w + 30
    base_height = base_margin_top + len(rows) * base_cell_h + 30
    scale, width, height = png_geometry(base_width, base_height, target_width)
    image, draw = new_canvas(width, height, "#ffffff")

    cell_w = base_cell_w * scale
    cell_h = base_cell_h * scale
    margin_left = base_margin_left * scale
    margin_top = base_margin_top * scale

    def fill(pct: float) -> tuple[int, int, int, int]:
        pct = max(0.0, min(1.0, pct))
        red = int(236 - pct * 148)
        green = int(97 + pct * 128)
        blue = int(103 - pct * 42)
        return (red, green, blue, 255)

    draw_text(draw, (width / 2, 24 * scale), "Anchor Matchup Heatmap", size=int(18 * scale), fill="#1A202C", bold=True, anchor="mm")

    for idx, anchor in enumerate(anchors):
        x = margin_left + idx * cell_w + cell_w / 2
        draw_text(draw, (x, 52 * scale), anchor, size=int(12 * scale), fill="#2D3748", bold=True, anchor="mm")

    for row_idx, row in enumerate(rows):
        y = margin_top + row_idx * cell_h
        draw_text(draw, (margin_left - 10 * scale, y + cell_h / 2), str(row["variant_name"]), size=int(12 * scale), fill="#1A202C", anchor="rm")
        for col_idx, anchor in enumerate(anchors):
            x = margin_left + col_idx * cell_w
            score = float(row[f"{anchor}_score"])
            games_count = int(row[f"{anchor}_games"])
            pct = score / games_count if games_count else 0.0
            draw.rounded_rectangle(
                (x, y, x + cell_w, y + cell_h),
                radius=max(4, int(5 * scale)),
                fill=fill(pct),
                outline=rgba("#FFFFFF"),
                width=max(1, int(2 * scale)),
            )
            draw_text(draw, (x + cell_w / 2, y + cell_h / 2), f"{score:.1f}/{games_count}", size=int(11 * scale), fill="#0F172A", bold=True, anchor="mm")

    save_png(image, out_path)


def write_rank_shift_png(rows: list[dict[str, object]], out_path: Path, *, target_width: int) -> None:
    base_width = 980
    base_row_h = 22
    base_height = 80 + base_row_h * len(rows)
    scale, width, height = png_geometry(base_width, base_height, target_width)
    image, draw = new_canvas(width, height, "#ffffff")

    margin_left = 290 * scale
    margin_right = 40 * scale
    plot_w = width - margin_left - margin_right
    row_h = base_row_h * scale
    max_abs = max(abs(float(row["delta_score_pct"])) for row in rows) if rows else 1.0

    def map_x(delta: float) -> float:
        return margin_left + plot_w / 2 + (delta / max_abs) * (plot_w / 2)

    draw_text(draw, (width / 2, 24 * scale), "Rank Shift: Shallow Depth-3 vs Realistic 10+0.1", size=int(18 * scale), fill="#1A202C", bold=True, anchor="mm")

    for step in range(-4, 5):
        delta = max_abs * step / 4
        x = map_x(delta)
        draw.line((x, 40 * scale, x, height - 24 * scale), fill=rgba("#E2E8F0"), width=max(1, int(2 * scale)))
        draw_text(draw, (x, height - 6 * scale), f"{delta:.0f}", size=int(11 * scale), fill="#4A5568", anchor="ms")

    zero_x = map_x(0.0)
    draw.line((zero_x, 40 * scale, zero_x, height - 24 * scale), fill=rgba("#2D3748"), width=max(2, int(3 * scale)))

    for idx, row in enumerate(rows):
        y = 42 * scale + idx * row_h
        delta = float(row["delta_score_pct"])
        x0 = map_x(0.0)
        x1 = map_x(delta)
        bar_x = min(x0, x1)
        bar_w = abs(x1 - x0)
        color = "#3182CE" if delta >= 0 else "#E53E3E"
        draw_text(draw, (10 * scale, y + 5 * scale), str(row["variant_name"]), size=int(11 * scale), fill="#1A202C", anchor="lm")
        draw.rounded_rectangle(
            (bar_x, y - 2 * scale, bar_x + bar_w, y + 12 * scale),
            radius=max(2, int(3 * scale)),
            fill=rgba(color),
        )
        label_anchor = "lm" if delta >= 0 else "rm"
        label_x = x1 + 8 * scale if delta >= 0 else x1 - 8 * scale
        draw_text(draw, (label_x, y + 5 * scale), f"{delta:+.1f}", size=int(11 * scale), fill="#2D3748", bold=True, anchor=label_anchor)

    save_png(image, out_path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Analyze a finished realistic tournament and emit paper-friendly outputs")
    parser.add_argument("--standings", required=True)
    parser.add_argument("--games", required=True)
    parser.add_argument("--perft-screen", required=True)
    parser.add_argument("--shallow-standings", default="")
    parser.add_argument("--summary-json", default="")
    parser.add_argument("--openings-pgn", default="")
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--png-density", type=int, default=300)
    parser.add_argument("--png-width", type=int, default=2400)
    return parser


def main() -> int:
    args = build_parser().parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    standings = load_rows(Path(args.standings))
    games = load_rows(Path(args.games))
    perft_rows = load_rows(Path(args.perft_screen))
    perft_by_name = {row["variant_name"]: row for row in perft_rows}

    shallow_by_name: dict[str, float] = {}
    if args.shallow_standings:
        shallow_by_name = {row["player"]: float(row["score_pct"]) for row in load_rows(Path(args.shallow_standings))}

    tournament_summary: dict[str, object] = {}
    if args.summary_json:
        tournament_summary = json.loads(Path(args.summary_json).read_text(encoding="utf-8"))
    settings = (
        tournament_summary.get("params")
        or tournament_summary.get("settings")
        or {}
    ) if tournament_summary else {}
    search_mode = str(settings.get("search_mode") or "").strip() or "unknown"
    if search_mode == "unknown":
        if settings.get("tc"):
            search_mode = f"tc={settings['tc']}"
        elif settings.get("st"):
            search_mode = f"st={settings['st']}"
        elif settings.get("nodes"):
            search_mode = f"nodes={settings['nodes']}"
        elif settings.get("depth"):
            search_mode = f"depth={settings['depth']}"
    rounds = int(settings.get("rounds", 0) or 0)
    games_per_encounter = int(settings.get("games_per_encounter", 0) or 0)
    pairing_mode = str(settings.get("pairing_mode", "full"))
    openings_count = count_pgn_games(Path(args.openings_pgn)) if args.openings_pgn else 0

    anchor_names = [row["player"] for row in standings if row["kind"] == "stockfish"]
    anchor_score_pct = {row["player"]: float(row["score_pct"]) for row in standings if row["kind"] == "stockfish"}
    sf1500_pct = anchor_score_pct.get("sf1500", min(anchor_score_pct.values()))
    sf2000_pct = anchor_score_pct.get("sf2000", max(anchor_score_pct.values()))
    matchups = compute_anchor_matchups(games, anchor_names)
    pairwise_scores = compute_pairwise_scores(games)

    merged_rows: list[dict[str, object]] = []
    for row in standings:
        if row["kind"] != "variant":
            continue
        perft = perft_by_name.get(row["player"])
        if perft is None:
            continue

        score_pct = float(row["score_pct"])
        merged: dict[str, object] = {
            "variant_name": row["player"],
            "bucket": compute_bucket(score_pct, sf1500_pct, sf2000_pct),
            "score_pct": score_pct,
            "score": float(row["score"]),
            "games": int(row["games"]),
            "wins": int(row["wins"]),
            "draws": int(row["draws"]),
            "losses": int(row["losses"]),
            "board_family": perft["board_family"],
            "search_tier": perft["search_tier"],
            "eval_tier": perft["eval_tier"],
            "perft6_sec": float(perft["perft_sec"]),
            "selected_feature_count": int(perft["selected_feature_count"]),
            "source_kind": perft["source_kind"],
            "shallow_score_pct": shallow_by_name.get(row["player"], ""),
            "delta_score_pct": "",
        }
        if row["player"] in shallow_by_name:
            merged["delta_score_pct"] = round(score_pct - shallow_by_name[row["player"]], 1)

        anchor_row = matchups.get(row["player"], {})
        for anchor_name in anchor_names:
            score, games_count = anchor_row.get(anchor_name, (0.0, 0))
            merged[f"{anchor_name}_score"] = score
            merged[f"{anchor_name}_games"] = games_count
            merged[f"{anchor_name}_pct"] = round(100.0 * score / games_count, 1) if games_count else 0.0
        merged_rows.append(merged)

    merged_rows.sort(key=lambda row: (-float(row["score_pct"]), str(row["variant_name"])))
    write_csv(out_dir / "paper_variant_summary.csv", merged_rows)
    write_group_stats_csv(merged_rows, "board_family", out_dir / "board_family_score_stats.csv")
    write_group_stats_csv(merged_rows, "search_tier", out_dir / "search_tier_score_stats.csv")
    write_group_stats_csv(merged_rows, "eval_tier", out_dir / "eval_tier_score_stats.csv")

    xs = [float(row["perft6_sec"]) for row in merged_rows]
    ys = [float(row["score_pct"]) for row in merged_rows]
    perft_corr = corr(xs, ys)

    beat_counts: dict[str, int] = {}
    draw_counts: dict[str, int] = {}
    for anchor_name in anchor_names:
        beat_counts[anchor_name] = sum(1 for row in merged_rows if float(row[f"{anchor_name}_score"]) > float(row[f"{anchor_name}_games"]) / 2)
        draw_counts[anchor_name] = sum(1 for row in merged_rows if float(row[f"{anchor_name}_score"]) == float(row[f"{anchor_name}_games"]) / 2 and float(row[f"{anchor_name}_games"]) > 0)

    shift_rows = [row for row in merged_rows if row["delta_score_pct"] != ""]
    shift_rows.sort(key=lambda row: float(row["delta_score_pct"]))

    merged_by_name = {str(row["variant_name"]): row for row in merged_rows}
    overall_ladder_rows: list[dict[str, object]] = []
    standings_order = [row["player"] for row in standings]
    for row in standings:
        name = row["player"]
        if row["kind"] == "stockfish":
            bucket = "stockfish"
        else:
            bucket = str(merged_by_name.get(name, {}).get("bucket", "unknown"))
        overall_ladder_rows.append(
            {
                "name": name,
                "score_pct": float(row["score_pct"]),
                "kind": row["kind"],
                "bucket": bucket,
            }
        )

    total_players = len(standings)
    variant_count = sum(1 for row in standings if row["kind"] == "variant")
    stockfish_count = sum(1 for row in standings if row["kind"] == "stockfish")
    total_games = len(games)
    games_per_player_values = sorted({int(row["games"]) for row in standings})
    games_per_player_label = (
        str(games_per_player_values[0])
        if len(games_per_player_values) == 1
        else ", ".join(str(value) for value in games_per_player_values)
    )
    pairings = total_players * (total_players - 1) // 2 if total_players else 0
    games_per_pair = rounds * games_per_encounter if rounds and games_per_encounter else 0
    variants_above_sf1500 = sum(1 for row in merged_rows if float(row["score_pct"]) > sf1500_pct)
    variants_above_sf2000 = sum(1 for row in merged_rows if float(row["score_pct"]) > sf2000_pct)
    variants_above_sf2500 = sum(1 for row in merged_rows if float(row["score_pct"]) > anchor_score_pct.get("sf2500", 101.0))

    mid_start = max(0, len(merged_rows) // 2 - 2)
    representative_variant_names = [str(row["variant_name"]) for row in merged_rows[:4]]
    representative_variant_names.extend(str(row["variant_name"]) for row in merged_rows[mid_start : mid_start + 4])
    representative_variant_names.extend(str(row["variant_name"]) for row in merged_rows[-4:])
    seen_reps: set[str] = set()
    representative_variant_names = [
        name for name in representative_variant_names
        if not (name in seen_reps or seen_reps.add(name))
    ]
    representative_name_set = set(anchor_names) | set(representative_variant_names)
    representative_names = [name for name in standings_order if name in representative_name_set]

    plots_dir = out_dir / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)
    write_strength_vs_perft(
        merged_rows,
        anchor_lines={name: anchor_score_pct[name] for name in anchor_names},
        out_path=plots_dir / "strength_vs_perft6.svg",
    )
    write_anchor_heatmap(merged_rows, anchor_names, plots_dir / "anchor_matchup_heatmap.svg")
    if shift_rows:
        write_rank_shift(shift_rows, plots_dir / "rank_shift_shallow_vs_realistic.svg")

    write_strength_vs_perft_png(
        merged_rows,
        anchor_lines={name: anchor_score_pct[name] for name in anchor_names},
        out_path=plots_dir / "strength_vs_perft6.png",
        target_width=args.png_width,
    )
    write_strength_vs_perft_publication_png(
        merged_rows,
        anchor_lines={name: anchor_score_pct[name] for name in anchor_names},
        out_path=plots_dir / "strength_vs_perft6_publication.png",
        key_csv_path=out_dir / "strength_vs_perft6_publication_key.csv",
        target_width=args.png_width,
    )
    write_anchor_heatmap_png(
        merged_rows,
        anchor_names,
        plots_dir / "anchor_matchup_heatmap.png",
        target_width=args.png_width,
    )
    write_score_ladder_png(
        overall_ladder_rows,
        plots_dir / "score_ladder.png",
        target_width=args.png_width,
        title=f"Full Round-Robin Score Ladder ({total_players} Players)",
    )
    write_mean_score_bar_png(
        merged_rows,
        "board_family",
        "Mean Tournament Score by Board Family",
        plots_dir / "score_by_board_family.png",
        target_width=args.png_width,
    )
    write_mean_score_bar_png(
        merged_rows,
        "search_tier",
        "Mean Tournament Score by Search Tier",
        plots_dir / "score_by_search_tier.png",
        target_width=args.png_width,
    )
    write_mean_score_bar_png(
        merged_rows,
        "eval_tier",
        "Mean Tournament Score by Eval Tier",
        plots_dir / "score_by_eval_tier.png",
        target_width=args.png_width,
    )
    write_pairwise_heatmap_png(
        representative_names,
        pairwise_scores,
        plots_dir / "representative_pairwise_heatmap.png",
        target_width=args.png_width,
        title="Representative Pairwise Heatmap",
    )
    if shift_rows:
        write_rank_shift_png(
            shift_rows,
            plots_dir / "rank_shift_shallow_vs_realistic.png",
            target_width=args.png_width,
        )

    grayscale_dir = out_dir / "plots_gray"
    for src in sorted(plots_dir.glob("*.png")):
        write_grayscale_png(src, grayscale_dir / src.name.replace(".png", "_gray.png"))

    top_rows = merged_rows[:5]
    bottom_rows = merged_rows[-5:]
    strong_rows = [row for row in merged_rows if row["bucket"] == "strong"]
    mid_rows = [row for row in merged_rows if row["bucket"] == "mid"]
    weak_rows = [row for row in merged_rows if row["bucket"] == "weak"]
    representative_rows: list[dict[str, object]] = []
    for bucket in ("strong", "mid", "weak"):
        representative_rows.extend(select_bucket_representatives(merged_rows, bucket))
    write_csv(
        out_dir / "representative_variants.csv",
        [
            {
                "bucket": row["bucket"],
                "representative_role": row["representative_role"],
                "variant_name": row["variant_name"],
                "score_pct": row["score_pct"],
                "board_family": row["board_family"],
                "search_tier": row["search_tier"],
                "eval_tier": row["eval_tier"],
                "perft6_sec": row["perft6_sec"],
                "source_kind": row["source_kind"],
            }
            for row in representative_rows
        ],
    )
    best_control = max(
        (row for row in merged_rows if str(row["variant_name"]) in {"phase1_minimax", "phase2_10x12_ab_pvs_id", "phase3_full_eval", "strong_variant_02"}),
        key=lambda row: float(row["score_pct"]),
        default=None,
    )
    best_board_family = max(
        (
            (group_name, statistics.mean(float(row["score_pct"]) for row in merged_rows if str(row["board_family"]) == group_name))
            for group_name in sorted({str(row["board_family"]) for row in merged_rows})
        ),
        key=lambda item: item[1],
        default=("n/a", 0.0),
    )
    best_search_tier = max(
        (
            (group_name, statistics.mean(float(row["score_pct"]) for row in merged_rows if str(row["search_tier"]) == group_name))
            for group_name in sorted({str(row["search_tier"]) for row in merged_rows})
        ),
        key=lambda item: item[1],
        default=("n/a", 0.0),
    )

    report_lines = [
        "# Realistic Tournament Analysis",
        "",
        "## Design",
        "",
        f"- Candidate pool: `N=100` stratified variants were screened earlier with legality checks and perft-6; this run evaluates the resulting `N'={variant_count}` shortlist under real games.",
        f"- Goal: measure diversity of *playing strength*, not just move-generation cost, via a full round-robin that exposes internal matchup structure.",
        f"- Tournament setup: `{total_players}` total players (`{variant_count}` variants + `{stockfish_count}` Stockfish anchors), pairing mode `{pairing_mode}`, `{pairings}` unique pairings, `{games_per_pair}` games per pairing.",
        f"- Search mode: `{search_mode}`.",
        f"- Schedule: `{total_games}` finished games, `{games_per_player_label}` games per player.",
    ]
    if openings_count:
        report_lines.append(f"- Opening suite: `{openings_count}` fixed opening lines repeated across encounters.")

    report_lines.extend(
        [
            "",
            "## Rationale",
            "",
            "- The earlier anchor-only screen was cheaper, but it could only place variants relative to Stockfish profiles.",
            "- This full round-robin is much more expensive, but it supports stronger claims about internal strength structure, matchup-specific behavior, and representative weak/mid/strong selection.",
            "",
            "## Key Findings",
            "",
            f"- Strength diversity is large: variant scores range from `{merged_rows[-1]['score_pct']:.1f}%` to `{merged_rows[0]['score_pct']:.1f}%`.",
            f"- The strongest variant is `{merged_rows[0]['variant_name']}` at `{merged_rows[0]['score_pct']:.1f}%`; the weakest is `{merged_rows[-1]['variant_name']}` at `{merged_rows[-1]['score_pct']:.1f}%`.",
            f"- `{variants_above_sf1500}` variants finished above `sf1500` in the overall table, `{variants_above_sf2000}` finished above `sf2000`, and `{variants_above_sf2500}` finished above `sf2500`.",
            f"- Head-to-head anchor results are also diverse: `{beat_counts.get('sf1500', 0)}` variants scored above 50% against `sf1500`, `{beat_counts.get('sf2000', 0)}` against `sf2000`, `{beat_counts.get('sf2500', 0)}` against `sf2500`, and `{draw_counts.get('sf2500', 0)}` drew `sf2500` exactly.",
            f"- Perft-6 runtime remains only weakly related to playing strength (`r = {perft_corr:.3f}`), so move-generation speed is not a reliable proxy for tournament performance.",
            f"- The strongest mean board family in this shortlist is `{best_board_family[0]}` (`{best_board_family[1]:.1f}%` mean score); the strongest mean search tier is `{best_search_tier[0]}` (`{best_search_tier[1]:.1f}%`).",
        ]
    )

    if best_control is not None:
        report_lines.append(
            f"- Among the fixed controls, `{best_control['variant_name']}` is best at `{best_control['score_pct']:.1f}%`."
        )

    if shift_rows:
        biggest_drop = shift_rows[0]
        biggest_gain = shift_rows[-1]
        report_lines.append(
            f"- Realistic time control reorders the shallow ranking: biggest drop is `{biggest_drop['variant_name']}` (`{float(biggest_drop['delta_score_pct']):+.1f}` points), biggest gain is `{biggest_gain['variant_name']}` (`{float(biggest_gain['delta_score_pct']):+.1f}` points)."
        )

    report_lines.extend(
        [
            "",
            "## Buckets",
            "",
            f"- strong (`>{sf2000_pct:.1f}%`, above `sf2000` overall): " + ", ".join(f"`{row['variant_name']}`" for row in strong_rows),
            f"- mid (`{sf1500_pct:.1f}%` to `{sf2000_pct:.1f}%`): " + ", ".join(f"`{row['variant_name']}`" for row in mid_rows),
            f"- weak (`<{sf1500_pct:.1f}%`, below `sf1500` overall): " + ", ".join(f"`{row['variant_name']}`" for row in weak_rows),
            "",
            "## Top Variants",
            "",
        ]
    )

    for row in top_rows:
        report_lines.append(
            f"- `{row['variant_name']}`: `{row['score_pct']:.1f}%`, `{row['board_family']}`, `{row['search_tier']}`, `{row['eval_tier']}`, `perft6={row['perft6_sec']:.3f}s`"
        )

    report_lines.extend(["", "## Weak Tail", ""])
    for row in bottom_rows:
        report_lines.append(
            f"- `{row['variant_name']}`: `{row['score_pct']:.1f}%`, `{row['board_family']}`, `{row['search_tier']}`, `{row['eval_tier']}`, `perft6={row['perft6_sec']:.3f}s`"
        )

    report_lines.extend(
        [
            "",
            "## Figure Set",
            "",
            "- `plots/strength_vs_perft6_publication.png`: final publication-oriented version with numbered callouts and a compact key.",
            "- `plots/score_ladder.png`: full 53-player score ladder with anchors and weak/mid/strong variant bands.",
            "- `plots/strength_vs_perft6.png`: tournament score versus perft-6 runtime, with anchor score lines.",
            "- `plots/anchor_matchup_heatmap.png`: direct head-to-head scores against `sf1500`, `sf2000`, and `sf2500`.",
            "- `plots/representative_pairwise_heatmap.png`: representative pairwise matrix showing internal matchup structure beyond anchors.",
            "- `plots/score_by_board_family.png`: mean score by board family.",
            "- `plots/score_by_search_tier.png`: mean score by search tier.",
            "- `plots/score_by_eval_tier.png`: mean score by eval tier.",
            "- `plots_gray/*.png`: grayscale journal-style versions of the PNG figures.",
        ]
    )
    if shift_rows:
        report_lines.append("- `plots/rank_shift_shallow_vs_realistic.png`: score change from the shallow depth-3 run to the realistic time-control run.")

    report_lines.extend(
        [
            "",
            "## Representative Set",
            "",
            "- `representative_variants.csv`: nine representative variants selected from the full round-robin (`3` strong, `3` mid, `3` weak).",
            "- Selection rule: top / median / bottom within each bucket, with light diversity preference across board family, search tier, and eval tier.",
        ]
    )

    report_lines.extend(
        [
            "",
            "## Caveats",
            "",
            "- This is a strong diversity benchmark, but it is still not a formal Elo study.",
            "- The bucket labels are relative to overall round-robin score, not calibrated rating intervals.",
            "- The anchor trio improves interpretability, but conclusions about strength should rely on the full interaction graph, not on any single anchor alone.",
        ]
    )

    (out_dir / "paper_report.md").write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    results_lines = [
        "## Results",
        "",
        f"Our full round-robin evaluated `50` shortlisted variants together with `3` Stockfish anchors under `{search_mode}`, yielding `{total_games}` games (`{games_per_player_label}` per player) across `{pairings}` unique pairings. This design moves beyond anchor-only screening by exposing the internal competitive structure of the variant space.",
        "",
        f"The resulting strength distribution is broad. Variant scores span from `{merged_rows[-1]['score_pct']:.1f}%` to `{merged_rows[0]['score_pct']:.1f}%`, with `{variants_above_sf1500}` variants finishing above `sf1500` in the overall table and `{variants_above_sf2000}` finishing above `sf2000`. The strongest three variants are `{merged_rows[0]['variant_name']}` (`{merged_rows[0]['score_pct']:.1f}%`), `{merged_rows[1]['variant_name']}` (`{merged_rows[1]['score_pct']:.1f}%`), and `{merged_rows[2]['variant_name']}` (`{merged_rows[2]['score_pct']:.1f}%`). At the other extreme, `{merged_rows[-1]['variant_name']}` and the other tail variants form a clearly separated weak region of the space.",
        "",
        f"Perft remains a poor proxy for playing strength in this experiment. The correlation between perft-6 runtime and tournament score is only `{perft_corr:.3f}`, showing that faster move generation does not reliably imply stronger play. The board-family and search-tier aggregates also show that strength is structured by architectural choices rather than by raw feature count alone.",
        "",
        f"Most importantly, the full round-robin reveals internal diversity that anchor-only screening cannot capture. The score ladder and representative pairwise heatmap show that variants with similar anchor-relative performance can still occupy very different positions in the interaction graph. For downstream analysis, we therefore retain a representative set of nine variants, with three representatives from each weak, mid, and strong bucket, extracted directly from the full round-robin results.",
        "",
    ]
    (out_dir / "results_subsection.md").write_text("\n".join(results_lines), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
