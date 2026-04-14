#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from pathlib import Path


CONTROL_NAMES = {
    "phase1_minimax",
    "phase2_10x12_ab_pvs_id",
    "phase3_full_eval",
    "strong_variant_02",
}


def load_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_rows(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def enrich_rows(bucket_rows: list[dict[str, str]], perft_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    perft_by_name = {row["variant_name"]: row for row in perft_rows}
    enriched: list[dict[str, str]] = []
    for row in bucket_rows:
        merged = dict(row)
        perft = perft_by_name.get(row["variant_name"], {})
        for key in ("board_family", "search_tier", "eval_tier", "stratum", "perft_sec", "source_kind"):
            merged[key] = perft.get(key, "")
        enriched.append(merged)
    return enriched


def dedupe_preserve_order(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[str] = set()
    deduped: list[dict[str, str]] = []
    for row in rows:
        name = row["variant_name"]
        if name in seen:
            continue
        seen.add(name)
        deduped.append(row)
    return deduped


def sorted_bucket_rows(rows: list[dict[str, str]], bucket: str) -> list[dict[str, str]]:
    if bucket == "strong":
        return sorted(rows, key=lambda r: (-float(r["score_pct"]), r["variant_name"]))
    if bucket == "weak":
        return sorted(rows, key=lambda r: (float(r["score_pct"]), r["variant_name"]))
    median = sorted(float(row["score_pct"]) for row in rows)[len(rows) // 2] if rows else 0.0
    return sorted(rows, key=lambda r: (abs(float(r["score_pct"]) - median), r["variant_name"]))


def take_diverse(rows: list[dict[str, str]], count: int) -> list[dict[str, str]]:
    grouped: dict[tuple[str, str, str], list[dict[str, str]]] = {}
    for row in rows:
        key = (row.get("board_family", ""), row.get("search_tier", ""), row.get("eval_tier", ""))
        grouped.setdefault(key, []).append(row)

    shortlist: list[dict[str, str]] = []
    keys = list(grouped)
    while len(shortlist) < count and keys:
        next_keys: list[tuple[str, str, str]] = []
        for key in keys:
            bucket = grouped[key]
            if not bucket:
                continue
            shortlist.append(bucket.pop(0))
            if bucket:
                next_keys.append(key)
            if len(shortlist) >= count:
                break
        keys = next_keys
    return shortlist[:count]


def build_subset(rows: list[dict[str, str]], count: int) -> list[dict[str, str]]:
    controls = [row for row in rows if row["variant_name"] in CONTROL_NAMES]
    controls = dedupe_preserve_order(sorted(controls, key=lambda r: r["variant_name"]))
    selected: list[dict[str, str]] = controls[:count]
    selected_names = {row["variant_name"] for row in selected}
    if len(selected) >= count:
        return selected[:count]

    remaining = count - len(selected)
    bucket_names = ["strong", "mid", "weak"]
    candidates_by_bucket = {
        bucket: [row for row in sorted_bucket_rows([r for r in rows if r["bucket"] == bucket and r["variant_name"] not in selected_names], bucket)]
        for bucket in bucket_names
    }

    available_buckets = [bucket for bucket in bucket_names if candidates_by_bucket[bucket]]
    if not available_buckets:
        return selected[:count]

    base = remaining // len(available_buckets)
    extra = remaining % len(available_buckets)
    quotas = {bucket: 0 for bucket in bucket_names}
    for idx, bucket in enumerate(available_buckets):
        quotas[bucket] = base + (1 if idx < extra else 0)

    for bucket in bucket_names:
        if quotas[bucket] <= 0:
            continue
        picked = take_diverse(candidates_by_bucket[bucket], quotas[bucket])
        selected.extend(picked)
        selected_names.update(row["variant_name"] for row in picked)

    if len(selected) < count:
        leftovers: list[dict[str, str]] = []
        for bucket in bucket_names:
            leftovers.extend(row for row in candidates_by_bucket[bucket] if row["variant_name"] not in selected_names)
        selected.extend(leftovers[: count - len(selected)])

    return dedupe_preserve_order(selected)[:count]


def main() -> int:
    parser = argparse.ArgumentParser(description="Select a diverse round-robin subset from an anchor screen")
    parser.add_argument("--strength-buckets", required=True)
    parser.add_argument("--perft-screen", required=True)
    parser.add_argument("--count", type=int, default=16)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    rows = enrich_rows(load_rows(Path(args.strength_buckets)), load_rows(Path(args.perft_screen)))
    subset = build_subset(rows, args.count)
    if not subset:
        raise ValueError("No subset rows selected")

    fieldnames = list(subset[0].keys())
    write_rows(Path(args.out), subset, fieldnames)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
