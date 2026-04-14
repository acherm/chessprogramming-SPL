# Testing Story Report

This report re-analyzes the Codex sessions with one narrow question in mind:
how much of the testing and benchmarking infrastructure was actually built by the coding agent, which strategies emerged, and where human supervision had to redirect the effort.

## 1. Scope

- Workspace: `/Users/mathieuacher/SANDBOX/chessprogramming-vm`
- Relevant threads analyzed: **3 threads** across **3 roles** (engineering, experiments, paper)
- Testing-related prompts (engineering + experiments): **46**
- Testing/benchmarking command invocations matched to explicit families: **342**
- Broadly micromanagement-like testing prompts: **3 / 46**
- Current collected test cases in the repository: **35**

The supervision signal is therefore mostly strategic: the user set quality gates and corrected weak directions, but usually did not prescribe test files, harness structure, or benchmark scripts line by line.

## 2. Main Finding

The sessions show a layered testing strategy that was progressively built rather than fully specified upfront.
The agent did not only run tests: it accumulated a testing stack spanning pipeline checks, derivation and constraint tests, functional-correctness harnesses, legality scenarios, pairwise interaction probes, runtime-setup tests, stratified screening, tournaments, and Stockfish-anchored calibration.
What the user repeatedly supplied were stronger quality targets such as "make perft pass", "implement full tournament legality", "try pair-wise combinations", or "move to real chess games".

## 3. Testing Strategies Observed in the Sessions

| Strategy | Prompt count | Command count | What it was used for |
| --- | ---: | ---: | --- |
| Pipeline / mining tests | 6 | 69 | Cache-first crawling, deterministic mining, offline reruns, and early pipeline validation. |
| Functional correctness | 20 | 107 | Move-count correctness screening and pass/fail gates before broader experiments. |
| Legality | 9 | 5 | Castling, en passant, repetition, and 50-move-rule behavior under realistic engine use. |
| Interaction probes | 4 | 38 | Checking whether board/search/evaluation combinations genuinely interact as intended. |
| Runtime setup | 8 | 23 | Separating compile-time variability from setup variability such as book and pondering. |
| Strength benchmarking | 36 | 181 | Moving from smoke/correctness checks to tournaments, anchors, and Elo-style calibration. |

## 4. Infrastructure Built in the Repository

| Infrastructure slice | Current files | First added (git) | Examples |
| --- | ---: | --- | --- |
| Pipeline and mining tests | 6 | 2026-03-01T11:23:57+01:00 | `test_fetcher.py`, `test_parser.py`, `test_discovery_resume.py`, ... |
| Derivation and constraint tests | 4 | 2026-03-05T13:43:41+01:00 | `test_constraints.py`, `test_pl_codegen.py`, `test_implementation_mining.py`, ... |
| Perft and legality harnesses | 5 | 2026-03-05T13:43:41+01:00 | `test_c_engine_perft.py`, `test_c_engine_tournament_legality.py`, `uci_perft_check.py`, ... |
| Interaction and probe tooling | 4 | 2026-04-02T19:09:02+02:00 | `board_search_pairwise.py`, `board_search_multi_probe.py`, `eval_feature_assessment.py`, ... |
| Runtime setup and UCI testing | 3 | 2026-04-04T13:17:59+02:00 | `test_c_engine_uci_runtime_features.py`, `test_setup_model.py`, `setup_variant_tournament.py` |
| Tournament and anchor benchmarking | 5 | 2026-04-05T20:04:03+02:00 | `variant_diversity_tournament.py`, `proper_elo_tournament.py`, `sf_anchor_match.py`, ... |

This is important for the paper: the sessions did not stop at a few ad hoc `pytest` calls.
They left behind a reusable infrastructure of tests and experiment scripts that now anchors the SPL engineering workflow.

## 5. Timeline of the Testing Story

### 2026-03-01: pipeline validation appears immediately

- `2026-03-01T07:53:39.400Z`: PLEASE IMPLEMENT THIS PLAN: # CPW Variability Mining Pipeline and SPL Feature Model ## Summary Build a Python CLI pipeline that mines `chessprogramming.org` into: 1. A 2-3 level SPL feature model (~150 features) in FeatureIDE XML + JSON. 2. Full traceability for each feature (URL + snippet + confidence + justification rule). 3. An all-engines vs all-modeled-features tri-state matrix (`SUPPORTED`, `UNSUPPORTED_EXPLIC...
- `2026-03-05T12:50:05.381Z`: pick n=3 random chess variants and organize a small tournament among them (check before the perft test)
- Repository effect: mining-pipeline tests for fetching, parsing, discovery resume, matrix building, and offline integration were introduced from the start.

### 2026-03-05: the user turns testing into a gate for executable variants

- `2026-03-05T08:26:38.386Z`: can we envision to derive one variant, and to make perft pass?
- `2026-03-05T08:31:55.230Z`: can you try 5 random configurations/variants, make the perft, and report results on a CSV-like format, where each row is a variant, and features are both features of the variant/chess engine, and then computed results at depth1, 2, 3, 4, and whether it passes or not... time it takes is also interesting
- `2026-03-05T08:44:22.323Z`: why are variants not passing?
- `2026-03-05T10:03:27.276Z`: can we try perft depth=5? and re-run bench...
- Repository effect: `test_c_engine_perft.py`, `test_c_engine_tournament_legality.py`, `test_constraints.py`, `test_pl_codegen.py`, `uci_perft_check.py`, `uci_legality_scenarios.py`, and `perft_random_variants.py` were added around this stage.

### 2026-04-02 to 2026-04-04: testing shifts from isolated variants to interactions and setup

- `2026-04-02T12:33:52.656Z`: please go with Phase 1... but assess quickly that your modularization pays off and that features can be combined
- `2026-04-02T17:01:44.903Z`: a natural challenge is to handle properly feature interactions and how features combined... specifically here, after Phase 1 and Phase 2, we can combine different board representations with different search strategies, but is it really the case? try to test pair-wise combinations
- `2026-04-04T11:55:37.149Z`: please elaborate a feature model for modeling variability of "setup"... and then design a recommended setup table per variant, and ideally per feature...
- `2026-04-04T12:33:57.075Z`: please add a setup section in the main README.md organize a tournament with N=3 (variant, setup), where setup is the best given a variant... and the N=3 variants cover supposedly best, supposedly worst, and a random variant (but best setup)
- Repository effect: `board_search_pairwise.py`, `board_search_multi_probe.py`, `eval_feature_assessment.py`, `eval_subfeature_probes.py`, `test_c_engine_uci_runtime_features.py`, `test_setup_model.py`, and `setup_variant_tournament.py` appeared in this phase.

### 2026-04-09 onward: experiments become family-level evidence

- Repository effect: `stratified_variant_experiment.py`, `variant_diversity_tournament.py`, `proper_elo_tournament.py`, `sf_anchor_match.py`, and `best_variant_elo_assessment.py` support scalable screening and anchored strength assessment.

## 6. What the User Had to Ask For

The user did not micro-design the testing stack, but several decisive interventions changed its direction:

- From compilation to correctness: prompts such as "can we make perft pass?" and "why are variants not passing?" turned testing into a hard gate.
- From correctness to legality: "implement full tournament legality" pushed the infrastructure toward castling, en passant, repetition, and 50-move behavior.
- From isolated features to combinations: "try to test pair-wise combinations" forced interaction-aware probes.
- From synthetic metrics to chess play: "check the functional correctness in addition to metrics" and then "move to a strength benchmark" redirected the effort toward full games and anchors.
- From superficial variability to semantic honesty: the `CFG_NEGAMAX` criticism showed that even a passing build and some tests can hide cosmetic or partial features.

## 7. Representative Evidence by Strategy

### Pipeline / mining tests

- `2026-03-01T07:53:39.400Z` (engineering): PLEASE IMPLEMENT THIS PLAN: # CPW Variability Mining Pipeline and SPL Feature Model ## Summary Build a Python CLI pipeline that mines `chessprogramming.org` into: 1. A 2-3 level SPL feature model (~150 features) in FeatureIDE XML + JSON. 2. Full traceability for each feature (URL + snippet + confidence + justification rule). 3. An all-engines vs all-modeled-features tri-state matrix (`SUPPORTED`, `UNSUPPORTED_EXPLIC...
- `2026-03-05T12:50:05.381Z` (engineering): pick n=3 random chess variants and organize a small tournament among them (check before the perft test)
- `2026-04-02T17:01:44.903Z` (engineering): a natural challenge is to handle properly feature interactions and how features combined... specifically here, after Phase 1 and Phase 2, we can combine different board representations with different search strategies, but is it really the case? try to test pair-wise combinations

### Functional correctness

- `2026-03-05T08:26:38.386Z` (engineering): can we envision to derive one variant, and to make perft pass?
- `2026-03-05T08:31:55.230Z` (engineering): can you try 5 random configurations/variants, make the perft, and report results on a CSV-like format, where each row is a variant, and features are both features of the variant/chess engine, and then computed results at depth1, 2, 3, 4, and whether it passes or not... time it takes is also interesting
- `2026-03-05T08:44:22.323Z` (engineering): why are variants not passing?

### Legality

- `2026-03-04T23:39:27.297Z` (engineering): implement full tournament legality” (castling/en-passant/repetition/50-move) and then map additional CPW features on top
- `2026-03-05T10:38:02.027Z` (engineering): can you generate n=5 random chess engines without Castling feature?
- `2026-03-05T17:25:07.749Z` (engineering): investigate why there are illegal moves in these variants

### Interaction probes

- `2026-04-02T12:33:52.656Z` (engineering): please go with Phase 1... but assess quickly that your modularization pays off and that features can be combined
- `2026-04-02T17:01:44.903Z` (engineering): a natural challenge is to handle properly feature interactions and how features combined... specifically here, after Phase 1 and Phase 2, we can combine different board representations with different search strategies, but is it really the case? try to test pair-wise combinations
- `2026-04-09T20:42:46.250Z` (paper): Main result: 104/104 variants passed UCI smoke, perft, and all legality probes (416/416 probe checks passed). The perft spread is large: min 0.191s, median 0.237s, max 35.738s. Feature count explains almost none of it (r ≈ 0.084), so the interesting variation is in specific architectural combinations, not just “more features”. Useful plots: Perft vs feature count (see /Users/mathieuacher/SANDBOX/chessprogramming-vm/...

### Runtime setup

- `2026-04-04T11:55:37.149Z` (engineering): please elaborate a feature model for modeling variability of "setup"... and then design a recommended setup table per variant, and ideally per feature...
- `2026-04-04T12:33:57.075Z` (engineering): please add a setup section in the main README.md organize a tournament with N=3 (variant, setup), where setup is the best given a variant... and the N=3 variants cover supposedly best, supposedly worst, and a random variant (but best setup)
- `2026-04-05T06:15:07.918Z` (engineering): can you organize a relatistic tournament between Stockfish at ~2500 Elo and best supposedly variant (including best setup with high depth)? I'd like to know the current potential of the best SPL variant

### Strength benchmarking

- `2026-03-01T07:53:39.400Z` (engineering): PLEASE IMPLEMENT THIS PLAN: # CPW Variability Mining Pipeline and SPL Feature Model ## Summary Build a Python CLI pipeline that mines `chessprogramming.org` into: 1. A 2-3 level SPL feature model (~150 features) in FeatureIDE XML + JSON. 2. Full traceability for each feature (URL + snippet + confidence + justification rule). 3. An all-engines vs all-modeled-features tri-state matrix (`SUPPORTED`, `UNSUPPORTED_EXPLIC...
- `2026-03-04T23:39:27.297Z` (engineering): implement full tournament legality” (castling/en-passant/repetition/50-move) and then map additional CPW features on top
- `2026-03-05T12:50:05.381Z` (engineering): pick n=3 random chess variants and organize a small tournament among them (check before the perft test)

## 8. Interpretation for the Paper

A stronger Section 3 can now say, with evidence, that the agent built more than code for a few variants:

- it progressively assembled a layered validation infrastructure;
- the strategy evolved from offline pipeline tests to executable-variant gates, then to interaction probes, setup testing, and finally family-level tournaments;
- user supervision mostly operated through quality gates and conceptual corrections rather than test-file micromanagement;
- the difficult point is not whether the agent can produce tests at all, but whether the resulting tests are strong enough to reveal shallow or partially implemented features.

This is exactly the nuance worth making explicit in the paper: the coding agent can build a surprising amount of testing infrastructure on its own, but the user still had to decide what counted as convincing evidence for an SPL feature.
