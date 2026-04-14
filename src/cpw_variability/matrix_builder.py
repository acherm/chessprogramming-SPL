from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from .config import NEGATION_PATTERNS
from .evidence import build_trace
from .models import EngineFeatureStatus, FeatureNode, PageDocument, SupportStatus, TraceRecord
from .parser import split_sentences


@dataclass
class MatrixBuildResult:
    statuses: list[EngineFeatureStatus]
    evidences: list[TraceRecord]
    engine_lookup: dict[str, str]
    warnings: list[str]


def engine_id_from_title(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")
    return slug or "engine"


def _alias_pattern(alias: str) -> re.Pattern[str]:
    escaped = re.escape(alias.lower())
    escaped = escaped.replace(r"\ ", r"[\s\-_]+").replace(r"\-", r"[\-\s_]")
    return re.compile(rf"\b{escaped}\b")


def _contains_negation(sentence: str) -> bool:
    lowered = sentence.lower()
    return any(pattern in lowered for pattern in NEGATION_PATTERNS)


def detect_support_status(text: str, aliases: list[str]) -> tuple[SupportStatus, str, str]:
    if not aliases:
        return "UNKNOWN", "", ""

    sentences = split_sentences(text)
    patterns = [_alias_pattern(alias) for alias in aliases if alias.strip()]

    positive_hits: list[str] = []
    negative_hits: list[str] = []

    for sentence in sentences:
        sentence_l = sentence.lower()
        if not any(pattern.search(sentence_l) for pattern in patterns):
            continue

        if _contains_negation(sentence_l):
            negative_hits.append(sentence)
        else:
            positive_hits.append(sentence)

    if negative_hits:
        return "UNSUPPORTED_EXPLICIT", negative_hits[0], "engine_negation"

    if positive_hits:
        return "SUPPORTED", positive_hits[0], "engine_claim"

    return "UNKNOWN", "", ""


def _evidence_id(engine_id: str, feature_id: str, snippet: str) -> str:
    digest = hashlib.sha1(f"{engine_id}|{feature_id}|{snippet}".encode("utf-8")).hexdigest()  # noqa: S324
    return f"mx_{digest[:12]}"


def build_engine_feature_matrix(engine_pages: list[PageDocument], features: list[FeatureNode]) -> MatrixBuildResult:
    statuses: list[EngineFeatureStatus] = []
    evidences: list[TraceRecord] = []
    warnings: list[str] = []
    engine_lookup: dict[str, str] = {}

    considered_features = [
        feature
        for feature in features
        if feature.parent_id is not None and feature.variation_role == "option" and feature.configurable
    ]

    for engine in engine_pages:
        engine_id = engine_id_from_title(engine.title)
        engine_lookup[engine_id] = engine.title

        for feature in considered_features:
            aliases = [feature.name] + list(feature.aliases)
            status, snippet, rule_id = detect_support_status(engine.text, aliases)
            evidence_ids: list[str] = []

            if status != "UNKNOWN" and snippet:
                trace = build_trace(
                    feature_id=feature.id,
                    source_url=engine.url,
                    source_title=engine.title,
                    snippet=snippet,
                    rule_id=rule_id,
                    term=feature.name,
                )
                trace.id = _evidence_id(engine_id, feature.id, snippet)
                evidences.append(trace)
                evidence_ids.append(trace.id)

            statuses.append(
                EngineFeatureStatus(
                    engine_id=engine_id,
                    feature_id=feature.id,
                    status=status,
                    evidence_ids=evidence_ids,
                )
            )

    if not engine_pages:
        warnings.append("No engine pages found; matrix is empty")

    if not considered_features:
        warnings.append("No model features found (excluding root); matrix is empty")

    return MatrixBuildResult(statuses=statuses, evidences=evidences, engine_lookup=engine_lookup, warnings=warnings)
