#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from cpw_variability.pl_codegen import derive_variant, run_build, run_smoke


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Derive and build a C chess engine variant from feature model configuration")
    parser.add_argument("--feature-model", default="outputs/feature_model.json")
    parser.add_argument("--config", required=True, help="Variant config JSON with selected_options")
    parser.add_argument("--header-out", default="c_engine_pl/include/generated/variant_config.h")
    parser.add_argument("--manifest-out", default="c_engine_pl/include/generated/variant_manifest.json")
    parser.add_argument("--makefile", default="c_engine_pl/Makefile")
    parser.add_argument("--engine-bin", default="c_engine_pl/build/engine_pl")
    parser.add_argument("--build", action="store_true", help="Build engine after generating variant header")
    parser.add_argument("--smoke", action="store_true", help="Run UCI smoke test after build")
    parser.add_argument(
        "--allow-non-tournament-legality",
        action="store_true",
        help="Disable mandatory tournament-legality options (Castling/En Passant/Threefold/Fifty-Move) validation",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()

    try:
        report = derive_variant(
            feature_model_path=Path(args.feature_model),
            config_path=Path(args.config),
            header_out=Path(args.header_out),
            manifest_out=Path(args.manifest_out),
            enforce_tournament_legality=not args.allow_non_tournament_legality,
        )
    except ValueError as exc:
        print(f"ERROR: {exc}")
        return 2

    print(json.dumps(report, indent=2))

    if args.build:
        run_build(Path(args.makefile))
        print("Build: OK")

    if args.smoke:
        output = run_smoke(Path(args.engine_bin))
        print("Smoke: OK")
        print(output)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
