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

BOARD_PRESETS: dict[str, str] = {
    "bitboards": "Bitboards",
    "0x88": "0x88",
    "10x12": "10x12 Board",
}

SEARCH_BASE = [
    "Negamax",
    "Alpha-Beta",
    "Principal Variation Search",
    "Iterative Deepening",
    "Quiescence Search",
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

EVAL_PRESETS: dict[str, list[str]] = {
    "material_only": ["Evaluation"],
    "pst": ["Evaluation", "Piece-Square Tables"],
    "pst_pawn": [
        "Evaluation",
        "Piece-Square Tables",
        "Passed Pawn",
        "Isolated Pawn",
        "Doubled Pawn",
        "Connected Pawn",
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
    (
        "knight_activation",
        "position fen 4k3/8/8/8/8/8/N7/4K3 w - - 0 1",
    ),
    (
        "doubled_pawns",
        "position fen 4k3/8/8/8/8/2P5/2P5/4K3 w - - 0 1",
    ),
    (
        "king_attack",
        "position fen 6k1/5ppp/8/8/8/5Q2/6PP/6K1 w - - 0 1",
    ),
    (
        "passed_pawn_endgame",
        "position fen 8/4k3/8/3P4/8/4K3/8/8 w - - 0 1",
    ),
]


@dataclass
class VariantSummary:
    variant: str
    board: str
    eval_preset: str
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
    eval_preset: str
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
    parser = argparse.ArgumentParser(description="Assess modular evaluation presets as real feature combinations")
    parser.add_argument("--feature-model", default="outputs/feature_model.json")
    parser.add_argument("--header-out", default="c_engine_pl/include/generated/variant_config.h")
    parser.add_argument("--manifest-out", default="c_engine_pl/include/generated/variant_manifest.json")
    parser.add_argument("--makefile", default="c_engine_pl/Makefile")
    parser.add_argument("--engine-bin", default="c_engine_pl/build/engine_pl")
    parser.add_argument("--out-dir", default="outputs/phase3_eval_assessment")
    parser.add_argument("--restore-config", default="c_engine_pl/variants/phase2_bitboards_ab_pvs_id.json")
    parser.add_argument("--probe-depth", type=int, default=2)
    return parser


def write_markdown(variant_rows: list[VariantSummary], probe_rows: list[ProbeRow], out_path: Path) -> None:
    lines = [
        "| Variant | Board | Eval Preset | Position | Nodes | Bestmove | Score (cp) | Error |",
        "| --- | --- | --- | --- | ---: | --- | ---: | --- |",
    ]
    for row in probe_rows:
        lines.append(
            "| {variant} | {board} | {preset} | {position} | {nodes} | {move} | {score} | {error} |".format(
                variant=row.variant,
                board=row.board,
                preset=row.eval_preset,
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
    successful_probes = sum(1 for row in probe_rows if row.error is None and row.nodes is not None)

    lines = [
        "# Phase 3 Evaluation Assessment",
        "",
        "## Summary",
        "",
        f"- variants tested: {len(variant_rows)}",
        f"- compiled successfully: {compiled}",
        f"- passed start-position perft depth 5: {perft_ok}",
        f"- successful probes: {successful_probes}/{len(probe_rows)}",
        f"- probe depth: {probe_depth}",
        "",
        "## Divergence by Position",
        "",
    ]

    for position_id, _ in POSITIONS:
        rows = [row for row in probe_rows if row.position_id == position_id and row.error is None]
        outcomes = {(row.eval_preset, row.bestmove, row.score_cp) for row in rows}
        preset_outcomes = {(row.bestmove, row.score_cp) for row in rows}
        lines.append(
            f"- `{position_id}` produced {len(preset_outcomes)} distinct evaluation outcomes across presets and boards ({len(outcomes)} labeled rows)."
        )

    lines.extend(
        [
            "",
            "## Divergence by Board Backend",
            "",
        ]
    )
    for board_name in BOARD_PRESETS.values():
        board_rows = [row for row in probe_rows if row.board == board_name and row.error is None]
        divergent_positions = 0
        for position_id, _ in POSITIONS:
            subset = [row for row in board_rows if row.position_id == position_id]
            outcomes = {(row.bestmove, row.score_cp) for row in subset}
            if len(outcomes) > 1:
                divergent_positions += 1
        lines.append(
            f"- `{board_name}` showed distinct bestmove/score outcomes across evaluation presets on {divergent_positions}/{len(POSITIONS)} positions."
        )

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- Evaluation is now its own module and the presets in this assessment exercise different combinations of material, PST, pawn subfeatures, bishop-pair/open-file terms, mobility, king-pressure, king-shelter, king-activity, tapered-eval, and SEE.",
            "- Perft equality across presets is expected because evaluation does not change legality; search scores and best moves are the relevant observation point here.",
            "- If presets change scores or best moves on the same position while remaining perft-correct, they are behaving as real combinable implementation features rather than labels.",
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
        for preset_name, eval_options in EVAL_PRESETS.items():
            variant_name = f"eval_{board_key}_{preset_name}"
            config_path = config_dir / f"{variant_name}.json"
            selected_options = [board_name, *SEARCH_BASE, *eval_options]
            config_path.write_text(
                json.dumps({"name": variant_name, "selected_options": selected_options}, indent=2) + "\n",
                encoding="utf-8",
            )

            summary_row = VariantSummary(
                variant=variant_name,
                board=board_name,
                eval_preset=preset_name,
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
                            eval_preset=preset_name,
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
                            eval_preset=preset_name,
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
