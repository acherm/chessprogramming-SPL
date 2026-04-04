from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from cpw_variability.pl_codegen import derive_variant


@pytest.fixture()
def runtime_book_ponder_engine() -> Path:
    if shutil.which("cc") is None:
        pytest.skip("C compiler not available")

    root = Path.cwd()
    derive_variant(
        feature_model_path=Path("outputs/feature_model.json"),
        config_path=Path("c_engine_pl/variants/phase2_runtime_book_ponder.json"),
        header_out=Path("c_engine_pl/include/generated/variant_config.h"),
        manifest_out=Path("c_engine_pl/include/generated/variant_manifest.json"),
    )
    subprocess.run(
        ["make", "-B", "-f", "c_engine_pl/Makefile"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    try:
        yield root / "c_engine_pl" / "build" / "engine_pl"
    finally:
        derive_variant(
            feature_model_path=Path("outputs/feature_model.json"),
            config_path=Path("c_engine_pl/variants/phase3_full_eval.json"),
            header_out=Path("c_engine_pl/include/generated/variant_config.h"),
            manifest_out=Path("c_engine_pl/include/generated/variant_manifest.json"),
        )
        subprocess.run(
            ["make", "-B", "-f", "c_engine_pl/Makefile"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )


def test_external_book_file_controls_bestmove(tmp_path: Path, runtime_book_ponder_engine: Path) -> None:
    book_file = tmp_path / "test_opening_book.txt"
    book_file.write_text("startpos moves h2h4\n", encoding="utf-8")

    result = subprocess.run(
        [str(runtime_book_ponder_engine)],
        input=(
            "uci\n"
            "isready\n"
            "setoption name OwnBook value true\n"
            f"setoption name BookFile value {book_file}\n"
            "position startpos\n"
            "go depth 4\n"
            "quit\n"
        ),
        capture_output=True,
        text=True,
        check=True,
    )

    assert "option name OwnBook type check default true" in result.stdout
    assert "option name BookFile type string default c_engine_pl/books/default_openings.txt" in result.stdout
    assert "bestmove h2h4" in result.stdout


def test_go_ponder_runs_asynchronously_until_ponderhit(runtime_book_ponder_engine: Path) -> None:
    result = subprocess.run(
        [str(runtime_book_ponder_engine)],
        input=(
            "uci\n"
            "isready\n"
            "setoption name OwnBook value false\n"
            "setoption name Ponder value true\n"
            "position startpos moves e2e4 c7c5 g1f3\n"
            "go ponder depth 6\n"
            "isready\n"
            "ponderhit\n"
            "quit\n"
        ),
        capture_output=True,
        text=True,
        check=True,
    )

    ready_positions = [index for index in range(len(result.stdout)) if result.stdout.startswith("readyok", index)]
    bestmove_index = result.stdout.rfind("bestmove ")

    assert len(ready_positions) >= 2
    assert bestmove_index > ready_positions[-1]
    assert "bestmove 0000" not in result.stdout
