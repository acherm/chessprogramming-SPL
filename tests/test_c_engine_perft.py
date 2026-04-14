from __future__ import annotations

import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

from cpw_variability.pl_codegen import derive_variant


def _compile_and_run_harness(tmp_path: Path, source: str) -> str:
    if shutil.which("cc") is None:
        pytest.skip("C compiler not available")

    include_root = tmp_path
    generated_dir = include_root / "generated"
    generated_dir.mkdir(parents=True, exist_ok=True)

    derive_variant(
        feature_model_path=Path("outputs/feature_model.json"),
        config_path=Path("c_engine_pl/variants/bitboards_alpha.json"),
        header_out=generated_dir / "variant_config.h",
        manifest_out=generated_dir / "variant_manifest.json",
    )

    harness_c = tmp_path / "perft_harness.c"
    harness_bin = tmp_path / "perft_harness"
    harness_c.write_text(source, encoding="utf-8")

    subprocess.run(
        [
            "cc",
            f"-I{include_root}",
            "-Ic_engine_pl/include",
            "-std=c11",
            "-O2",
            "-Wall",
            "-Wextra",
            "-pedantic",
            str(harness_c),
            "c_engine_pl/src/engine.c",
            "c_engine_pl/src/search.c",
            "c_engine_pl/src/board_backend.c",
            "c_engine_pl/src/eval.c",
            "-o",
            str(harness_bin),
        ],
        check=True,
    )
    result = subprocess.run([str(harness_bin)], check=True, capture_output=True, text=True)
    return result.stdout


def test_startpos_perft_reference_counts(tmp_path: Path) -> None:
    source = textwrap.dedent(
        """
        #include <stdio.h>
        #include <stdint.h>
        #include "engine.h"

        int main(void) {
            EngineState s;
            uint64_t d1, d2, d3;
            engine_init(&s);
            d1 = engine_perft(&s, 1);
            d2 = engine_perft(&s, 2);
            d3 = engine_perft(&s, 3);
            printf("d1=%llu d2=%llu d3=%llu\\n",
                   (unsigned long long)d1,
                   (unsigned long long)d2,
                   (unsigned long long)d3);
            if (d1 != 20ULL || d2 != 400ULL || d3 != 8902ULL) {
                return 1;
            }
            return 0;
        }
        """
    )

    output = _compile_and_run_harness(tmp_path, source)
    assert "d1=20 d2=400 d3=8902" in output
