#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import statistics
from pathlib import Path

from pillow_plot_utils import draw_rotated_text, draw_text, new_canvas, rgba, save_png


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


def filter_screen_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [row for row in rows if row.get("perft_sec") and row.get("screen_pass") == "PASS"]


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_svg(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_scatter(rows: list[dict[str, str]], out_path: Path) -> None:
    width = 960
    height = 560
    margin_left = 70
    margin_right = 30
    margin_top = 35
    margin_bottom = 60
    plot_w = width - margin_left - margin_right
    plot_h = height - margin_top - margin_bottom

    colors = {
        "Bitboards": "#1f77b4",
        "0x88": "#ff7f0e",
        "Mailbox": "#2ca02c",
        "10x12 Board": "#d62728",
        "unknown": "#7f7f7f",
    }

    xs = [int(row["selected_feature_count"]) for row in rows]
    ys = [float(row["perft_sec"]) for row in rows]
    x_min = min(xs)
    x_max = max(xs)
    y_min = min(ys)
    y_max = max(ys)
    if x_min == x_max:
        x_min -= 1
        x_max += 1
    if y_min == y_max:
        y_min = max(0.0, y_min - 1.0)
        y_max += 1.0

    def map_x(value: int) -> float:
        return margin_left + (value - x_min) / (x_max - x_min) * plot_w

    def map_y(value: float) -> float:
        return margin_top + plot_h - (value - y_min) / (y_max - y_min) * plot_h

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<style>text{font-family:Menlo,Consolas,monospace;font-size:12px;fill:#222} .axis{stroke:#333;stroke-width:1} .grid{stroke:#ddd;stroke-width:1} .label{font-size:11px}</style>',
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="#fffaf0"/>',
        f'<text x="{width/2:.1f}" y="20" text-anchor="middle">Perft Time vs Feature Count</text>',
    ]

    for step in range(6):
        x_value = x_min + (x_max - x_min) * step / 5.0
        x_pos = map_x(x_value)
        lines.append(f'<line class="grid" x1="{x_pos:.1f}" y1="{margin_top}" x2="{x_pos:.1f}" y2="{margin_top + plot_h}"/>')
        lines.append(f'<text class="label" x="{x_pos:.1f}" y="{height - 22}" text-anchor="middle">{int(round(x_value))}</text>')

    for step in range(6):
        y_value = y_min + (y_max - y_min) * step / 5.0
        y_pos = map_y(y_value)
        lines.append(f'<line class="grid" x1="{margin_left}" y1="{y_pos:.1f}" x2="{margin_left + plot_w}" y2="{y_pos:.1f}"/>')
        lines.append(f'<text class="label" x="{margin_left - 10}" y="{y_pos + 4:.1f}" text-anchor="end">{y_value:.2f}</text>')

    lines.append(f'<line class="axis" x1="{margin_left}" y1="{margin_top + plot_h}" x2="{margin_left + plot_w}" y2="{margin_top + plot_h}"/>')
    lines.append(f'<line class="axis" x1="{margin_left}" y1="{margin_top}" x2="{margin_left}" y2="{margin_top + plot_h}"/>')
    lines.append(f'<text x="{width / 2:.1f}" y="{height - 8}" text-anchor="middle">Selected Feature Count</text>')
    lines.append(f'<text x="18" y="{height / 2:.1f}" text-anchor="middle" transform="rotate(-90 18 {height / 2:.1f})">Perft Time (s)</text>')

    labels = sorted(rows, key=lambda r: float(r["perft_sec"]))[:4] + sorted(rows, key=lambda r: float(r["perft_sec"]), reverse=True)[:4]
    label_names = {row["variant_name"] for row in labels}
    for row in rows:
        cx = map_x(int(row["selected_feature_count"]))
        cy = map_y(float(row["perft_sec"]))
        color = colors.get(row["board_family"], colors["unknown"])
        radius = 5 if row["source_kind"] == "control" else 3.5
        stroke = "#000" if row["source_kind"] == "control" else "none"
        lines.append(
            f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{radius}" fill="{color}" stroke="{stroke}" stroke-width="1">'
            f'<title>{svg_escape(row["variant_name"])} | {svg_escape(row["stratum"])} | perft={row["perft_sec"]}s</title></circle>'
        )
        if row["variant_name"] in label_names:
            lines.append(f'<text class="label" x="{cx + 7:.1f}" y="{cy - 7:.1f}">{svg_escape(row["variant_name"])}</text>')

    lines.append("</svg>")
    write_svg(out_path, lines)


def write_mean_bar(rows: list[dict[str, str]], key: str, title: str, out_path: Path) -> None:
    grouped: dict[str, list[float]] = {}
    for row in rows:
        grouped.setdefault(row[key], []).append(float(row["perft_sec"]))
    stats = sorted((name, sum(values) / len(values), len(values)) for name, values in grouped.items())
    if not stats:
        return

    width = 920
    height = 520
    margin_left = 70
    margin_right = 30
    margin_top = 40
    margin_bottom = 110
    plot_w = width - margin_left - margin_right
    plot_h = height - margin_top - margin_bottom
    max_value = max(value for _, value, _ in stats)
    palette = ["#4c78a8", "#f58518", "#54a24b", "#e45756", "#72b7b2", "#b279a2", "#ff9da6", "#9d755d"]

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<style>text{font-family:Menlo,Consolas,monospace;font-size:12px;fill:#222} .axis{stroke:#333;stroke-width:1} .grid{stroke:#ddd;stroke-width:1} .label{font-size:11px}</style>',
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="#f7fbff"/>',
        f'<text x="{width/2:.1f}" y="22" text-anchor="middle">{svg_escape(title)}</text>',
    ]

    for step in range(6):
        value = max_value * step / 5.0
        y = margin_top + plot_h - (value / max_value * plot_h if max_value > 0 else 0.0)
        lines.append(f'<line class="grid" x1="{margin_left}" y1="{y:.1f}" x2="{margin_left + plot_w}" y2="{y:.1f}"/>')
        lines.append(f'<text class="label" x="{margin_left - 8}" y="{y + 4:.1f}" text-anchor="end">{value:.2f}</text>')

    bar_w = plot_w / max(len(stats), 1) * 0.62
    gap = plot_w / max(len(stats), 1)
    for idx, (name, value, count) in enumerate(stats):
        x = margin_left + idx * gap + (gap - bar_w) / 2.0
        bar_h = 0.0 if max_value == 0 else value / max_value * plot_h
        y = margin_top + plot_h - bar_h
        color = palette[idx % len(palette)]
        lines.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{bar_h:.1f}" fill="{color}">'
            f'<title>{svg_escape(name)}: mean={value:.3f}s n={count}</title></rect>'
        )
        lines.append(f'<text class="label" x="{x + bar_w / 2:.1f}" y="{y - 8:.1f}" text-anchor="middle">{value:.2f}</text>')
        lines.append(f'<text class="label" x="{x + bar_w / 2:.1f}" y="{height - 45}" text-anchor="middle">{svg_escape(name)}</text>')
        lines.append(f'<text class="label" x="{x + bar_w / 2:.1f}" y="{height - 30}" text-anchor="middle">n={count}</text>')

    lines.append(f'<line class="axis" x1="{margin_left}" y1="{margin_top + plot_h}" x2="{margin_left + plot_w}" y2="{margin_top + plot_h}"/>')
    lines.append(f'<line class="axis" x1="{margin_left}" y1="{margin_top}" x2="{margin_left}" y2="{margin_top + plot_h}"/>')
    lines.append("</svg>")
    write_svg(out_path, lines)


def percentile(sorted_values: list[float], p: float) -> float:
    if not sorted_values:
        raise ValueError("percentile requires at least one value")
    if len(sorted_values) == 1:
        return sorted_values[0]
    index = (len(sorted_values) - 1) * p
    lower = int(index)
    upper = min(lower + 1, len(sorted_values) - 1)
    fraction = index - lower
    return sorted_values[lower] * (1.0 - fraction) + sorted_values[upper] * fraction


def compute_box_stats(values: list[float]) -> dict[str, float | int]:
    sorted_values = sorted(values)
    q1 = percentile(sorted_values, 0.25)
    median = percentile(sorted_values, 0.5)
    q3 = percentile(sorted_values, 0.75)
    iqr = q3 - q1
    low_fence = q1 - 1.5 * iqr
    high_fence = q3 + 1.5 * iqr
    inliers = [value for value in sorted_values if low_fence <= value <= high_fence]
    whisker_low = min(inliers) if inliers else sorted_values[0]
    whisker_high = max(inliers) if inliers else sorted_values[-1]
    outliers = [value for value in sorted_values if value < whisker_low or value > whisker_high]
    return {
        "count": len(sorted_values),
        "min": sorted_values[0],
        "q1": q1,
        "median": median,
        "q3": q3,
        "max": sorted_values[-1],
        "iqr": iqr,
        "mean": statistics.mean(sorted_values),
        "whisker_low": whisker_low,
        "whisker_high": whisker_high,
        "outlier_count": len(outliers),
    }


def write_boxplot_summary_csv(rows: list[dict[str, str]], key: str, out_path: Path) -> None:
    grouped: dict[str, list[float]] = {}
    for row in rows:
        grouped.setdefault(row[key], []).append(float(row["perft_sec"]))
    stats_rows: list[dict[str, str | int | float]] = []
    for group_name in sorted(grouped):
        stats = compute_box_stats(grouped[group_name])
        stats_rows.append(
            {
                key: group_name,
                "count": int(stats["count"]),
                "min": round(float(stats["min"]), 6),
                "q1": round(float(stats["q1"]), 6),
                "median": round(float(stats["median"]), 6),
                "q3": round(float(stats["q3"]), 6),
                "max": round(float(stats["max"]), 6),
                "iqr": round(float(stats["iqr"]), 6),
                "mean": round(float(stats["mean"]), 6),
                "whisker_low": round(float(stats["whisker_low"]), 6),
                "whisker_high": round(float(stats["whisker_high"]), 6),
                "outlier_count": int(stats["outlier_count"]),
            }
        )
    with out_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                key,
                "count",
                "min",
                "q1",
                "median",
                "q3",
                "max",
                "iqr",
                "mean",
                "whisker_low",
                "whisker_high",
                "outlier_count",
            ],
        )
        writer.writeheader()
        writer.writerows(stats_rows)


def write_boxplot(rows: list[dict[str, str]], key: str, title: str, out_path: Path) -> None:
    grouped: dict[str, list[float]] = {}
    for row in rows:
        grouped.setdefault(row[key], []).append(float(row["perft_sec"]))
    groups = [(group_name, compute_box_stats(values)) for group_name, values in sorted(grouped.items())]
    if not groups:
        return

    width = 980
    height = 560
    margin_left = 80
    margin_right = 30
    margin_top = 40
    margin_bottom = 110
    plot_w = width - margin_left - margin_right
    plot_h = height - margin_top - margin_bottom
    y_max = max(float(stats["max"]) for _, stats in groups)
    if y_max <= 0:
        y_max = 1.0
    palette = ["#4c78a8", "#f58518", "#54a24b", "#e45756", "#72b7b2", "#b279a2", "#ff9da6", "#9d755d"]

    def map_y(value: float) -> float:
        return margin_top + plot_h - (value / y_max) * plot_h

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<style>text{font-family:Menlo,Consolas,monospace;font-size:12px;fill:#222} .axis{stroke:#333;stroke-width:1} .grid{stroke:#ddd;stroke-width:1} .box{stroke:#333;stroke-width:1.2} .median{stroke:#111;stroke-width:2} .whisker{stroke:#333;stroke-width:1.2} .outlier{fill:#111}</style>',
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="#fff"/>',
        f'<text x="{width / 2:.1f}" y="22" text-anchor="middle">{svg_escape(title)}</text>',
    ]

    for step in range(6):
        value = y_max * step / 5.0
        y = map_y(value)
        lines.append(f'<line class="grid" x1="{margin_left}" y1="{y:.1f}" x2="{margin_left + plot_w}" y2="{y:.1f}"/>')
        lines.append(f'<text x="{margin_left - 8}" y="{y + 4:.1f}" text-anchor="end">{value:.2f}</text>')

    gap = plot_w / max(len(groups), 1)
    box_w = min(gap * 0.46, 100.0)
    for idx, (group_name, stats) in enumerate(groups):
        center_x = margin_left + idx * gap + gap / 2.0
        color = palette[idx % len(palette)]
        q1_y = map_y(float(stats["q1"]))
        median_y = map_y(float(stats["median"]))
        q3_y = map_y(float(stats["q3"]))
        whisker_low_y = map_y(float(stats["whisker_low"]))
        whisker_high_y = map_y(float(stats["whisker_high"]))
        box_x = center_x - box_w / 2.0
        box_h = max(1.5, q1_y - q3_y)
        lines.append(
            f'<rect class="box" x="{box_x:.1f}" y="{q3_y:.1f}" width="{box_w:.1f}" height="{box_h:.1f}" fill="{color}" fill-opacity="0.70">'
            f'<title>{svg_escape(group_name)}: median={float(stats["median"]):.3f}s q1={float(stats["q1"]):.3f}s q3={float(stats["q3"]):.3f}s n={int(stats["count"])}</title></rect>'
        )
        lines.append(f'<line class="median" x1="{box_x:.1f}" y1="{median_y:.1f}" x2="{box_x + box_w:.1f}" y2="{median_y:.1f}"/>')
        lines.append(f'<line class="whisker" x1="{center_x:.1f}" y1="{q3_y:.1f}" x2="{center_x:.1f}" y2="{whisker_high_y:.1f}"/>')
        lines.append(f'<line class="whisker" x1="{center_x:.1f}" y1="{q1_y:.1f}" x2="{center_x:.1f}" y2="{whisker_low_y:.1f}"/>')
        lines.append(f'<line class="whisker" x1="{center_x - box_w * 0.28:.1f}" y1="{whisker_high_y:.1f}" x2="{center_x + box_w * 0.28:.1f}" y2="{whisker_high_y:.1f}"/>')
        lines.append(f'<line class="whisker" x1="{center_x - box_w * 0.28:.1f}" y1="{whisker_low_y:.1f}" x2="{center_x + box_w * 0.28:.1f}" y2="{whisker_low_y:.1f}"/>')

        group_values = sorted(float(row["perft_sec"]) for row in rows if row[key] == group_name)
        for value in group_values:
            if value < float(stats["whisker_low"]) or value > float(stats["whisker_high"]):
                lines.append(f'<circle class="outlier" cx="{center_x:.1f}" cy="{map_y(value):.1f}" r="3"/>')

        lines.append(f'<text x="{center_x:.1f}" y="{height - 45}" text-anchor="middle">{svg_escape(group_name)}</text>')
        lines.append(f'<text x="{center_x:.1f}" y="{height - 28}" text-anchor="middle">n={int(stats["count"])}</text>')

    lines.append(f'<line class="axis" x1="{margin_left}" y1="{margin_top + plot_h}" x2="{margin_left + plot_w}" y2="{margin_top + plot_h}"/>')
    lines.append(f'<line class="axis" x1="{margin_left}" y1="{margin_top}" x2="{margin_left}" y2="{margin_top + plot_h}"/>')
    lines.append(f'<text x="18" y="{height / 2:.1f}" text-anchor="middle" transform="rotate(-90 18 {height / 2:.1f})">Perft Time (s)</text>')
    lines.append("</svg>")
    write_svg(out_path, lines)


def write_rank_plot(rows: list[dict[str, str]], out_path: Path, limit: int = 25) -> None:
    ranked = sorted(rows, key=lambda r: float(r["perft_sec"]))[:limit]
    width = 980
    row_h = 22
    height = 80 + row_h * len(ranked)
    margin_left = 250
    margin_right = 40
    plot_w = width - margin_left - margin_right
    max_value = max(float(row["perft_sec"]) for row in ranked)

    colors = {
        "Bitboards": "#1f77b4",
        "0x88": "#ff7f0e",
        "Mailbox": "#2ca02c",
        "10x12 Board": "#d62728",
        "unknown": "#7f7f7f",
    }

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<style>text{font-family:Menlo,Consolas,monospace;font-size:12px;fill:#222} .axis{stroke:#333;stroke-width:1} .grid{stroke:#ddd;stroke-width:1}</style>',
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="#ffffff"/>',
        f'<text x="{width/2:.1f}" y="24" text-anchor="middle">Fastest Screen-Passing Variants by Perft Time</text>',
    ]

    for idx, row in enumerate(ranked):
        y = 50 + idx * row_h
        value = float(row["perft_sec"])
        bar_w = 0.0 if max_value == 0 else value / max_value * plot_w
        lines.append(f'<text x="10" y="{y + 14:.1f}">{idx + 1:02d}</text>')
        lines.append(f'<text x="40" y="{y + 14:.1f}">{svg_escape(row["variant_name"])}</text>')
        lines.append(f'<rect x="{margin_left}" y="{y:.1f}" width="{bar_w:.1f}" height="14" fill="{colors.get(row["board_family"], colors["unknown"])}"/>')
        lines.append(f'<text x="{margin_left + bar_w + 8:.1f}" y="{y + 12:.1f}">{value:.3f}s</text>')
        lines.append(f'<text x="{width - 10}" y="{y + 14:.1f}" text-anchor="end">{svg_escape(row["stratum"])}</text>')

    lines.append("</svg>")
    write_svg(out_path, lines)


def write_slowest_plot(rows: list[dict[str, str]], out_path: Path, limit: int = 25) -> None:
    ranked = sorted(rows, key=lambda r: float(r["perft_sec"]), reverse=True)[:limit]
    width = 980
    row_h = 22
    height = 80 + row_h * len(ranked)
    margin_left = 250
    margin_right = 40
    plot_w = width - margin_left - margin_right
    max_value = max(float(row["perft_sec"]) for row in ranked)

    colors = {
        "Bitboards": "#1f77b4",
        "0x88": "#ff7f0e",
        "Mailbox": "#2ca02c",
        "10x12 Board": "#d62728",
        "unknown": "#7f7f7f",
    }

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<style>text{font-family:Menlo,Consolas,monospace;font-size:12px;fill:#222} .axis{stroke:#333;stroke-width:1} .grid{stroke:#ddd;stroke-width:1}</style>',
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="#ffffff"/>',
        f'<text x="{width/2:.1f}" y="24" text-anchor="middle">Slowest Screen-Passing Variants by Perft Time</text>',
    ]

    for idx, row in enumerate(ranked):
        y = 50 + idx * row_h
        value = float(row["perft_sec"])
        bar_w = 0.0 if max_value == 0 else value / max_value * plot_w
        lines.append(f'<text x="10" y="{y + 14:.1f}">{idx + 1:02d}</text>')
        lines.append(f'<text x="40" y="{y + 14:.1f}">{svg_escape(row["variant_name"])}</text>')
        lines.append(f'<rect x="{margin_left}" y="{y:.1f}" width="{bar_w:.1f}" height="14" fill="{colors.get(row["board_family"], colors["unknown"])}"/>')
        lines.append(f'<text x="{margin_left + bar_w + 8:.1f}" y="{y + 12:.1f}">{value:.3f}s</text>')
        lines.append(f'<text x="{width - 10}" y="{y + 14:.1f}" text-anchor="end">{svg_escape(row["stratum"])}</text>')

    lines.append("</svg>")
    write_svg(out_path, lines)


def write_heatmap(rows: list[dict[str, str]], out_path: Path) -> None:
    board_keys = sorted({row["board_family"] for row in rows})
    search_keys = sorted({row["search_tier"] for row in rows})
    counts = {(board, search): 0 for board in board_keys for search in search_keys}
    for row in rows:
        counts[(row["board_family"], row["search_tier"])] += 1
    max_count = max(counts.values()) if counts else 1

    cell_w = 120
    cell_h = 40
    margin_left = 140
    margin_top = 80
    width = margin_left + cell_w * len(search_keys) + 40
    height = margin_top + cell_h * len(board_keys) + 40

    def fill_for(value: int) -> str:
        scale = value / max_count if max_count else 0.0
        blue = int(255 - scale * 120)
        red = int(247 - scale * 30)
        green = int(251 - scale * 80)
        return f"rgb({red},{green},{blue})"

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<style>text{font-family:Menlo,Consolas,monospace;font-size:12px;fill:#222} .cell{stroke:#ddd;stroke-width:1}</style>',
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="#fff"/>',
        f'<text x="{width/2:.1f}" y="28" text-anchor="middle">Sample Diversity: Board Family x Search Tier</text>',
    ]

    for idx, search in enumerate(search_keys):
        x = margin_left + idx * cell_w + cell_w / 2
        lines.append(f'<text x="{x:.1f}" y="58" text-anchor="middle">{svg_escape(search)}</text>')
    for idx, board in enumerate(board_keys):
        y = margin_top + idx * cell_h + cell_h / 2 + 4
        lines.append(f'<text x="{margin_left - 10}" y="{y:.1f}" text-anchor="end">{svg_escape(board)}</text>')

    for row_idx, board in enumerate(board_keys):
        for col_idx, search in enumerate(search_keys):
            x = margin_left + col_idx * cell_w
            y = margin_top + row_idx * cell_h
            value = counts[(board, search)]
            lines.append(f'<rect class="cell" x="{x}" y="{y}" width="{cell_w}" height="{cell_h}" fill="{fill_for(value)}"/>')
            lines.append(f'<text x="{x + cell_w/2:.1f}" y="{y + cell_h/2 + 4:.1f}" text-anchor="middle">{value}</text>')

    lines.append("</svg>")
    write_svg(out_path, lines)


def write_correctness_bar(probe_rows: list[dict[str, str]], out_path: Path) -> None:
    grouped: dict[str, tuple[int, int]] = {}
    for row in probe_rows:
        probe = row["probe"]
        passed, total = grouped.get(probe, (0, 0))
        grouped[probe] = (passed + (1 if row["legal"] == "PASS" else 0), total + 1)
    stats = sorted((probe, passed, total) for probe, (passed, total) in grouped.items())
    if not stats:
        return

    width = 820
    height = 420
    margin_left = 70
    margin_right = 30
    margin_top = 40
    margin_bottom = 90
    plot_w = width - margin_left - margin_right
    plot_h = height - margin_top - margin_bottom

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<style>text{font-family:Menlo,Consolas,monospace;font-size:12px;fill:#222} .axis{stroke:#333;stroke-width:1} .grid{stroke:#ddd;stroke-width:1}</style>',
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="#fff"/>',
        f'<text x="{width/2:.1f}" y="22" text-anchor="middle">Correctness Probe Pass Rate</text>',
    ]

    for step in range(6):
        pct = step / 5.0
        y = margin_top + plot_h - pct * plot_h
        lines.append(f'<line class="grid" x1="{margin_left}" y1="{y:.1f}" x2="{margin_left + plot_w}" y2="{y:.1f}"/>')
        lines.append(f'<text x="{margin_left - 8}" y="{y + 4:.1f}" text-anchor="end">{pct:.1f}</text>')

    gap = plot_w / len(stats)
    bar_w = gap * 0.6
    for idx, (probe, passed, total) in enumerate(stats):
        pct = passed / total if total else 0.0
        x = margin_left + idx * gap + (gap - bar_w) / 2
        h = pct * plot_h
        y = margin_top + plot_h - h
        color = "#2ca02c" if passed == total else "#d62728"
        lines.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{h:.1f}" fill="{color}"/>')
        lines.append(f'<text x="{x + bar_w/2:.1f}" y="{y - 8:.1f}" text-anchor="middle">{passed}/{total}</text>')
        lines.append(f'<text x="{x + bar_w/2:.1f}" y="{height - 35}" text-anchor="middle">{svg_escape(probe)}</text>')

    lines.append(f'<line class="axis" x1="{margin_left}" y1="{margin_top + plot_h}" x2="{margin_left + plot_w}" y2="{margin_top + plot_h}"/>')
    lines.append(f'<line class="axis" x1="{margin_left}" y1="{margin_top}" x2="{margin_left}" y2="{margin_top + plot_h}"/>')
    lines.append("</svg>")
    write_svg(out_path, lines)


def png_geometry(base_width: int, base_height: int, target_width: int) -> tuple[float, int, int]:
    scale = max(0.5, float(target_width) / float(base_width))
    return scale, int(round(base_width * scale)), int(round(base_height * scale))


def write_scatter_png(rows: list[dict[str, str]], out_path: Path, *, target_width: int) -> None:
    base_width = 960
    base_height = 560
    scale, width, height = png_geometry(base_width, base_height, target_width)
    image, draw = new_canvas(width, height, "#ffffff")

    margin_left = 70 * scale
    margin_right = 36 * scale
    margin_top = 35 * scale
    margin_bottom = 60 * scale
    plot_w = width - margin_left - margin_right
    plot_h = height - margin_top - margin_bottom

    colors = {
        "Bitboards": "#2E86DE",
        "0x88": "#FF8C42",
        "Mailbox": "#3FA34D",
        "10x12 Board": "#D94E41",
        "unknown": "#7F8C8D",
    }

    xs = [int(row["selected_feature_count"]) for row in rows]
    ys = [float(row["perft_sec"]) for row in rows]
    x_min = min(xs)
    x_max = max(xs)
    y_min = min(ys)
    y_max = max(ys)
    if x_min == x_max:
        x_min -= 1
        x_max += 1
    if y_min == y_max:
        y_min = max(0.0, y_min - 1.0)
        y_max += 1.0

    def map_x(value: int) -> float:
        return margin_left + (value - x_min) / (x_max - x_min) * plot_w

    def map_y(value: float) -> float:
        return margin_top + plot_h - (value - y_min) / (y_max - y_min) * plot_h

    draw_text(draw, (width / 2, 20 * scale), "Perft Time vs Feature Count", size=int(18 * scale), fill="#1A202C", bold=True, anchor="mm")
    for step in range(6):
        x_value = x_min + (x_max - x_min) * step / 5.0
        x_pos = map_x(x_value)
        draw.line((x_pos, margin_top, x_pos, margin_top + plot_h), fill=rgba("#EDF2F7"), width=max(1, int(2 * scale)))
        draw_text(draw, (x_pos, height - 22 * scale), f"{int(round(x_value))}", size=int(12 * scale), fill="#4A5568", anchor="mm")
    for step in range(6):
        y_value = y_min + (y_max - y_min) * step / 5.0
        y_pos = map_y(y_value)
        draw.line((margin_left, y_pos, margin_left + plot_w, y_pos), fill=rgba("#D9DEE7"), width=max(1, int(2 * scale)))
        draw_text(draw, (margin_left - 10 * scale, y_pos), f"{y_value:.2f}", size=int(12 * scale), fill="#4A5568", anchor="rm")

    draw.line((margin_left, margin_top + plot_h, margin_left + plot_w, margin_top + plot_h), fill=rgba("#2D3748"), width=max(2, int(3 * scale)))
    draw.line((margin_left, margin_top, margin_left, margin_top + plot_h), fill=rgba("#2D3748"), width=max(2, int(3 * scale)))
    draw_text(draw, (width / 2, height - 8 * scale), "Selected Feature Count", size=int(14 * scale), fill="#2D3748", bold=True, anchor="mm")
    draw_rotated_text(image, (18 * scale, height / 2), "Perft Time (s)", size=int(14 * scale), fill="#2D3748", bold=True, angle=90, anchor="mm")

    labels = sorted(rows, key=lambda r: float(r["perft_sec"]))[:4] + sorted(rows, key=lambda r: float(r["perft_sec"]), reverse=True)[:4]
    label_names = {row["variant_name"] for row in labels}
    for row in rows:
        cx = map_x(int(row["selected_feature_count"]))
        cy = map_y(float(row["perft_sec"]))
        color = colors.get(row["board_family"], colors["unknown"])
        radius = 5.5 * scale if row["source_kind"] == "control" else 4.0 * scale
        draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=rgba(color), outline=rgba("#1F2933"), width=max(1, int(2 * scale)))
        if row["variant_name"] in label_names:
            draw_text(draw, (cx + 8 * scale, cy - 8 * scale), row["variant_name"], size=int(11 * scale), fill="#1A202C", anchor="lm")

    save_png(image, out_path)


def write_mean_bar_png(rows: list[dict[str, str]], key: str, title: str, out_path: Path, *, target_width: int) -> None:
    grouped: dict[str, list[float]] = {}
    for row in rows:
        grouped.setdefault(row[key], []).append(float(row["perft_sec"]))
    stats = sorted((name, sum(values) / len(values), len(values)) for name, values in grouped.items())
    if not stats:
        return

    base_width = 920
    base_height = 520
    scale, width, height = png_geometry(base_width, base_height, target_width)
    image, draw = new_canvas(width, height, "#ffffff")

    margin_left = 70 * scale
    margin_right = 30 * scale
    margin_top = 40 * scale
    margin_bottom = 110 * scale
    plot_w = width - margin_left - margin_right
    plot_h = height - margin_top - margin_bottom
    max_value = max(value for _, value, _ in stats)
    palette = ["#4C78A8", "#F58518", "#54A24B", "#E45756", "#72B7B2", "#B279A2", "#FF9DA6", "#9D755D"]

    draw_text(draw, (width / 2, 22 * scale), title, size=int(18 * scale), fill="#1A202C", bold=True, anchor="mm")
    for step in range(6):
        value = max_value * step / 5.0
        y = margin_top + plot_h - (value / max_value * plot_h if max_value > 0 else 0.0)
        draw.line((margin_left, y, margin_left + plot_w, y), fill=rgba("#D9DEE7"), width=max(1, int(2 * scale)))
        draw_text(draw, (margin_left - 8 * scale, y), f"{value:.2f}", size=int(12 * scale), fill="#4A5568", anchor="rm")

    bar_w = plot_w / max(len(stats), 1) * 0.62
    gap = plot_w / max(len(stats), 1)
    for idx, (name, value, count) in enumerate(stats):
        x = margin_left + idx * gap + (gap - bar_w) / 2.0
        bar_h = 0.0 if max_value == 0 else value / max_value * plot_h
        y = margin_top + plot_h - bar_h
        color = palette[idx % len(palette)]
        draw.rounded_rectangle((x, y, x + bar_w, y + bar_h), radius=max(4, int(5 * scale)), fill=rgba(color))
        draw_text(draw, (x + bar_w / 2, y - 8 * scale), f"{value:.2f}", size=int(11 * scale), fill="#1A202C", bold=True, anchor="mm")
        draw_text(draw, (x + bar_w / 2, height - 45 * scale), name, size=int(11 * scale), fill="#2D3748", anchor="mm")
        draw_text(draw, (x + bar_w / 2, height - 28 * scale), f"n={count}", size=int(10 * scale), fill="#4A5568", anchor="mm")

    draw.line((margin_left, margin_top + plot_h, margin_left + plot_w, margin_top + plot_h), fill=rgba("#2D3748"), width=max(2, int(3 * scale)))
    draw.line((margin_left, margin_top, margin_left, margin_top + plot_h), fill=rgba("#2D3748"), width=max(2, int(3 * scale)))
    save_png(image, out_path)


def write_boxplot_png(rows: list[dict[str, str]], key: str, title: str, out_path: Path, *, target_width: int) -> None:
    grouped: dict[str, list[float]] = {}
    for row in rows:
        grouped.setdefault(row[key], []).append(float(row["perft_sec"]))
    groups = [(group_name, compute_box_stats(values)) for group_name, values in sorted(grouped.items())]
    if not groups:
        return

    base_width = 980
    base_height = 560
    scale, width, height = png_geometry(base_width, base_height, target_width)
    image, draw = new_canvas(width, height, "#ffffff")

    margin_left = 80 * scale
    margin_right = 30 * scale
    margin_top = 40 * scale
    margin_bottom = 110 * scale
    plot_w = width - margin_left - margin_right
    plot_h = height - margin_top - margin_bottom
    y_max = max(float(stats["max"]) for _, stats in groups)
    if y_max <= 0:
        y_max = 1.0
    palette = ["#4C78A8", "#F58518", "#54A24B", "#E45756", "#72B7B2", "#B279A2", "#FF9DA6", "#9D755D"]

    def map_y(value: float) -> float:
        return margin_top + plot_h - (value / y_max) * plot_h

    draw_text(draw, (width / 2, 22 * scale), title, size=int(18 * scale), fill="#1A202C", bold=True, anchor="mm")
    for step in range(6):
        value = y_max * step / 5.0
        y = map_y(value)
        draw.line((margin_left, y, margin_left + plot_w, y), fill=rgba("#D9DEE7"), width=max(1, int(2 * scale)))
        draw_text(draw, (margin_left - 8 * scale, y), f"{value:.2f}", size=int(12 * scale), fill="#4A5568", anchor="rm")

    gap = plot_w / max(len(groups), 1)
    box_w = min(gap * 0.46, 100.0 * scale)
    for idx, (group_name, stats) in enumerate(groups):
        center_x = margin_left + idx * gap + gap / 2.0
        color = palette[idx % len(palette)]
        q1_y = map_y(float(stats["q1"]))
        median_y = map_y(float(stats["median"]))
        q3_y = map_y(float(stats["q3"]))
        whisker_low_y = map_y(float(stats["whisker_low"]))
        whisker_high_y = map_y(float(stats["whisker_high"]))
        box_x = center_x - box_w / 2.0
        box_h = max(2.0, q1_y - q3_y)
        draw.rounded_rectangle(
            (box_x, q3_y, box_x + box_w, q3_y + box_h),
            radius=max(4, int(5 * scale)),
            fill=rgba(color, 200),
            outline=rgba("#2D3748"),
            width=max(1, int(2 * scale)),
        )
        draw.line((box_x, median_y, box_x + box_w, median_y), fill=rgba("#111827"), width=max(2, int(3 * scale)))
        draw.line((center_x, q3_y, center_x, whisker_high_y), fill=rgba("#2D3748"), width=max(1, int(2 * scale)))
        draw.line((center_x, q1_y, center_x, whisker_low_y), fill=rgba("#2D3748"), width=max(1, int(2 * scale)))
        draw.line((center_x - box_w * 0.28, whisker_high_y, center_x + box_w * 0.28, whisker_high_y), fill=rgba("#2D3748"), width=max(1, int(2 * scale)))
        draw.line((center_x - box_w * 0.28, whisker_low_y, center_x + box_w * 0.28, whisker_low_y), fill=rgba("#2D3748"), width=max(1, int(2 * scale)))

        group_values = sorted(float(row["perft_sec"]) for row in rows if row[key] == group_name)
        radius = max(2, int(3 * scale))
        for value in group_values:
            if value < float(stats["whisker_low"]) or value > float(stats["whisker_high"]):
                cy = map_y(value)
                draw.ellipse((center_x - radius, cy - radius, center_x + radius, cy + radius), fill=rgba("#111827"))

        draw_text(draw, (center_x, height - 45 * scale), group_name, size=int(11 * scale), fill="#2D3748", anchor="mm")
        draw_text(draw, (center_x, height - 28 * scale), f"n={int(stats['count'])}", size=int(10 * scale), fill="#4A5568", anchor="mm")

    draw.line((margin_left, margin_top + plot_h, margin_left + plot_w, margin_top + plot_h), fill=rgba("#2D3748"), width=max(2, int(3 * scale)))
    draw.line((margin_left, margin_top, margin_left, margin_top + plot_h), fill=rgba("#2D3748"), width=max(2, int(3 * scale)))
    draw_rotated_text(image, (18 * scale, height / 2), "Perft Time (s)", size=int(14 * scale), fill="#2D3748", bold=True, angle=90, anchor="mm")
    save_png(image, out_path)


def write_rank_bar_png(rows: list[dict[str, str]], out_path: Path, *, title: str, descending: bool, limit: int, target_width: int) -> None:
    ranked = sorted(rows, key=lambda r: float(r["perft_sec"]), reverse=descending)[:limit]
    base_width = 980
    base_row_h = 22
    base_height = 80 + base_row_h * len(ranked)
    scale, width, height = png_geometry(base_width, base_height, target_width)
    image, draw = new_canvas(width, height, "#ffffff")

    row_h = base_row_h * scale
    margin_left = 250 * scale
    margin_right = 40 * scale
    plot_w = width - margin_left - margin_right
    max_value = max(float(row["perft_sec"]) for row in ranked)
    colors = {
        "Bitboards": "#2E86DE",
        "0x88": "#FF8C42",
        "Mailbox": "#3FA34D",
        "10x12 Board": "#D94E41",
        "unknown": "#7F8C8D",
    }

    draw_text(draw, (width / 2, 24 * scale), title, size=int(18 * scale), fill="#1A202C", bold=True, anchor="mm")
    for idx, row in enumerate(ranked):
        y = 50 * scale + idx * row_h
        value = float(row["perft_sec"])
        bar_w = 0.0 if max_value == 0 else value / max_value * plot_w
        draw_text(draw, (10 * scale, y + 7 * scale), f"{idx + 1:02d}", size=int(11 * scale), fill="#4A5568", anchor="lm")
        draw_text(draw, (40 * scale, y + 7 * scale), row["variant_name"], size=int(11 * scale), fill="#1A202C", anchor="lm")
        draw.rounded_rectangle(
            (margin_left, y, margin_left + bar_w, y + 14 * scale),
            radius=max(3, int(4 * scale)),
            fill=rgba(colors.get(row["board_family"], colors["unknown"])),
        )
        draw_text(draw, (margin_left + bar_w + 8 * scale, y + 7 * scale), f"{value:.3f}s", size=int(11 * scale), fill="#2D3748", anchor="lm")
        draw_text(draw, (width - 10 * scale, y + 7 * scale), row["stratum"], size=int(10 * scale), fill="#4A5568", anchor="rm")

    save_png(image, out_path)


def write_heatmap_png(rows: list[dict[str, str]], out_path: Path, *, target_width: int) -> None:
    board_keys = sorted({row["board_family"] for row in rows})
    search_keys = sorted({row["search_tier"] for row in rows})
    counts = {(board, search): 0 for board in board_keys for search in search_keys}
    for row in rows:
        counts[(row["board_family"], row["search_tier"])] += 1
    max_count = max(counts.values()) if counts else 1

    base_cell_w = 120
    base_cell_h = 40
    base_margin_left = 140
    base_margin_top = 80
    base_width = base_margin_left + base_cell_w * len(search_keys) + 40
    base_height = base_margin_top + base_cell_h * len(board_keys) + 40
    scale, width, height = png_geometry(base_width, base_height, target_width)
    image, draw = new_canvas(width, height, "#ffffff")

    cell_w = base_cell_w * scale
    cell_h = base_cell_h * scale
    margin_left = base_margin_left * scale
    margin_top = base_margin_top * scale

    def fill_for(value: int) -> tuple[int, int, int, int]:
        intensity = value / max_count if max_count else 0.0
        red = int(241 - intensity * 92)
        green = int(245 - intensity * 69)
        blue = int(250 - intensity * 128)
        return (red, green, blue, 255)

    draw_text(draw, (width / 2, 28 * scale), "Sample Diversity: Board Family x Search Tier", size=int(18 * scale), fill="#1A202C", bold=True, anchor="mm")
    for idx, search in enumerate(search_keys):
        x = margin_left + idx * cell_w + cell_w / 2
        draw_text(draw, (x, 58 * scale), search, size=int(12 * scale), fill="#2D3748", bold=True, anchor="mm")
    for idx, board in enumerate(board_keys):
        y = margin_top + idx * cell_h + cell_h / 2
        draw_text(draw, (margin_left - 10 * scale, y), board, size=int(12 * scale), fill="#2D3748", anchor="rm")

    for row_idx, board in enumerate(board_keys):
        for col_idx, search in enumerate(search_keys):
            x = margin_left + col_idx * cell_w
            y = margin_top + row_idx * cell_h
            value = counts[(board, search)]
            draw.rounded_rectangle(
                (x, y, x + cell_w, y + cell_h),
                radius=max(4, int(5 * scale)),
                fill=fill_for(value),
                outline=rgba("#FFFFFF"),
                width=max(1, int(2 * scale)),
            )
            draw_text(draw, (x + cell_w / 2, y + cell_h / 2), str(value), size=int(13 * scale), fill="#0F172A", bold=True, anchor="mm")

    save_png(image, out_path)


def write_correctness_bar_png(probe_rows: list[dict[str, str]], out_path: Path, *, target_width: int) -> None:
    grouped: dict[str, tuple[int, int]] = {}
    for row in probe_rows:
        probe = row["probe"]
        passed, total = grouped.get(probe, (0, 0))
        grouped[probe] = (passed + (1 if row["legal"] == "PASS" else 0), total + 1)
    stats = sorted((probe, passed, total) for probe, (passed, total) in grouped.items())
    if not stats:
        return

    base_width = 820
    base_height = 420
    scale, width, height = png_geometry(base_width, base_height, target_width)
    image, draw = new_canvas(width, height, "#ffffff")

    margin_left = 70 * scale
    margin_right = 30 * scale
    margin_top = 40 * scale
    margin_bottom = 90 * scale
    plot_w = width - margin_left - margin_right
    plot_h = height - margin_top - margin_bottom

    draw_text(draw, (width / 2, 22 * scale), "Correctness Probe Pass Rate", size=int(18 * scale), fill="#1A202C", bold=True, anchor="mm")
    for step in range(6):
        pct = step / 5.0
        y = margin_top + plot_h - pct * plot_h
        draw.line((margin_left, y, margin_left + plot_w, y), fill=rgba("#D9DEE7"), width=max(1, int(2 * scale)))
        draw_text(draw, (margin_left - 8 * scale, y), f"{pct:.1f}", size=int(12 * scale), fill="#4A5568", anchor="rm")

    gap = plot_w / len(stats)
    bar_w = gap * 0.6
    for idx, (probe, passed, total) in enumerate(stats):
        pct = passed / total if total else 0.0
        x = margin_left + idx * gap + (gap - bar_w) / 2
        h = pct * plot_h
        y = margin_top + plot_h - h
        color = "#38A169" if passed == total else "#E53E3E"
        draw.rounded_rectangle((x, y, x + bar_w, y + h), radius=max(4, int(5 * scale)), fill=rgba(color))
        draw_text(draw, (x + bar_w / 2, y - 8 * scale), f"{passed}/{total}", size=int(11 * scale), fill="#1A202C", bold=True, anchor="mm")
        draw_text(draw, (x + bar_w / 2, height - 35 * scale), probe, size=int(11 * scale), fill="#2D3748", anchor="mm")

    draw.line((margin_left, margin_top + plot_h, margin_left + plot_w, margin_top + plot_h), fill=rgba("#2D3748"), width=max(2, int(3 * scale)))
    draw.line((margin_left, margin_top, margin_left, margin_top + plot_h), fill=rgba("#2D3748"), width=max(2, int(3 * scale)))
    save_png(image, out_path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate simple SVG plots from stratified perft and correctness outputs")
    parser.add_argument("--perft-screen", required=True)
    parser.add_argument("--correctness-probes", default="")
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--png-density", type=int, default=300)
    parser.add_argument("--png-width", type=int, default=2400)
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    ensure_dir(out_dir)

    rows = filter_screen_rows(load_rows(Path(args.perft_screen)))
    if not rows:
        raise ValueError("No screen-passing rows found in perft screen CSV")

    write_scatter(rows, out_dir / "perft_vs_feature_count.svg")
    write_scatter_png(rows, out_dir / "perft_vs_feature_count.png", target_width=args.png_width)
    write_mean_bar(rows, "board_family", "Mean Perft Time by Board Family", out_dir / "perft_by_board.svg")
    write_mean_bar_png(rows, "board_family", "Mean Perft Time by Board Family", out_dir / "perft_by_board.png", target_width=args.png_width)
    write_mean_bar(rows, "search_tier", "Mean Perft Time by Search Tier", out_dir / "perft_by_search_tier.svg")
    write_mean_bar_png(rows, "search_tier", "Mean Perft Time by Search Tier", out_dir / "perft_by_search_tier.png", target_width=args.png_width)
    write_mean_bar(rows, "eval_tier", "Mean Perft Time by Eval Tier", out_dir / "perft_by_eval_tier.svg")
    write_mean_bar_png(rows, "eval_tier", "Mean Perft Time by Eval Tier", out_dir / "perft_by_eval_tier.png", target_width=args.png_width)
    write_boxplot(rows, "board_family", "Perft Distribution by Board Family", out_dir / "perft_by_board_boxplot.svg")
    write_boxplot_png(rows, "board_family", "Perft Distribution by Board Family", out_dir / "perft_by_board_boxplot.png", target_width=args.png_width)
    write_boxplot(rows, "search_tier", "Perft Distribution by Search Tier", out_dir / "perft_by_search_tier_boxplot.svg")
    write_boxplot_png(rows, "search_tier", "Perft Distribution by Search Tier", out_dir / "perft_by_search_tier_boxplot.png", target_width=args.png_width)
    write_boxplot(rows, "eval_tier", "Perft Distribution by Eval Tier", out_dir / "perft_by_eval_tier_boxplot.svg")
    write_boxplot_png(rows, "eval_tier", "Perft Distribution by Eval Tier", out_dir / "perft_by_eval_tier_boxplot.png", target_width=args.png_width)
    write_boxplot_summary_csv(rows, "board_family", out_dir / "perft_by_board_boxplot_stats.csv")
    write_boxplot_summary_csv(rows, "search_tier", out_dir / "perft_by_search_tier_boxplot_stats.csv")
    write_boxplot_summary_csv(rows, "eval_tier", out_dir / "perft_by_eval_tier_boxplot_stats.csv")
    write_rank_plot(rows, out_dir / "fastest_variants.svg")
    write_rank_bar_png(rows, out_dir / "fastest_variants.png", title="Fastest Screen-Passing Variants by Perft Time", descending=False, limit=25, target_width=args.png_width)
    write_slowest_plot(rows, out_dir / "slowest_variants.svg")
    write_rank_bar_png(rows, out_dir / "slowest_variants.png", title="Slowest Screen-Passing Variants by Perft Time", descending=True, limit=25, target_width=args.png_width)
    write_heatmap(rows, out_dir / "board_search_heatmap.svg")
    write_heatmap_png(rows, out_dir / "board_search_heatmap.png", target_width=args.png_width)

    if args.correctness_probes:
        probe_path = Path(args.correctness_probes)
        if probe_path.exists():
            write_correctness_bar(load_rows(probe_path), out_dir / "correctness_probe_pass_rate.svg")
            write_correctness_bar_png(load_rows(probe_path), out_dir / "correctness_probe_pass_rate.png", target_width=args.png_width)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
