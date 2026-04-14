from __future__ import annotations

import hashlib
import re

from .models import TraceRecord
from .parser import split_sentences

RULE_WEIGHTS: dict[str, float] = {
    "heading_match": 0.9,
    "bold_term": 0.82,
    "link_anchor": 0.66,
    "definition_pattern": 0.78,
    "seed_keyword_match": 0.62,
    "seed_page_fallback": 0.45,
    "core_feature_match": 0.92,
    "binding_inferred": 0.7,
    "engine_claim": 0.84,
    "engine_negation": 0.86,
}


def compute_confidence(rule_id: str, term: str, snippet: str) -> float:
    base = RULE_WEIGHTS.get(rule_id, 0.5)
    term_l = term.lower().strip()
    snippet_l = snippet.lower()

    if term_l and term_l in snippet_l:
        base += 0.08

    if re.search(r"\b(is|uses?|supports?|implements?)\b", snippet_l):
        base += 0.04

    return max(0.0, min(1.0, round(base, 2)))


def extract_snippet(text: str, term: str, max_len: int = 220) -> str:
    term_l = term.lower().strip()
    for sentence in split_sentences(text):
        if term_l and term_l in sentence.lower():
            return sentence[:max_len].strip()

    fallback = split_sentences(text)
    if fallback:
        return fallback[0][:max_len].strip()

    return text[:max_len].strip()


def make_trace_id(feature_id: str, source_url: str, snippet: str) -> str:
    digest = hashlib.sha1(f"{feature_id}|{source_url}|{snippet}".encode("utf-8")).hexdigest()  # noqa: S324
    return f"tr_{digest[:12]}"


def build_trace(
    feature_id: str,
    source_url: str,
    source_title: str,
    snippet: str,
    rule_id: str,
    term: str,
) -> TraceRecord:
    trace_id = make_trace_id(feature_id, source_url, snippet)
    confidence = compute_confidence(rule_id, term, snippet)
    return TraceRecord(
        id=trace_id,
        feature_id=feature_id,
        source_url=source_url,
        source_title=source_title,
        snippet=snippet,
        confidence=confidence,
        rule_id=rule_id,
    )
