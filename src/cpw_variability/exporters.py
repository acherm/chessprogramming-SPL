from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path
from xml.etree import ElementTree as ET

from .models import ConstraintRule, EngineFeatureStatus, FeatureNode, PageDocument, TraceRecord


def write_json(path: Path, payload: dict | list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)


def read_json(path: Path) -> dict | list:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def save_discovered_pages(path: Path, pages: list[PageDocument]) -> None:
    write_json(path, [page.to_dict() for page in pages])


def load_discovered_pages(path: Path) -> list[PageDocument]:
    payload = read_json(path)
    assert isinstance(payload, list)
    return [PageDocument.from_dict(item) for item in payload]


def export_feature_model_json(
    path: Path,
    features: list[FeatureNode],
    traces: list[TraceRecord],
    constraints: list[ConstraintRule],
    meta: dict,
) -> None:
    payload = {
        "meta": meta,
        "features": [feature.to_dict() for feature in features],
        "traces": [trace.to_dict() for trace in traces],
        "constraints": [constraint.to_dict() for constraint in constraints],
    }
    write_json(path, payload)


def load_feature_model_json(path: Path) -> tuple[list[FeatureNode], list[TraceRecord], list[ConstraintRule], dict]:
    payload = read_json(path)
    assert isinstance(payload, dict)
    raw_features = payload.get("features", [])
    raw_traces = payload.get("traces", [])
    raw_constraints = payload.get("constraints", [])
    meta = payload.get("meta", {})

    features = [FeatureNode(**item) for item in raw_features]
    traces = [TraceRecord(**item) for item in raw_traces]
    constraints = [ConstraintRule(**item) for item in raw_constraints]
    return features, traces, constraints, meta


def export_feature_traces_csv(path: Path, traces: list[TraceRecord]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["id", "feature_id", "source_url", "source_title", "snippet", "confidence", "rule_id"])
        for trace in traces:
            writer.writerow(
                [
                    trace.id,
                    trace.feature_id,
                    trace.source_url,
                    trace.source_title,
                    trace.snippet,
                    trace.confidence,
                    trace.rule_id,
                ]
            )


def _feature_children(features: list[FeatureNode]) -> tuple[dict[str, FeatureNode], dict[str, list[str]], FeatureNode]:
    id_map = {feature.id: feature for feature in features}
    children: dict[str, list[str]] = defaultdict(list)

    root: FeatureNode | None = None
    for feature in features:
        if feature.parent_id is None:
            root = feature
            continue
        children[feature.parent_id].append(feature.id)

    if root is None:
        raise ValueError("Feature model must have a root node")

    for key in children:
        children[key].sort(key=lambda feature_id: id_map[feature_id].name.lower())

    return id_map, children, root


def _create_featureide_node(
    parent_xml: ET.Element,
    feature: FeatureNode,
    children_map: dict[str, list[str]],
    id_map: dict[str, FeatureNode],
) -> None:
    child_ids = children_map.get(feature.id, [])
    attrs = {"name": feature.name}
    if feature.parent_id is not None and feature.kind == "mandatory":
        attrs["mandatory"] = "true"

    if child_ids:
        tag = "and"
        if feature.kind == "or":
            tag = "or"
        elif feature.kind == "xor":
            tag = "alt"
        node = ET.SubElement(parent_xml, tag, attrs)
        for child_id in child_ids:
            _create_featureide_node(node, id_map[child_id], children_map, id_map)
    else:
        ET.SubElement(parent_xml, "feature", attrs)


def _append_constraint_xml(
    constraints_xml: ET.Element,
    constraints: list[ConstraintRule],
    id_map: dict[str, FeatureNode],
) -> None:
    for constraint in constraints:
        left = id_map.get(constraint.left_feature_id)
        right = id_map.get(constraint.right_feature_id)
        if left is None or right is None:
            continue

        rule = ET.SubElement(constraints_xml, "rule")
        if constraint.kind == "requires":
            imp = ET.SubElement(rule, "imp")
            ET.SubElement(imp, "var").text = left.name
            ET.SubElement(imp, "var").text = right.name
            continue

        if constraint.kind == "excludes":
            not_node = ET.SubElement(rule, "not")
            and_node = ET.SubElement(not_node, "and")
            ET.SubElement(and_node, "var").text = left.name
            ET.SubElement(and_node, "var").text = right.name


def export_featureide_xml(path: Path, features: list[FeatureNode], constraints: list[ConstraintRule]) -> None:
    id_map, children_map, root_feature = _feature_children(features)

    model = ET.Element("featureModel")
    struct = ET.SubElement(model, "struct")
    _create_featureide_node(struct, root_feature, children_map, id_map)
    constraints_xml = ET.SubElement(model, "constraints")
    _append_constraint_xml(constraints_xml, constraints, id_map)

    tree = ET.ElementTree(model)
    try:
        ET.indent(tree, space="  ")
    except Exception:  # pragma: no cover - Python <3.9
        pass

    path.parent.mkdir(parents=True, exist_ok=True)
    tree.write(path, encoding="utf-8", xml_declaration=True)


def export_engine_feature_matrix_csv(
    path: Path,
    statuses: list[EngineFeatureStatus],
    features: list[FeatureNode],
    engine_lookup: dict[str, str],
) -> None:
    feature_columns = [
        feature
        for feature in features
        if feature.parent_id is not None and feature.variation_role == "option" and feature.configurable
    ]
    feature_order = [feature.id for feature in feature_columns]
    feature_header = [f"{feature.id}:{feature.name}" for feature in feature_columns]

    matrix: dict[str, dict[str, str]] = defaultdict(dict)
    for row in statuses:
        matrix[row.engine_id][row.feature_id] = row.status

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["engine_id", "engine_name", *feature_header])

        for engine_id in sorted(matrix.keys()):
            row = [engine_id, engine_lookup.get(engine_id, engine_id)]
            row.extend(matrix[engine_id].get(feature_id, "UNKNOWN") for feature_id in feature_order)
            writer.writerow(row)


def export_engine_feature_matrix_markdown(
    path: Path,
    statuses: list[EngineFeatureStatus],
    features: list[FeatureNode],
    engine_lookup: dict[str, str],
) -> None:
    feature_columns = [
        feature
        for feature in features
        if feature.parent_id is not None and feature.variation_role == "option" and feature.configurable
    ]
    feature_order = [feature.id for feature in feature_columns]

    matrix: dict[str, dict[str, str]] = defaultdict(dict)
    for row in statuses:
        matrix[row.engine_id][row.feature_id] = row.status

    headers = ["engine_id", *[feature.name for feature in feature_columns]]
    divider = ["---"] * len(headers)

    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(divider) + " |"]
    for engine_id in sorted(matrix.keys()):
        values = [engine_lookup.get(engine_id, engine_id)]
        values.extend(matrix[engine_id].get(feature_id, "UNKNOWN") for feature_id in feature_order)
        lines.append("| " + " | ".join(values) + " |")

    lines.append("")
    lines.append("Legend: SUPPORTED, UNSUPPORTED_EXPLICIT, UNKNOWN")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def export_run_report(path: Path, metrics: dict, warnings: list[str]) -> None:
    lines = ["# CPW Variability Run Report", ""]
    lines.append("## Metrics")
    for key, value in metrics.items():
        lines.append(f"- {key}: {value}")

    lines.append("")
    lines.append("## Warnings")
    if warnings:
        for warning in warnings:
            lines.append(f"- {warning}")
    else:
        lines.append("- None")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
