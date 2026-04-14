#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from pathlib import Path


def load_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_rows(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def normalized_output_rows(rows: list[dict[str, str]]) -> tuple[list[dict[str, str]], list[str]]:
    fieldnames: list[str] = []
    seen: set[str] = set()
    cleaned_rows: list[dict[str, str]] = []
    for row in rows:
        cleaned = {key: value for key, value in row.items() if not key.startswith("_")}
        cleaned_rows.append(cleaned)
        for key in cleaned:
            if key in seen:
                continue
            seen.add(key)
            fieldnames.append(key)
    return cleaned_rows, fieldnames


def assign_perft_bands(rows: list[dict[str, str]]) -> None:
    perft_values = sorted(float(row["perft_sec"]) for row in rows)
    if not perft_values:
        return
    low_cut = perft_values[max(0, len(perft_values) // 3 - 1)]
    high_cut = perft_values[min(len(perft_values) - 1, (2 * len(perft_values)) // 3)]
    for row in rows:
        sec = float(row["perft_sec"])
        if sec <= low_cut:
            row["_perft_band"] = "fast"
        elif sec >= high_cut:
            row["_perft_band"] = "slow"
        else:
            row["_perft_band"] = "mid"


def build_shortlist(rows: list[dict[str, str]], count: int) -> list[dict[str, str]]:
    if count <= 0:
        return []

    screen_pass_rows = [dict(row) for row in rows if row.get("screen_pass") == "PASS" and row.get("perft_sec")]
    controls = [row for row in screen_pass_rows if row.get("source_kind") == "control"]
    controls.sort(key=lambda row: row["variant_name"])
    shortlist: list[dict[str, str]] = []
    selected_names: set[str] = set()

    for row in controls:
        row["shortlist_reason"] = "fixed_control"
        shortlist.append(row)
        selected_names.add(row["variant_name"])
        if len(shortlist) >= count:
            return shortlist[:count]

    candidates = [row for row in screen_pass_rows if row.get("source_kind") != "control"]
    assign_perft_bands(candidates)

    grouped: dict[tuple[str, str], list[dict[str, str]]] = {}
    for row in sorted(candidates, key=lambda r: (r["stratum"], float(r["perft_sec"]), r["variant_name"])):
        grouped.setdefault((row["stratum"], row["_perft_band"]), []).append(row)

    keys = list(grouped)
    round_index = 0
    while len(shortlist) < count and keys:
        next_keys: list[tuple[str, str]] = []
        for key in keys:
            bucket = grouped[key]
            if not bucket:
                continue
            row = dict(bucket.pop(0))
            if row["variant_name"] in selected_names:
                if bucket:
                    next_keys.append(key)
                continue
            row["shortlist_reason"] = f"stratified_{key[1]}"
            shortlist.append(row)
            selected_names.add(row["variant_name"])
            if bucket:
                next_keys.append(key)
            if len(shortlist) >= count:
                break
        keys = next_keys
        round_index += 1
        if round_index > count * 4:
            break

    return shortlist[:count]


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a diverse shortlist from a perft screen CSV")
    parser.add_argument("--perft-screen", required=True)
    parser.add_argument("--count", type=int, default=50)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    rows = load_rows(Path(args.perft_screen))
    shortlist = build_shortlist(rows, args.count)
    if not shortlist:
        raise ValueError("No shortlist rows selected")

    cleaned_rows, fieldnames = normalized_output_rows(shortlist)
    write_rows(Path(args.out), cleaned_rows, fieldnames)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
