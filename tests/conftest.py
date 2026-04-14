from __future__ import annotations

import pytest

from cpw_variability.models import PageDocument


@pytest.fixture
def sample_pages() -> list[PageDocument]:
    return [
        PageDocument(
            title="Main_Page",
            url="https://www.chessprogramming.org/Main_Page",
            source_type="html",
            retrieved_at="2026-01-01T00:00:00+00:00",
            content_hash="h_main",
            text=(
                "Chess engines combine search, evaluation, transposition table, and time management techniques. "
                "The encyclopedia references major algorithms and engine implementations."
            ),
            headings=["Main Page", "Search", "Evaluation"],
            links=["Alpha-Beta", "Quiescence Search", "Monte-Carlo Tree Search", "Stockfish", "Leela Chess Zero"],
            bold_terms=["Search", "Evaluation", "Transposition Table"],
            categories=["Meta"],
            page_type="meta",
        ),
        PageDocument(
            title="Alpha-Beta",
            url="https://www.chessprogramming.org/Alpha-Beta",
            source_type="html",
            retrieved_at="2026-01-01T00:00:00+00:00",
            content_hash="h_ab",
            text=(
                "Alpha-Beta is a minimax search algorithm. "
                "Iterative deepening often surrounds alpha-beta search. "
                "Transposition table integration is common."
            ),
            headings=["Alpha-Beta", "Iterative Deepening"],
            links=["Search", "Iterative Deepening", "Transposition Table"],
            bold_terms=["Alpha-Beta", "Iterative Deepening"],
            categories=["Search"],
            page_type="technique",
        ),
        PageDocument(
            title="Quiescence Search",
            url="https://www.chessprogramming.org/Quiescence_Search",
            source_type="html",
            retrieved_at="2026-01-01T00:00:00+00:00",
            content_hash="h_qs",
            text=(
                "Quiescence Search is a selective extension used after the horizon. "
                "It usually evaluates tactical captures and checks."
            ),
            headings=["Quiescence Search"],
            links=["Search", "Evaluation"],
            bold_terms=["Quiescence Search"],
            categories=["Search"],
            page_type="technique",
        ),
        PageDocument(
            title="Pawn Structure",
            url="https://www.chessprogramming.org/Pawn_Structure",
            source_type="html",
            retrieved_at="2026-01-01T00:00:00+00:00",
            content_hash="h_pawn",
            text=(
                "Pawn structure evaluation includes passed pawn, isolated pawn, doubled pawn, and connected pawn bonuses or penalties."
            ),
            headings=["Pawn Structure"],
            links=["Passed Pawn", "Isolated Pawn", "Doubled Pawn", "Connected Pawn"],
            bold_terms=["Pawn Structure", "Passed Pawn"],
            categories=["Evaluation"],
            page_type="technique",
        ),
        PageDocument(
            title="Material",
            url="https://www.chessprogramming.org/Material",
            source_type="html",
            retrieved_at="2026-01-01T00:00:00+00:00",
            content_hash="h_material",
            text=(
                "Material evaluation often includes the bishop pair bonus and rook on open file or semi-open file bonuses."
            ),
            headings=["Material", "Other Material Considerations"],
            links=["Bishop Pair", "Rook on Open File"],
            bold_terms=["Bishop Pair"],
            categories=["Evaluation"],
            page_type="technique",
        ),
        PageDocument(
            title="King Safety",
            url="https://www.chessprogramming.org/King_Safety",
            source_type="html",
            retrieved_at="2026-01-01T00:00:00+00:00",
            content_hash="h_king",
            text=(
                "King safety can include pawn shelter and king activity or king centralization in later phases."
            ),
            headings=["King Safety"],
            links=["Pawn Shelter", "King Centralization"],
            bold_terms=["King Safety", "Pawn Shelter"],
            categories=["Evaluation"],
            page_type="technique",
        ),
        PageDocument(
            title="Monte-Carlo Tree Search",
            url="https://www.chessprogramming.org/Monte-Carlo_Tree_Search",
            source_type="html",
            retrieved_at="2026-01-01T00:00:00+00:00",
            content_hash="h_mcts",
            text=(
                "Monte-Carlo Tree Search is a best-first strategy. "
                "MCTS can be combined with neural network policy and value guidance."
            ),
            headings=["Monte-Carlo Tree Search"],
            links=["Search", "Neural Network"],
            bold_terms=["Monte-Carlo Tree Search", "MCTS"],
            categories=["Search"],
            page_type="technique",
        ),
        PageDocument(
            title="Stockfish",
            url="https://www.chessprogramming.org/Stockfish",
            source_type="html",
            retrieved_at="2026-01-01T00:00:00+00:00",
            content_hash="h_sf",
            text=(
                "Stockfish uses alpha-beta search with iterative deepening and transposition table. "
                "It does not use Monte-Carlo Tree Search."
            ),
            headings=["Stockfish"],
            links=["Alpha-Beta", "Iterative Deepening", "Transposition Table"],
            bold_terms=["Stockfish"],
            categories=["Chess Engines"],
            page_type="engine",
        ),
        PageDocument(
            title="Leela Chess Zero",
            url="https://www.chessprogramming.org/Leela_Chess_Zero",
            source_type="html",
            retrieved_at="2026-01-01T00:00:00+00:00",
            content_hash="h_lc0",
            text=(
                "Leela Chess Zero uses Monte-Carlo Tree Search with neural network evaluation. "
                "It operates without alpha-beta pruning."
            ),
            headings=["Leela Chess Zero"],
            links=["Monte-Carlo Tree Search", "Neural Network"],
            bold_terms=["Leela Chess Zero"],
            categories=["Chess Engines"],
            page_type="engine",
        ),
    ]
