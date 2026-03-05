from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from .config import DEFAULT_TARGET_FEATURES
from .constraints import build_cross_tree_constraints
from .discovery import extract_non_engine_pages
from .evidence import build_trace, extract_snippet
from .feature_miner import (
    mine_implementation_features,
)
from .models import ConstraintRule, FeatureNode, PageDocument, TraceRecord
from .taxonomy_seed import IMPLEMENTATION_GROUP_SPECS, ROOT_FEATURE_ID, seed_feature_nodes


@dataclass
class ModelBuildResult:
    features: list[FeatureNode]
    traces: list[TraceRecord]
    constraints: list[ConstraintRule]
    warnings: list[str]
    meta: dict


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

    for group in IMPLEMENTATION_GROUP_SPECS:
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

        if feature.variation_role in {"option", "binding"}:
            warnings.append(f"Option feature '{feature.name}' has no direct evidence trace")
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


def _add_binding_layer(
    features: list[FeatureNode],
    traces: list[TraceRecord],
) -> tuple[list[FeatureNode], list[TraceRecord], list[str]]:
    warnings: list[str] = []
    by_feature_id = {feature.id: feature for feature in features}
    used_ids = set(by_feature_id.keys())

    parent_trace_by_feature: dict[str, TraceRecord] = {}
    for trace in traces:
        if trace.feature_id not in parent_trace_by_feature:
            parent_trace_by_feature[trace.feature_id] = trace

    new_features: list[FeatureNode] = []
    new_traces: list[TraceRecord] = []

    for feature in list(features):
        if feature.variation_role != "option" or not feature.configurable:
            continue

        parent_trace = parent_trace_by_feature.get(feature.id)
        source_url = parent_trace.source_url if parent_trace else "local://binding-derived"
        source_title = parent_trace.source_title if parent_trace else "Derived Binding"

        if feature.compile_flag:
            binding_id = f"{feature.id}_compile_binding"
            if binding_id not in used_ids:
                used_ids.add(binding_id)
                compile_binding = FeatureNode(
                    id=binding_id,
                    name=f"CompileFlag {feature.compile_flag}",
                    parent_id=feature.id,
                    kind="mandatory",
                    description=f"Compile-time toggle backing {feature.name}.",
                    variation_role="binding",
                    variability_stage="compile_time",
                    configurable=False,
                    compile_flag=feature.compile_flag,
                    runtime_flag="",
                )
                new_features.append(compile_binding)
                new_traces.append(
                    build_trace(
                        feature_id=compile_binding.id,
                        source_url=source_url,
                        source_title=source_title,
                        snippet=f"{feature.name} is controlled at compile time through {feature.compile_flag}.",
                        rule_id="binding_inferred",
                        term=feature.name,
                    )
                )

        if feature.runtime_flag:
            binding_id = f"{feature.id}_runtime_binding"
            if binding_id not in used_ids:
                used_ids.add(binding_id)
                runtime_binding = FeatureNode(
                    id=binding_id,
                    name=f"RuntimeFlag {feature.runtime_flag}",
                    parent_id=feature.id,
                    kind="optional",
                    description=f"Runtime toggle backing {feature.name}.",
                    variation_role="binding",
                    variability_stage="runtime",
                    configurable=False,
                    compile_flag="",
                    runtime_flag=feature.runtime_flag,
                )
                new_features.append(runtime_binding)
                new_traces.append(
                    build_trace(
                        feature_id=runtime_binding.id,
                        source_url=source_url,
                        source_title=source_title,
                        snippet=f"{feature.name} is controlled at runtime through {feature.runtime_flag}.",
                        rule_id="binding_inferred",
                        term=feature.name,
                    )
                )

        if not feature.compile_flag and not feature.runtime_flag:
            warnings.append(f"Option '{feature.name}' has no compile/runtime binding metadata")

    return features + new_features, traces + new_traces, warnings


def build_feature_model(
    pages: list[PageDocument],
    depth: int = 3,
    target_features: int = DEFAULT_TARGET_FEATURES,
) -> ModelBuildResult:
    warnings: list[str] = []
    seeded = seed_feature_nodes()
    normalized_depth = max(1, depth)
    non_engine_pages = extract_non_engine_pages(pages)

    if normalized_depth == 1:
        # Depth 1 keeps only variability structure: root + top-level variation points.
        features = seeded
        traces = _seed_traces(features, non_engine_pages)
        constraints: list[ConstraintRule] = []
    else:
        leaf_nodes, leaf_traces, mining_warnings = mine_implementation_features(
            non_engine_pages,
            target_count=target_features,
        )
        warnings.extend(mining_warnings)

        features = seeded + leaf_nodes
        traces = _seed_traces(features, non_engine_pages) + leaf_traces
        constraints, constraint_warnings = build_cross_tree_constraints(features)
        warnings.extend(constraint_warnings)

        if normalized_depth >= 4:
            features, traces, binding_warnings = _add_binding_layer(features, traces)
            warnings.extend(binding_warnings)

    traces, trace_warnings = _ensure_trace_per_feature(features, traces, non_engine_pages)
    warnings.extend(trace_warnings)

    if depth < 1:
        warnings.append(f"Requested depth={depth}; clamped to depth=1")
    if depth > 4:
        warnings.append(f"Requested depth={depth}; current implementation emits depth up to 4")

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
        "model_perspective": "implementation_product_line",
        "configuration_goal": "each valid feature configuration maps to a chess-engine variant",
        "primary_variability_strategy": "compile_time_first_with_limited_runtime_options",
        "depth": normalized_depth,
        "target_features": target_features,
        "total_features": len(features),
        "total_traces": len(traces),
        "total_constraints": len(constraints),
        "non_engine_pages": len(non_engine_pages),
    }

    return ModelBuildResult(features=features, traces=traces, constraints=constraints, warnings=warnings, meta=meta)
