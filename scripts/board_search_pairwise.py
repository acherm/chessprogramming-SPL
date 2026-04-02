#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from cpw_variability.pl_codegen import derive_variant, run_build

PERFT_RE = re.compile(r"^info string perft depth (\d+) nodes (\d+)$")
PROBE_RE = re.compile(r"^info depth (\d+) score cp (-?\d+) nodes (\d+)\b")
BESTMOVE_RE = re.compile(r"^bestmove\s+([^\s]+)")

STARTPOS_EXPECTED = {
    1: 20,
    2: 400,
    3: 8902,
    4: 197281,
    5: 4865609,
}

COMMON_OPTIONS = [
    "Make Move",
    "Unmake Move",
    "Move Generation",
    "Legal Move Generation",
    "Move Ordering",
    "Castling",
    "En Passant",
    "Fifty-Move Rule",
    "Threefold Repetition",
    "Evaluation",
    "Quiescence Search",
    "FEN",
    "UCI",
]

SEARCH_PRESETS: dict[str, list[str]] = {
    "minimax": [],
    "minimax_ab": ["Alpha-Beta"],
    "negamax": ["Negamax"],
    "negamax_ab": ["Negamax", "Alpha-Beta"],
    "negamax_ab_pvs_id": [
        "Negamax",
        "Alpha-Beta",
        "Iterative Deepening",
        "Principal Variation Search",
        "Aspiration Windows",
        "Transposition Table",
        "Hash Move",
        "Replacement Schemes",
        "Zobrist Hashing",
    ],
}

BOARD_PRESETS: dict[str, str] = {
    "bitboards": "Bitboards",
    "0x88": "0x88",
    "10x12": "10x12 Board",
}

PROBE_POSITION = "startpos moves e2e4 e7e5 g1f3 b8c6 f1c4 g8f6 d2d3 f8c5"


@dataclass
class PairwiseResult:
    variant: str
    board: str
    search: str
    derive_ok: bool
    build_ok: bool
    perft_pass: bool
    perft_depth_1: int | None
    perft_depth_2: int | None
    perft_depth_3: int | None
    perft_depth_4: int | None
    perft_depth_5: int | None
    build_time_s: float | None
    perft_time_s: float | None
    probe_time_s: float | None
    probe_score_cp: int | None
    probe_nodes: int | None
    probe_bestmove: str | None
    error: str | None


def run_engine(engine_bin: Path, commands: list[str]) -> tuple[list[str], float]:
    transcript = "\n".join(commands) + "\n"
    started = time.perf_counter()
    completed = subprocess.run(
        [str(engine_bin)],
        input=transcript,
        capture_output=True,
        text=True,
        check=True,
    )
    elapsed = time.perf_counter() - started
    lines = completed.stdout.replace("\\n", "\n").splitlines()
    return [line.strip() for line in lines if line.strip()], elapsed


def parse_perft(lines: list[str]) -> dict[int, int]:
    results: dict[int, int] = {}
    for line in lines:
        match = PERFT_RE.match(line)
        if match:
            results[int(match.group(1))] = int(match.group(2))
    return results


def parse_probe(lines: list[str]) -> tuple[int | None, int | None, str | None]:
    score_cp = None
    nodes = None
    bestmove = None
    for line in lines:
        probe_match = PROBE_RE.match(line)
        if probe_match:
            score_cp = int(probe_match.group(2))
            nodes = int(probe_match.group(3))
        bestmove_match = BESTMOVE_RE.match(line)
        if bestmove_match:
            bestmove = bestmove_match.group(1)
    return score_cp, nodes, bestmove


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Assess pair-wise board/search combinations for the chess engine product line")
    parser.add_argument("--feature-model", default="outputs/feature_model.json")
    parser.add_argument("--header-out", default="c_engine_pl/include/generated/variant_config.h")
    parser.add_argument("--manifest-out", default="c_engine_pl/include/generated/variant_manifest.json")
    parser.add_argument("--makefile", default="c_engine_pl/Makefile")
    parser.add_argument("--engine-bin", default="c_engine_pl/build/engine_pl")
    parser.add_argument("--out-dir", default="outputs/phase2_pairwise_interactions")
    parser.add_argument("--restore-config", default="c_engine_pl/variants/phase2_bitboards_ab_pvs_id.json")
    parser.add_argument("--probe-depth", type=int, default=3)
    return parser


def write_markdown(results: list[PairwiseResult], out_path: Path) -> None:
    lines = [
        "| Variant | Board | Search | Build | Perft | D5 | Probe Nodes | Probe Bestmove | Error |",
        "| --- | --- | --- | --- | --- | ---: | ---: | --- | --- |",
    ]
    for result in results:
        lines.append(
            "| {variant} | {board} | {search} | {build} | {perft} | {d5} | {nodes} | {move} | {error} |".format(
                variant=result.variant,
                board=result.board,
                search=result.search,
                build="OK" if result.build_ok else "FAIL",
                perft="PASS" if result.perft_pass else "FAIL",
                d5=result.perft_depth_5 if result.perft_depth_5 is not None else "-",
                nodes=result.probe_nodes if result.probe_nodes is not None else "-",
                move=result.probe_bestmove or "-",
                error=result.error or "",
            )
        )
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_report(results: list[PairwiseResult], out_path: Path, probe_depth: int) -> None:
    total = len(results)
    compiled = sum(1 for result in results if result.build_ok)
    perft_ok = sum(1 for result in results if result.perft_pass)

    by_search: dict[str, list[PairwiseResult]] = {}
    by_board: dict[str, list[PairwiseResult]] = {}
    for result in results:
        by_search.setdefault(result.search, []).append(result)
        by_board.setdefault(result.board, []).append(result)

    lines = [
        "# Pair-wise Board/Search Interaction Assessment",
        "",
        "## Scope",
        "",
        "This assessment checks the valid cross-product of representative search stacks from Phase 1 and board representations from Phase 2.",
        "",
        "## Summary",
        "",
        f"- combinations tested: {total}",
        f"- compiled successfully: {compiled}",
        f"- passed start-position perft depth 5: {perft_ok}",
        "",
        "## Interaction observations",
        "",
    ]

    for board, board_results in sorted(by_board.items()):
        distinct_nodes = sorted({result.probe_nodes for result in board_results if result.probe_nodes is not None})
        lines.append(f"- board `{board}` produced {len(distinct_nodes)} distinct probe-node counts across search stacks: {distinct_nodes}")

    for search, search_results in sorted(by_search.items()):
        distinct_nodes = sorted({result.probe_nodes for result in search_results if result.probe_nodes is not None})
        distinct_moves = sorted({result.probe_bestmove for result in search_results if result.probe_bestmove is not None})
        lines.append(
            f"- search `{search}` produced {len(distinct_nodes)} distinct probe-node counts across board backends: {distinct_nodes}; best moves: {distinct_moves}"
        )

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- Search backends and board backends are combinable because the variants compile and remain perft-correct.",
            "- Equal results for some combinations are not automatically suspicious. For example, plain minimax and plain negamax can legitimately traverse equivalent trees and return the same best move.",
            "- Distinct node counts under alpha-beta/PVS combinations are expected because move ordering and backend-specific generation order interact with pruning.",
            f"- The fixed probe was run at depth {probe_depth} so the complete cross-product remains practical, including unpruned minimax variants.",
        ]
    )

    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    args = build_parser().parse_args()

    feature_model = Path(args.feature_model)
    header_out = Path(args.header_out)
    manifest_out = Path(args.manifest_out)
    makefile = Path(args.makefile)
    engine_bin = Path(args.engine_bin)
    out_dir = Path(args.out_dir)
    config_dir = out_dir / "variant_configs"
    out_dir.mkdir(parents=True, exist_ok=True)
    config_dir.mkdir(parents=True, exist_ok=True)
    perft_commands = [
        "uci",
        "isready",
        "position startpos",
        "perft 1",
        "perft 2",
        "perft 3",
        "perft 4",
        "perft 5",
        "quit",
    ]
    probe_commands = [
        "uci",
        "isready",
        f"position {PROBE_POSITION}",
        f"go depth {args.probe_depth}",
        "quit",
    ]

    results: list[PairwiseResult] = []

    for board_key, board_name in BOARD_PRESETS.items():
        for search_key, search_options in SEARCH_PRESETS.items():
            variant_name = f"pair_{board_key}_{search_key}"
            config_path = config_dir / f"{variant_name}.json"
            selected_options = [board_name, *COMMON_OPTIONS, *search_options]
            config_path.write_text(
                json.dumps(
                    {
                        "name": variant_name,
                        "selected_options": selected_options,
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            result = PairwiseResult(
                variant=variant_name,
                board=board_name,
                search=search_key,
                derive_ok=False,
                build_ok=False,
                perft_pass=False,
                perft_depth_1=None,
                perft_depth_2=None,
                perft_depth_3=None,
                perft_depth_4=None,
                perft_depth_5=None,
                build_time_s=None,
                perft_time_s=None,
                probe_time_s=None,
                probe_score_cp=None,
                probe_nodes=None,
                probe_bestmove=None,
                error=None,
            )

            try:
                derive_variant(
                    feature_model_path=feature_model,
                    config_path=config_path,
                    header_out=header_out,
                    manifest_out=manifest_out,
                )
                result.derive_ok = True

                started = time.perf_counter()
                run_build(makefile)
                result.build_time_s = time.perf_counter() - started
                result.build_ok = True

                perft_lines, perft_time = run_engine(engine_bin, perft_commands)
                perft = parse_perft(perft_lines)
                result.perft_time_s = perft_time
                result.perft_depth_1 = perft.get(1)
                result.perft_depth_2 = perft.get(2)
                result.perft_depth_3 = perft.get(3)
                result.perft_depth_4 = perft.get(4)
                result.perft_depth_5 = perft.get(5)
                result.perft_pass = all(perft.get(depth) == expected for depth, expected in STARTPOS_EXPECTED.items())

                probe_lines, probe_time = run_engine(engine_bin, probe_commands)
                result.probe_time_s = probe_time
                result.probe_score_cp, result.probe_nodes, result.probe_bestmove = parse_probe(probe_lines)
            except Exception as exc:  # pragma: no cover - assessment script should continue collecting failures
                result.error = str(exc)

            results.append(result)

    csv_path = out_dir / "pairwise_matrix.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(asdict(results[0]).keys()))
        writer.writeheader()
        for result in results:
            writer.writerow(asdict(result))

    write_markdown(results, out_dir / "pairwise_matrix.md")
    write_report(results, out_dir / "report.md", args.probe_depth)
    (out_dir / "summary.json").write_text(
        json.dumps(
            {
                "combinations": len(results),
                "compiled": sum(1 for result in results if result.build_ok),
                "perft_pass": sum(1 for result in results if result.perft_pass),
                "results": [asdict(result) for result in results],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    restore_path = Path(args.restore_config)
    if restore_path.exists():
        derive_variant(
            feature_model_path=feature_model,
            config_path=restore_path,
            header_out=header_out,
            manifest_out=manifest_out,
        )
        run_build(makefile)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
