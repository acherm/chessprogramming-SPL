# Chessprogramming SPL Replication Repository

This repository is a standalone replication artifact for the exploratory study on constructing a chess-engine software product line from curated knowledge with coding agents.

> **Status.** The current product line combines a 1,316-page chessprogramming.org snapshot, a 74-feature implementation-backed feature model, and 7,537 non-empty lines of maintained C code, together with the infrastructure that derives many robust and strength-diverse variants from that model. As is normal for ongoing development at this scale, there is room for improvement — across the C engine, the feature model, and the experimental pipeline — and some of it is already tracked and actionable as open issues.

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
- `data/chessprogramming_cache/`: Cache metadata for the Chessprogramming.org snapshot used during the study. Public redistribution of mirrored page bodies is intentionally omitted from this repository.
- `outputs/`: Generated experiment outputs, reports, plots, and benchmark artifacts — including the feature model itself (`feature_model.json` plus FeatureIDE XML, UVL, FAMILIAR, and SVG exports; see [`FEATURE_MODEL.md`](FEATURE_MODEL.md)).
- `paper/data/`: Session-analysis reports and generated tables/figures that fed the short paper.
- `sessions/`: Codex session artifacts and trimming metadata.

## Session Artifacts

- `sessions/engineering_thread_raw.jsonl`: Raw Codex rollout for the SPL-engineering thread.
- `sessions/engineering_thread.md`: Readable transcript exported from the engineering rollout.
- `sessions/design_variant_experiments_trimmed.md`: Readable transcript of the experiment thread after removing paper-editing turns.
- `sessions/design_variant_experiments_trimmed.json`: Machine-readable version of the trimmed experiment transcript plus the dropped-turn list.
- `artifact_manifest.json`: Provenance record for copied directories, ignored artifacts, and the exact source threads.

## Notes

- This repository is intentionally artifact-oriented. It does not include the final paper source.
- The public artifact omits mirrored CPW page payloads. To rebuild the cache locally, install the package and run the pipeline, for example:

```bash
pip install -e .
PYTHONPATH=src python3 -m cpw_variability.cli fetch --seed implementation --mode snapshot --max-pages 1500
```

  or rerun the full pipeline:

```bash
pip install -e .
PYTHONPATH=src python3 -m cpw_variability.cli run-all --seed implementation --mode snapshot --max-pages 1500
```

- Several scripts reflect the original working environment and may still contain absolute paths from the study workspace.
- The included Codex sessions come from local Codex Desktop storage and were copied into this standalone artifact.
