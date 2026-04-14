#!/usr/bin/env python3

from __future__ import annotations

import csv
import json
import math
import re
from bisect import bisect_right
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from statistics import median


WORKSPACE = Path(__file__).resolve().parents[1]
ENGINE_ROOT = WORKSPACE / "c_engine_pl"
MODEL_PATH = WORKSPACE / "outputs" / "feature_model.json"
OUTPUT_DIR = WORKSPACE / "paper" / "data"

MACRO_PATTERN = re.compile(r"CFG_[A-Z0-9_]+")
CALL_PATTERN = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(")
FUNCTION_PATTERN = re.compile(
    r"(?ms)^(?P<header>[A-Za-z_][A-Za-z0-9_\s\*\(\)]*?\b(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*\([^;{}]*\)\s*)\{"
)

CONTROL_KEYWORDS = {
    "if",
    "for",
    "while",
    "switch",
    "return",
    "sizeof",
}

CALL_KEYWORDS = CONTROL_KEYWORDS | {
    "defined",
    "do",
}


@dataclass
class FunctionInfo:
    key: str
    name: str
    path: str
    start_line: int
    end_line: int
    nonempty_loc: int
    flags: set[str] = field(default_factory=set)
    raw_calls: set[str] = field(default_factory=set)
    callees: set[str] = field(default_factory=set)
    callers: set[str] = field(default_factory=set)
    is_static: bool = False


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


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def read_lines(path: Path) -> list[str]:
    return read_text(path).splitlines()


def code_files() -> list[Path]:
    return sorted((ENGINE_ROOT / "src").glob("*.c")) + sorted(
        p for p in (ENGINE_ROOT / "include").glob("*.h") if "generated" not in p.parts
    )


def relative_path(path: Path) -> str:
    return str(path.relative_to(WORKSPACE))


def sanitize_c_source(text: str) -> str:
    out: list[str] = []
    i = 0
    state = "normal"
    while i < len(text):
        ch = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ""
        if state == "normal":
            if ch == "/" and nxt == "/":
                out.extend([" ", " "])
                i += 2
                state = "line_comment"
                continue
            if ch == "/" and nxt == "*":
                out.extend([" ", " "])
                i += 2
                state = "block_comment"
                continue
            if ch == '"':
                out.append(" ")
                i += 1
                state = "string"
                continue
            if ch == "'":
                out.append(" ")
                i += 1
                state = "char"
                continue
            out.append(ch)
            i += 1
            continue

        if state == "line_comment":
            if ch == "\n":
                out.append("\n")
                state = "normal"
            else:
                out.append(" ")
            i += 1
            continue

        if state == "block_comment":
            if ch == "*" and nxt == "/":
                out.extend([" ", " "])
                i += 2
                state = "normal"
                continue
            out.append("\n" if ch == "\n" else " ")
            i += 1
            continue

        if state == "string":
            if ch == "\\" and i + 1 < len(text):
                out.extend([" ", " "])
                i += 2
                continue
            if ch == '"':
                out.append(" ")
                i += 1
                state = "normal"
                continue
            out.append("\n" if ch == "\n" else " ")
            i += 1
            continue

        if ch == "\\" and i + 1 < len(text):
            out.extend([" ", " "])
            i += 2
            continue
        if ch == "'":
            out.append(" ")
            i += 1
            state = "normal"
            continue
        out.append("\n" if ch == "\n" else " ")
        i += 1

    return "".join(out)


def line_starts(text: str) -> list[int]:
    starts = [0]
    for idx, ch in enumerate(text):
        if ch == "\n":
            starts.append(idx + 1)
    return starts


def line_for_offset(starts: list[int], offset: int) -> int:
    return bisect_right(starts, offset)


def brace_depths(text: str) -> list[int]:
    depths = [0] * (len(text) + 1)
    depth = 0
    for idx, ch in enumerate(text):
        depths[idx] = depth
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth = max(depth - 1, 0)
    depths[len(text)] = depth
    return depths


def find_matching_brace(text: str, open_idx: int) -> int | None:
    depth = 0
    for idx in range(open_idx, len(text)):
        ch = text[idx]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return idx
    return None


def active_flags_by_line(path: Path, tracked_flags: set[str]) -> list[set[str]]:
    lines = read_lines(path)
    active = [set()]
    stack: list[set[str]] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#if"):
            stack.append(set(MACRO_PATTERN.findall(stripped)) & tracked_flags)
            active.append(set().union(*stack) if stack else set())
            continue
        if stripped.startswith("#elif"):
            if stack:
                stack.pop()
            stack.append(set(MACRO_PATTERN.findall(stripped)) & tracked_flags)
            active.append(set().union(*stack) if stack else set())
            continue
        if stripped.startswith("#else"):
            if stack:
                stack.pop()
                stack.append(set())
            active.append(set().union(*stack) if stack else set())
            continue
        if stripped.startswith("#endif"):
            if stack:
                stack.pop()
            active.append(set().union(*stack) if stack else set())
            continue
        active.append(set().union(*stack) if stack else set())
    return active


def extract_functions(path: Path, tracked_flags: set[str]) -> list[FunctionInfo]:
    raw = read_text(path)
    sanitized = sanitize_c_source(raw)
    starts = line_starts(sanitized)
    depths = brace_depths(sanitized)
    lines = raw.splitlines()
    active = active_flags_by_line(path, tracked_flags)
    functions: list[FunctionInfo] = []

    for match in FUNCTION_PATTERN.finditer(sanitized):
        name = match.group("name")
        if name in CONTROL_KEYWORDS:
            continue
        if depths[match.start()] != 0:
            continue
        open_idx = match.end() - 1
        close_idx = find_matching_brace(sanitized, open_idx)
        if close_idx is None:
            continue

        start_line = line_for_offset(starts, match.start())
        end_line = line_for_offset(starts, close_idx)
        body_lines = lines[start_line - 1 : end_line]
        body_text = raw[match.start() : close_idx + 1]
        body_sanitized = sanitized[open_idx + 1 : close_idx]
        flags = set()
        for line_no in range(start_line, end_line + 1):
            flags.update(active[line_no])
            flags.update(set(MACRO_PATTERN.findall(lines[line_no - 1])) & tracked_flags)
        raw_calls = {
            call_name
            for call_name in CALL_PATTERN.findall(body_sanitized)
            if call_name not in CALL_KEYWORDS
        }
        functions.append(
            FunctionInfo(
                key=f"{relative_path(path)}:{name}:{start_line}",
                name=name,
                path=relative_path(path),
                start_line=start_line,
                end_line=end_line,
                nonempty_loc=sum(1 for line in body_lines if line.strip()),
                flags=flags,
                raw_calls=raw_calls,
                is_static=bool(re.search(r"\bstatic\b", match.group("header"))),
            )
        )
    return functions


def build_call_graph(functions: list[FunctionInfo]) -> dict[str, FunctionInfo]:
    by_key = {function.key: function for function in functions}
    by_name: dict[str, list[FunctionInfo]] = defaultdict(list)
    for function in functions:
        by_name[function.name].append(function)

    for function in functions:
        for call_name in function.raw_calls:
            candidates = by_name.get(call_name, [])
            if not candidates:
                continue
            same_file = [candidate for candidate in candidates if candidate.path == function.path]
            if same_file:
                targets = same_file
            elif len(candidates) == 1:
                targets = candidates
            else:
                non_static = [candidate for candidate in candidates if not candidate.is_static]
                targets = non_static if len(non_static) == 1 else []
            for target in targets:
                function.callees.add(target.key)
                target.callers.add(function.key)
    return by_key


def direct_files_by_feature(paths: list[Path], tracked_flags: set[str]) -> dict[str, set[str]]:
    files: dict[str, set[str]] = defaultdict(set)
    for path in paths:
        active = active_flags_by_line(path, tracked_flags)
        for line_no, line in enumerate(read_lines(path), start=1):
            flags = set(MACRO_PATTERN.findall(line)) & tracked_flags
            flags.update(active[line_no])
            for flag in flags:
                files[flag].add(relative_path(path))
    return files


def expand_feature_span(seed_keys: set[str], functions: dict[str, FunctionInfo]) -> set[str]:
    span = set(seed_keys)
    caller_keys: set[str] = set()
    for key in seed_keys:
        function = functions[key]
        span.update(function.callers)
        span.update(function.callees)
        caller_keys.update(function.callers)
    for caller_key in caller_keys:
        span.update(functions[caller_key].callees)
    return span


def feature_rows(
    model: dict,
    functions: dict[str, FunctionInfo],
    direct_files: dict[str, set[str]],
    guard_loc_rows: dict[str, dict[str, int | str]],
) -> list[dict[str, object]]:
    feature_by_flag = {
        feature["compile_flag"]: feature
        for feature in model["features"]
        if feature.get("compile_flag")
    }
    feature_by_id = {feature["id"]: feature for feature in model["features"]}
    rows: list[dict[str, object]] = []

    for flag in sorted(feature_by_flag):
        feature = feature_by_flag[flag]
        parent = feature_by_id.get(feature.get("parent_id"))
        seeds = sorted(key for key, function in functions.items() if flag in function.flags)
        span = sorted(expand_feature_span(set(seeds), functions))
        seed_files = sorted({functions[key].path for key in seeds})
        span_files = sorted({functions[key].path for key in span})
        row = {
            "feature": feature["name"],
            "family": parent["name"] if parent else "",
            "compile_flag": flag,
            "guarded_nonempty_loc": int(guard_loc_rows[flag]["guarded_nonempty_loc"]),
            "direct_files": len(direct_files.get(flag, set())),
            "seed_functions": len(seeds),
            "seed_nonempty_loc": sum(functions[key].nonempty_loc for key in seeds),
            "span_functions": len(span),
            "span_files": len(span_files),
            "span_nonempty_loc": sum(functions[key].nonempty_loc for key in span),
            "span_guard_ratio": (
                round(sum(functions[key].nonempty_loc for key in span) / int(guard_loc_rows[flag]["guarded_nonempty_loc"]), 2)
                if int(guard_loc_rows[flag]["guarded_nonempty_loc"]) > 0
                else None
            ),
            "seed_function_names": [functions[key].name for key in seeds],
            "seed_files_list": seed_files,
            "span_function_names": [functions[key].name for key in span],
            "span_files_list": span_files,
        }
        rows.append(row)
    rows.sort(key=lambda row: (int(row["span_nonempty_loc"]), int(row["guarded_nonempty_loc"])), reverse=True)
    return rows


def guard_loc_rows(model: dict, tracked_flags: set[str], paths: list[Path]) -> dict[str, dict[str, int | str]]:
    feature_by_flag = {
        feature["compile_flag"]: feature
        for feature in model["features"]
        if feature.get("compile_flag")
    }
    feature_by_id = {feature["id"]: feature for feature in model["features"]}
    guard_counts = {flag: 0 for flag in tracked_flags}
    for path in paths:
        stack: list[set[str]] = []
        for raw_line in read_lines(path):
            stripped = raw_line.strip()
            if stripped.startswith("#if"):
                stack.append(set(MACRO_PATTERN.findall(stripped)) & tracked_flags)
                continue
            if stripped.startswith("#elif"):
                if stack:
                    stack.pop()
                stack.append(set(MACRO_PATTERN.findall(stripped)) & tracked_flags)
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
                guard_counts[flag] += 1

    rows = {}
    for flag, count in guard_counts.items():
        feature = feature_by_flag[flag]
        parent = feature_by_id.get(feature.get("parent_id"))
        rows[flag] = {
            "feature": feature["name"],
            "family": parent["name"] if parent else "",
            "compile_flag": flag,
            "guarded_nonempty_loc": count,
        }
    return rows


def write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def render_top_markdown_table(path: Path, rows: list[dict[str, object]], limit: int = 10) -> None:
    lines = [
        "# Top Features by Span LOC",
        "",
        "| Rank | Feature | Family | CFG | Span LOC | Span funcs | Span files | Guarded LOC |",
        "| --- | --- | --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for rank, row in enumerate(rows[:limit], start=1):
        lines.append(
            f"| {rank} | `{row['feature']}` | `{row['family']}` | `{row['compile_flag']}` | {row['span_nonempty_loc']} | {row['span_functions']} | {row['span_files']} | {row['guarded_nonempty_loc']} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def render_top_latex_table(path: Path, rows: list[dict[str, object]], limit: int = 10) -> None:
    latex = [
        r"\begin{table}[t]",
        r"\centering",
        r"\caption{Top compile-time features by heuristic implementation span.}",
        r"\label{tab:feature-span-top}",
        r"\begin{tabular}{llrr}",
        r"\toprule",
        r"Feature & CFG & Span LOC & Guard LOC \\",
        r"\midrule",
    ]
    for row in rows[:limit]:
        feature = str(row["feature"]).replace("_", r"\_")
        flag = str(row["compile_flag"]).replace("_", r"\_")
        latex.append(f"{feature} & \\texttt{{{flag}}} & {row['span_nonempty_loc']} & {row['guarded_nonempty_loc']} \\\\")
    latex.extend([r"\bottomrule", r"\end{tabular}", r"\end{table}"])
    path.write_text("\n".join(latex) + "\n", encoding="utf-8")


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
        return left + (value - min_v) * (right - left) / (max_v - min_v)

    span = max(max_v - min_v, 1)
    rough_step = max(100, int(math.ceil(span / 6.0 / 50.0) * 50))
    tick_start = (min_v // rough_step) * rough_step
    tick_values = []
    current = tick_start
    while current <= max_v + rough_step:
        if current >= min_v and current <= max_v:
            tick_values.append(current)
        current += rough_step
    if min_v not in tick_values:
        tick_values.insert(0, min_v)
    if max_v not in tick_values:
        tick_values.append(max_v)
    tick_values = sorted(set(tick_values))

    grid_color = "#d8e0d8"
    axis_color = "#2b2b2b"
    whisker_color = "#3f6b35"
    box_fill = "#e7f2e1"
    median_color = "#8f2424"
    text_color = "#222222"

    draw.rectangle([0, 0, canvas.width, canvas.height], fill="white")
    draw.line([(left, axis_y), (right, axis_y)], fill=axis_color, width=6 * scale_factor // 2)
    for tick_value in tick_values:
        x = scale(tick_value)
        draw.line([(x, top_y), (x, bottom_y)], fill=grid_color, width=2 * scale_factor)
        draw.line([(x, axis_y), (x, axis_y + 16 * scale_factor)], fill=axis_color, width=2 * scale_factor)
        label = str(tick_value)
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

    xlabel = "Heuristic span non-empty LOC per compile-time feature"
    bbox = draw.textbbox((0, 0), xlabel, font=label_font)
    draw.text(((canvas.width - (bbox[2] - bbox[0])) / 2, 640 * scale_factor), xlabel, fill=text_color, font=label_font)

    resized = canvas.resize((width, height), Image.Resampling.LANCZOS)
    resized.save(png_path)


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    fieldnames = [
        "feature",
        "family",
        "compile_flag",
        "guarded_nonempty_loc",
        "direct_files",
        "seed_functions",
        "seed_nonempty_loc",
        "span_functions",
        "span_files",
        "span_nonempty_loc",
        "span_guard_ratio",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row[field] for field in fieldnames})


def write_markdown(path: Path, rows: list[dict[str, object]]) -> None:
    lines = [
        "# Feature Implementation Span",
        "",
        "This heuristic complements guarded LOC. It seeds each feature from functions that mention the `CFG_*` flag or are lexically enclosed by it, then expands one step through the static call graph (callers, callees, and callers' callees).",
        "",
        "| Rank | Feature | CFG | Guarded LOC | Seed funcs | Seed LOC | Span funcs | Span files | Span LOC | Span/Guard |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for rank, row in enumerate(rows, start=1):
        lines.append(
            f"| {rank} | `{row['feature']}` | `{row['compile_flag']}` | {row['guarded_nonempty_loc']} | {row['seed_functions']} | {row['seed_nonempty_loc']} | {row['span_functions']} | {row['span_files']} | {row['span_nonempty_loc']} | {row['span_guard_ratio']} |"
        )
    lines.extend(
        [
            "",
            "## Selected Cases",
            "",
        ]
    )
    for flag in ["CFG_NEGAMAX", "CFG_MAGIC_BITBOARDS", "CFG_OPENING_BOOK", "CFG_PONDERING"]:
        row = next((item for item in rows if item["compile_flag"] == flag), None)
        if row is None:
            continue
        span_names = row["span_function_names"]
        if len(span_names) > 16:
            span_preview = ", ".join(span_names[:16]) + ", ..."
        else:
            span_preview = ", ".join(span_names)
        lines.extend(
            [
                f"### `{flag}`",
                f"- Feature: `{row['feature']}`",
                f"- Guarded non-empty LOC: **{row['guarded_nonempty_loc']}**",
                f"- Seed functions ({row['seed_functions']}): `{', '.join(row['seed_function_names']) or 'none'}`",
                f"- Seed files ({len(row['seed_files_list'])}): `{', '.join(row['seed_files_list']) or 'none'}`",
                f"- Span functions ({row['span_functions']}): `{span_preview}`",
                f"- Span files ({len(row['span_files_list'])}): `{', '.join(row['span_files_list']) or 'none'}`",
                f"- Span non-empty LOC: **{row['span_nonempty_loc']}**",
                "",
            ]
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    model = json.loads(MODEL_PATH.read_text(encoding="utf-8"))
    tracked_flags = {
        feature["compile_flag"]
        for feature in model["features"]
        if feature.get("compile_flag")
    }
    paths = code_files()
    guards = guard_loc_rows(model, tracked_flags, paths)
    functions = build_call_graph(
        [
            function
            for path in paths
            for function in extract_functions(path, tracked_flags)
        ]
    )
    rows = feature_rows(
        model=model,
        functions=functions,
        direct_files=direct_files_by_feature(paths, tracked_flags),
        guard_loc_rows=guards,
    )
    span_values = [int(row["span_nonempty_loc"]) for row in rows]

    write_json(OUTPUT_DIR / "feature_span_metrics.json", rows)
    write_csv(OUTPUT_DIR / "feature_span_metrics.csv", rows)
    write_markdown(OUTPUT_DIR / "feature_span_report.md", rows)
    render_top_markdown_table(OUTPUT_DIR / "feature_span_top10.md", rows)
    render_top_latex_table(OUTPUT_DIR / "feature_span_top10.tex", rows)
    render_boxplot_image(span_values, OUTPUT_DIR / "feature_span_boxplot.png")


if __name__ == "__main__":
    main()
