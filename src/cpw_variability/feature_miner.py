from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from difflib import SequenceMatcher

try:
    from rapidfuzz import fuzz
except Exception:  # pragma: no cover - optional dependency fallback
    fuzz = None

from .config import DEFAULT_TARGET_FEATURES
from .evidence import build_trace, extract_snippet
from .models import FeatureNode, PageDocument, TraceRecord
from .taxonomy_seed import IMPLEMENTATION_GROUP_SPECS, canonical_synonym_map, group_keywords

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
    for group in IMPLEMENTATION_GROUP_SPECS
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
    variability_stage: str = "compile_time"
    compile_flag: str = ""
    runtime_flag: str = ""


CORE_FEATURE_SPECS = [
    CoreFeatureSpec("Bitboards", "board_representation", ("bitboard", "bitboards")),
    CoreFeatureSpec("0x88", "board_representation", ("0x88",)),
    CoreFeatureSpec("Mailbox", "board_representation", ("mailbox", "mailbox board")),
    CoreFeatureSpec("10x12 Board", "board_representation", ("10x12 board", "10x12")),
    CoreFeatureSpec("Piece Lists", "board_representation", ("piece lists", "piece list")),
    CoreFeatureSpec("Copy-Make", "board_representation", ("copy make", "copy-make")),
    CoreFeatureSpec("Make Move", "board_representation", ("make move",)),
    CoreFeatureSpec("Unmake Move", "board_representation", ("unmake move",)),
    CoreFeatureSpec("Move Generation", "move_generation", ("move generation",)),
    CoreFeatureSpec("Pseudo-Legal Move Generation", "move_generation", ("pseudo legal", "pseudo-legal")),
    CoreFeatureSpec("Legal Move Generation", "move_generation", ("legal move generation",)),
    CoreFeatureSpec("Castling", "move_generation", ("castling", "castling rights")),
    CoreFeatureSpec("En Passant", "move_generation", ("en passant", "ep capture")),
    CoreFeatureSpec("Move Ordering", "move_generation", ("move ordering",)),
    CoreFeatureSpec("Magic Bitboards", "move_generation", ("magic bitboards", "magic bitboard")),
    CoreFeatureSpec("Alpha-Beta", "search", ("alpha-beta", "alpha beta", "alphabeta")),
    CoreFeatureSpec("Minimax", "search", ("minimax",)),
    CoreFeatureSpec("Negamax", "search", ("negamax",)),
    CoreFeatureSpec("Principal Variation Search", "search", ("principal variation search", "pvs")),
    CoreFeatureSpec("Iterative Deepening", "search", ("iterative deepening",)),
    CoreFeatureSpec("Quiescence Search", "search", ("quiescence search",)),
    CoreFeatureSpec("Threefold Repetition", "search", ("threefold repetition", "repetition draw")),
    CoreFeatureSpec("Fifty-Move Rule", "search", ("fifty-move rule", "50-move rule")),
    CoreFeatureSpec("Aspiration Windows", "search", ("aspiration windows", "aspiration window")),
    CoreFeatureSpec("Killer Heuristic", "search", ("killer heuristic",)),
    CoreFeatureSpec("History Heuristic", "search", ("history heuristic",)),
    CoreFeatureSpec("Evaluation", "evaluation", ("evaluation",)),
    CoreFeatureSpec("Piece-Square Tables", "evaluation", ("piece-square tables", "piece square tables")),
    CoreFeatureSpec("Tapered Eval", "evaluation", ("tapered eval", "tapered evaluation")),
    CoreFeatureSpec("Static Exchange Evaluation", "evaluation", ("static exchange evaluation",)),
    CoreFeatureSpec("King Safety", "evaluation", ("king safety",)),
    CoreFeatureSpec(
        "King Shelter",
        "evaluation",
        ("king shelter", "pawn shelter", "pawn shield"),
        compile_flag="CFG_KING_SHELTER",
    ),
    CoreFeatureSpec(
        "King Activity",
        "evaluation",
        ("king activity", "king centralization"),
        compile_flag="CFG_KING_ACTIVITY",
    ),
    CoreFeatureSpec("Pawn Structure", "evaluation", ("pawn structure",)),
    CoreFeatureSpec(
        "Passed Pawn",
        "evaluation",
        ("passed pawn", "passed pawns"),
        compile_flag="CFG_PASSED_PAWN",
    ),
    CoreFeatureSpec(
        "Isolated Pawn",
        "evaluation",
        ("isolated pawn", "isolated pawns", "isolani"),
        compile_flag="CFG_ISOLATED_PAWN",
    ),
    CoreFeatureSpec(
        "Doubled Pawn",
        "evaluation",
        ("doubled pawn", "doubled pawns"),
        compile_flag="CFG_DOUBLED_PAWN",
    ),
    CoreFeatureSpec(
        "Connected Pawn",
        "evaluation",
        ("connected pawn", "connected pawns", "connected passed pawns"),
        compile_flag="CFG_CONNECTED_PAWN",
    ),
    CoreFeatureSpec(
        "Bishop Pair",
        "evaluation",
        ("bishop pair",),
        compile_flag="CFG_BISHOP_PAIR",
    ),
    CoreFeatureSpec(
        "Rook on Open File",
        "evaluation",
        ("rook on open file", "rooks on open files", "rook open file"),
        compile_flag="CFG_ROOK_OPEN_FILE",
    ),
    CoreFeatureSpec(
        "Rook Semi-Open File",
        "evaluation",
        (
            "rook semi-open file",
            "rook on semi-open file",
            "rooks on semi open files",
            "rooks on semi-open files",
            "rook on half open file",
            "rook on half-open file",
            "rook on (half) open file",
            "rooks on (semi) open files",
        ),
        compile_flag="CFG_ROOK_SEMI_OPEN_FILE",
    ),
    CoreFeatureSpec("Mobility", "evaluation", ("mobility",)),
    CoreFeatureSpec("Transposition Table", "transposition_table", ("transposition table",)),
    CoreFeatureSpec("Zobrist Hashing", "transposition_table", ("zobrist", "zobrist hashing")),
    CoreFeatureSpec("Replacement Schemes", "transposition_table", ("replacement scheme", "replacement schemes")),
    CoreFeatureSpec("Pawn Hash Table", "transposition_table", ("pawn hash", "pawn hash table")),
    CoreFeatureSpec("Hash Move", "transposition_table", ("hash move",)),
    CoreFeatureSpec("Time Management", "time_management", ("time management",), variability_stage="runtime"),
    CoreFeatureSpec("Pondering", "time_management", ("pondering", "ponder"), variability_stage="runtime"),
    CoreFeatureSpec("Opening Book", "opening", ("opening book",)),
    CoreFeatureSpec("UCI", "protocol", ("uci", "universal chess interface")),
    CoreFeatureSpec("FEN", "protocol", ("fen", "forsyth edwards notation")),
    CoreFeatureSpec("Null Move Pruning", "pruning_reductions", ("null move pruning", "null move")),
    CoreFeatureSpec("Late Move Reductions", "pruning_reductions", ("late move reductions", "lmr")),
    CoreFeatureSpec("Futility Pruning", "pruning_reductions", ("futility pruning", "futility")),
    CoreFeatureSpec("Razoring", "pruning_reductions", ("razoring",)),
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


def _has_alias_match(alias_norm: str, text_norm: str) -> bool:
    escaped = re.escape(alias_norm)
    pattern = re.compile(rf"(?<![a-z0-9]){escaped}(?![a-z0-9])")
    return bool(pattern.search(text_norm))


def _find_page_evidence(pages: list[PageDocument], aliases: list[str]) -> tuple[PageDocument, str, str] | None:
    normalized_aliases: list[tuple[str, str]] = []
    for alias in aliases:
        alias_norm = normalize_term(alias)
        if not alias_norm:
            continue
        normalized_aliases.append((alias, alias_norm))

    best_match: tuple[int, int, PageDocument, str, str] | None = None
    page_type_bonus = {"technique": 30, "engine": 10, "meta": 0}

    for page in pages:
        title_norm = normalize_term(page.title)
        heading_norms = [normalize_term(heading) for heading in page.headings[:24]]
        bold_norms = [normalize_term(term) for term in page.bold_terms[:24]]
        link_norms = [normalize_term(term) for term in page.links[:48]]
        text_norm = normalize_term(page.text)

        for alias, alias_norm in normalized_aliases:
            score = 0

            if len(alias_norm) <= 2 and alias_norm not in {"0x88"}:
                continue

            if title_norm == alias_norm:
                score += 120
            elif _has_alias_match(alias_norm, title_norm):
                score += 80

            if any(heading == alias_norm for heading in heading_norms):
                score += 70
            elif any(_has_alias_match(alias_norm, heading) for heading in heading_norms):
                score += 45

            if any(_has_alias_match(alias_norm, term) for term in bold_norms):
                score += 25
            if any(_has_alias_match(alias_norm, term) for term in link_norms):
                score += 12
            if _has_alias_match(alias_norm, text_norm):
                score += 6

            score += page_type_bonus.get(page.page_type, 0)
            if score <= 0:
                continue

            rank = 0 if page.page_type == "technique" else 1 if page.page_type == "engine" else 2
            snippet = extract_snippet(page.text, alias)
            candidate = (score, -rank, page, alias, snippet)
            if best_match is None or candidate[:2] > best_match[:2]:
                best_match = candidate

    if best_match is None:
        return None
    return best_match[2], best_match[3], best_match[4]


def _stage_from_spec(spec: CoreFeatureSpec) -> str:
    return spec.variability_stage if spec.variability_stage in {"compile_time", "runtime", "mixed"} else "compile_time"


def _compile_flag_for(spec: CoreFeatureSpec) -> str:
    if spec.compile_flag:
        return spec.compile_flag
    return f"CFG_{slugify(spec.name).upper()}"


def _runtime_flag_for(spec: CoreFeatureSpec) -> str:
    if spec.runtime_flag:
        return spec.runtime_flag
    if _stage_from_spec(spec) in {"runtime", "mixed"}:
        return f"--{slugify(spec.name).replace('_', '-')}"
    return ""


def mine_implementation_features(
    pages: list[PageDocument],
    target_count: int = DEFAULT_TARGET_FEATURES,
) -> tuple[list[FeatureNode], list[TraceRecord], list[str]]:
    leaves: list[FeatureNode] = []
    traces: list[TraceRecord] = []
    warnings: list[str] = []
    used_ids: set[str] = set()
    missing: list[str] = []

    for spec in CORE_FEATURE_SPECS:
        aliases = [spec.name, *spec.aliases]
        match = _find_page_evidence(pages, aliases)
        if match is None:
            missing.append(spec.name)
            continue

        page, alias_used, snippet = match
        feature_id_base = f"feat_{slugify(spec.name)}"
        feature_id = feature_id_base
        index = 2
        while feature_id in used_ids:
            feature_id = f"{feature_id_base}_{index}"
            index += 1
        used_ids.add(feature_id)

        stage = _stage_from_spec(spec)
        leaves.append(
            FeatureNode(
                id=feature_id,
                name=spec.name,
                parent_id=spec.group_id,
                kind="optional",
                description=snippet[:180],
                aliases=[alias for alias in spec.aliases if normalize_term(alias) != normalize_term(spec.name)],
                variation_role="option",
                variability_stage=stage if stage in {"compile_time", "runtime", "mixed"} else "compile_time",
                configurable=True,
                compile_flag=_compile_flag_for(spec),
                runtime_flag=_runtime_flag_for(spec),
            )
        )

        traces.append(
            build_trace(
                feature_id=feature_id,
                source_url=page.url,
                source_title=page.title,
                snippet=snippet,
                rule_id="core_feature_match",
                term=alias_used,
            )
        )

    leaves.sort(key=lambda feature: (feature.parent_id or "", feature.name.lower()))
    if target_count > 0 and len(leaves) > target_count:
        kept_ids = {feature.id for feature in leaves[:target_count]}
        leaves = leaves[:target_count]
        traces = [trace for trace in traces if trace.feature_id in kept_ids]

    if missing:
        preview = ", ".join(sorted(missing)[:12])
        warnings.append(
            f"{len(missing)} catalog variability options were not evidenced in current cache (e.g., {preview})"
        )

    if not leaves:
        warnings.append("No implementation-oriented feature options were mined from cache")

    return leaves, traces, warnings


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
            compile_flag=_compile_flag_for(spec),
            runtime_flag=_runtime_flag_for(spec),
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
