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

    harness_c = tmp_path / "harness.c"
    harness_bin = tmp_path / "harness"
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


def test_tournament_legality_behaviors(tmp_path: Path) -> None:
    source = textwrap.dedent(
        """
        #include <stdio.h>
        #include "engine.h"

        static int test_castling(void) {
            EngineState s;
            int rc;
            engine_init(&s);
            rc = engine_set_fen(&s, "r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1");
            if (rc != 0) return 1;
            rc = engine_apply_move_uci(&s, "e1g1");
            if (rc != 0) return 2;
            if (s.board[6] != 6 || s.board[5] != 4 || s.board[4] != 0 || s.board[7] != 0) return 3;
            return 0;
        }

        static int test_en_passant(void) {
            EngineState s;
            int rc;
            engine_init(&s);
            rc = engine_set_fen(&s, "4k3/8/8/3pP3/8/8/8/4K3 w - d6 0 1");
            if (rc != 0) return 1;
            rc = engine_apply_move_uci(&s, "e5d6");
            if (rc != 0) return 2;
            if (s.board[43] != 1) return 3;
            if (s.board[36] != 0) return 4;
            if (s.board[35] != 0) return 5;
            return 0;
        }

        static int test_fifty_move_draw(void) {
            EngineState s;
            EngineSearchResult r;
            engine_init(&s);
            if (engine_set_fen(&s, "8/8/8/8/8/8/4k3/7K w - - 100 1") != 0) return 1;
            r = engine_search(&s, 2, 50);
            if (!r.has_move) return 2;
            if (r.score_cp != 0) return 3;
            if (r.depth != 0) return 4;
            return 0;
        }

        static int test_threefold_draw(void) {
            EngineState s;
            EngineSearchResult r;
            const char *moves[] = {"g1f3","g8f6","f3g1","f6g8","g1f3","g8f6","f3g1","f6g8"};
            size_t i;
            engine_init(&s);
            for (i = 0; i < sizeof(moves) / sizeof(moves[0]); ++i) {
                if (engine_apply_move_uci(&s, moves[i]) != 0) return 1;
            }
            r = engine_search(&s, 3, 80);
            if (!r.has_move) return 2;
            if (r.score_cp != 0) return 3;
            if (r.depth != 0) return 4;
            return 0;
        }

        int main(void) {
            int castling = test_castling();
            int ep = test_en_passant();
            int fifty = test_fifty_move_draw();
            int rep = test_threefold_draw();
            printf("castling=%d en_passant=%d fifty=%d repetition=%d\\n", castling, ep, fifty, rep);
            return (castling == 0 && ep == 0 && fifty == 0 && rep == 0) ? 0 : 1;
        }
        """
    )

    output = _compile_and_run_harness(tmp_path, source)
    assert "castling=0 en_passant=0 fifty=0 repetition=0" in output
