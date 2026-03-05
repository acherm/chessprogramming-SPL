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


def test_move_generation_is_mandatory_for_executable_variants(tmp_path):
    model = load_model_index(Path("outputs/feature_model.json"))
    tokens = _read_variant_tokens(Path("c_engine_pl/variants/bitboards_alpha.json"))
    tokens = [token for token in tokens if token != "Move Generation"]

    selected, resolve_errors = resolve_selected_option_ids(model, tokens)
    validation_errors = validate_selection(model, selected)

    assert not resolve_errors
    assert any("Move Generation" in message and "mandatory" in message for message in validation_errors)
