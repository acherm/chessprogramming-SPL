# Session Evidence Report

This report complements the paper draft with a more explicit audit trail derived from:

- `scripts/analyze_codex_rollout.py`
- `scripts/analyze_repo_history.py`
- the local Codex rollout transcript stored in `~/.codex/sessions/...019ca85a-6373-7353-a31f-d6fd652de95e.jsonl`
- repository artifacts under `outputs/`

It focuses on three questions:

1. Which SPL activities were actually carried out?
2. Which software-engineering activities were necessary to support them?
3. What were the main difficulties revealed by the sessions?

## 1. Dataset Overview

- Main engineering thread: `019ca85a-6373-7353-a31f-d6fd652de95e`
- Active period: `2026-03-01` to `2026-04-06`
- Active days: `8`
- User prompts: `98`
- Assistant commentary/final messages: `913`
- `exec_command` calls: `1,699`
- `write_stdin` polls: `400`
- Command-family breakdown:
  - exploration: `825`
  - build/run: `384`
  - testing: `206`
  - benchmarking: `131`
  - versioning: `88`
  - process management: `44`

Repository state summarized from the current branch:

- commits in the storyline: `12`
- cached CPW pages: `1,316`
- modeled features: `74`
- engine-feature matrix rows: `242`
- setup recommendations by variant: `17`
- collected tests: `35`
- variant configs: `18`

## 2. High-Level Timeline

The sessions show four major phases.

### Phase A. CPW Mining and Feature Modeling (`2026-03-01`)

Main prompts:

- `2026-03-01T07:47:17Z`: build a feature model from `chessprogramming.org`, with traceability, caching, and an engine-feature comparison table
- `2026-03-01T10:33:31Z`: revise a noisy initial `FeatureIDE` model containing years, people, and navigation items
- `2026-03-01T14:52:07Z`: add explicit cross-tree constraints and expand the crawl

Representative commit evidence:

- `3ffe70a` `Add CPW variability mining pipeline with safe resumable crawling`
- `2f957dd` `Improve feature mining precision with core anchors and strict noise filtering`

Interpretation:

- This is classic domain analysis plus feature modeling.
- The agent did not only scrape pages; it had to bootstrap a full offline-first mining pipeline with cache, parser, model builder, exporters, and tests.
- The strongest supervision need appeared here: distinguishing true variation points from generic CPW content.

### Phase B. Executable SPL Construction and Legality (`2026-03-04` to `2026-03-05`)

Main prompts:

- `2026-03-04T23:07:15Z`: implement a family of chess engines in C from the extracted feature model
- `2026-03-04T23:19:25Z`: require a real implementation of each feature
- `2026-03-04T23:39:27Z`: implement full tournament legality
- `2026-03-05T08:26:38Z`: derive a variant and make perft pass

Representative commit evidence:

- `932eb04` `Enforce executable variant constraints and add perft benchmarking workflows`

Interpretation:

- This phase turns descriptive variability into executable variability.
- The sessions moved from “feature model as concept map” to “variant derivation, compilation, legality, and perft.”
- The user repeatedly rejected cosmetic variability, forcing the product line to map options to actual code paths.

### Phase C. Refactoring, Interactions, and Deep Variability (`2026-04-02` to `2026-04-04`)

Main prompts:

- `2026-04-02T12:29:39Z`: many features are not fully implemented; design a plan to truly implement them and their combinations
- `2026-04-02T17:01:44Z`: explicitly test interactions between board representations and search strategies
- `2026-04-03T12:20:47Z`: promote evaluation subfeatures to first-class options
- `2026-04-04T11:55:37Z`: elaborate a feature model for setup variability and recommend setups per variant

Representative commit evidence:

- `bbb79ca` `Modularize engine variation points and document feature interactions`
- `748f796` `Promote evaluation leaves into hierarchical groups`
- `bedf3d1` `Implement real engine feature backends and runtime book/pondering`
- `c5c01a2` `Add setup variability model and setup-based tournament tooling`
- `7b1682d` `Add controlled tournament artifacts and setup comparison`

Interpretation:

- This is the phase where the work became recognizably SPL-oriented “by the book”.
- It covers modularization, interaction testing, hierarchical model refinement, and deep variability via `(variant, setup)`.
- It also shows an important conceptual move: separating compile-time engine variability from runtime/harness variability.

### Phase D. Commonality Optimization and Anchored Assessment (`2026-04-05` to `2026-04-06`)

Main prompts:

- `2026-04-05T11:41:59Z`: search efficiency seems to be the dominant issue; is this in commonality space?
- `2026-04-05T11:51:26Z`: remove the depth-5 limitation at `2s/move`
- `2026-04-05T17:39:21Z`: add king-square caching, checker/pin awareness, and TT observability
- `2026-04-05T22:21:01Z`: run a larger 20-game match against Stockfish ~2500
- `2026-04-05T23:29:01Z`: commit the 20-game artifacts and rerun against a stronger anchor

Representative commit evidence:

- `0a72c9b` `Optimize common search path and document anchor assessment`
- `2aaf95e` `Add 20-game 2500 anchor match artifacts`

Interpretation:

- This phase is not about adding new features.
- The sessions explicitly identify a commonality space: time management, TT quality, legality fast paths, and other shared infrastructure.
- This is a critical SPL observation: strength improvements may belong outside the feature model while still benefiting many variants.

## 3. Lifecycle Evidence Matrix

| Activity | Transcript evidence | Artifact evidence | Main difficulty |
| --- | --- | --- | --- |
| Domain analysis and feature modeling | initial CPW-mining prompts; 10 prompts categorized as feature-modeling | `outputs/feature_model.featureide.xml`, `outputs/feature_model.json`, `outputs/feature_traces.csv` | CPW pages are noisy and not all named entities are features |
| Feature-model repair and constraints | repeated review of the initial `FeatureIDE` export; “add the obvious constraint” prompts | executable constraints in model JSON and derivation logic | conceptual validity lagged behind extraction |
| Product-line implementation | prompts to “implement a family of chess engines in C” and to ensure each feature is real | `c_engine_pl/`, `scripts/derive_variant.py`, `tests/test_pl_codegen.py` | cosmetic variability had to be rejected |
| Interaction testing and legality | prompts about perft failures, legality, and board-representation/search combinations | 35 tests, perft datasets, legality-oriented test cases | arbitrary combinations were initially unsafe |
| Benchmarking and comparison | 11 benchmarking/comparison prompts; escalation to anchored matches | tournament CSVs, Elo summaries, anchor-match artifacts | fair comparison depends on protocol and setup choices |
| Commonality-space evolution | prompts on search efficiency, TT quality, king-square caching, and removing shallow-depth bottlenecks | commonality optimization commits and benchmark deltas | performance gains do not map cleanly to “features” |
| Deep variability and setup | prompt to model setup variability and recommend setups per variant | `outputs/setup_feature_model.json`, setup recommendation CSVs | compile-time and runtime variability had to be separated |

## 4. Key SPL Activities Observed

### 4.1 Domain Analysis and Feature Modeling

Evidence:

- 10 prompts were categorized as feature-modeling requests.
- The initial prompt already asked for traceability, justification, caching, and a comparison matrix.
- The user performed manual review of a first `FeatureIDE` export and forced a major narrowing of scope.

Outputs:

- `outputs/feature_model.featureide.xml`
- `outputs/feature_model.json`
- `outputs/feature_traces.csv`
- `outputs/engine_feature_matrix.csv`

Important observation:

- The sessions show that CPW is not directly a feature model.
- Human supervision was essential to turn “anything named on the wiki” into “implementation-backed variability.”

### 4.2 Derivation and Product-Line Implementation

Evidence:

- prompts explicitly asked to derive variants, compile them, and make perft pass
- executable constraints were added after repeated failures
- the product line was implemented in C with preprocessor-based derivation

Outputs:

- `c_engine_pl/`
- `scripts/derive_variant.py`
- `tests/test_pl_codegen.py`

Important observation:

- The thread shows a shift from conceptual SPL artifacts to actual software product derivation.
- This is stronger evidence than a model-only study.

### 4.3 Testing and Validation

Evidence:

- 7 prompts were categorized as testing/validation
- the user repeatedly asked why variants did not pass
- illegal moves were explicitly investigated

Outputs:

- 35 collected tests
- multiple perft datasets such as `outputs/perft_random_variants_depth6.csv`
- legality- and runtime-feature tests in `tests/`

Important observation:

- testing was not an afterthought; it was used to decide which combinations counted as legitimate products
- perft served both as correctness oracle and as diversity probe

### 4.4 Benchmarking and Variant Comparison

Evidence:

- 11 prompts were categorized as benchmarking/comparison
- the user progressively escalated from random mini-tournaments to anchored Elo assessment and 20-game Stockfish matches

Outputs:

- controlled equal-condition tournament: best/random/worst variants score `87.5% / 56.2% / 6.2%`
- anchored Elo estimates: top two variants around `1421.5` and `1099.5`
- 20-game Stockfish anchor scores:
  - `65.0%` vs `2500`
  - `30.0%` vs `2700`

Important observation:

- benchmarking itself became part of the SPL lifecycle, not only a post-hoc evaluation.
- The sessions repeatedly negotiated fairness: equal-condition tournaments vs best-setup-per-variant evaluations.

### 4.5 Deep Variability

Evidence:

- explicit prompt to model “setup” variability
- recommendation tables generated per variant and per feature

Outputs:

- `outputs/setup_feature_model.json`
- `outputs/setup_recommendations_by_variant.csv`
- `outputs/setup_recommendations_by_feature.csv`

Important observation:

- The sessions evolve from “a feature model of engines” to “a feature model of engines plus setup”.
- This is a strong example of revisiting SPL concepts with agent support.

## 5. Key Software-Engineering Activities Observed

### 5.1 Bootstrapping from an Empty Workspace

The first rollout messages show an empty repository.
The agent had to create project structure, CLI, tests, data directories, and exporters from scratch.

### 5.2 Offline-First, Resume-Safe Data Engineering

The user explicitly asked to avoid acting like an aggressive scraper.
This led to:

- cache-first fetching
- resumable discovery state
- offline-friendly runs
- clear failure modes when cache entries are missing

This is a substantial software-engineering task independent of SPL theory.

### 5.3 Experiment Automation

A large part of the transcript is about scripts and harnesses:

- perft sweeps
- variant derivation
- cutechess tournaments
- anchored matches
- summary/CSV generation

This automation work made the SPL evaluable in practice.

### 5.4 Architecture Refactoring

The implementation moved toward explicit variation points:

- search module
- board backend module
- evaluation module
- runtime feature hooks in UCI

This is a software-architecture task, not just code generation.

## 6. Main Difficulties Revealed by the Sessions

### Difficulty 1. CPW Is Noisy as a Variability Source

Strong evidence:

- the initial mined model included `1995[edit]`, `Main Page`, `Robert Hyatt`, and `References[edit]`
- the user explicitly called this out and demanded a drastic revision

Implication:

- agent autonomy is not enough here; conceptual supervision is necessary
- domain analysis from a wiki is fragile without strong filtering rules

### Difficulty 2. “Feature Exists” vs “Feature Is Real”

Strong evidence:

- the prompt from `2026-04-02T12:29:39Z` explicitly notes that some features only affected strings or labels
- the concrete extreme case was `CFG_NEGAMAX`, which at one point only selected the string `Negamax` in a variant summary `snprintf(...)` without changing the search behavior
- the user then required a significant plan to truly implement features and combinations

Implication:

- coding agents can easily create the appearance of variability before creating real variability
- more bluntly, they may stop at the shallowest feature implementation that compiles or passes superficial checks unless a human challenges semantic honesty
- implementation-backed criteria are essential

### Difficulty 3. Constraints Were Initially Incomplete

Strong evidence:

- several prompts asked why variants were not passing perft
- the user then requested “the obvious constraint”
- executable constraints were added and documented

Implication:

- deriving arbitrary combinations from a mined model is unsafe without a second pass that encodes implementation constraints

### Difficulty 4. Legality and Search Correctness Are Hard

Strong evidence:

- tournament legality was explicitly requested
- illegal moves were investigated later during benchmarking
- dedicated legality behavior tests were added

Implication:

- agent-generated product lines can reach compilation quickly, but chess legality exposes deeper correctness demands

### Difficulty 5. Feature vs Commonality vs Setup Is Conceptually Slippery

Strong evidence:

- multiple prompts debate whether SEE, move ordering, TT quality, or time management are true features
- setup variability is introduced only after tournament fairness concerns appear

Implication:

- the main hard problem became conceptual modeling, not code syntax
- the agent benefitted from human correction when deciding what belongs in the feature model

### Difficulty 6. Benchmarking Protocols Can Mislead

Strong evidence:

- the sessions moved from depth-limited tournaments to setup-aware comparisons and finally anchored matches
- even after commonality optimization increased search depth and NPS, match outcomes did not always improve in the expected way

Implication:

- stronger engineering signals (depth, NPS) do not automatically translate into stronger chess results
- evaluation design is part of the engineering problem

## 7. Takeaways for the Paper

The sessions support four main claims in the paper:

1. Coding agents can cover multiple SPL lifecycle activities in one sustained endeavor, not only isolated subtasks.
2. CPW is a valuable but noisy source of variability knowledge.
3. Human supervision is most needed for conceptual alignment: feature scope, honesty of implementation, and evaluation fairness.
4. The endeavor is pedagogically interesting because it revisits canonical SPL activities—domain analysis, modeling, derivation, testing, benchmarking, and evolution—with a new kind of assistant.

## 8. Suggested Next Evidence Extensions

If stronger evidence is needed for a camera-ready version, the most useful additions would be:

- a larger random-variant study with stratified sampling by feature family
- a controlled ablation study separating feature and commonality effects
- a second-agent replication of the same CPW-to-SPL protocol
- a short qualitative coding of assistant failures and correction loops
