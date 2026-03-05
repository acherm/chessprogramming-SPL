from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from .config import (
    DEFAULT_DISCOVERY_CHECKPOINT_EVERY,
    DEFAULT_HTTP_BACKOFF_SECONDS,
    DEFAULT_MAX_DISCOVERY_PAGES,
    DEFAULT_MAX_FETCH_FAILURES_PER_PAGE,
    DEFAULT_MAX_HTTP_RETRIES,
    DEFAULT_MIN_REQUEST_INTERVAL_SECONDS,
    DEFAULT_TARGET_FEATURES,
    SEED_TITLES,
    resolve_paths,
)
from .discovery import discover_from_cache, discover_snapshot, extract_engine_pages
from .exporters import (
    export_engine_feature_matrix_csv,
    export_engine_feature_matrix_markdown,
    export_feature_model_json,
    export_feature_traces_csv,
    export_featureide_xml,
    export_run_report,
    load_discovered_pages,
    load_feature_model_json,
    save_discovered_pages,
)
from .fetcher import CPWFetcher
from .matrix_builder import build_engine_feature_matrix
from .model_builder import ModelBuildResult, build_feature_model


class PipelineError(Exception):
    """Raised when required pipeline inputs are missing."""


def _seed_titles(seed: str) -> list[str]:
    if seed in SEED_TITLES:
        return SEED_TITLES[seed]
    return [seed]


def run_fetch(
    paths,
    seed: str = "implementation",
    mode: str = "snapshot",
    max_pages: int = DEFAULT_MAX_DISCOVERY_PAGES,
    allow_network: bool = True,
    resume: bool = True,
    fresh: bool = False,
    checkpoint_every: int = DEFAULT_DISCOVERY_CHECKPOINT_EVERY,
    max_failures_per_page: int = DEFAULT_MAX_FETCH_FAILURES_PER_PAGE,
    min_request_interval_seconds: float = DEFAULT_MIN_REQUEST_INTERVAL_SECONDS,
    max_http_retries: int = DEFAULT_MAX_HTTP_RETRIES,
    http_backoff_seconds: float = DEFAULT_HTTP_BACKOFF_SECONDS,
    respect_robots: bool = True,
) -> tuple[list, list[str]]:
    if mode != "snapshot":
        raise PipelineError(f"Unsupported fetch mode '{mode}', expected 'snapshot'")

    fetcher = CPWFetcher(
        paths,
        min_request_interval_seconds=min_request_interval_seconds,
        max_http_retries=max_http_retries,
        http_backoff_seconds=http_backoff_seconds,
        respect_robots=respect_robots,
    )
    pages, warnings = discover_snapshot(
        fetcher,
        seed_titles=_seed_titles(seed),
        max_pages=max_pages,
        allow_network=allow_network,
        resume=resume,
        fresh=fresh,
        checkpoint_every=checkpoint_every,
        max_failures_per_page=max_failures_per_page,
    )

    if not pages:
        pages = discover_from_cache(fetcher)

    if not pages:
        raise PipelineError("No pages available from fetch or cache")

    save_discovered_pages(paths.discovered_pages_path, pages)
    return pages, warnings


def _load_pages(paths) -> list:
    if paths.discovered_pages_path.exists():
        return load_discovered_pages(paths.discovered_pages_path)

    fetcher = CPWFetcher(paths)
    pages = discover_from_cache(fetcher)
    if not pages:
        raise PipelineError("No discovered pages found. Run fetch first.")
    save_discovered_pages(paths.discovered_pages_path, pages)
    return pages


def run_build_model(paths, depth: int = 3, target_features: int = DEFAULT_TARGET_FEATURES) -> ModelBuildResult:
    pages = _load_pages(paths)
    result = build_feature_model(pages, depth=depth, target_features=target_features)

    export_feature_model_json(
        paths.feature_model_json_path,
        result.features,
        result.traces,
        result.constraints,
        result.meta,
    )
    export_featureide_xml(paths.feature_model_featureide_path, result.features, result.constraints)
    export_feature_traces_csv(paths.feature_traces_csv_path, result.traces)
    return result


def run_build_matrix(paths, all_engines: bool = True, all_features: bool = True):
    if not all_engines or not all_features:
        raise PipelineError("Current implementation requires --all-engines and --all-features")

    pages = _load_pages(paths)
    features, _, _, _ = load_feature_model_json(paths.feature_model_json_path)

    engine_pages = extract_engine_pages(pages)
    matrix = build_engine_feature_matrix(engine_pages, features)

    export_engine_feature_matrix_csv(
        paths.engine_feature_matrix_csv_path,
        matrix.statuses,
        features,
        matrix.engine_lookup,
    )
    export_engine_feature_matrix_markdown(
        paths.engine_feature_matrix_md_path,
        matrix.statuses,
        features,
        matrix.engine_lookup,
    )

    return matrix


def run_all(
    paths,
    seed: str = "implementation",
    mode: str = "snapshot",
    max_pages: int = DEFAULT_MAX_DISCOVERY_PAGES,
    depth: int = 3,
    target_features: int = DEFAULT_TARGET_FEATURES,
    allow_network: bool = True,
    resume: bool = True,
    fresh: bool = False,
    checkpoint_every: int = DEFAULT_DISCOVERY_CHECKPOINT_EVERY,
    max_failures_per_page: int = DEFAULT_MAX_FETCH_FAILURES_PER_PAGE,
    min_request_interval_seconds: float = DEFAULT_MIN_REQUEST_INTERVAL_SECONDS,
    max_http_retries: int = DEFAULT_MAX_HTTP_RETRIES,
    http_backoff_seconds: float = DEFAULT_HTTP_BACKOFF_SECONDS,
    respect_robots: bool = True,
):
    pages, fetch_warnings = run_fetch(
        paths,
        seed=seed,
        mode=mode,
        max_pages=max_pages,
        allow_network=allow_network,
        resume=resume,
        fresh=fresh,
        checkpoint_every=checkpoint_every,
        max_failures_per_page=max_failures_per_page,
        min_request_interval_seconds=min_request_interval_seconds,
        max_http_retries=max_http_retries,
        http_backoff_seconds=http_backoff_seconds,
        respect_robots=respect_robots,
    )

    model_result = build_feature_model(pages, depth=depth, target_features=target_features)
    export_feature_model_json(
        paths.feature_model_json_path,
        model_result.features,
        model_result.traces,
        model_result.constraints,
        model_result.meta,
    )
    export_featureide_xml(paths.feature_model_featureide_path, model_result.features, model_result.constraints)
    export_feature_traces_csv(paths.feature_traces_csv_path, model_result.traces)

    matrix_result = build_engine_feature_matrix(extract_engine_pages(pages), model_result.features)
    export_engine_feature_matrix_csv(
        paths.engine_feature_matrix_csv_path,
        matrix_result.statuses,
        model_result.features,
        matrix_result.engine_lookup,
    )
    export_engine_feature_matrix_markdown(
        paths.engine_feature_matrix_md_path,
        matrix_result.statuses,
        model_result.features,
        matrix_result.engine_lookup,
    )

    traced_feature_ids = {trace.feature_id for trace in model_result.traces}
    traced_features = sum(1 for feature in model_result.features if feature.id in traced_feature_ids)
    option_features = [feature for feature in model_result.features if feature.variation_role == "option" and feature.configurable]
    compile_time_options = sum(1 for feature in option_features if feature.variability_stage == "compile_time")
    runtime_options = sum(1 for feature in option_features if feature.variability_stage == "runtime")
    mixed_options = sum(1 for feature in option_features if feature.variability_stage == "mixed")

    status_counts = {"SUPPORTED": 0, "UNSUPPORTED_EXPLICIT": 0, "UNKNOWN": 0}
    for status in matrix_result.statuses:
        status_counts[status.status] = status_counts.get(status.status, 0) + 1

    metrics = {
        "pages_discovered": len(pages),
        "engines_discovered": len(extract_engine_pages(pages)),
        "features_total": len(model_result.features),
        "constraints_total": len(model_result.constraints),
        "features_options_configurable": len(option_features),
        "options_compile_time": compile_time_options,
        "options_runtime": runtime_options,
        "options_mixed": mixed_options,
        "features_traced": traced_features,
        "trace_coverage_percent": round((traced_features / max(1, len(model_result.features))) * 100.0, 2),
        "matrix_rows": len(matrix_result.statuses),
        "matrix_supported": status_counts["SUPPORTED"],
        "matrix_unsupported_explicit": status_counts["UNSUPPORTED_EXPLICIT"],
        "matrix_unknown": status_counts["UNKNOWN"],
    }

    warnings = fetch_warnings + model_result.warnings + matrix_result.warnings
    export_run_report(paths.run_report_path, metrics, warnings)

    return {
        "metrics": metrics,
        "warnings": warnings,
        "model": asdict(model_result),
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cpw-var", description="CPW variability mining pipeline")
    subparsers = parser.add_subparsers(dest="command", required=True)

    fetch_cmd = subparsers.add_parser("fetch", help="Fetch and cache CPW snapshot")
    fetch_cmd.add_argument("--seed", default="implementation")
    fetch_cmd.add_argument("--mode", default="snapshot")
    fetch_cmd.add_argument("--max-pages", type=int, default=DEFAULT_MAX_DISCOVERY_PAGES)
    fetch_cmd.add_argument("--offline", action="store_true", help="Disable network requests")
    fetch_cmd.add_argument("--no-resume", action="store_true", help="Do not resume from discovery state")
    fetch_cmd.add_argument("--fresh", action="store_true", help="Reset discovery state before crawling")
    fetch_cmd.add_argument("--crawl-delay", type=float, default=DEFAULT_MIN_REQUEST_INTERVAL_SECONDS, help="Minimum delay between network requests (seconds)")
    fetch_cmd.add_argument("--http-retries", type=int, default=DEFAULT_MAX_HTTP_RETRIES, help="Max HTTP retries per request")
    fetch_cmd.add_argument("--http-backoff", type=float, default=DEFAULT_HTTP_BACKOFF_SECONDS, help="Base exponential backoff (seconds)")
    fetch_cmd.add_argument("--checkpoint-every", type=int, default=DEFAULT_DISCOVERY_CHECKPOINT_EVERY, help="Persist discovery state every N processed pages")
    fetch_cmd.add_argument("--max-failures-per-page", type=int, default=DEFAULT_MAX_FETCH_FAILURES_PER_PAGE, help="Retries across the queue before dropping a failing page")
    fetch_cmd.add_argument("--ignore-robots", action="store_true", help="Disable robots.txt checks (not recommended)")

    model_cmd = subparsers.add_parser("build-model", help="Build feature model")
    model_cmd.add_argument("--depth", type=int, default=3)
    model_cmd.add_argument("--target-features", type=int, default=DEFAULT_TARGET_FEATURES)

    matrix_cmd = subparsers.add_parser("build-matrix", help="Build engine-feature matrix")
    matrix_cmd.add_argument("--all-engines", action="store_true", default=True, help="Include all discovered engines")
    matrix_cmd.add_argument("--all-features", action="store_true", default=True, help="Include all modeled features")

    run_all_cmd = subparsers.add_parser("run-all", help="Run full pipeline")
    run_all_cmd.add_argument("--seed", default="implementation")
    run_all_cmd.add_argument("--mode", default="snapshot")
    run_all_cmd.add_argument("--max-pages", type=int, default=DEFAULT_MAX_DISCOVERY_PAGES)
    run_all_cmd.add_argument("--depth", type=int, default=3)
    run_all_cmd.add_argument("--target-features", type=int, default=DEFAULT_TARGET_FEATURES)
    run_all_cmd.add_argument("--offline", action="store_true", help="Disable network requests")
    run_all_cmd.add_argument("--no-resume", action="store_true", help="Do not resume from discovery state")
    run_all_cmd.add_argument("--fresh", action="store_true", help="Reset discovery state before crawling")
    run_all_cmd.add_argument("--crawl-delay", type=float, default=DEFAULT_MIN_REQUEST_INTERVAL_SECONDS, help="Minimum delay between network requests (seconds)")
    run_all_cmd.add_argument("--http-retries", type=int, default=DEFAULT_MAX_HTTP_RETRIES, help="Max HTTP retries per request")
    run_all_cmd.add_argument("--http-backoff", type=float, default=DEFAULT_HTTP_BACKOFF_SECONDS, help="Base exponential backoff (seconds)")
    run_all_cmd.add_argument("--checkpoint-every", type=int, default=DEFAULT_DISCOVERY_CHECKPOINT_EVERY, help="Persist discovery state every N processed pages")
    run_all_cmd.add_argument("--max-failures-per-page", type=int, default=DEFAULT_MAX_FETCH_FAILURES_PER_PAGE, help="Retries across the queue before dropping a failing page")
    run_all_cmd.add_argument("--ignore-robots", action="store_true", help="Disable robots.txt checks (not recommended)")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    paths = resolve_paths()
    paths.ensure_dirs()

    try:
        if args.command == "fetch":
            pages, warnings = run_fetch(
                paths,
                seed=args.seed,
                mode=args.mode,
                max_pages=args.max_pages,
                allow_network=not args.offline,
                resume=not args.no_resume,
                fresh=args.fresh,
                checkpoint_every=args.checkpoint_every,
                max_failures_per_page=args.max_failures_per_page,
                min_request_interval_seconds=args.crawl_delay,
                max_http_retries=args.http_retries,
                http_backoff_seconds=args.http_backoff,
                respect_robots=not args.ignore_robots,
            )
            print(f"Fetched/discovered pages: {len(pages)}")
            if warnings:
                print(f"Warnings: {len(warnings)}")
            return 0

        if args.command == "build-model":
            result = run_build_model(paths, depth=args.depth, target_features=args.target_features)
            print(f"Features: {len(result.features)}; Traces: {len(result.traces)}")
            return 0

        if args.command == "build-matrix":
            result = run_build_matrix(paths, all_engines=args.all_engines, all_features=args.all_features)
            print(f"Matrix rows: {len(result.statuses)}")
            return 0

        if args.command == "run-all":
            summary = run_all(
                paths,
                seed=args.seed,
                mode=args.mode,
                max_pages=args.max_pages,
                depth=args.depth,
                target_features=args.target_features,
                allow_network=not args.offline,
                resume=not args.no_resume,
                fresh=args.fresh,
                checkpoint_every=args.checkpoint_every,
                max_failures_per_page=args.max_failures_per_page,
                min_request_interval_seconds=args.crawl_delay,
                max_http_retries=args.http_retries,
                http_backoff_seconds=args.http_backoff,
                respect_robots=not args.ignore_robots,
            )
            print("Pipeline completed")
            print(json.dumps(summary["metrics"], indent=2))
            return 0

        raise PipelineError(f"Unknown command: {args.command}")
    except PipelineError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
