#!/usr/bin/env python3

from __future__ import annotations

import csv
import json
import math
import re
from collections import defaultdict
from pathlib import Path
from statistics import median


WORKSPACE = Path(__file__).resolve().parents[1]
ENGINE_ROOT = WORKSPACE / "c_engine_pl"
MODEL_PATH = WORKSPACE / "outputs" / "feature_model.json"
OUTPUT_DIR = WORKSPACE / "paper" / "data"

MACRO_PATTERN = re.compile(r"CFG_[A-Z0-9_]+")


def read_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8", errors="ignore").splitlines()


def count_lines(path: Path) -> tuple[int, int]:
    lines = read_lines(path)
    return len(lines), sum(1 for line in lines if line.strip())


def percentile(values: list[int], p: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return float(values[0])
    idx = (len(values) - 1) * p
    lo = math.floor(idx)
    hi = math.ceil(idx)
    if lo == hi:
        return float(values[lo])
    frac = idx - lo
    return values[lo] * (1.0 - frac) + values[hi] * frac


def file_category(path: Path) -> str:
    rel = path.relative_to(ENGINE_ROOT)
    if rel.parts[0] == "build":
        return "build"
    if rel.parts[0] == "include" and len(rel.parts) > 1 and rel.parts[1] == "generated":
        if path.suffix == ".h":
            return "generated_header"
        return "generated_manifest"
    if path.name == "Makefile":
        return "makefile"
    if rel.parts[0] == "src" and path.suffix == ".c":
        return "c_source"
    if rel.parts[0] == "include" and path.suffix == ".h":
        return "header"
    if rel.parts[0] == "variants" and path.suffix == ".json":
        return "variant_json"
    if rel.parts[0] == "books" and path.suffix == ".txt":
        return "book_txt"
    return "other"


def aggregate_files() -> dict[str, dict[str, int]]:
    aggregates: dict[str, dict[str, int]] = defaultdict(lambda: {"files": 0, "physical_loc": 0, "nonempty_loc": 0})
    for path in sorted(p for p in ENGINE_ROOT.rglob("*") if p.is_file()):
        category = file_category(path)
        physical_loc, nonempty_loc = count_lines(path)
        item = aggregates[category]
        item["files"] += 1
        item["physical_loc"] += physical_loc
        item["nonempty_loc"] += nonempty_loc
    return dict(aggregates)


def compute_guard_loc(model: dict, flag_to_name: dict[str, str]) -> dict[str, dict[str, int | str]]:
    feature_by_flag = {
        feature["compile_flag"]: feature
        for feature in model["features"]
        if feature.get("compile_flag")
    }
    feature_by_id = {feature["id"]: feature for feature in model["features"]}
    guard_counts = {flag: 0 for flag in flag_to_name}
    code_files = sorted((ENGINE_ROOT / "src").glob("*.c")) + sorted(
        p for p in (ENGINE_ROOT / "include").glob("*.h") if "generated" not in p.parts
    )

    for path in code_files:
        stack: list[set[str]] = []
        for raw_line in read_lines(path):
            stripped = raw_line.strip()
            if stripped.startswith("#if"):
                stack.append(set(MACRO_PATTERN.findall(stripped)))
                continue
            if stripped.startswith("#elif"):
                if stack:
                    stack.pop()
                stack.append(set(MACRO_PATTERN.findall(stripped)))
                continue
            if stripped.startswith("#else"):
                if stack:
                    stack.pop()
                    stack.append(set())
                continue
            if stripped.startswith("#endif"):
                if stack:
                    stack.pop()
                continue
            if not stripped:
                continue
            active_flags = set().union(*stack) if stack else set()
            for flag in active_flags:
                if flag in guard_counts:
                    guard_counts[flag] += 1

    rows = {}
    for flag, count in guard_counts.items():
        feature = feature_by_flag[flag]
        parent = feature_by_id.get(feature.get("parent_id"))
        rows[flag] = {
            "feature": flag_to_name[flag],
            "family": parent["name"] if parent else "",
            "compile_flag": flag,
            "guarded_nonempty_loc": count,
        }
    return rows


def render_boxplot_csv(rows: dict[str, dict[str, int | str]], path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["feature", "family", "compile_flag", "guarded_nonempty_loc"])
        writer.writeheader()
        writer.writerows(sorted(rows.values(), key=lambda row: int(row["guarded_nonempty_loc"]), reverse=True))


def render_guard_loc_markdown_table(rows: dict[str, dict[str, int | str]], path: Path) -> None:
    sorted_rows = sorted(rows.values(), key=lambda row: int(row["guarded_nonempty_loc"]), reverse=True)
    lines = [
        "# Guarded LOC per Compile-Time Feature",
        "",
        "| Rank | Feature | Family | CFG | Guarded non-empty LOC |",
        "| --- | --- | --- | --- | ---: |",
    ]
    for rank, row in enumerate(sorted_rows, start=1):
        lines.append(
            f"| {rank} | `{row['feature']}` | `{row['family']}` | `{row['compile_flag']}` | {row['guarded_nonempty_loc']} |"
        )
    write_text(path, "\n".join(lines) + "\n")


def render_guard_loc_latex_table(rows: dict[str, dict[str, int | str]], path: Path, limit: int = 10) -> None:
    sorted_rows = sorted(rows.values(), key=lambda row: int(row["guarded_nonempty_loc"]), reverse=True)[:limit]
    latex = [
        r"\begin{table}[t]",
        r"\centering",
        r"\caption{Top compile-time features by guarded non-empty LOC in maintained C sources and headers.}",
        r"\label{tab:feature-guard-loc-top}",
        r"\begin{tabular}{llr}",
        r"\toprule",
        r"Feature & CFG & LOC \\",
        r"\midrule",
    ]
    for row in sorted_rows:
        feature = str(row["feature"]).replace("_", r"\_")
        flag = str(row["compile_flag"]).replace("_", r"\_")
        latex.append(f"{feature} & \\texttt{{{flag}}} & {row['guarded_nonempty_loc']} \\\\")
    latex.extend([r"\bottomrule", r"\end{tabular}", r"\end{table}"])
    write_text(path, "\n".join(latex) + "\n")


def write_text(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def render_boxplot_image(values: list[int], png_path: Path) -> None:
    from PIL import Image, ImageDraw, ImageFont

    scale_factor = 2
    width = 2200
    height = 760
    canvas = Image.new("RGB", (width * scale_factor, height * scale_factor), "white")
    draw = ImageDraw.Draw(canvas)
    left = 220 * scale_factor
    right = (width - 120) * scale_factor
    axis_y = 360 * scale_factor
    top_y = 170 * scale_factor
    bottom_y = 620 * scale_factor
    box_y = 286 * scale_factor
    box_h = 86 * scale_factor

    def load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        candidates = [
            "/System/Library/Fonts/Supplemental/Helvetica.ttc",
            "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/Library/Fonts/Arial.ttf",
            "/System/Library/Fonts/Supplemental/Trebuchet MS.ttf",
        ]
        for candidate in candidates:
            try:
                return ImageFont.truetype(candidate, size * scale_factor)
            except OSError:
                continue
        return ImageFont.load_default()

    tick_font = load_font(24)
    label_font = load_font(28)

    min_v = min(values)
    q1 = percentile(values, 0.25)
    med = median(values)
    q3 = percentile(values, 0.75)
    max_v = max(values)
    iqr = q3 - q1
    lower_candidates = [v for v in values if v >= q1 - 1.5 * iqr]
    upper_candidates = [v for v in values if v <= q3 + 1.5 * iqr]
    low_whisker = min(lower_candidates) if lower_candidates else min_v
    high_whisker = max(upper_candidates) if upper_candidates else max_v
    outliers = [v for v in values if v < low_whisker or v > high_whisker]

    def scale(value: float) -> float:
        if max_v == min_v:
            return (left + right) / 2.0
        lo = math.log10(max(min_v, 1))
        hi = math.log10(max(max_v, 1))
        current = math.log10(max(value, 1))
        return left + (current - lo) * (right - left) / (hi - lo)

    tick_candidates = [1, 3, 10, 30, 100, max_v]
    ticks = []
    for tick in tick_candidates:
        if min_v <= tick <= max_v and tick not in ticks:
            ticks.append(tick)
    grid_color = "#d7deea"
    axis_color = "#2b2b2b"
    whisker_color = "#2b4c7e"
    box_fill = "#dbe8f5"
    median_color = "#98223f"
    text_color = "#222222"

    draw.rectangle([0, 0, canvas.width, canvas.height], fill="white")
    draw.line([(left, axis_y), (right, axis_y)], fill=axis_color, width=6 * scale_factor // 2)
    for tick in ticks:
        x = scale(tick)
        draw.line([(x, top_y), (x, bottom_y)], fill=grid_color, width=2 * scale_factor)
        draw.line([(x, axis_y), (x, axis_y + 16 * scale_factor)], fill=axis_color, width=2 * scale_factor)
        label = str(tick)
        bbox = draw.textbbox((0, 0), label, font=tick_font)
        draw.text((x - (bbox[2] - bbox[0]) / 2, axis_y + 28 * scale_factor), label, fill=text_color, font=tick_font)

    draw.line([(scale(low_whisker), axis_y - 30 * scale_factor), (scale(q1), axis_y - 30 * scale_factor)], fill=whisker_color, width=6 * scale_factor)
    draw.line([(scale(q3), axis_y - 30 * scale_factor), (scale(high_whisker), axis_y - 30 * scale_factor)], fill=whisker_color, width=6 * scale_factor)
    draw.line([(scale(low_whisker), axis_y - 56 * scale_factor), (scale(low_whisker), axis_y - 4 * scale_factor)], fill=whisker_color, width=6 * scale_factor)
    draw.line([(scale(high_whisker), axis_y - 56 * scale_factor), (scale(high_whisker), axis_y - 4 * scale_factor)], fill=whisker_color, width=6 * scale_factor)
    draw.rounded_rectangle(
        [scale(q1), box_y, max(scale(q3), scale(q1) + 4 * scale_factor), box_y + box_h],
        radius=14 * scale_factor,
        fill=box_fill,
        outline=whisker_color,
        width=6 * scale_factor,
    )
    draw.line([(scale(med), box_y), (scale(med), box_y + box_h)], fill=median_color, width=7 * scale_factor)
    for value in outliers:
        x = scale(value)
        draw.ellipse(
            [x - 10 * scale_factor, axis_y - 40 * scale_factor, x + 10 * scale_factor, axis_y - 20 * scale_factor],
            fill=whisker_color,
            outline=whisker_color,
        )

    xlabel = "Guarded non-empty LOC per compile-time feature (log scale)"
    bbox = draw.textbbox((0, 0), xlabel, font=label_font)
    draw.text(((canvas.width - (bbox[2] - bbox[0])) / 2, 640 * scale_factor), xlabel, fill=text_color, font=label_font)

    resized = canvas.resize((width, height), Image.Resampling.LANCZOS)
    resized.save(png_path)


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def write_markdown(path: Path, metrics: dict) -> None:
    categories = metrics["categories"]
    guard = metrics["guard_loc"]
    top_features = guard["top_features"]
    lines = [
        "# SPL Codebase Metrics",
        "",
        "## File and LOC Breakdown",
        "",
        f"- Files under `c_engine_pl/`: **{metrics['file_totals']['all_files']}**",
        f"- Maintained SPL files excluding `build/`: **{metrics['file_totals']['maintained_files']}**",
        f"- Maintained SPL files excluding `build/` and generated bindings: **{metrics['file_totals']['maintained_nongenerated_files']}**",
        f"- C source files: **{categories['c_source']['files']}**",
        f"- Maintained headers: **{categories['header']['files']}**",
        f"- Variant configurations: **{categories['variant_json']['files']}**",
        f"- C source LOC (physical / non-empty): **{categories['c_source']['physical_loc']} / {categories['c_source']['nonempty_loc']}**",
        f"- Maintained header LOC (physical / non-empty): **{categories['header']['physical_loc']} / {categories['header']['nonempty_loc']}**",
        f"- Variant configuration LOC (physical / non-empty): **{categories['variant_json']['physical_loc']} / {categories['variant_json']['nonempty_loc']}**",
        "",
        "## Guarded LOC Per Compile-Time Feature",
        "",
        f"- Compile-time features with a `CFG_*` binding: **{guard['feature_count']}**",
        f"- Minimum / median / maximum guarded non-empty LOC: **{guard['min']} / {guard['median']} / {guard['max']}**",
        f"- First quartile / third quartile: **{guard['q1']:.2f} / {guard['q3']:.2f}**",
        f"- Features with guarded LOC <= 5: **{guard['lte_5']}**",
        f"- Features with guarded LOC <= 10: **{guard['lte_10']}**",
        f"- Features with guarded LOC <= 20: **{guard['lte_20']}**",
        "",
        "Top guarded-LOC features:",
        "",
    ]
    for row in top_features:
        lines.append(f"- `{row['feature']}`: **{row['guarded_nonempty_loc']}** guarded non-empty LOC")
    lines.extend(
        [
            "",
            "This metric is intentionally conservative: it counts non-empty lines lexically enclosed by `CFG_*` preprocessor conditions in maintained C sources and headers.",
            "A full sorted table with feature names, families, and `CFG_*` flags is exported in `feature_guard_loc_table.md` and `feature_guard_loc.csv`.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    model = json.loads(MODEL_PATH.read_text(encoding="utf-8"))
    flag_to_name = {
        feature["compile_flag"]: feature["name"]
        for feature in model["features"]
        if feature.get("compile_flag")
    }

    categories = aggregate_files()
    guard_rows = compute_guard_loc(model, flag_to_name)
    guard_values = sorted(int(row["guarded_nonempty_loc"]) for row in guard_rows.values())

    payload = {
        "file_totals": {
            "all_files": sum(item["files"] for item in categories.values()),
            "maintained_files": sum(
                item["files"] for category, item in categories.items() if category not in {"build"}
            ),
            "maintained_nongenerated_files": sum(
                item["files"]
                for category, item in categories.items()
                if category not in {"build", "generated_header", "generated_manifest"}
            ),
        },
        "categories": categories,
        "guard_loc": {
            "feature_count": len(guard_values),
            "min": min(guard_values),
            "q1": percentile(guard_values, 0.25),
            "median": median(guard_values),
            "q3": percentile(guard_values, 0.75),
            "max": max(guard_values),
            "lte_5": sum(value <= 5 for value in guard_values),
            "lte_10": sum(value <= 10 for value in guard_values),
            "lte_20": sum(value <= 20 for value in guard_values),
            "top_features": sorted(guard_rows.values(), key=lambda row: int(row["guarded_nonempty_loc"]), reverse=True)[:10],
        },
    }

    write_json(OUTPUT_DIR / "spl_code_metrics.json", payload)
    render_boxplot_csv(guard_rows, OUTPUT_DIR / "feature_guard_loc.csv")
    render_guard_loc_markdown_table(guard_rows, OUTPUT_DIR / "feature_guard_loc_table.md")
    render_guard_loc_latex_table(guard_rows, OUTPUT_DIR / "feature_guard_loc_top_table.tex")
    write_markdown(OUTPUT_DIR / "spl_code_metrics.md", payload)
    render_boxplot_image(guard_values, OUTPUT_DIR / "feature_guard_loc_boxplot.png")


if __name__ == "__main__":
    main()
