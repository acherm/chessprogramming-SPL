from __future__ import annotations

import os
from pathlib import Path

from .models import Paths

BASE_URL = "https://www.chessprogramming.org"
DEFAULT_TIMEOUT_SECONDS = 12
DEFAULT_MAX_DISCOVERY_PAGES = 600
DEFAULT_TARGET_FEATURES = 150
DEFAULT_USER_AGENT = "cpw-var/0.1 (+cache-first; polite-crawl)"
DEFAULT_MIN_REQUEST_INTERVAL_SECONDS = 1.5
DEFAULT_MAX_HTTP_RETRIES = 3
DEFAULT_HTTP_BACKOFF_SECONDS = 1.5
DEFAULT_MAX_FETCH_FAILURES_PER_PAGE = 2
DEFAULT_DISCOVERY_CHECKPOINT_EVERY = 10

SEED_TITLES: dict[str, list[str]] = {
    "main": [
        "Main_Page",
        "Category:Chess_Engines",
        "Category:Search",
        "Category:Evaluation",
        "Category:Endgame",
    ]
}

NEGATION_PATTERNS = [
    "does not",
    "doesn't",
    "do not",
    "without",
    "lacks",
    "lack",
    "never",
    "no",
    "not",
]

GROUP_SPECS = [
    {
        "id": "search",
        "name": "Search",
        "description": "Tree search and node expansion strategies.",
        "keywords": [
            "search",
            "alpha-beta",
            "negamax",
            "iterative deepening",
            "mcts",
            "quiescence",
            "aspiration",
            "null move",
        ],
    },
    {
        "id": "evaluation",
        "name": "Evaluation",
        "description": "Position scoring, features, and neural/classical evaluators.",
        "keywords": [
            "evaluation",
            "neural",
            "nnue",
            "king safety",
            "piece-square",
            "pawn structure",
        ],
    },
    {
        "id": "move_generation",
        "name": "MoveGeneration",
        "description": "Legal/pseudo-legal generation and move ordering inputs.",
        "keywords": ["move generation", "bitboard", "magic", "move ordering", "captures"],
    },
    {
        "id": "board_representation",
        "name": "BoardRepresentation",
        "description": "Internal board and state representations.",
        "keywords": ["bitboard", "mailbox", "0x88", "representation", "zobrist"],
    },
    {
        "id": "transposition_table",
        "name": "TranspositionTable",
        "description": "Hashing and transposition storage techniques.",
        "keywords": ["transposition", "hash", "zobrist", "tt", "replacement"],
    },
    {
        "id": "time_management",
        "name": "TimeManagement",
        "description": "Clock allocation and control heuristics.",
        "keywords": ["time management", "time control", "clock", "ponder"],
    },
    {
        "id": "parallelism",
        "name": "Parallelism",
        "description": "Parallel search and SMP/distributed strategies.",
        "keywords": ["parallel", "smp", "threads", "distributed", "lazy smp"],
    },
    {
        "id": "endgame",
        "name": "Endgame",
        "description": "Endgame-specific search/evaluation/tablebase techniques.",
        "keywords": ["endgame", "tablebase", "syzygy", "egtb"],
    },
    {
        "id": "opening",
        "name": "Opening",
        "description": "Opening books and opening-phase heuristics.",
        "keywords": ["opening", "book", "polyglot"],
    },
    {
        "id": "protocol",
        "name": "Protocol",
        "description": "Engine communication protocols and interfaces.",
        "keywords": ["uci", "xboard", "protocol", "cecp"],
    },
    {
        "id": "tuning",
        "name": "Tuning",
        "description": "Automated/manual parameter tuning workflows.",
        "keywords": ["tuning", "sprt", "parameter", "optimization"],
    },
    {
        "id": "pruning_reductions",
        "name": "PruningReductions",
        "description": "Pruning/reduction heuristics and search reductions.",
        "keywords": ["pruning", "reduction", "lmr", "futility", "null move"],
    },
]

SYNONYM_MAP = {
    "alphabeta": "alpha-beta",
    "alpha beta": "alpha-beta",
    "mcts": "monte carlo tree search",
    "monte-carlo tree search": "monte carlo tree search",
    "tt": "transposition table",
    "nn": "neural network",
    "nnue": "nnue",
    "lmr": "late move reductions",
    "null move pruning": "null move",
    "iterative deepening search": "iterative deepening",
}


def resolve_paths(root: Path | None = None) -> Paths:
    env_root = os.environ.get("CPW_VAR_ROOT")
    workspace_root = root or (Path(env_root).resolve() if env_root else Path(__file__).resolve().parents[2])

    data_dir = workspace_root / "data"
    cache_dir = data_dir / "chessprogramming_cache"
    cache_pages_dir = cache_dir / "pages"
    cache_raw_dir = cache_dir / "raw"
    cache_manifest_path = cache_dir / "manifest.json"
    outputs_dir = workspace_root / "outputs"

    return Paths(
        root=workspace_root,
        data_dir=data_dir,
        cache_dir=cache_dir,
        cache_pages_dir=cache_pages_dir,
        cache_raw_dir=cache_raw_dir,
        cache_manifest_path=cache_manifest_path,
        outputs_dir=outputs_dir,
        discovered_pages_path=outputs_dir / "discovered_pages.json",
        discovery_state_path=cache_dir / "discovery_state.json",
        feature_model_json_path=outputs_dir / "feature_model.json",
        feature_model_featureide_path=outputs_dir / "feature_model.featureide.xml",
        feature_traces_csv_path=outputs_dir / "feature_traces.csv",
        engine_feature_matrix_csv_path=outputs_dir / "engine_feature_matrix.csv",
        engine_feature_matrix_md_path=outputs_dir / "engine_feature_matrix.md",
        run_report_path=outputs_dir / "run_report.md",
    )
