from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from difflib import SequenceMatcher

try:
    from rapidfuzz import fuzz
except Exception:  # pragma: no cover - optional dependency fallback
    fuzz = None

from .config import DEFAULT_TARGET_FEATURES, GROUP_SPECS
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

NOISE_EXACT_TERMS = {
    "contents",
    "references",
    "external links",
    "see also",
    "forum posts",
    "publications",
    "main page",
    "up one level",
    "index.php",
    "index php",
    "ccc",
    "icga journal",
    "computer chess forums",
    "compuer chess forums",
    "board representation",
    "move generation",
    "time management",
    "transposition table",
    "pruning reductions",
    "chess engine variability",
}

NOISE_SUBSTRINGS = (
    "[edit]",
    "contents",
    "external links",
    "references",
    "see also",
    "forum posts",
    "publications",
    "up one level",
    "index.php",
)

NON_TECHNICAL_CONTEXT_TERMS = {
    "programmer",
    "researcher",
    "person",
    "people",
    "forum",
    "journal",
    "conference",
    "workshop",
    "timeline",
    "history",
    "publication",
    "bibliography",
    "book review",
    "organizations",
}

NON_STANDARD_GAME_TERMS = {
    "chinese chess",
    "xiangqi",
    "shogi",
    "checkers",
    "othello",
    "backgammon",
    "go ",
    "arimaa",
    "connect6",
}

TECHNICAL_CONTEXT_HINTS = {
    "search",
    "evaluation",
    "move generation",
    "board representation",
    "bitboard",
    "0x88",
    "mailbox",
    "transposition table",
    "zobrist",
    "time management",
    "parallel search",
    "smp",
    "endgame",
    "tablebase",
    "opening book",
    "protocol",
    "uci",
    "xboard",
    "tuning",
    "pruning",
    "reduction",
    "nnue",
    "neural network",
}

TECHNICAL_NAME_TOKENS = {
    "search",
    "board",
    "representation",
    "bitboard",
    "bitboards",
    "mailbox",
    "move",
    "generation",
    "evaluation",
    "table",
    "tablebase",
    "book",
    "protocol",
    "uci",
    "xboard",
    "cecp",
    "hash",
    "zobrist",
    "pruning",
    "reduction",
    "extension",
    "time",
    "management",
    "parallel",
    "smp",
    "nnue",
    "neural",
    "network",
    "alpha",
    "beta",
    "negamax",
    "mcts",
    "uct",
    "0x88",
    "fen",
    "epd",
    "spsa",
    "sprt",
    "polyglot",
}

EPONYM_SURNAME_TOKENS = {
    "zobrist",
}

GROUP_NAME_TERMS = {
    re.sub(r"\\s+", " ", re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", group["name"]).replace("_", " "))
    .lower()
    .strip()
    for group in GROUP_SPECS
}

ALLOWED_SINGLE_TOKEN_FEATURES = {
    "0x88",
    "bitboards",
    "mailbox",
    "negamax",
    "nnue",
    "uci",
    "xboard",
    "cecp",
    "fen",
    "epd",
    "spsa",
    "sprt",
    "clop",
    "probcut",
    "mcts",
    "uct",
    "abdada",
    "ybwc",
    "polyglot",
    "gaviota",
    "razoring",
}


@dataclass(frozen=True)
class CoreFeatureSpec:
    name: str
    group_id: str
    aliases: tuple[str, ...]


CORE_FEATURE_SPECS = [
    CoreFeatureSpec("Bitboards", "board_representation", ("bitboard", "bitboards")),
    CoreFeatureSpec("0x88", "board_representation", ("0x88",)),
    CoreFeatureSpec("Mailbox", "board_representation", ("mailbox", "mailbox board")),
    CoreFeatureSpec("10x12 Board", "board_representation", ("10x12 board", "10x12")),
    CoreFeatureSpec("Piece Lists", "board_representation", ("piece lists", "piece list")),
    CoreFeatureSpec("Bitboard Serialization", "board_representation", ("bitboard serialization",)),
    CoreFeatureSpec("Rotated Bitboards", "board_representation", ("rotated bitboards", "rotated bitboard")),
    CoreFeatureSpec("Copy-Make", "board_representation", ("copy make", "copy-make")),
    CoreFeatureSpec("Make Move", "board_representation", ("make move",)),
    CoreFeatureSpec("Unmake Move", "board_representation", ("unmake move",)),
    CoreFeatureSpec("Move Generation", "move_generation", ("move generation",)),
    CoreFeatureSpec("Pseudo-Legal Move Generation", "move_generation", ("pseudo legal", "pseudo-legal")),
    CoreFeatureSpec("Legal Move Generation", "move_generation", ("legal move generation",)),
    CoreFeatureSpec("Magic Bitboards", "move_generation", ("magic bitboards", "magic bitboard")),
    CoreFeatureSpec("Move Ordering", "move_generation", ("move ordering",)),
    CoreFeatureSpec("Alpha-Beta", "search", ("alpha-beta", "alpha beta", "alphabeta")),
    CoreFeatureSpec("Negamax", "search", ("negamax",)),
    CoreFeatureSpec("Principal Variation Search", "search", ("principal variation search", "pvs")),
    CoreFeatureSpec("Iterative Deepening", "search", ("iterative deepening",)),
    CoreFeatureSpec("Quiescence Search", "search", ("quiescence search",)),
    CoreFeatureSpec("Aspiration Windows", "search", ("aspiration windows", "aspiration window")),
    CoreFeatureSpec("NegaScout", "search", ("negascout", "scout")),
    CoreFeatureSpec("MTD(f)", "search", ("mtd(f)", "mtdf")),
    CoreFeatureSpec("Monte Carlo Tree Search", "search", ("monte carlo tree search", "mcts")),
    CoreFeatureSpec("UCT", "search", ("uct", "upper confidence bound")),
    CoreFeatureSpec("Killer Heuristic", "search", ("killer heuristic",)),
    CoreFeatureSpec("History Heuristic", "search", ("history heuristic",)),
    CoreFeatureSpec("Evaluation", "evaluation", ("evaluation",)),
    CoreFeatureSpec("Piece-Square Tables", "evaluation", ("piece-square tables", "piece square tables")),
    CoreFeatureSpec("Tapered Eval", "evaluation", ("tapered eval", "tapered evaluation")),
    CoreFeatureSpec("NNUE", "evaluation", ("nnue",)),
    CoreFeatureSpec("Neural Network Evaluation", "evaluation", ("neural network", "neural evaluation")),
    CoreFeatureSpec("Static Exchange Evaluation", "evaluation", ("static exchange evaluation", "see")),
    CoreFeatureSpec("King Safety", "evaluation", ("king safety",)),
    CoreFeatureSpec("Pawn Structure", "evaluation", ("pawn structure",)),
    CoreFeatureSpec("Mobility", "evaluation", ("mobility",)),
    CoreFeatureSpec("Transposition Table", "transposition_table", ("transposition table", "tt")),
    CoreFeatureSpec("Zobrist Hashing", "transposition_table", ("zobrist", "zobrist hashing")),
    CoreFeatureSpec("Replacement Schemes", "transposition_table", ("replacement scheme", "replacement schemes")),
    CoreFeatureSpec("Pawn Hash Table", "transposition_table", ("pawn hash", "pawn hash table")),
    CoreFeatureSpec("Hash Move", "transposition_table", ("hash move",)),
    CoreFeatureSpec("Time Management", "time_management", ("time management",)),
    CoreFeatureSpec("Pondering", "time_management", ("ponder", "pondering")),
    CoreFeatureSpec("Parallel Search", "parallelism", ("parallel search",)),
    CoreFeatureSpec("Lazy SMP", "parallelism", ("lazy smp",)),
    CoreFeatureSpec("YBWC", "parallelism", ("ybwc", "young brothers wait concept")),
    CoreFeatureSpec("ABDADA", "parallelism", ("abdada",)),
    CoreFeatureSpec("Endgame Tablebases", "endgame", ("endgame tablebases", "tablebases")),
    CoreFeatureSpec("Syzygy Bases", "endgame", ("syzygy", "syzygy bases")),
    CoreFeatureSpec("Gaviota", "endgame", ("gaviota",)),
    CoreFeatureSpec("Opening Book", "opening", ("opening book",)),
    CoreFeatureSpec("Polyglot", "opening", ("polyglot",)),
    CoreFeatureSpec("UCI", "protocol", ("uci", "universal chess interface")),
    CoreFeatureSpec("XBoard", "protocol", ("xboard", "cecp")),
    CoreFeatureSpec("FEN", "protocol", ("fen", "forsyth edwards notation")),
    CoreFeatureSpec("EPD", "protocol", ("epd", "extended position description")),
    CoreFeatureSpec("SPSA", "tuning", ("spsa",)),
    CoreFeatureSpec("Texel's Tuning Method", "tuning", ("texel", "texel's tuning")),
    CoreFeatureSpec("CLOP", "tuning", ("clop",)),
    CoreFeatureSpec("SPRT", "tuning", ("sprt",)),
    CoreFeatureSpec("Null Move Pruning", "pruning_reductions", ("null move pruning", "null move")),
    CoreFeatureSpec("Late Move Reductions", "pruning_reductions", ("late move reductions", "lmr")),
    CoreFeatureSpec("Late Move Pruning", "pruning_reductions", ("late move pruning", "lmp")),
    CoreFeatureSpec("Futility Pruning", "pruning_reductions", ("futility pruning", "futility")),
    CoreFeatureSpec("Razoring", "pruning_reductions", ("razoring",)),
    CoreFeatureSpec("ProbCut", "pruning_reductions", ("probcut",)),
    CoreFeatureSpec("Multi-Cut", "pruning_reductions", ("multi-cut", "multicut")),
    CoreFeatureSpec("Delta Pruning", "pruning_reductions", ("delta pruning",)),
]


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
        heading_hits = sum(1 for evidence in self.evidences if evidence.rule_id == "heading_match")
        definition_hits = sum(1 for evidence in self.evidences if evidence.rule_id == "definition_pattern")
        core_hits = sum(1 for evidence in self.evidences if evidence.rule_id == "core_feature_match")
        return base + heading_hits * 0.6 + definition_hits * 0.4 + core_hits * 2.0


def _clean_display_term(term: str) -> str:
    cleaned = term.strip()
    cleaned = re.sub(r"\[\s*edit\s*\]", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\[[0-9]+\]", "", cleaned)
    cleaned = cleaned.replace("*", " ")
    cleaned = cleaned.replace("|", " ")
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = cleaned.strip(" -:/")
    return cleaned


def normalize_term(term: str) -> str:
    text = _clean_display_term(term).lower().strip()
    text = text.replace("_", " ")
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[^a-z0-9+\-/#() ]", "", text)
    text = text.strip(" -/")
    return text


def _build_technical_hints() -> set[str]:
    hints: set[str] = set(TECHNICAL_CONTEXT_HINTS)
    for keywords in group_keywords().values():
        hints.update(normalize_term(keyword) for keyword in keywords)
    for core in CORE_FEATURE_SPECS:
        hints.add(normalize_term(core.name))
        for alias in core.aliases:
            hints.add(normalize_term(alias))
    return {hint for hint in hints if hint}


TECHNICAL_HINTS = _build_technical_hints()


def _is_year_or_yearish(text: str) -> bool:
    normalized = normalize_term(text)
    if re.fullmatch(r"(?:19|20)\d{2}", normalized):
        return True
    if re.fullmatch(r"(?:19|20)\d{2}\s*\.\.\.", normalized):
        return True
    return False


def _is_probable_person_name(text: str) -> bool:
    stripped = _clean_display_term(text)
    if not re.fullmatch(r"[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3}", stripped):
        return False

    tokens = [token.lower() for token in stripped.split()]
    if len(tokens) >= 2 and tokens[-1] in EPONYM_SURNAME_TOKENS:
        return True

    if any(token in TECHNICAL_NAME_TOKENS for token in tokens):
        return False

    return True


def _is_noise_term(term: str) -> bool:
    normalized = normalize_term(term)
    if not normalized:
        return True

    if normalized in NOISE_EXACT_TERMS:
        return True

    if normalized in GROUP_NAME_TERMS:
        return True

    if normalized in STOPWORDS:
        return True

    if _is_year_or_yearish(normalized):
        return True

    if normalized.startswith(("home ", "such ", "this ", "that ", "these ", "those ", "the ")):
        return True

    if any(game in normalized for game in NON_STANDARD_GAME_TERMS):
        return True

    if any(fragment in normalized for fragment in NOISE_SUBSTRINGS):
        return True

    if _is_probable_person_name(_clean_display_term(term)):
        return True

    return False


def _looks_technical_term(term: str) -> bool:
    normalized = normalize_term(term)
    if not normalized:
        return False

    if normalized in TECHNICAL_HINTS:
        return True

    for hint in TECHNICAL_HINTS:
        if len(hint) >= 5 and hint in normalized:
            return True
        if len(normalized) >= 5 and normalized in hint:
            return True
    return False


def _is_feature_like(term: str) -> bool:
    value = _clean_display_term(term)
    normalized = normalize_term(value)

    if len(value) < 2 or len(value) > 80:
        return False

    if not re.search(r"[a-zA-Z0-9]", value):
        return False

    if len(normalized.split()) > 8:
        return False

    if len(normalized.split()) == 1:
        if normalized in ALLOWED_SINGLE_TOKEN_FEATURES:
            pass
        elif "-" in normalized or "/" in normalized:
            pass
        elif normalized in TECHNICAL_HINTS and len(normalized) >= 4:
            pass
        else:
            return False

    if _is_noise_term(value):
        return False

    if value.lower().startswith(("list of", "category:", "portal:")):
        return False

    return True


def _is_technical_page(page: PageDocument) -> bool:
    descriptor = normalize_term(" ".join([page.title, *page.headings[:12], *page.categories]))
    if not descriptor:
        return False

    if any(game in descriptor for game in NON_STANDARD_GAME_TERMS):
        return False

    has_technical_signal = any(hint in descriptor for hint in TECHNICAL_HINTS)
    has_non_technical_bias = any(term in descriptor for term in NON_TECHNICAL_CONTEXT_TERMS)

    if has_non_technical_bias and not has_technical_signal:
        return False

    return has_technical_signal


def _candidate_group_hint(term: str, source_title: str) -> str | None:
    value = normalize_term(f"{term} {source_title}")
    for group_id, keywords in group_keywords().items():
        if any(normalize_term(keyword) in value for keyword in keywords):
            return group_id
    return None


def mine_feature_candidates(pages: list[PageDocument]) -> list[FeatureCandidate]:
    candidates: list[FeatureCandidate] = []

    for page in pages:
        if page.page_type == "engine":
            continue
        if not _is_technical_page(page):
            continue

        heading_terms = page.headings[:40]
        bold_terms = page.bold_terms[:40]
        link_terms = [link for link in page.links[:100] if ":" not in link]

        for term in heading_terms:
            cleaned = _clean_display_term(term)
            if not _is_feature_like(cleaned):
                continue
            if not _looks_technical_term(cleaned):
                continue
            snippet = extract_snippet(page.text, cleaned)
            candidates.append(
                FeatureCandidate(
                    name=cleaned,
                    source_url=page.url,
                    source_title=page.title,
                    snippet=snippet,
                    rule_id="heading_match",
                    group_hint=_candidate_group_hint(cleaned, page.title),
                )
            )

        for term in bold_terms:
            cleaned = _clean_display_term(term)
            if not _is_feature_like(cleaned):
                continue
            if not _looks_technical_term(cleaned):
                continue
            snippet = extract_snippet(page.text, cleaned)
            candidates.append(
                FeatureCandidate(
                    name=cleaned,
                    source_url=page.url,
                    source_title=page.title,
                    snippet=snippet,
                    rule_id="bold_term",
                    group_hint=_candidate_group_hint(cleaned, page.title),
                )
            )

        for term in link_terms:
            cleaned = _clean_display_term(term)
            if not _is_feature_like(cleaned):
                continue
            if not _looks_technical_term(cleaned):
                continue
            snippet = extract_snippet(page.text, cleaned)
            candidates.append(
                FeatureCandidate(
                    name=cleaned,
                    source_url=page.url,
                    source_title=page.title,
                    snippet=snippet,
                    rule_id="link_anchor",
                    group_hint=_candidate_group_hint(cleaned, page.title),
                )
            )

        def_pattern = re.compile(r"^([A-Z][A-Za-z0-9+/\- ()]{1,80})\s+(?:is|are|refers to|means)\b")
        for sentence in page.text.split(". ")[:80]:
            match = def_pattern.match(sentence.strip())
            if not match:
                continue
            term = _clean_display_term(match.group(1).strip())
            if not _is_feature_like(term):
                continue
            if not _looks_technical_term(term):
                continue
            candidates.append(
                FeatureCandidate(
                    name=term,
                    source_url=page.url,
                    source_title=page.title,
                    snippet=sentence.strip()[:240],
                    rule_id="definition_pattern",
                    group_hint=_candidate_group_hint(term, page.title),
                )
            )

        title_term = _clean_display_term(page.title)
        if _is_feature_like(title_term) and _looks_technical_term(title_term):
            candidates.append(
                FeatureCandidate(
                    name=title_term,
                    source_url=page.url,
                    source_title=page.title,
                    snippet=extract_snippet(page.text, title_term),
                    rule_id="heading_match",
                    group_hint=_candidate_group_hint(title_term, page.title),
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

        if not normalized or _is_noise_term(candidate.name):
            continue

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
        score = sum(1 for keyword in keywords if normalize_term(keyword) in combined)
        if score > best_score:
            best_group = group_id
            best_score = score

    return best_group


def _emit_feature_from_canonical(
    canonical: CanonicalFeature,
    group_id: str,
    used_ids: set[str],
) -> tuple[FeatureNode, list[TraceRecord]] | None:
    if not canonical.evidences:
        return None

    canonical_name = _clean_display_term(canonical.canonical_name)
    if not _is_feature_like(canonical_name):
        return None

    feature_id_base = f"feat_{slugify(canonical.canonical_key)}"
    feature_id = feature_id_base
    index = 2
    while feature_id in used_ids:
        feature_id = f"{feature_id_base}_{index}"
        index += 1
    used_ids.add(feature_id)

    aliases = sorted(set(canonical.aliases))
    aliases = [alias for alias in aliases if alias.lower() != canonical_name.lower()]

    best_evidence = canonical.evidences[0]
    node = FeatureNode(
        id=feature_id,
        name=canonical_name,
        parent_id=group_id,
        kind="optional",
        description=best_evidence.snippet[:180],
        aliases=aliases[:8],
    )

    traces: list[TraceRecord] = []
    for evidence in canonical.evidences[:2]:
        traces.append(
            build_trace(
                feature_id=feature_id,
                source_url=evidence.source_url,
                source_title=evidence.source_title,
                snippet=evidence.snippet,
                rule_id=evidence.rule_id,
                term=canonical_name,
            )
        )

    return node, traces


def synthesize_leaf_features(
    canonical_features: list[CanonicalFeature],
    target_count: int = DEFAULT_TARGET_FEATURES,
) -> tuple[list[FeatureNode], list[TraceRecord]]:
    leaves: list[FeatureNode] = []
    traces: list[TraceRecord] = []

    group_order = list(group_keywords().keys())
    per_group: dict[str, list[CanonicalFeature]] = defaultdict(list)
    for canonical in canonical_features:
        if not canonical.evidences:
            continue
        evidence = canonical.evidences[0]
        group_id = pick_group_id(canonical.canonical_name, evidence.group_hint, evidence.snippet)
        per_group[group_id].append(canonical)

    for group_id in per_group:
        per_group[group_id].sort(key=lambda item: (-item.score(), item.canonical_name.lower()))

    used_ids: set[str] = set()
    selected_keys: set[str] = set()

    per_group_quota = max(3, min(8, target_count // max(1, len(group_order))))
    for group_id in group_order:
        bucket = per_group.get(group_id, [])
        picked = 0
        for canonical in bucket:
            if picked >= per_group_quota:
                break
            if canonical.canonical_key in selected_keys:
                continue
            emitted = _emit_feature_from_canonical(canonical, group_id, used_ids)
            if emitted is None:
                continue
            node, node_traces = emitted
            leaves.append(node)
            traces.extend(node_traces)
            selected_keys.add(canonical.canonical_key)
            picked += 1

    remaining_candidates = sorted(
        [candidate for candidate in canonical_features if candidate.canonical_key not in selected_keys],
        key=lambda item: (-item.score(), item.canonical_name.lower()),
    )

    for canonical in remaining_candidates:
        if len(leaves) >= target_count:
            break
        evidence = canonical.evidences[0] if canonical.evidences else None
        if evidence is None:
            continue
        group_id = pick_group_id(canonical.canonical_name, evidence.group_hint, evidence.snippet)
        emitted = _emit_feature_from_canonical(canonical, group_id, used_ids)
        if emitted is None:
            continue
        node, node_traces = emitted
        leaves.append(node)
        traces.extend(node_traces)
        selected_keys.add(canonical.canonical_key)

    return leaves, traces


def _find_page_evidence(pages: list[PageDocument], aliases: list[str]) -> tuple[PageDocument, str, str] | None:
    alias_norms = [normalize_term(alias) for alias in aliases if normalize_term(alias)]
    for page in pages:
        title_norm = normalize_term(page.title)
        heading_blob = normalize_term(" ".join(page.headings[:20]))
        text_norm = normalize_term(page.text)
        for alias, alias_norm in zip(aliases, alias_norms):
            if not alias_norm:
                continue
            if alias_norm in title_norm or alias_norm in heading_blob or alias_norm in text_norm:
                snippet = extract_snippet(page.text, alias)
                return page, alias, snippet
    return None


def augment_with_core_features(
    leaves: list[FeatureNode],
    traces: list[TraceRecord],
    pages: list[PageDocument],
) -> tuple[list[FeatureNode], list[TraceRecord], list[str]]:
    warnings: list[str] = []
    by_normalized_name = {normalize_term(feature.name): feature for feature in leaves}
    used_ids = {feature.id for feature in leaves}

    for spec in CORE_FEATURE_SPECS:
        canonical_name = _clean_display_term(spec.name)
        canonical_norm = normalize_term(canonical_name)
        evidence_aliases = [canonical_name, *spec.aliases]

        existing = by_normalized_name.get(canonical_norm)
        if existing is not None:
            if existing.parent_id != spec.group_id:
                existing.parent_id = spec.group_id
            continue

        match = _find_page_evidence(pages, evidence_aliases)
        if match is None:
            warnings.append(f"Core feature '{canonical_name}' not evidenced in cached pages")
            continue

        page, alias, snippet = match
        base_id = f"feat_{slugify(canonical_norm)}"
        feature_id = base_id
        counter = 2
        while feature_id in used_ids:
            feature_id = f"{base_id}_{counter}"
            counter += 1
        used_ids.add(feature_id)

        node = FeatureNode(
            id=feature_id,
            name=canonical_name,
            parent_id=spec.group_id,
            kind="optional",
            description=snippet[:180],
            aliases=[alias for alias in spec.aliases if normalize_term(alias) != canonical_norm][:8],
        )
        leaves.append(node)
        by_normalized_name[canonical_norm] = node

        traces.append(
            build_trace(
                feature_id=feature_id,
                source_url=page.url,
                source_title=page.title,
                snippet=snippet,
                rule_id="core_feature_match",
                term=canonical_name,
            )
        )

    return leaves, traces, warnings


def filter_noise_features(
    leaves: list[FeatureNode],
    traces: list[TraceRecord],
) -> tuple[list[FeatureNode], list[TraceRecord], list[str]]:
    kept: list[FeatureNode] = []
    removed_names: list[str] = []
    removed_ids: set[str] = set()

    for leaf in leaves:
        if _is_feature_like(leaf.name) and _looks_technical_term(leaf.name):
            kept.append(leaf)
        else:
            removed_names.append(leaf.name)
            removed_ids.add(leaf.id)

    filtered_traces = [trace for trace in traces if trace.feature_id not in removed_ids]
    removed_names.sort(key=str.lower)
    return kept, filtered_traces, removed_names
