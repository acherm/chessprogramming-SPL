#!/usr/bin/env python3
"""
Collect repository, artifact, and benchmark evidence for the VARIABILITY paper.

Outputs JSON, CSV, Markdown, and LaTeX snippets under paper/data/.
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
from collections import Counter
from pathlib import Path
from statistics import mean
from typing import Any


DEFAULT_WORKSPACE = Path("/Users/mathieuacher/SANDBOX/chessprogramming-vm")


def run_git(workspace: Path, args: list[str]) -> str:
    result = subprocess.run(
        ["git", "-C", str(workspace), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def commit_category(subject: str) -> str:
    lower = subject.lower()
    if "pipeline" in lower or "mining" in lower:
        return "feature_model_mining"
    if "precision" in lower or "constraint" in lower:
        return "model_refinement"
    if "setup variability" in lower or "setup" in lower:
        return "deep_variability"
    if "optimize common search path" in lower:
        return "commonality_optimization"
    if "modularize" in lower or "hierarchical" in lower or "promote" in lower:
        return "modularity_refactoring"
    if "implement real engine feature backends" in lower or "runtime book" in lower:
        return "feature_completion"
    if "tournament" in lower or "assessment" in lower or "anchor" in lower:
        return "benchmarking"
    if "strength" in lower:
        return "strengthening"
    return "other"


def collect_git_history(workspace: Path) -> dict[str, Any]:
    raw_log = run_git(workspace, ["log", "--reverse", "--format=%H|%ai|%s"])
    root_commits = set(run_git(workspace, ["rev-list", "--max-parents=0", "HEAD"]).splitlines())
    commits: list[dict[str, Any]] = []
    for line in raw_log.splitlines():
        sha, date_str, subject = line.split("|", 2)
        if sha in root_commits:
            shortstat = run_git(workspace, ["show", "--shortstat", "--format=", sha])
        else:
            shortstat = run_git(workspace, ["diff", "--shortstat", f"{sha}~1..{sha}"])
        files_changed = insertions = deletions = 0
        if shortstat:
            parts = shortstat.replace(",", "").split()
            for idx, token in enumerate(parts):
                if token == "files" or token == "file":
                    files_changed = int(parts[idx - 1])
                elif token == "insertions(+)" or token == "insertion(+)":
                    insertions = int(parts[idx - 1])
                elif token == "deletions(-)" or token == "deletion(-)":
                    deletions = int(parts[idx - 1])
        commits.append(
            {
                "sha": sha[:7],
                "date": date_str,
                "subject": subject,
                "files_changed": files_changed,
                "insertions": insertions,
                "deletions": deletions,
                "category": commit_category(subject),
            }
        )
    return {
        "commits": commits,
        "summary": {
            "count": len(commits),
            "insertions": sum(commit["insertions"] for commit in commits),
            "deletions": sum(commit["deletions"] for commit in commits),
            "files_changed": sum(commit["files_changed"] for commit in commits),
            "categories": dict(Counter(commit["category"] for commit in commits)),
        },
    }


def load_json(path: Path) -> Any:
    return json.loads(path.read_text())


def row_count(path: Path) -> int:
    with path.open() as handle:
        return max(sum(1 for _ in handle) - 1, 0)


def collect_feature_metrics(workspace: Path) -> dict[str, Any]:
    feature_model = load_json(workspace / "outputs" / "feature_model.json")
    features = feature_model.get("features", [])
    traces_csv = workspace / "outputs" / "feature_traces.csv"
    setup_variant_csv = workspace / "outputs" / "setup_recommendations_by_variant.csv"
    setup_feature_csv = workspace / "outputs" / "setup_recommendations_by_feature.csv"

    return {
        "cpw_cached_pages": sum(1 for _ in (workspace / "data" / "chessprogramming_cache" / "raw").glob("*.json")),
        "modeled_features": len(features),
        "compile_time_options": sum(1 for feature in features if feature.get("variability_stage") == "compile_time"),
        "mixed_or_runtime_options": sum(
            1 for feature in features if feature.get("variability_stage") in {"runtime", "mixed"}
        ),
        "compile_flags": sum(1 for feature in features if feature.get("compile_flag")),
        "runtime_flags": sum(1 for feature in features if feature.get("runtime_flag")),
        "feature_traces": row_count(traces_csv),
        "engine_feature_matrix_rows": row_count(workspace / "outputs" / "engine_feature_matrix.csv"),
        "setup_variant_rows": row_count(setup_variant_csv) if setup_variant_csv.exists() else 0,
        "setup_feature_rows": row_count(setup_feature_csv) if setup_feature_csv.exists() else 0,
    }


def collect_test_metrics(workspace: Path) -> dict[str, Any]:
    result = subprocess.run(
        ["pytest", "--collect-only", "-q"],
        cwd=workspace,
        check=True,
        capture_output=True,
        text=True,
    )
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    collected = [line for line in lines if line.startswith("tests/")]
    return {
        "collected_tests": len(collected),
        "python_source_files": sum(1 for _ in (workspace / "src").rglob("*.py")),
        "c_source_files": sum(1 for _ in (workspace / "c_engine_pl" / "src").rglob("*.c")),
        "script_files": sum(1 for _ in (workspace / "scripts").rglob("*.py")),
        "variant_configs": sum(1 for _ in (workspace / "c_engine_pl" / "variants").glob("*.json")),
    }


def collect_benchmark_metrics(workspace: Path) -> dict[str, Any]:
    equal_condition_rows = list(
        csv.DictReader((workspace / "outputs" / "controlled_equal_condition_tournament_best_worst_random" / "standings.csv").open())
    )
    equal_condition = {row["role"]: row for row in equal_condition_rows}

    elo_rows = list(csv.DictReader((workspace / "outputs" / "proper_elo_tournament_best2" / "elo_estimates.csv").open()))
    variant_elo_rows = [row for row in elo_rows if row["kind"] == "variant"]

    sf2500 = load_json(workspace / "outputs" / "sf2500_after_commonality_opt_20g" / "summary.json")
    sf2700 = load_json(workspace / "outputs" / "sf2700_after_commonality_opt_20g" / "summary.json")

    commonality_rows = list(csv.DictReader((workspace / "outputs" / "commonality_opt_round3_comparison.csv").open()))
    commonality = {
        "avg_prev_depth": mean(float(row["prev_depth"]) for row in commonality_rows),
        "avg_new_depth": mean(float(row["new_depth"]) for row in commonality_rows),
        "avg_prev_nps": mean(float(row["prev_nps"]) for row in commonality_rows),
        "avg_new_nps": mean(float(row["new_nps"]) for row in commonality_rows),
    }

    random_depth6_rows = list(csv.DictReader((workspace / "outputs" / "perft_random_variants_depth6.csv").open()))
    random_perft_sec = [float(row["perft_sec"]) for row in random_depth6_rows]
    random_feature_counts = [int(row["selected_feature_count"]) for row in random_depth6_rows]

    return {
        "equal_condition_scores": {
            role: {
                "score_pct": float(row["score_pct"]),
                "wins": int(row["wins"]),
                "losses": int(row["losses"]),
                "draws": int(row["draws"]),
            }
            for role, row in equal_condition.items()
        },
        "best2_elo_estimates": [
            {
                "player": row["player"],
                "elo_estimate": float(row["elo_estimate"]),
                "elo_ci95": float(row["elo_ci95"]),
            }
            for row in variant_elo_rows
        ],
        "stockfish_anchors": {
            "sf2500_score_pct": float(sf2500["result"]["score_pct"]),
            "sf2700_score_pct": float(sf2700["result"]["score_pct"]),
            "sf2500_score": float(sf2500["result"]["score"]),
            "sf2700_score": float(sf2700["result"]["score"]),
            "sf2500_illegal": int(sf2500["result"]["illegal_count"]),
            "sf2700_illegal": int(sf2700["result"]["illegal_count"]),
        },
        "commonality_depth_shift": commonality,
        "random_perft_diversity": {
            "variants": len(random_depth6_rows),
            "feature_count_min": min(random_feature_counts),
            "feature_count_max": max(random_feature_counts),
            "perft_sec_min": min(random_perft_sec),
            "perft_sec_max": max(random_perft_sec),
        },
    }


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


def tex_escape(value: str) -> str:
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    for src, dst in replacements.items():
        value = value.replace(src, dst)
    return value


def export_commit_table(commits: list[dict[str, Any]], path: Path) -> None:
    lines = [
        r"\begin{table*}[t]",
        r"\centering",
        r"\caption{Chronological commit trace of the chess-engine SPL construction.}",
        r"\label{tab:commit-trace}",
        r"\small",
        r"\begin{tabular}{@{}llllr@{}}",
        r"\toprule",
        r"\textbf{Date} & \textbf{SHA} & \textbf{Category} & \textbf{Subject} & \textbf{Files} \\",
        r"\midrule",
    ]
    for commit in commits:
        date = commit["date"][:10]
        lines.append(
            f"{date} & {commit['sha']} & {tex_escape(commit['category'].replace('_', ' '))} & "
            f"{tex_escape(commit['subject'])} & {commit['files_changed']} \\\\"
        )
    lines.extend(
        [
            r"\bottomrule",
            r"\end{tabular}",
            r"\end{table*}",
        ]
    )
    path.write_text("\n".join(lines) + "\n")


def export_repo_metrics_table(feature_metrics: dict[str, Any], test_metrics: dict[str, Any], path: Path) -> None:
    rows = {
        "Cached CPW pages": feature_metrics["cpw_cached_pages"],
        "Modeled features": feature_metrics["modeled_features"],
        "Compile-time options": feature_metrics["compile_time_options"],
        "Mixed/runtime options": feature_metrics["mixed_or_runtime_options"],
        "Feature traces": feature_metrics["feature_traces"],
        "Engine-matrix rows": feature_metrics["engine_feature_matrix_rows"],
        "Setup recommendations (variant)": feature_metrics["setup_variant_rows"],
        "Collected tests": test_metrics["collected_tests"],
        "C source files": test_metrics["c_source_files"],
        "Python source files": test_metrics["python_source_files"],
        "Variant configs": test_metrics["variant_configs"],
    }
    lines = [
        r"\begin{table}[t]",
        r"\centering",
        r"\caption{Repository and artifact metrics of the current SPL prototype.}",
        r"\label{tab:repo-metrics}",
        r"\small",
        r"\begin{tabular}{@{}lr@{}}",
        r"\toprule",
        r"\textbf{Metric} & \textbf{Value} \\",
        r"\midrule",
    ]
    for label, value in rows.items():
        lines.append(f"{tex_escape(label)} & {value} \\\\")
    lines.extend(
        [
            r"\bottomrule",
            r"\end{tabular}",
            r"\end{table}",
        ]
    )
    path.write_text("\n".join(lines) + "\n")


def export_benchmark_table(benchmarks: dict[str, Any], path: Path) -> None:
    eq = benchmarks["equal_condition_scores"]
    lines = [
        r"\begin{table}[t]",
        r"\centering",
        r"\caption{Illustrative diversity and performance results from the current prototype.}",
        r"\label{tab:benchmark-summary}",
        r"\small",
        r"\begin{tabular}{@{}lr@{}}",
        r"\toprule",
        r"\textbf{Observation} & \textbf{Value} \\",
        r"\midrule",
        f"Equal-condition best variant score & {eq['best']['score_pct']:.1f}\\% \\\\",
        f"Equal-condition random variant score & {eq['random']['score_pct']:.1f}\\% \\\\",
        f"Equal-condition weakest variant score & {eq['worst']['score_pct']:.1f}\\% \\\\",
        f"Best anchored variant Elo & {benchmarks['best2_elo_estimates'][0]['elo_estimate']:.1f} \\\\",
        f"Second anchored variant Elo & {benchmarks['best2_elo_estimates'][1]['elo_estimate']:.1f} \\\\",
        f"20-game score vs Stockfish 2500 & {benchmarks['stockfish_anchors']['sf2500_score_pct']:.1f}\\% \\\\",
        f"20-game score vs Stockfish 2700 & {benchmarks['stockfish_anchors']['sf2700_score_pct']:.1f}\\% \\\\",
        f"Average timed-search depth before commonality batch & {benchmarks['commonality_depth_shift']['avg_prev_depth']:.2f} \\\\",
        f"Average timed-search depth after commonality batch & {benchmarks['commonality_depth_shift']['avg_new_depth']:.2f} \\\\",
        f"Random depth-6 perft runtime range & "
        f"{benchmarks['random_perft_diversity']['perft_sec_min']:.2f}--{benchmarks['random_perft_diversity']['perft_sec_max']:.2f}s \\\\",
    ]
    lines.extend(
        [
            r"\bottomrule",
            r"\end{tabular}",
            r"\end{table}",
        ]
    )
    path.write_text("\n".join(lines) + "\n")


def export_summary_markdown(history: dict[str, Any], features: dict[str, Any], tests: dict[str, Any], benchmarks: dict[str, Any], path: Path) -> None:
    lines = [
        "# Repository Analysis",
        "",
        f"- Commits in current history: **{history['summary']['count']}**",
        f"- Total insertions: **{history['summary']['insertions']}**",
        f"- Total deletions: **{history['summary']['deletions']}**",
        f"- Cached CPW pages: **{features['cpw_cached_pages']}**",
        f"- Modeled features: **{features['modeled_features']}**",
        f"- Engine-feature matrix rows: **{features['engine_feature_matrix_rows']}**",
        f"- Collected tests: **{tests['collected_tests']}**",
        "",
        "## Benchmark Highlights",
        "",
        f"- Equal-condition best/random/worst: "
        f"{benchmarks['equal_condition_scores']['best']['score_pct']:.1f}% / "
        f"{benchmarks['equal_condition_scores']['random']['score_pct']:.1f}% / "
        f"{benchmarks['equal_condition_scores']['worst']['score_pct']:.1f}%",
        f"- 20-game Stockfish anchors: "
        f"{benchmarks['stockfish_anchors']['sf2500_score_pct']:.1f}% vs 2500, "
        f"{benchmarks['stockfish_anchors']['sf2700_score_pct']:.1f}% vs 2700",
        f"- Random depth-6 perft runtime range: "
        f"{benchmarks['random_perft_diversity']['perft_sec_min']:.2f}s to "
        f"{benchmarks['random_perft_diversity']['perft_sec_max']:.2f}s",
    ]
    path.write_text("\n".join(lines) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, default=DEFAULT_WORKSPACE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_WORKSPACE / "paper" / "data")
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)

    history = collect_git_history(args.workspace)
    feature_metrics = collect_feature_metrics(args.workspace)
    test_metrics = collect_test_metrics(args.workspace)
    benchmark_metrics = collect_benchmark_metrics(args.workspace)

    payload = {
        "git_history": history,
        "feature_metrics": feature_metrics,
        "test_metrics": test_metrics,
        "benchmark_metrics": benchmark_metrics,
    }
    write_json(args.output_dir / "repo_analysis_summary.json", payload)
    export_commit_table(history["commits"], args.output_dir / "commit_trace_table.tex")
    export_repo_metrics_table(feature_metrics, test_metrics, args.output_dir / "repo_metrics_table.tex")
    export_benchmark_table(benchmark_metrics, args.output_dir / "benchmark_summary_table.tex")
    export_summary_markdown(history, feature_metrics, test_metrics, benchmark_metrics, args.output_dir / "repo_analysis_summary.md")

    print(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
