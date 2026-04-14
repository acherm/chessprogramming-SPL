from __future__ import annotations

import json
from pathlib import Path


def test_every_modeled_option_has_c_implementation_guard():
    model = json.loads(Path("outputs/feature_model.json").read_text(encoding="utf-8"))
    options = [
        feature
        for feature in model.get("features", [])
        if feature.get("variation_role") == "option" and feature.get("configurable")
    ]

    c_sources = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(Path("c_engine_pl/src").glob("*.c"))
    )

    missing = []
    for option in options:
        flag = option.get("compile_flag", "")
        if not flag or flag not in c_sources:
            missing.append((option.get("name", "<unnamed>"), flag))

    assert not missing, f"Unimplemented feature guards detected: {missing}"
