# Testing Infrastructure Report

This report complements the paper with a testing-focused reconstruction of the endeavor.
Its goal is to document, for the record, what the coding agent actually built in terms of validation and benchmarking infrastructure, how the strategy evolved over time, and what kind of user supervision was required.

It builds on:

- [testing_story_report.md](/Users/mathieuacher/SANDBOX/chessprogramming-vm/paper/data/testing_story_report.md)
- [session_story_report.md](/Users/mathieuacher/SANDBOX/chessprogramming-vm/paper/data/session_story_report.md)
- [session_evidence_report.md](/Users/mathieuacher/SANDBOX/chessprogramming-vm/paper/data/session_evidence_report.md)
- the local Codex rollouts in `~/.codex/sessions/...`
- the current repository state, including `tests/`, `scripts/`, and `outputs/`

## 1. Executive Summary

The main result of the re-analysis is that testing was not merely used to check the final artifact.
It became one of the main ways of steering the SPL engineering process.

Three points are especially clear.

1. The coding agent did build substantial testing and benchmarking infrastructure on its own.
   The repository now contains `35` collected tests, plus dedicated Python scripts for perft-oriented screening, legality scenarios, pairwise interaction probes, runtime setup evaluation, stratified family sampling, tournaments, and Stockfish-anchor matches.

2. The user did not micro-manage this infrastructure file by file.
   Across the engineering and experiment work, `46` prompts are testing-related, but only `3` look broadly micromanagement-like.
   The supervision was mostly strategic: set stronger quality gates, reject weak evidence, and redirect the work when the current tests were not convincing enough.

3. The testing strategy matured in layers.
   It started with pipeline tests for offline CPW mining, then moved to derivation checks, functional correctness, legality, interaction probes, runtime setup, and finally family-level tournaments and anchored strength assessment.

## 2. Core Numbers

- Relevant testing-bearing threads: `3`
- Testing-related prompts in engineering + experiment threads: `46`
- Testing/benchmarking command invocations matched in the sessions: `342`
- Broadly micromanagement-like testing prompts: `3 / 46`
- Current collected test cases in the repository: `35`

Strategy counts extracted from the sessions:

| Strategy | Prompt count | Command count | Main role |
| --- | ---: | ---: | --- |
| Pipeline / mining tests | 6 | 69 | Validate cache-first crawling, parsing, matrix generation, and offline reruns |
| Functional correctness | 20 | 107 | Turn derivation into a pass/fail gate using move-tree counting checks |
| Legality | 9 | 5 | Validate castling, en passant, repetition, and 50-move behavior |
| Interaction probes | 4 | 38 | Check whether combinations of features really interact as intended |
| Runtime setup | 8 | 23 | Separate `(variant, setup)` concerns from compile-time variability |
| Strength benchmarking | 36 | 181 | Compare variants through tournaments, anchors, and Elo-style calibration |

## 3. What the User Asked For

The testing stack was not specified upfront in detail.
What the user repeatedly asked for were stronger forms of evidence.

Key examples from the sessions:

- `2026-03-05T08:26:38Z`: derive one variant and make the standard move-tree counting correctness check pass
- `2026-03-05T08:31:55Z`: try 5 random configurations, report features and correctness results in a CSV-like format
- `2026-03-04T23:39:27Z`: implement full tournament legality, including castling, en passant, repetition, and the 50-move rule
- `2026-04-02T17:01:44Z`: test whether board representations and search strategies can really be combined pairwise
- `2026-04-04T11:55:37Z`: model setup variability and recommend setups per variant
- `2026-04-09T19:41:00Z`: check functional correctness in addition to metrics, then move to large-scale sampling and chess-game experiments

The supervision pattern is important:

- the user mostly asked for better gates, not for particular test-file structures
- the user repeatedly challenged insufficient evidence
- the user stepped in when tests passed while the underlying feature was still conceptually wrong, as in the `CFG_NEGAMAX` cosmetic-feature episode

## 4. What the Coding Agent Built

The current repository shows that the agent accumulated several layers of validation infrastructure.

### 4.1 Pipeline and Mining Tests

First added in git on `2026-03-01T11:23:57+01:00`.

Files:

- `tests/test_fetcher.py`
- `tests/test_parser.py`
- `tests/test_discovery_resume.py`
- `tests/test_feature_miner.py`
- `tests/test_matrix_builder.py`
- `tests/test_integration_pipeline.py`

Purpose:

- validate cache and manifest integrity
- validate parsing and extraction
- validate resumable discovery
- validate canonicalization and noise filtering
- validate tri-state matrix generation
- validate offline end-to-end pipeline behavior

Why it matters:

- the project started from a local CPW snapshot, not from an existing chess engine
- therefore testing infrastructure had to cover the knowledge-mining pipeline itself, not only the later C SPL

### 4.2 Derivation and Constraint Tests

First added in git on `2026-03-05T13:43:41+01:00`.

Files:

- `tests/test_constraints.py`
- `tests/test_pl_codegen.py`
- `tests/test_implementation_mining.py`
- `tests/test_c_engine_feature_coverage.py`

Purpose:

- validate executable cross-tree constraints
- validate derivation and generated headers/manifests
- validate implementation-oriented modeling decisions
- validate that modeled options correspond to implementation guards

Why it matters:

- these tests sit at the SPL boundary itself
- they do not test one variant only; they test whether the family mechanism is coherent

### 4.3 Functional Correctness and Legality Harnesses

First added in git on `2026-03-05T13:43:41+01:00`.

Files:

- `tests/test_c_engine_perft.py`
- `tests/test_c_engine_tournament_legality.py`
- `scripts/uci_perft_check.py`
- `scripts/uci_legality_scenarios.py`
- `scripts/perft_random_variants.py`

Purpose:

- compile derived engines and check reference move-tree counts
- validate chess-rule behavior under castling, en passant, and repetition scenarios
- screen random variants for pass/fail behavior rather than trusting compilation alone

Why it matters:

- this is the stage where “derivable configuration” became “candidate product”
- it also marks the point where the user clearly rejected build success as sufficient evidence

### 4.4 Interaction and Probe Tooling

First added in git on `2026-04-02T19:09:02+02:00`.

Files:

- `scripts/board_search_pairwise.py`
- `scripts/board_search_multi_probe.py`
- `scripts/eval_feature_assessment.py`
- `scripts/eval_subfeature_probes.py`

Purpose:

- test pairwise combinations of board backends and search schemes
- probe multiple positions, not only a single start position
- examine whether promoted evaluation features actually manifest in behavior

Why it matters:

- this layer is particularly SPL-specific
- it targets feature interaction rather than isolated feature existence

### 4.5 Runtime Setup and UCI Testing

First added in git on `2026-04-04T13:17:59+02:00`.

Files:

- `tests/test_c_engine_uci_runtime_features.py`
- `tests/test_setup_model.py`
- `scripts/setup_variant_tournament.py`

Purpose:

- validate runtime features such as opening book and pondering
- validate the setup variability model and setup recommendations
- compare `(variant, setup)` combinations rather than only compile-time variants

Why it matters:

- this is the concrete point where the work moved toward deep variability
- it also made the compile-time vs runtime distinction operational

### 4.6 Family-Level Tournament and Anchor Benchmarking

First added in git on `2026-04-05T20:04:03+02:00` and extended later.

Files:

- `scripts/variant_diversity_tournament.py`
- `scripts/proper_elo_tournament.py`
- `scripts/sf_anchor_match.py`
- `scripts/stratified_variant_experiment.py`
- `scripts/best_variant_elo_assessment.py`

Purpose:

- sample many legal variants
- screen them for correctness before match play
- run round-robin tournaments among variants
- calibrate selected variants against weakened Stockfish anchors

Why it matters:

- the validation target is no longer “does it compile and pass a local check?”
- it becomes “does the family exhibit robust and diverse behavior under realistic comparison?”

## 5. Maturation of the Testing Strategy

The testing strategy did not appear fully formed.
It matured in recognizable phases.

### Phase A. Validate the CPW pipeline itself

At the beginning, the main testing problem was reproducible acquisition and extraction from a cache-first CPW snapshot.
This led naturally to pipeline tests, parser tests, discovery-resume tests, and offline integration tests.

### Phase B. Turn derivation into a hard product gate

Once the C SPL appeared, the main concern became:

- can a valid configuration really be derived?
- does the engine compile?
- do correctness counts pass?
- are the added constraints justified?

This is when perft-oriented checks and legality harnesses became central.

### Phase C. Move from isolated variants to combinations

After modularization and feature strengthening, the concern shifted toward:

- are combined board/search variants actually meaningful?
- do evaluation subfeatures change observable behavior?
- can runtime setup be treated as a second variability layer?

This produced pairwise probes, multi-position probes, and setup-aware tournaments.

### Phase D. Move from gates to evidence of family diversity

In the last phase, validation shifted again:

- from local pass/fail checks
- to large-scale screening
- to family-level comparison
- to anchored strength estimation

This is where the experiments described in the paper emerged.

## 6. Why This Counts as Agent-Built Infrastructure

The key claim is not that the user never mentioned testing.
The user mentioned it often, and decisively.
The claim is more specific:

- the user mostly defined the *goal of evidence*
- the coding agent mostly materialized the *shape of the infrastructure*

Evidence supporting this interpretation:

- only `3 / 46` testing-related prompts look broadly micromanagement-like
- the repository contains a diverse test and script ecosystem rather than one monolithic benchmark
- the infrastructure spans Python-pipeline tests, C harness compilation, UCI protocol checks, scenario runners, and tournament orchestration

So the agent was not merely following a single pre-written test plan.
It was repeatedly extending the validation stack in response to higher-level criticism and stronger gates.

## 7. Where Supervision Was Still Necessary

The sessions also show clear limits.

### 7.1 Tests did not automatically guarantee feature honesty

The `CFG_NEGAMAX` episode is the clearest example.
A feature could appear selectable, variants could compile, and some checks could still pass, while the feature was only cosmetic.

This means:

- testing infrastructure is necessary
- but current testing still misses some forms of partial or dishonest implementation

### 7.2 The user had to define what counted as convincing evidence

Examples:

- compilation was not enough
- move-tree correctness was not enough
- legality was not enough
- even tournament participation was not enough when the underlying feature was suspicious

This is a crucial point for the paper.
The coding agent can build a lot of validation machinery, but the human still decides which evidence threshold is acceptable for SPL engineering.

### 7.3 The transition from metrics to chess-play evidence had to be explicitly requested

The agent did build benchmark scripts and tournament tooling, but the move toward stronger, more realistic evidence happened because the user pushed:

- “check correctness in addition to metrics”
- “move to real chess games”
- “add anchors”

So autonomy remains limited in experiment design and in recognizing when a current benchmark is too weak.

## 8. Current Validation Inventory

Current test collection from `pytest --collect-only -q`:

- pipeline/mining/integration tests: `11`
- derivation/constraint/model tests: `13`
- engine correctness/legality/runtime/setup tests: `11`

Representative high-value tests:

- `test_run_all_offline_cache_only`
- `test_move_generation_is_mandatory_for_executable_variants`
- `test_startpos_perft_reference_counts`
- `test_tournament_legality_behaviors`
- `test_external_book_file_controls_bestmove`
- `test_go_ponder_runs_asynchronously_until_ponderhit`
- `test_setup_feature_model_structure`

Representative high-value scripts:

- `uci_perft_check.py`
- `uci_legality_scenarios.py`
- `board_search_pairwise.py`
- `board_search_multi_probe.py`
- `setup_variant_tournament.py`
- `stratified_variant_experiment.py`
- `variant_diversity_tournament.py`
- `sf_anchor_match.py`

## 9. Implications for the Paper

The paper can now support the following claims more concretely.

1. The coding agent did not only implement features; it also helped build a non-trivial validation infrastructure.

2. Testing matured from pipeline validation to executable-variant gates, then to interaction-aware probing and family-level benchmarking.

3. User supervision was mostly strategic and evidence-oriented rather than line-by-line.

4. The main unresolved challenge is no longer “can the agent write tests at all?” but “can the resulting tests reveal partial, shallow, or cosmetic features early enough?”

## 10. Open Questions

- How can suspicious features be identified earlier, before they survive multiple validation layers?
- Which feature-review process should complement automated tests in an agent-supported SPL?
- How much stronger should performance and match-play evaluation become before a feature is trusted?
- Can the same testing maturity be obtained with weaker or open-weight coding agents?
- How far can the chess-engine SPL be pushed in Elo once NNUE-style evaluation and tuning layers are added?
