from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher

try:
    from rapidfuzz import fuzz
except Exception:  # pragma: no cover - optional dependency fallback
    fuzz = None

from .config import DEFAULT_TARGET_FEATURES
from .evidence import build_trace, extract_snippet
from .models import FeatureNode, PageDocument, TraceRecord
from .taxonomy_seed import canonical_synonym_map, group_keywords

STOPWORDS = {
    "chess",
    "engine",
    "engines",
    "page",
    "pages",
    "author",
    "years",
    "category",
    "external links",
    "references",
    "bibliography",
    "forum",
}


@dataclass
class FeatureCandidate:
    name: str
    source_url: str
    source_title: str
    snippet: str
    rule_id: str
    group_hint: str | None = None

    @property
    def normalized(self) -> str:
        return normalize_term(self.name)


@dataclass
class CanonicalFeature:
    canonical_name: str
    canonical_key: str
    aliases: set[str] = field(default_factory=set)
    evidences: list[FeatureCandidate] = field(default_factory=list)

    def score(self) -> float:
        base = float(len(self.evidences))
        heading_hits = sum(1 for e in self.evidences if e.rule_id == "heading_match")
        definition_hits = sum(1 for e in self.evidences if e.rule_id == "definition_pattern")
        return base + heading_hits * 0.6 + definition_hits * 0.4


def normalize_term(term: str) -> str:
    text = term.lower().strip()
    text = text.replace("_", " ")
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[^a-z0-9+\-/# ]", "", text)
    text = text.strip(" -/")
    return text


def _clean_display_term(term: str) -> str:
    cleaned = term.strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = cleaned.strip(" -:/")
    return cleaned


def _is_feature_like(term: str) -> bool:
    value = _clean_display_term(term)
    normalized = normalize_term(value)

    if len(value) < 3 or len(value) > 72:
        return False

    if not re.search(r"[a-zA-Z]", value):
        return False

    if normalized in STOPWORDS:
        return False

    if value.lower().startswith(("list of", "category:", "portal:")):
        return False

    if len(normalized.split()) > 7:
        return False

    return True


def _candidate_group_hint(term: str, source_title: str) -> str | None:
    value = normalize_term(f"{term} {source_title}")
    for group_id, keywords in group_keywords().items():
        if any(keyword in value for keyword in keywords):
            return group_id
    return None


def mine_feature_candidates(pages: list[PageDocument]) -> list[FeatureCandidate]:
    candidates: list[FeatureCandidate] = []

    for page in pages:
        if page.page_type == "engine":
            continue

        heading_terms = page.headings[:40]
        bold_terms = page.bold_terms[:40]
        link_terms = [link for link in page.links[:80] if ":" not in link or link.startswith("Category:")]

        for term in heading_terms:
            if not _is_feature_like(term):
                continue
            snippet = extract_snippet(page.text, term)
            candidates.append(
                FeatureCandidate(
                    name=_clean_display_term(term),
                    source_url=page.url,
                    source_title=page.title,
                    snippet=snippet,
                    rule_id="heading_match",
                    group_hint=_candidate_group_hint(term, page.title),
                )
            )

        for term in bold_terms:
            if not _is_feature_like(term):
                continue
            snippet = extract_snippet(page.text, term)
            candidates.append(
                FeatureCandidate(
                    name=_clean_display_term(term),
                    source_url=page.url,
                    source_title=page.title,
                    snippet=snippet,
                    rule_id="bold_term",
                    group_hint=_candidate_group_hint(term, page.title),
                )
            )

        for term in link_terms:
            if term.startswith("Category:"):
                continue
            if not _is_feature_like(term):
                continue
            snippet = extract_snippet(page.text, term)
            candidates.append(
                FeatureCandidate(
                    name=_clean_display_term(term),
                    source_url=page.url,
                    source_title=page.title,
                    snippet=snippet,
                    rule_id="link_anchor",
                    group_hint=_candidate_group_hint(term, page.title),
                )
            )

        def_pattern = re.compile(r"^([A-Z][A-Za-z0-9+/\- ]{2,64})\s+(?:is|are|refers to|means)\b")
        for sentence in page.text.split(". ")[:60]:
            match = def_pattern.match(sentence.strip())
            if not match:
                continue
            term = match.group(1).strip()
            if not _is_feature_like(term):
                continue
            candidates.append(
                FeatureCandidate(
                    name=_clean_display_term(term),
                    source_url=page.url,
                    source_title=page.title,
                    snippet=sentence.strip()[:220],
                    rule_id="definition_pattern",
                    group_hint=_candidate_group_hint(term, page.title),
                )
            )

        if _is_feature_like(page.title):
            candidates.append(
                FeatureCandidate(
                    name=_clean_display_term(page.title),
                    source_url=page.url,
                    source_title=page.title,
                    snippet=extract_snippet(page.text, page.title),
                    rule_id="link_anchor",
                    group_hint=_candidate_group_hint(page.title, page.title),
                )
            )

    return candidates


def _find_fuzzy_match(key: str, existing_keys: list[str]) -> str | None:
    if not existing_keys:
        return None

    if fuzz is not None:
        best_key: str | None = None
        best_score = 0.0
        for candidate in existing_keys:
            score = float(fuzz.ratio(key, candidate))
            if score > best_score:
                best_key = candidate
                best_score = score
        if best_score >= 94:
            return best_key
        return None

    best_key = None
    best_score = 0.0
    for candidate in existing_keys:
        score = SequenceMatcher(None, key, candidate).ratio() * 100.0
        if score > best_score:
            best_key = candidate
            best_score = score
    if best_score >= 94:
        return best_key
    return None


def canonicalize_candidates(candidates: list[FeatureCandidate]) -> list[CanonicalFeature]:
    synonym_map = canonical_synonym_map()
    canonical_map: dict[str, CanonicalFeature] = {}

    for candidate in candidates:
        normalized = candidate.normalized
        normalized = synonym_map.get(normalized, normalized)

        if normalized in canonical_map:
            canonical = canonical_map[normalized]
        else:
            fuzzy_match = _find_fuzzy_match(normalized, list(canonical_map.keys()))
            if fuzzy_match is not None:
                canonical = canonical_map[fuzzy_match]
            else:
                canonical = CanonicalFeature(canonical_name=candidate.name, canonical_key=normalized)
                canonical_map[normalized] = canonical

        canonical.aliases.add(candidate.name)
        canonical.evidences.append(candidate)

        if len(candidate.name) < len(canonical.canonical_name):
            canonical.canonical_name = candidate.name

    features = list(canonical_map.values())
    features.sort(key=lambda item: (-item.score(), item.canonical_name.lower()))
    return features


def slugify(value: str) -> str:
    normalized = normalize_term(value)
    slug = re.sub(r"[^a-z0-9]+", "_", normalized)
    slug = slug.strip("_")
    return slug[:64] or "feature"


def pick_group_id(feature_name: str, group_hint: str | None, snippet: str) -> str:
    if group_hint is not None:
        return group_hint

    combined = normalize_term(f"{feature_name} {snippet}")
    best_group = "search"
    best_score = -1
    for group_id, keywords in group_keywords().items():
        score = sum(1 for keyword in keywords if keyword in combined)
        if score > best_score:
            best_group = group_id
            best_score = score

    return best_group


def synthesize_leaf_features(
    canonical_features: list[CanonicalFeature],
    target_count: int = DEFAULT_TARGET_FEATURES,
) -> tuple[list[FeatureNode], list[TraceRecord]]:
    leaves: list[FeatureNode] = []
    traces: list[TraceRecord] = []

    used_ids: set[str] = set()
    selected = canonical_features[:target_count]

    for canonical in selected:
        if not canonical.evidences:
            continue

        best_evidence = canonical.evidences[0]
        group_id = pick_group_id(canonical.canonical_name, best_evidence.group_hint, best_evidence.snippet)
        feature_id_base = f"feat_{slugify(canonical.canonical_key)}"

        feature_id = feature_id_base
        index = 2
        while feature_id in used_ids:
            feature_id = f"{feature_id_base}_{index}"
            index += 1
        used_ids.add(feature_id)

        aliases = sorted(set(canonical.aliases))
        aliases = [alias for alias in aliases if alias.lower() != canonical.canonical_name.lower()]

        leaves.append(
            FeatureNode(
                id=feature_id,
                name=canonical.canonical_name,
                parent_id=group_id,
                kind="optional",
                description=best_evidence.snippet[:180],
                aliases=aliases[:8],
            )
        )

        for evidence in canonical.evidences[:2]:
            traces.append(
                build_trace(
                    feature_id=feature_id,
                    source_url=evidence.source_url,
                    source_title=evidence.source_title,
                    snippet=evidence.snippet,
                    rule_id=evidence.rule_id,
                    term=canonical.canonical_name,
                )
            )

    return leaves, traces
