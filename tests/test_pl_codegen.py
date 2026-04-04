from __future__ import annotations

import json
from pathlib import Path

from cpw_variability.pl_codegen import (
    derive_variant,
    load_model_index,
    resolve_selected_option_ids,
    validate_selection,
)


def _read_variant_tokens(path: Path) -> list[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [str(item) for item in payload.get("selected_options", [])]


def test_valid_variant_config_passes_validation():
    model = load_model_index(Path("outputs/feature_model.json"))
    tokens = _read_variant_tokens(Path("c_engine_pl/variants/bitboards_alpha.json"))

    selected, resolve_errors = resolve_selected_option_ids(model, tokens)
    validation_errors = validate_selection(model, selected)

    assert not resolve_errors
    assert not validation_errors


def test_invalid_variant_config_fails_validation():
    model = load_model_index(Path("outputs/feature_model.json"))
    tokens = _read_variant_tokens(Path("c_engine_pl/variants/invalid_excludes.json"))

    selected, resolve_errors = resolve_selected_option_ids(model, tokens)
    validation_errors = validate_selection(model, selected)

    assert not resolve_errors
    assert validation_errors
    assert any("excludes" in message for message in validation_errors)


def test_derive_variant_writes_header_and_manifest(tmp_path):
    header = tmp_path / "variant_config.h"
    manifest = tmp_path / "variant_manifest.json"

    report = derive_variant(
        feature_model_path=Path("outputs/feature_model.json"),
        config_path=Path("c_engine_pl/variants/bitboards_alpha.json"),
        header_out=header,
        manifest_out=manifest,
    )

    assert report["selected_count"] > 0
    assert header.exists()
    assert manifest.exists()

    header_text = header.read_text(encoding="utf-8")
    assert "#define CFG_ALPHA_BETA 1" in header_text
    assert "#define CFG_BITBOARDS 1" in header_text
    assert "#define CFG_MINIMAX 1" in header_text


def test_move_generation_is_mandatory_for_executable_variants(tmp_path):
    model = load_model_index(Path("outputs/feature_model.json"))
    tokens = _read_variant_tokens(Path("c_engine_pl/variants/bitboards_alpha.json"))
    tokens = [token for token in tokens if token != "Move Generation"]

    selected, resolve_errors = resolve_selected_option_ids(model, tokens)
    validation_errors = validate_selection(model, selected)

    assert not resolve_errors
    assert any("Move Generation" in message and "mandatory" in message for message in validation_errors)


def test_exactly_one_search_core_is_required():
    model = load_model_index(Path("outputs/feature_model.json"))
    tokens = [
        "Bitboards",
        "Alpha-Beta",
        "Move Generation",
        "Legal Move Generation",
        "Make Move",
        "Unmake Move",
        "Castling",
        "En Passant",
        "Threefold Repetition",
        "Fifty-Move Rule",
        "Evaluation",
        "UCI",
    ]

    selected, resolve_errors = resolve_selected_option_ids(model, tokens)
    validation_errors = validate_selection(model, selected)

    assert not resolve_errors
    assert any("primary search core" in message for message in validation_errors)


def test_promoted_eval_subfeatures_generate_dedicated_flags(tmp_path):
    config = tmp_path / "eval_subfeatures.json"
    header = tmp_path / "variant_config.h"
    manifest = tmp_path / "variant_manifest.json"

    config.write_text(
        json.dumps(
            {
                "name": "eval_subfeatures",
                "selected_options": [
                    "Bitboards",
                    "Negamax",
                    "Alpha-Beta",
                    "Move Generation",
                    "Legal Move Generation",
                    "Make Move",
                    "Unmake Move",
                    "Castling",
                    "En Passant",
                    "Threefold Repetition",
                    "Fifty-Move Rule",
                    "Evaluation",
                    "Passed Pawn",
                    "Bishop Pair",
                    "King Shelter",
                    "Tapered Eval",
                    "King Activity",
                    "UCI",
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    report = derive_variant(
        feature_model_path=Path("outputs/feature_model.json"),
        config_path=config,
        header_out=header,
        manifest_out=manifest,
    )

    assert report["selected_count"] > 0

    header_text = header.read_text(encoding="utf-8")
    assert "#define CFG_PASSED_PAWN 1" in header_text
    assert "#define CFG_BISHOP_PAIR 1" in header_text
    assert "#define CFG_KING_SHELTER 1" in header_text
    assert "#define CFG_KING_ACTIVITY 1" in header_text


def test_completed_feature_variants_generate_expected_flags(tmp_path):
    header = tmp_path / "variant_config.h"
    manifest = tmp_path / "variant_manifest.json"

    derive_variant(
        feature_model_path=Path("outputs/feature_model.json"),
        config_path=Path("c_engine_pl/variants/phase2_magic_bitboards_ab_pvs_id.json"),
        header_out=header,
        manifest_out=manifest,
    )
    header_text = header.read_text(encoding="utf-8")
    assert "#define CFG_MAGIC_BITBOARDS 1" in header_text
    assert "#define CFG_NEGAMAX 1" in header_text

    derive_variant(
        feature_model_path=Path("outputs/feature_model.json"),
        config_path=Path("c_engine_pl/variants/phase2_mailbox_piece_lists_ab_pvs_id.json"),
        header_out=header,
        manifest_out=manifest,
    )
    header_text = header.read_text(encoding="utf-8")
    assert "#define CFG_MAILBOX 1" in header_text
    assert "#define CFG_PIECE_LISTS 1" in header_text

    derive_variant(
        feature_model_path=Path("outputs/feature_model.json"),
        config_path=Path("c_engine_pl/variants/phase2_runtime_book_ponder.json"),
        header_out=header,
        manifest_out=manifest,
    )
    header_text = header.read_text(encoding="utf-8")
    assert "#define CFG_MINIMAX 1" in header_text
    assert "#define CFG_OPENING_BOOK 1" in header_text
    assert "#define CFG_PONDERING 1" in header_text


def test_legacy_eval_group_tokens_expand_to_leaf_options(tmp_path):
    config = tmp_path / "legacy_eval_groups.json"
    header = tmp_path / "variant_config.h"
    manifest = tmp_path / "variant_manifest.json"

    config.write_text(
        json.dumps(
            {
                "name": "legacy_eval_groups",
                "selected_options": [
                    "Bitboards",
                    "Negamax",
                    "Alpha-Beta",
                    "Move Generation",
                    "Legal Move Generation",
                    "Make Move",
                    "Unmake Move",
                    "Castling",
                    "En Passant",
                    "Threefold Repetition",
                    "Fifty-Move Rule",
                    "Evaluation",
                    "Pawn Structure",
                    "King Safety",
                    "Tapered Eval",
                    "UCI",
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    report = derive_variant(
        feature_model_path=Path("outputs/feature_model.json"),
        config_path=config,
        header_out=header,
        manifest_out=manifest,
    )

    assert report["selected_count"] > 0
    header_text = header.read_text(encoding="utf-8")
    assert "#define CFG_PASSED_PAWN 1" in header_text
    assert "#define CFG_ISOLATED_PAWN 1" in header_text
    assert "#define CFG_DOUBLED_PAWN 1" in header_text
    assert "#define CFG_CONNECTED_PAWN 1" in header_text
    assert "#define CFG_KING_SAFETY 1" in header_text
    assert "#define CFG_KING_SHELTER 1" in header_text


def test_move_ordering_subfeatures_require_master_feature():
    model = load_model_index(Path("outputs/feature_model.json"))
    tokens = [
        "Bitboards",
        "Negamax",
        "Alpha-Beta",
        "Move Generation",
        "Legal Move Generation",
        "Make Move",
        "Unmake Move",
        "Castling",
        "En Passant",
        "Threefold Repetition",
        "Fifty-Move Rule",
        "Transposition Table",
        "Hash Move",
        "Killer Heuristic",
        "History Heuristic",
        "Evaluation",
        "UCI",
    ]

    selected, resolve_errors = resolve_selected_option_ids(model, tokens)
    validation_errors = validate_selection(model, selected)

    assert not resolve_errors
    assert any("Hash Move" in message and "Move Ordering" in message for message in validation_errors)
    assert any("Killer Heuristic" in message and "Move Ordering" in message for message in validation_errors)
    assert any("History Heuristic" in message and "Move Ordering" in message for message in validation_errors)
