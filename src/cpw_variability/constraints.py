from __future__ import annotations

from dataclasses import dataclass

from .models import ConstraintKind, ConstraintRule, FeatureNode


@dataclass(frozen=True)
class ConstraintSpec:
    kind: ConstraintKind
    left: str
    right: str
    rationale: str


CONSTRAINT_SPECS: list[ConstraintSpec] = [
    ConstraintSpec("requires", "Magic Bitboards", "Bitboards", "Magic indexing is defined over bitboard representation."),
    ConstraintSpec("requires", "Legal Move Generation", "Move Generation", "Legal move generation extends the base move generation pipeline."),
    ConstraintSpec("requires", "Pseudo-Legal Move Generation", "Move Generation", "Pseudo-legal generation still depends on core move generation support."),
    ConstraintSpec("requires", "Copy-Make", "Make Move", "Copy-make still needs deterministic move application."),
    ConstraintSpec("requires", "Unmake Move", "Make Move", "Unmake is the inverse operation of make-move."),
    ConstraintSpec("requires", "Castling", "Legal Move Generation", "Castling legality depends on attack-aware legal move generation."),
    ConstraintSpec("requires", "En Passant", "Legal Move Generation", "En-passant legality depends on legal move validation."),
    ConstraintSpec("requires", "Minimax", "Make Move", "Tree search requires move application."),
    ConstraintSpec("requires", "Minimax", "Unmake Move", "Minimax implementation uses make/unmake in recursion."),
    ConstraintSpec("requires", "Alpha-Beta", "Make Move", "Tree search requires move application."),
    ConstraintSpec("requires", "Alpha-Beta", "Unmake Move", "Alpha-Beta implementation uses make/unmake in recursion."),
    ConstraintSpec("requires", "Alpha-Beta", "Castling", "Tournament-legal alpha-beta variants include castling rules."),
    ConstraintSpec("requires", "Alpha-Beta", "En Passant", "Tournament-legal alpha-beta variants include en-passant rules."),
    ConstraintSpec("requires", "Alpha-Beta", "Threefold Repetition", "Tournament-legal alpha-beta variants detect repetition draws."),
    ConstraintSpec("requires", "Alpha-Beta", "Fifty-Move Rule", "Tournament-legal alpha-beta variants detect 50-move draws."),
    ConstraintSpec("requires", "Negamax", "Make Move", "Tree search requires move application."),
    ConstraintSpec("requires", "Negamax", "Unmake Move", "Negamax implementation uses make/unmake in recursion."),
    ConstraintSpec("requires", "Quiescence Search", "Make Move", "Quiescence examines tactical continuations via move application."),
    ConstraintSpec("requires", "Quiescence Search", "Unmake Move", "Quiescence implementation reverts explored captures."),
    ConstraintSpec("requires", "Hash Move", "Transposition Table", "Hash move retrieval requires a transposition table."),
    ConstraintSpec("requires", "Hash Move", "Move Ordering", "Hash move ordering refines the move ordering framework."),
    ConstraintSpec("requires", "Killer Heuristic", "Move Ordering", "Killer heuristic is part of the move ordering framework."),
    ConstraintSpec("requires", "History Heuristic", "Move Ordering", "History heuristic is part of the move ordering framework."),
    ConstraintSpec("requires", "Pawn Hash Table", "Zobrist Hashing", "Pawn-hash keys are derived from hashing strategy."),
    ConstraintSpec("requires", "Replacement Schemes", "Transposition Table", "Replacement schemes refine how TT entries are stored."),
    ConstraintSpec("requires", "Principal Variation Search", "Alpha-Beta", "PVS is an Alpha-Beta refinement."),
    ConstraintSpec("requires", "Aspiration Windows", "Alpha-Beta", "Aspiration windows wrap around Alpha-Beta search bounds."),
    ConstraintSpec("requires", "Null Move Pruning", "Alpha-Beta", "Null-move pruning is integrated in alpha-beta style search."),
    ConstraintSpec("requires", "Late Move Reductions", "Alpha-Beta", "LMR depends on alpha-beta move ordering and bounds."),
    ConstraintSpec("requires", "Futility Pruning", "Alpha-Beta", "Futility pruning relies on alpha-beta bound context."),
    ConstraintSpec("requires", "Delta Pruning", "Quiescence Search", "Delta pruning is applied in quiescence search."),
    ConstraintSpec("requires", "Passed Pawn", "Evaluation", "Passed-pawn scoring is an evaluation term."),
    ConstraintSpec("requires", "Isolated Pawn", "Evaluation", "Isolated-pawn scoring is an evaluation term."),
    ConstraintSpec("requires", "Doubled Pawn", "Evaluation", "Doubled-pawn scoring is an evaluation term."),
    ConstraintSpec("requires", "Connected Pawn", "Evaluation", "Connected-pawn scoring is an evaluation term."),
    ConstraintSpec("requires", "Bishop Pair", "Evaluation", "Bishop-pair scoring is an evaluation term."),
    ConstraintSpec("requires", "Rook on Open File", "Evaluation", "Open-file rook bonuses are evaluation terms."),
    ConstraintSpec("requires", "Rook Semi-Open File", "Evaluation", "Semi-open-file rook bonuses are evaluation terms."),
    ConstraintSpec("requires", "King Pressure", "Evaluation", "King-pressure scoring is an evaluation term."),
    ConstraintSpec("requires", "King Shelter", "Evaluation", "King shelter is an evaluation term."),
    ConstraintSpec("requires", "King Activity", "Evaluation", "King activity is an evaluation term."),
    ConstraintSpec("requires", "King Activity", "Tapered Eval", "King activity is modeled as an endgame-weighted evaluation term."),
    ConstraintSpec("excludes", "Minimax", "Negamax", "Search core is modeled as a single primary choice."),
    ConstraintSpec("excludes", "Bitboards", "Mailbox", "Board encodings are modeled as alternative primary representations."),
    ConstraintSpec("excludes", "Bitboards", "0x88", "Board encodings are modeled as alternative primary representations."),
    ConstraintSpec("excludes", "Bitboards", "10x12 Board", "Board encodings are modeled as alternative primary representations."),
    ConstraintSpec("excludes", "Mailbox", "0x88", "Board encodings are modeled as alternative primary representations."),
    ConstraintSpec("excludes", "Mailbox", "10x12 Board", "Board encodings are modeled as alternative primary representations."),
    ConstraintSpec("excludes", "0x88", "10x12 Board", "Board encodings are modeled as alternative primary representations."),
]


def _normalize_name(name: str) -> str:
    return " ".join(name.lower().split())


def build_cross_tree_constraints(features: list[FeatureNode]) -> tuple[list[ConstraintRule], list[str]]:
    by_name: dict[str, FeatureNode] = {}
    for feature in features:
        by_name[_normalize_name(feature.name)] = feature

    constraints: list[ConstraintRule] = []
    warnings: list[str] = []
    seen: set[tuple[str, str, str]] = set()

    for index, spec in enumerate(CONSTRAINT_SPECS, start=1):
        left = by_name.get(_normalize_name(spec.left))
        right = by_name.get(_normalize_name(spec.right))

        if left is None or right is None:
            warnings.append(
                f"Skipped constraint '{spec.kind}({spec.left}, {spec.right})' because one feature is missing"
            )
            continue

        if left.id == right.id:
            warnings.append(f"Skipped malformed self-constraint '{spec.kind}({spec.left})'")
            continue

        sig = (spec.kind, left.id, right.id)
        if sig in seen:
            continue
        seen.add(sig)

        constraints.append(
            ConstraintRule(
                id=f"ctr_{index:03d}_{spec.kind}",
                kind=spec.kind,
                left_feature_id=left.id,
                right_feature_id=right.id,
                rationale=spec.rationale,
                source="implementation_catalog",
            )
        )

    return constraints, warnings
