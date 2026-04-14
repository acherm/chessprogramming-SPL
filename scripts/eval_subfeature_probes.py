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

STATIC_EVAL_RE = re.compile(r"^info string static_eval cp (-?\d+)$")
PROBE_RE = re.compile(r"^info depth (\d+) score cp (-?\d+) nodes (\d+)\b")
BESTMOVE_RE = re.compile(r"^bestmove\s+([^\s]+)")
SUMMARY_RE = re.compile(r"^info string variant=(.+)$")
PERFT_RE = re.compile(r"^info string perft depth (\d+) nodes (\d+)$")

STARTPOS_EXPECTED = {
    1: 20,
    2: 400,
    3: 8902,
    4: 197281,
    5: 4865609,
}

SEARCH_STACK = [
    "Bitboards",
    "Negamax",
    "Alpha-Beta",
    "Principal Variation Search",
    "Iterative Deepening",
    "Aspiration Windows",
    "Quiescence Search",
    "Null Move Pruning",
    "Late Move Reductions",
    "Futility Pruning",
    "Razoring",
    "Delta Pruning",
    "Killer Heuristic",
    "History Heuristic",
    "Transposition Table",
    "Hash Move",
    "Replacement Schemes",
    "Zobrist Hashing",
    "Make Move",
    "Unmake Move",
    "Move Generation",
    "Legal Move Generation",
    "Move Ordering",
    "Castling",
    "En Passant",
    "Threefold Repetition",
    "Fifty-Move Rule",
    "FEN",
    "UCI",
]

EVAL_PRESETS = {
    "material_only": ["Evaluation"],
    "pawn_terms": [
        "Evaluation",
        "Passed Pawn",
        "Isolated Pawn",
        "Doubled Pawn",
        "Connected Pawn",
    ],
    "coordination": [
        "Evaluation",
        "Piece-Square Tables",
        "Bishop Pair",
        "Rook on Open File",
        "Rook Semi-Open File",
    ],
    "king_terms": [
        "Evaluation",
        "Piece-Square Tables",
        "King Pressure",
        "King Shelter",
        "Tapered Eval",
        "King Activity",
    ],
    "full": [
        "Evaluation",
        "Piece-Square Tables",
        "Passed Pawn",
        "Isolated Pawn",
        "Doubled Pawn",
        "Connected Pawn",
        "Pawn Hash Table",
        "Bishop Pair",
        "Rook on Open File",
        "Rook Semi-Open File",
        "Mobility",
        "King Pressure",
        "King Shelter",
        "Tapered Eval",
        "King Activity",
        "Static Exchange Evaluation",
    ],
}

POSITIONS = [
    ("bishop_pair", "position fen 4k3/8/8/8/8/8/3BB3/4K3 w - - 0 1"),
    ("rook_open_file", "position fen 4k3/8/8/8/8/8/4R3/4K3 w - - 0 1"),
    ("rook_semi_open_file", "position fen 4k3/4p3/8/8/8/8/4R3/4K3 w - - 0 1"),
    ("doubled_isolated_pawns", "position fen 4k3/8/8/8/8/2P5/2P5/4K3 w - - 0 1"),
    ("connected_pawns", "position fen 4k3/8/8/8/8/2PP4/8/4K3 w - - 0 1"),
    ("passed_pawn_endgame", "position fen 8/4k3/8/3P4/8/4K3/8/8 w - - 0 1"),
    ("king_shelter", "position fen 6k1/5ppp/8/8/8/8/6PP/6K1 w - - 0 1"),
    ("king_activity_endgame", "position fen 8/8/4k3/8/8/8/8/4K3 w - - 0 1"),
]


@dataclass
class VariantSummary:
    variant: str
    eval_preset: str
    derive_ok: bool
    build_ok: bool
    build_time_s: float | None
    perft_pass: bool
    perft_depth_5: int | None
    summary: str | None
    error: str | None


@dataclass
class ProbeRow:
    variant: str
    eval_preset: str
    position_id: str
    summary: str | None
    static_eval_cp: int | None
    search_depth: int
    search_score_cp: int | None
    search_nodes: int | None
    bestmove: str | None
    elapsed_s: float | None
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
    return [line.strip() for line in completed.stdout.splitlines() if line.strip()], elapsed


def parse_perft(lines: list[str]) -> dict[int, int]:
    result: dict[int, int] = {}
    for line in lines:
        match = PERFT_RE.match(line)
        if match:
            result[int(match.group(1))] = int(match.group(2))
    return result


def parse_eval_probe(lines: list[str]) -> tuple[str | None, int | None, int | None, int | None, str | None]:
    summary = None
    static_eval = None
    search_score = None
    search_nodes = None
    bestmove = None
    for line in lines:
        summary_match = SUMMARY_RE.match(line)
        if summary_match:
            summary = summary_match.group(1)
        static_match = STATIC_EVAL_RE.match(line)
        if static_match:
            static_eval = int(static_match.group(1))
        probe_match = PROBE_RE.match(line)
        if probe_match:
            search_score = int(probe_match.group(2))
            search_nodes = int(probe_match.group(3))
        bestmove_match = BESTMOVE_RE.match(line)
        if bestmove_match:
            bestmove = bestmove_match.group(1)
    return summary, static_eval, search_score, search_nodes, bestmove


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run strong evaluation-specific probes on a negamax/alpha-beta/pruning/ID engine stack")
    parser.add_argument("--feature-model", default="outputs/feature_model.json")
    parser.add_argument("--header-out", default="c_engine_pl/include/generated/variant_config.h")
    parser.add_argument("--manifest-out", default="c_engine_pl/include/generated/variant_manifest.json")
    parser.add_argument("--makefile", default="c_engine_pl/Makefile")
    parser.add_argument("--engine-bin", default="c_engine_pl/build/engine_pl")
    parser.add_argument("--out-dir", default="outputs/phase3_eval_subfeature_probes")
    parser.add_argument("--restore-config", default="c_engine_pl/variants/phase2_bitboards_ab_pvs_id.json")
    parser.add_argument("--search-depth", type=int, default=3)
    return parser


def write_report(variant_rows: list[VariantSummary], probe_rows: list[ProbeRow], out_path: Path, search_depth: int) -> None:
    lines = [
        "# Phase 3 Subfeature Probes",
        "",
        "## Summary",
        "",
        f"- variants tested: {len(variant_rows)}",
        f"- compiled successfully: {sum(1 for row in variant_rows if row.build_ok)}",
        f"- passed perft depth 5: {sum(1 for row in variant_rows if row.perft_pass)}",
        f"- probe rows: {sum(1 for row in probe_rows if row.error is None)}/{len(probe_rows)}",
        f"- search depth for reference move: {search_depth}",
        "",
        "## Position Signals",
        "",
    ]

    for position_id, _ in POSITIONS:
        subset = [row for row in probe_rows if row.position_id == position_id and row.error is None]
        static_outcomes = {(row.eval_preset, row.static_eval_cp) for row in subset}
        move_outcomes = {(row.eval_preset, row.bestmove, row.search_score_cp) for row in subset}
        lines.append(
            f"- `{position_id}` produced {len(static_outcomes)} distinct static-eval outcomes and {len(move_outcomes)} distinct search outcomes across presets."
        )

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- These probes use the strong engine stack: negamax + alpha-beta + pruning + iterative deepening.",
            "- `eval` isolates the evaluator itself; `go depth N` shows how those promoted evaluation leaves propagate into move choice.",
            "- The presets are leaf-oriented rather than umbrella-oriented, so the matrix directly exercises bishop-pair, rook-file, pawn, shelter, and king-activity options.",
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

    perft_commands = ["uci", "isready", "position startpos", "perft 1", "perft 2", "perft 3", "perft 4", "perft 5", "quit"]

    for preset_name, eval_options in EVAL_PRESETS.items():
        variant_name = f"subprobe_{preset_name}"
        config_path = config_dir / f"{variant_name}.json"
        config_path.write_text(
            json.dumps({"name": variant_name, "selected_options": [*SEARCH_STACK, *eval_options]}, indent=2) + "\n",
            encoding="utf-8",
        )

        summary_row = VariantSummary(
            variant=variant_name,
            eval_preset=preset_name,
            derive_ok=False,
            build_ok=False,
            build_time_s=None,
            perft_pass=False,
            perft_depth_5=None,
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

            perft_lines, _ = run_engine(engine_bin, perft_commands)
            perft = parse_perft(perft_lines)
            summary_row.perft_depth_5 = perft.get(5)
            summary_row.perft_pass = all(perft.get(depth) == expected for depth, expected in STARTPOS_EXPECTED.items())

            for position_id, position_command in POSITIONS:
                lines, elapsed = run_engine(
                    engine_bin,
                    ["uci", "isready", position_command, "eval", f"go depth {args.search_depth}", "quit"],
                )
                summary, static_eval, search_score, search_nodes, bestmove = parse_eval_probe(lines)
                if summary_row.summary is None:
                    summary_row.summary = summary
                probe_rows.append(
                    ProbeRow(
                        variant=variant_name,
                        eval_preset=preset_name,
                        position_id=position_id,
                        summary=summary,
                        static_eval_cp=static_eval,
                        search_depth=args.search_depth,
                        search_score_cp=search_score,
                        search_nodes=search_nodes,
                        bestmove=bestmove,
                        elapsed_s=elapsed,
                        error=None,
                    )
                )
        except Exception as exc:  # pragma: no cover
            summary_row.error = str(exc)
            for position_id, _ in POSITIONS:
                probe_rows.append(
                    ProbeRow(
                        variant=variant_name,
                        eval_preset=preset_name,
                        position_id=position_id,
                        summary=summary_row.summary,
                        static_eval_cp=None,
                        search_depth=args.search_depth,
                        search_score_cp=None,
                        search_nodes=None,
                        bestmove=None,
                        elapsed_s=None,
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

    write_report(variant_rows, probe_rows, out_dir / "report.md", args.search_depth)
    (out_dir / "summary.json").write_text(
        json.dumps({"variants": [asdict(row) for row in variant_rows], "probes": [asdict(row) for row in probe_rows]}, indent=2) + "\n",
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
