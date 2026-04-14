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
SUMMARY_RE = re.compile(r"^info string variant=(.+)$")

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

POSITIONS = [
    (
        "italian_dev",
        "position startpos moves e2e4 e7e5 g1f3 b8c6 f1c4 g8f6 d2d3 f8c5",
    ),
    (
        "queen_pawn_dev",
        "position startpos moves d2d4 d7d5 c1g5 g8f6 e2e3 c8f5 f1d3 e7e6",
    ),
    (
        "castle_tension",
        "position fen r3k2r/pppq1ppp/2n1bn2/3pp3/3PP3/2N1BN2/PPP2PPP/R2Q1RK1 w kq - 0 9",
    ),
    (
        "pawn_endgame",
        "position fen 8/2p5/3p4/3P4/2P1k3/8/4K3/8 w - - 0 1",
    ),
    (
        "promotion_race",
        "position fen 8/P7/2k5/8/8/8/7p/2K5 w - - 0 1",
    ),
]


@dataclass
class VariantSummary:
    variant: str
    board: str
    search: str
    derive_ok: bool
    build_ok: bool
    build_time_s: float | None
    perft_pass: bool
    perft_depth_5: int | None
    perft_time_s: float | None
    summary: str | None
    error: str | None


@dataclass
class ProbeRow:
    variant: str
    board: str
    search: str
    position_id: str
    summary: str | None
    probe_depth: int
    score_cp: int | None
    nodes: int | None
    bestmove: str | None
    probe_time_s: float | None
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


def parse_probe(lines: list[str]) -> tuple[str | None, int | None, int | None, str | None]:
    summary = None
    score_cp = None
    nodes = None
    bestmove = None
    for line in lines:
        summary_match = SUMMARY_RE.match(line)
        if summary_match:
            summary = summary_match.group(1)
        probe_match = PROBE_RE.match(line)
        if probe_match:
            score_cp = int(probe_match.group(2))
            nodes = int(probe_match.group(3))
        bestmove_match = BESTMOVE_RE.match(line)
        if bestmove_match:
            bestmove = bestmove_match.group(1)
    return summary, score_cp, nodes, bestmove


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a broader multi-position board/search interaction assessment")
    parser.add_argument("--feature-model", default="outputs/feature_model.json")
    parser.add_argument("--header-out", default="c_engine_pl/include/generated/variant_config.h")
    parser.add_argument("--manifest-out", default="c_engine_pl/include/generated/variant_manifest.json")
    parser.add_argument("--makefile", default="c_engine_pl/Makefile")
    parser.add_argument("--engine-bin", default="c_engine_pl/build/engine_pl")
    parser.add_argument("--out-dir", default="outputs/phase2_multi_probe_suite")
    parser.add_argument("--restore-config", default="c_engine_pl/variants/phase2_bitboards_ab_pvs_id.json")
    parser.add_argument("--probe-depth", type=int, default=3)
    return parser


def write_markdown(variant_rows: list[VariantSummary], probe_rows: list[ProbeRow], out_path: Path) -> None:
    lines = [
        "| Variant | Board | Search | Position | Nodes | Bestmove | Score (cp) | Error |",
        "| --- | --- | --- | --- | ---: | --- | ---: | --- |",
    ]
    for row in probe_rows:
        lines.append(
            "| {variant} | {board} | {search} | {position} | {nodes} | {move} | {score} | {error} |".format(
                variant=row.variant,
                board=row.board,
                search=row.search,
                position=row.position_id,
                nodes=row.nodes if row.nodes is not None else "-",
                move=row.bestmove or "-",
                score=row.score_cp if row.score_cp is not None else "-",
                error=row.error or "",
            )
        )

    lines.extend(
        [
            "",
            "## Variant Summary",
            "",
            "| Variant | Build | Perft D5 | Summary | Error |",
            "| --- | --- | ---: | --- | --- |",
        ]
    )
    for row in variant_rows:
        lines.append(
            "| {variant} | {build} | {d5} | {summary} | {error} |".format(
                variant=row.variant,
                build="OK" if row.build_ok else "FAIL",
                d5=row.perft_depth_5 if row.perft_depth_5 is not None else "-",
                summary=row.summary or "-",
                error=row.error or "",
            )
        )
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_report(variant_rows: list[VariantSummary], probe_rows: list[ProbeRow], out_path: Path, probe_depth: int) -> None:
    compiled = sum(1 for row in variant_rows if row.build_ok)
    perft_ok = sum(1 for row in variant_rows if row.perft_pass)
    total_probes = len(probe_rows)
    successful_probes = sum(1 for row in probe_rows if row.error is None and row.nodes is not None)

    lines = [
        "# Multi-Position Board/Search Interaction Assessment",
        "",
        "## Summary",
        "",
        f"- variants tested: {len(variant_rows)}",
        f"- compiled successfully: {compiled}",
        f"- passed start-position perft depth 5: {perft_ok}",
        f"- probe rows collected: {successful_probes}/{total_probes}",
        f"- probe depth: {probe_depth}",
        "",
        "## Divergence by Search Stack",
        "",
    ]

    for search_key in SEARCH_PRESETS:
        search_rows = [row for row in probe_rows if row.search == search_key and row.error is None]
        divergent_positions = 0
        zero88_vs_10x12 = 0
        for position_id, _ in POSITIONS:
            subset = [row for row in search_rows if row.position_id == position_id]
            signatures = {(row.board, row.bestmove, row.nodes, row.score_cp) for row in subset}
            board_signatures = {(row.bestmove, row.nodes, row.score_cp) for row in subset}
            if len(board_signatures) > 1:
                divergent_positions += 1
            zero88 = next((row for row in subset if row.board == "0x88"), None)
            ten = next((row for row in subset if row.board == "10x12 Board"), None)
            if zero88 is not None and ten is not None and (
                zero88.bestmove != ten.bestmove or zero88.nodes != ten.nodes or zero88.score_cp != ten.score_cp
            ):
                zero88_vs_10x12 += 1
            _ = signatures
        lines.append(
            f"- `{search_key}` diverged across board backends on {divergent_positions}/{len(POSITIONS)} positions; `0x88` vs `10x12` diverged on {zero88_vs_10x12}/{len(POSITIONS)} positions."
        )

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- This suite broadens the earlier single-probe assessment to a small set of opening, middlegame, endgame, and promotion-race positions.",
            "- If `0x88` and `10x12` still match on a given position, that means the current backend implementations expose the same search-facing move order and legality behavior on that workload.",
            "- If they diverge on nodes, score, or best move, that is evidence that board representation is interacting with search rather than only serving as a storage detail.",
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

    variant_rows: list[VariantSummary] = []
    probe_rows: list[ProbeRow] = []

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

    for board_key, board_name in BOARD_PRESETS.items():
        for search_key, search_options in SEARCH_PRESETS.items():
            variant_name = f"multi_{board_key}_{search_key}"
            config_path = config_dir / f"{variant_name}.json"
            selected_options = [board_name, *COMMON_OPTIONS, *search_options]
            config_path.write_text(
                json.dumps({"name": variant_name, "selected_options": selected_options}, indent=2) + "\n",
                encoding="utf-8",
            )

            summary_row = VariantSummary(
                variant=variant_name,
                board=board_name,
                search=search_key,
                derive_ok=False,
                build_ok=False,
                build_time_s=None,
                perft_pass=False,
                perft_depth_5=None,
                perft_time_s=None,
                summary=None,
                error=None,
            )

            try:
                derive_variant(
                    feature_model_path=feature_model,
                    config_path=config_path,
                    header_out=header_out,
                    manifest_out=manifest_out,
                )
                summary_row.derive_ok = True

                started = time.perf_counter()
                run_build(makefile)
                summary_row.build_time_s = time.perf_counter() - started
                summary_row.build_ok = True

                perft_lines, perft_time = run_engine(engine_bin, perft_commands)
                perft = parse_perft(perft_lines)
                summary_row.perft_time_s = perft_time
                summary_row.perft_depth_5 = perft.get(5)
                summary_row.perft_pass = all(perft.get(depth) == expected for depth, expected in STARTPOS_EXPECTED.items())

                for position_id, position_command in POSITIONS:
                    probe_commands = [
                        "uci",
                        "isready",
                        "d",
                        position_command,
                        f"go depth {args.probe_depth}",
                        "quit",
                    ]
                    probe_lines, probe_time = run_engine(engine_bin, probe_commands)
                    summary, score_cp, nodes, bestmove = parse_probe(probe_lines)
                    if summary_row.summary is None:
                        summary_row.summary = summary
                    probe_rows.append(
                        ProbeRow(
                            variant=variant_name,
                            board=board_name,
                            search=search_key,
                            position_id=position_id,
                            summary=summary,
                            probe_depth=args.probe_depth,
                            score_cp=score_cp,
                            nodes=nodes,
                            bestmove=bestmove,
                            probe_time_s=probe_time,
                            error=None,
                        )
                    )
            except Exception as exc:  # pragma: no cover - assessment script should keep collecting failures
                summary_row.error = str(exc)
                for position_id, _ in POSITIONS:
                    probe_rows.append(
                        ProbeRow(
                            variant=variant_name,
                            board=board_name,
                            search=search_key,
                            position_id=position_id,
                            summary=summary_row.summary,
                            probe_depth=args.probe_depth,
                            score_cp=None,
                            nodes=None,
                            bestmove=None,
                            probe_time_s=None,
                            error=str(exc),
                        )
                    )

            variant_rows.append(summary_row)

    with (out_dir / "variant_summary.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(asdict(variant_rows[0]).keys()))
        writer.writeheader()
        for row in variant_rows:
            writer.writerow(asdict(row))

    with (out_dir / "probe_matrix.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(asdict(probe_rows[0]).keys()))
        writer.writeheader()
        for row in probe_rows:
            writer.writerow(asdict(row))

    write_markdown(variant_rows, probe_rows, out_dir / "probe_matrix.md")
    write_report(variant_rows, probe_rows, out_dir / "report.md", args.probe_depth)
    (out_dir / "summary.json").write_text(
        json.dumps(
            {
                "variants": [asdict(row) for row in variant_rows],
                "probes": [asdict(row) for row in probe_rows],
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
