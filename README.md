# Chessprogramming SPL Replication Repository

This repository is a standalone replication artifact for the exploratory study on constructing a chess-engine software product line from curated knowledge with coding agents.

It contains four main elements:

1. The SPL sources, including the Python mining/modeling pipeline and the C product-line implementation.
2. Analysis scripts and generated reports used to study the sessions, the codebase, and the experiments.
3. The full Codex engineering thread that started with `I'd like to build a feature model...`.
4. A trimmed Codex experiment thread starting with `it's time to perform experiments...`, with paper-editing turns removed.

## Layout

- `src/`: Python code for mining, feature-model elicitation, export, setup modeling, and product-line code generation.
- `c_engine_pl/`: C implementation of the chess-engine SPL, including feature-controlled variants.
- `tests/`: Python test suite covering mining, constraints, code generation, and the executable family.
- `scripts/`: Analysis and experiment scripts copied from the workspace.
- `data/chessprogramming_cache/`: Local snapshot of the Chessprogramming.org corpus used during the study.
- `outputs/`: Generated experiment outputs, reports, plots, and benchmark artifacts.
- `paper/data/`: Session-analysis reports and generated tables/figures that fed the short paper.
- `sessions/`: Codex session artifacts and trimming metadata.

## Session Artifacts

- `sessions/engineering_thread_raw.jsonl`: Raw Codex rollout for the SPL-engineering thread.
- `sessions/engineering_thread.md`: Readable transcript exported from the engineering rollout.
- `sessions/design_variant_experiments_trimmed.md`: Readable transcript of the experiment thread after removing paper-editing turns.
- `sessions/design_variant_experiments_trimmed.json`: Machine-readable version of the trimmed experiment transcript plus the dropped-turn list.
- `artifact_manifest.json`: Provenance record for copied directories, ignored artifacts, and the exact source threads.

## Session Trimming Policy

The experiment thread was not cut at a fixed date. Instead, explicit paper-editing turns were removed while keeping experiment design, execution, result analysis, plot refinement, and report generation. The dropped turns are identified by their source user-message line numbers in the original rollout and are listed in `artifact_manifest.json` and `sessions/design_variant_experiments_trimmed.json`.

## Notes

- This repository is intentionally artifact-oriented. It does not include the final paper source.
- Several scripts reflect the original working environment and may still contain absolute paths from the study workspace.
- The included Codex sessions come from local Codex Desktop storage and were copied into this standalone artifact.
