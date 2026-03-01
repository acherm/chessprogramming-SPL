from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from .config import DEFAULT_TARGET_FEATURES, GROUP_SPECS
from .discovery import extract_non_engine_pages
from .evidence import build_trace, extract_snippet
from .feature_miner import canonicalize_candidates, mine_feature_candidates, synthesize_leaf_features
from .models import FeatureNode, PageDocument, TraceRecord
from .taxonomy_seed import ROOT_FEATURE_ID, seed_feature_nodes


@dataclass
class ModelBuildResult:
    features: list[FeatureNode]
    traces: list[TraceRecord]
    warnings: list[str]
    meta: dict


def _group_name_to_id() -> dict[str, str]:
    return {group["name"]: group["id"] for group in GROUP_SPECS}


def _find_seed_page(pages: list[PageDocument], needle: str) -> PageDocument | None:
    needle_l = needle.lower()
    for page in pages:
        if needle_l in page.title.lower() or needle_l in page.text.lower():
            return page
    return pages[0] if pages else None


def _seed_traces(features: list[FeatureNode], pages: list[PageDocument]) -> list[TraceRecord]:
    traces: list[TraceRecord] = []

    root = next((feature for feature in features if feature.id == ROOT_FEATURE_ID), None)
    if root is not None and pages:
        seed_page = _find_seed_page(pages, "Main Page") or pages[0]
        snippet = extract_snippet(seed_page.text, "chess")
        traces.append(
            build_trace(
                feature_id=root.id,
                source_url=seed_page.url,
                source_title=seed_page.title,
                snippet=snippet,
                rule_id="seed_page_fallback",
                term=root.name,
            )
        )

    for group in GROUP_SPECS:
        group_feature = next((feature for feature in features if feature.id == group["id"]), None)
        if group_feature is None or not pages:
            continue

        candidate = None
        for keyword in group["keywords"]:
            candidate = _find_seed_page(pages, keyword)
            if candidate is not None:
                break
        if candidate is None:
            candidate = pages[0]

        snippet = extract_snippet(candidate.text, group["name"])
        traces.append(
            build_trace(
                feature_id=group_feature.id,
                source_url=candidate.url,
                source_title=candidate.title,
                snippet=snippet,
                rule_id="seed_keyword_match",
                term=group_feature.name,
            )
        )

    return traces


def _ensure_trace_per_feature(
    features: list[FeatureNode],
    traces: list[TraceRecord],
    pages: list[PageDocument],
) -> tuple[list[TraceRecord], list[str]]:
    warnings: list[str] = []
    traced_ids = {trace.feature_id for trace in traces}

    if not pages:
        for feature in features:
            if feature.id not in traced_ids:
                warnings.append(f"Feature '{feature.name}' has no trace and no pages are available")
        return traces, warnings

    fallback_page = pages[0]
    for feature in features:
        if feature.id in traced_ids:
            continue

        snippet = extract_snippet(fallback_page.text, feature.name)
        traces.append(
            build_trace(
                feature_id=feature.id,
                source_url=fallback_page.url,
                source_title=fallback_page.title,
                snippet=snippet,
                rule_id="seed_page_fallback",
                term=feature.name,
            )
        )
        warnings.append(f"Feature '{feature.name}' traced with fallback evidence")

    return traces, warnings


def build_feature_model(
    pages: list[PageDocument],
    depth: int = 3,
    target_features: int = DEFAULT_TARGET_FEATURES,
) -> ModelBuildResult:
    warnings: list[str] = []
    seeded = seed_feature_nodes()

    non_engine_pages = extract_non_engine_pages(pages)
    candidates = mine_feature_candidates(non_engine_pages)
    canonical = canonicalize_candidates(candidates)
    leaf_nodes, leaf_traces = synthesize_leaf_features(canonical, target_count=target_features)

    features = seeded + leaf_nodes
    traces = _seed_traces(features, non_engine_pages) + leaf_traces

    traces, trace_warnings = _ensure_trace_per_feature(features, traces, non_engine_pages)
    warnings.extend(trace_warnings)

    if depth < 2 or depth > 3:
        warnings.append(f"Requested depth={depth}; current implementation emits depth 2-3")

    duplicate_trace_ids: set[str] = set()
    seen_trace_ids: set[str] = set()
    for trace in traces:
        if trace.id in seen_trace_ids:
            duplicate_trace_ids.add(trace.id)
        seen_trace_ids.add(trace.id)

    if duplicate_trace_ids:
        warnings.append(f"Detected duplicate trace ids: {sorted(duplicate_trace_ids)[:5]}")

    meta = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "depth": depth,
        "target_features": target_features,
        "total_features": len(features),
        "total_traces": len(traces),
        "non_engine_pages": len(non_engine_pages),
    }

    return ModelBuildResult(features=features, traces=traces, warnings=warnings, meta=meta)
