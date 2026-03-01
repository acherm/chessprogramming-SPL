from __future__ import annotations

from .config import GROUP_SPECS, SYNONYM_MAP
from .models import FeatureNode

ROOT_FEATURE_ID = "chess_engine_variability"


def seed_feature_nodes() -> list[FeatureNode]:
    nodes: list[FeatureNode] = [
        FeatureNode(
            id=ROOT_FEATURE_ID,
            name="ChessEngineVariability",
            parent_id=None,
            kind="mandatory",
            description="Top-level SPL variability model for chess engine implementation.",
        )
    ]

    for group in GROUP_SPECS:
        nodes.append(
            FeatureNode(
                id=group["id"],
                name=group["name"],
                parent_id=ROOT_FEATURE_ID,
                kind="optional",
                description=group["description"],
                aliases=[],
            )
        )

    return nodes


def group_keywords() -> dict[str, list[str]]:
    return {group["id"]: list(group["keywords"]) for group in GROUP_SPECS}


def group_name(group_id: str) -> str:
    for group in GROUP_SPECS:
        if group["id"] == group_id:
            return str(group["name"])
    return group_id


def canonical_synonym_map() -> dict[str, str]:
    return dict(SYNONYM_MAP)
