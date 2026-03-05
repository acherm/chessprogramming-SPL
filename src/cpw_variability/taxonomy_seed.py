from __future__ import annotations

from .config import SYNONYM_MAP
from .models import FeatureNode

ROOT_FEATURE_ID = "chess_engine_product_line"

IMPLEMENTATION_GROUP_SPECS = [
    {
        "id": "board_representation",
        "name": "BoardRepresentation",
        "kind": "xor",
        "description": "Primary board-state encoding strategy (typically one per build).",
        "keywords": ["board representation", "bitboards", "0x88", "mailbox", "10x12"],
    },
    {
        "id": "search",
        "name": "Search",
        "kind": "or",
        "description": "Search core and search-level enhancements.",
        "keywords": [
            "alpha-beta",
            "negamax",
            "iterative deepening",
            "quiescence",
            "mcts",
            "uct",
            "pvs",
        ],
    },
    {
        "id": "pruning_reductions",
        "name": "PruningReductions",
        "kind": "or",
        "description": "Search pruning and reduction heuristics.",
        "keywords": ["pruning", "reduction", "lmr", "futility", "null move", "probcut"],
    },
    {
        "id": "evaluation",
        "name": "Evaluation",
        "kind": "xor",
        "description": "Primary evaluation framework and terms.",
        "keywords": ["evaluation", "nnue", "neural network", "piece-square", "king safety"],
    },
    {
        "id": "move_generation",
        "name": "MoveGeneration",
        "kind": "or",
        "description": "Move generation and ordering machinery.",
        "keywords": ["move generation", "magic bitboards", "move ordering", "legal move"],
    },
    {
        "id": "transposition_table",
        "name": "TranspositionTable",
        "kind": "or",
        "description": "Hashing and transposition storage mechanisms.",
        "keywords": ["transposition table", "zobrist", "hash move", "pawn hash"],
    },
    {
        "id": "time_management",
        "name": "TimeManagement",
        "kind": "or",
        "description": "Clock allocation and timing-related behavior.",
        "keywords": ["time management", "pondering", "time control"],
    },
    {
        "id": "parallelism",
        "name": "Parallelism",
        "kind": "or",
        "description": "Threading/distributed search strategies.",
        "keywords": ["parallel search", "lazy smp", "ybwc", "abdada"],
    },
    {
        "id": "endgame",
        "name": "Endgame",
        "kind": "or",
        "description": "Endgame databases and specialized logic.",
        "keywords": ["tablebases", "syzygy", "gaviota"],
    },
    {
        "id": "opening",
        "name": "Opening",
        "kind": "or",
        "description": "Opening phase support and books.",
        "keywords": ["opening book", "polyglot"],
    },
    {
        "id": "protocol",
        "name": "Protocol",
        "kind": "or",
        "description": "Engine communication and position I/O protocols.",
        "keywords": ["uci", "xboard", "cecp", "fen", "epd"],
    },
    {
        "id": "tuning",
        "name": "Tuning",
        "kind": "or",
        "description": "Automated tuning and validation workflows.",
        "keywords": ["spsa", "texel", "clop", "sprt"],
    },
]


def seed_feature_nodes() -> list[FeatureNode]:
    nodes: list[FeatureNode] = [
        FeatureNode(
            id=ROOT_FEATURE_ID,
            name="ChessEngineProductLine",
            parent_id=None,
            kind="mandatory",
            description="Implementation-oriented product-line model for configurable chess engine variants.",
            variation_role="root",
            variability_stage="none",
            configurable=False,
        )
    ]

    for group in IMPLEMENTATION_GROUP_SPECS:
        nodes.append(
            FeatureNode(
                id=group["id"],
                name=group["name"],
                parent_id=ROOT_FEATURE_ID,
                kind=group["kind"],
                description=group["description"],
                aliases=[],
                variation_role="group",
                variability_stage="none",
                configurable=False,
            )
        )

    return nodes


def group_keywords() -> dict[str, list[str]]:
    return {group["id"]: list(group["keywords"]) for group in IMPLEMENTATION_GROUP_SPECS}


def group_name(group_id: str) -> str:
    for group in IMPLEMENTATION_GROUP_SPECS:
        if group["id"] == group_id:
            return str(group["name"])
    return group_id


def canonical_synonym_map() -> dict[str, str]:
    synonyms = dict(SYNONYM_MAP)
    synonyms.update(
        {
            "principal variation search": "pvs",
            "pv search": "pvs",
            "transposition tables": "transposition table",
            "bitboard": "bitboards",
            "copy make": "copy-make",
            "null move": "null move pruning",
            "late move reduction": "late move reductions",
            "late move pruning": "late move pruning",
        }
    )
    return synonyms
