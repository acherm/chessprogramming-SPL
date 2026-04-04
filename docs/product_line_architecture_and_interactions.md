# Product-Line Architecture and Feature Interactions

This note documents the current implementation-backed chess engine product line after Phase 1, Phase 2, and Phase 3.

It is intentionally narrower than the mined CPW feature model. The CPW model is broader and descriptive; this document describes the subset that is actually realized as executable variation points in the C engine.

Related notes:

- `docs/feature_taxonomy_and_strengthening_roadmap.md`
- `docs/variant_constraints_and_perft.md`
- `outputs/phase1_search_assessment/report.md`
- `outputs/phase2_board_assessment/report.md`
- `outputs/phase2_pairwise_interactions/report.md`
- `outputs/phase2_multi_probe_suite/report.md`
- `outputs/phase3_eval_assessment/report.md`
- `outputs/phase3_eval_subfeature_probes/report.md`

## 1. Scope

The key design objective is honesty:

- a feature should not only change labels or metadata;
- enabling a feature should select a concrete implementation path;
- combinations of features should compile into real engine variants;
- those variants should remain legality-correct, at least as checked by perft and UCI smoke behavior.

The work completed so far covers three major variation families:

- Phase 1: search architecture
- Phase 2: board representation architecture
- Phase 3: evaluation architecture

This means the current implementation profile already supports meaningful combinations of:

- search core and search refinements
- board representation backend
- evaluation presets and evaluation terms

but does not yet give the same level of modular honesty to all time-management, opening, tuning, and protocol-adjacent features.

## 2. Executable Profile vs. Mined Model

The mined CPW model contains many features that are useful for software product-line analysis, but not all of them are currently backed by a dedicated implementation in the engine.

The executable derivation profile is enforced by:

- `src/cpw_variability/pl_codegen.py`
- `src/cpw_variability/constraints.py`

Important consequences:

- exactly one primary board representation must be selected;
- exactly one primary search core must be selected:
  - `Minimax`
  - `Negamax`
- `Move Generation` is mandatory for executable engine variants;
- tournament-legality features are enforced by default:
  - `Castling`
  - `En Passant`
  - `Threefold Repetition`
  - `Fifty-Move Rule`
- several cross-tree constraints are enforced, for example:
  - `Principal Variation Search -> Alpha-Beta`
  - `Hash Move -> Transposition Table`
  - `Legal Move Generation -> Move Generation`
  - `Magic Bitboards -> Bitboards`
  - `Minimax excludes Negamax`
  - board encodings exclude one another
- legacy coarse config tokens are still accepted for compatibility:
  - `Pawn Structure` expands to `Passed Pawn + Isolated Pawn + Doubled Pawn + Connected Pawn`
  - `King Safety` expands to `King Pressure + King Shelter`

This separation matters because the mined feature model is a conceptual space, while the executable profile is a derivable implementation space.

It also matters because not everything that improves engine strength should be modeled as a configurable feature. The current executable taxonomy distinguishes:

- configurable features: selectable variation points such as `Null Move Pruning`, `Hash Move`, `Bishop Pair`, `Bitboards`
- commonality: shared infrastructure and quality improvements such as time-allocation policy, TT replacement quality, or move-ordering plumbing
- feature implementation debt: cases where the feature exists in the model, but the implementation is still partial or naive

Recent commonality work landed in this layer rather than in the feature model:

- UCI clock allocation now uses `movestogo`, reserve, and increment-aware budgeting
- search uses soft/hard time cutoffs instead of a single naive deadline
- TT uses bucketed replacement, generation aging, and mate-score normalization

Depth convention in the current builder:

- `depth=3`: executable flat option catalog
- `depth=4`: adds intermediate groups such as `Pawn Structure`, `Piece Coordination`, `King Terms`, `Ordering Heuristics`, and `TT Support`
- `depth=5`: adds the compile/runtime binding layer below executable leaves

## 3. Architecture After Phase 1, Phase 2, and Phase 3

### 3.1 Search Variation Point

Phase 1 moved search orchestration out of the monolithic engine body:

- `c_engine_pl/include/engine_search_internal.h`
- `c_engine_pl/src/search.c`

`c_engine_pl/src/engine.c` now exposes search-facing primitives through an internal operations interface. Search no longer depends on a single hard-coded recursive routine hidden inside `engine.c`.

This makes the following search features real:

- `Minimax`
- `Negamax`
- `Alpha-Beta`
- `Principal Variation Search`
- `Iterative Deepening`

Search refinements are still layered on top of that stack, including:

- `Quiescence Search`
- `Move Ordering`
- `Ordering Heuristics`
  - `Hash Move`
  - `Killer Heuristic`
  - `History Heuristic`
- `Hash Move`
- `Transposition Table`
- `Replacement Schemes`
- `Aspiration Windows`
- `Null Move Pruning`
- `Late Move Reductions`
- `Futility Pruning`
- `Razoring`
- `Delta Pruning`

These are not all equally mature, but they are no longer purely cosmetic toggles. Some of them are feature families with internal subfeatures, while others are still waiting for stronger implementations behind the same feature name.

### 3.2 Board Representation Variation Point

Phase 2 introduced a real backend interface:

- `c_engine_pl/include/engine_backend_internal.h`
- `c_engine_pl/src/board_backend.c`

`EngineState` now stores backend-specific cached state:

- `board_0x88[128]`
- `board_120[120]`
- `bb_pieces[12]`
- `bb_white_occ`
- `bb_black_occ`

See:

- `c_engine_pl/include/engine.h`

The backend module owns:

- synchronization from canonical board state into backend caches;
- backend-specific king lookup;
- backend-specific attack detection;
- backend-specific pseudo-legal move generation;
- backend name reporting.

Implemented board backends:

- `Bitboards`
- `Magic Bitboards`
- `0x88`
- `Mailbox`
- `10x12 Board`

### 3.3 Evaluation Variation Point

Phase 3 extracted evaluation into its own internal module:

- `c_engine_pl/include/engine_eval_internal.h`
- `c_engine_pl/src/eval.c`

The evaluator now owns:

- position evaluation
- capture scoring support for move ordering
- evaluation-table reset hooks
- evaluation profile naming

Evaluation terms are organized as explicit term-level functions instead of remaining buried inside `engine.c`:

- material
- piece-square tables
- pawn structure:
  - doubled pawns
  - isolated pawns
  - connected pawns
  - passed pawns
- piece coordination:
  - bishop pair
  - rook open and semi-open files
- pawn hash table reuse
- mobility
- king safety
- king shelter / pawn shield
- endgame king activity
- tapered-eval finalization
- static exchange evaluation

The important modeling point is that `Static Exchange Evaluation` is treated as a configurable feature, while a stronger SEE implementation is still an implementation-quality improvement to be done underneath that feature.

### 3.4 How the Three Variation Points Compose

The architectural boundary is now:

- search code calls engine operations;
- engine operations delegate move generation and attack logic to the selected board backend;
- engine operations delegate scoring and capture ordering support to the evaluation module;
- legal-move generation still wraps pseudo-legal move generation plus `make_move` / `unmake_move` and in-check validation.

So a search configuration does not need to know whether it is exploring moves from:

- bitboards
- 0x88
- 10x12

It consumes the same engine-level move interface.

That is the core reason why Phase 1, Phase 2, and Phase 3 combinations are possible.

## 3.5 Revised Executable Hierarchy

The executable hierarchy is now intentionally more explicit about feature families:

- `Search`
  - search-core leaves such as `Negamax`, `Alpha-Beta`, `Principal Variation Search`, `Iterative Deepening`
  - `Move Ordering`
    - `Ordering Heuristics`
      - `Hash Move`
      - `Killer Heuristic`
      - `History Heuristic`
- `Transposition Table`
  - `Transposition Table`
  - `TT Support`
    - `Zobrist Hashing`
    - `Replacement Schemes`
    - `Pawn Hash Table`
- `Evaluation`
  - `Pawn Structure`
  - `Piece Coordination`
  - `King Terms`

This structure is meant to reflect implementation-backed variability, not only conceptual similarity.

## 3.6 Feature Completion Pass

The more recent completion pass addressed several previously weak or aliased features.

Completed items:

- `Minimax` is now an explicit selectable search-core feature in the executable model, with a search-core exclusivity rule against `Negamax`
- `Magic Bitboards` is now a real bitboard sub-backend with precomputed magic lookup tables for bishop and rook attacks
- `Mailbox` no longer aliases `10x12 Board`; it has its own 64-square mailbox move-generation path
- `Piece Lists` are now maintained in engine state and used by mailbox, `0x88`, and `10x12` generators for king lookup and piece iteration
- `Opening Book` is now a small position-aware repertoire rather than a single hard-coded first move
- `Opening Book` now reads from an external opening-book file and exposes `OwnBook` / `BookFile` UCI options
- `Pondering` now runs as a background `go ponder` session and responds to `ponderhit` / `stop`

Current caveats:

- the default book format is intentionally simple (`startpos moves ...` lines), not Polyglot or another binary format
- pondering is asynchronous and UCI-visible, but still implemented as repeated background search slices rather than a deeply integrated shared-search continuation model

## 4. What Is Actually Implemented

### 4.1 Implemented Search Family

Backed by dedicated code paths:

- `Minimax`
- `Negamax`
- `Alpha-Beta`
- `Principal Variation Search`
- `Iterative Deepening`

Behavioral evidence:

- `outputs/phase1_search_assessment/search_probe.csv`

Representative result on the fixed probe position:

- `phase1_minimax`: `63,338,044` nodes
- `phase1_minimax_ab`: `80,070` nodes
- `phase1_negamax`: `63,336,631` nodes
- `phase1_negamax_ab`: `80,070` nodes
- `phase1_negamax_ab_pvs_id`: `53,577` nodes

Interpretation:

- `Alpha-Beta` is a real pruning layer;
- `PVS + ID` is a real refinement on top of alpha-beta;
- `Minimax` and `Negamax` remain close on equivalent positions, which is expected.

### 4.2 Implemented Board-Representation Family

Backed by dedicated code paths:

- `Bitboards`
- `Magic Bitboards`
- `0x88`
- `Mailbox`
- `10x12 Board`

Behavioral evidence:

- `outputs/phase2_board_assessment/search_probe.csv`

Representative result with the same search stack:

- `Bitboards`: `93708` nodes, best move `b1c3`
- `0x88`: `161628` nodes, best move `b1c3`
- `10x12`: `161628` nodes, best move `b1c3`

Interpretation:

- board representation changes attack detection and move generation behavior;
- the effect is visible in search node counts and runtime;
- the bitboard backend is already behaviorally distinct, even though it is not yet the fastest backend for perft.
- `Magic Bitboards` and `Mailbox` are now executable variants rather than documentation-only labels.

### 4.3 Implemented Interactions Across Families

The interaction claim is stronger than “both feature families exist separately”.

The cross-product was tested explicitly:

- `3 board backends x 5 search stacks = 15 variants`

Artifacts:

- `outputs/phase2_pairwise_interactions/pairwise_matrix.csv`
- `outputs/phase2_pairwise_interactions/pairwise_matrix.md`
- `outputs/phase2_pairwise_interactions/report.md`
- `scripts/board_search_pairwise.py`

Results:

- `15/15` combinations derived successfully
- `15/15` combinations compiled successfully
- `15/15` combinations passed start-position perft through depth 5

This is the current strongest evidence that the feature combinations are not merely theoretical.

### 4.4 Implemented Evaluation Family

Backed by dedicated code paths in `c_engine_pl/src/eval.c`:

- `Evaluation`
- `Piece-Square Tables`
- `Pawn Hash Table`
- `Mobility`
- `Tapered Eval`
- `Static Exchange Evaluation`
- `Pawn Structure` group
  - `Passed Pawn`
  - `Isolated Pawn`
  - `Doubled Pawn`
  - `Connected Pawn`
- `Piece Coordination` group
  - `Bishop Pair`
  - `Rook on Open File`
  - `Rook Semi-Open File`
- `King Terms` group
  - `King Pressure`
  - `King Shelter`
  - `King Activity`

Behavioral evidence:

- `outputs/phase3_eval_assessment/variant_summary.csv`
- `outputs/phase3_eval_assessment/probe_matrix.csv`
- `outputs/phase3_eval_assessment/report.md`

Representative compiled profiles:

- `eval_bitboards_material_only`: `eval=Material`
- `eval_bitboards_pst`: `eval=Material+PST`
- `eval_bitboards_pst_pawn`: `eval=Material+PST+PassedPawn+IsolatedPawn+DoubledPawn+ConnectedPawn`
- `eval_bitboards_full`: `eval=Material+PST+PassedPawn+IsolatedPawn+DoubledPawn+ConnectedPawn+PawnHash+BishopPair+RookOpen+RookSemiOpen+Mobility+KingPressure+KingShelter+KingActivity+Tapered+SEE`

Representative outcomes on the evaluation probes:

- `knight_activation` on `Bitboards`:
  - `material_only`: `a2b4`, `320`
  - `pst`: `a2c3`, `320`
  - `full`: `a2c3`, `311`
- `passed_pawn_endgame` on all three backends:
  - `material_only`: `e3e4`, `100`
  - `pst`: `e3f3`, `125`
  - `full`: `e3e4`, `135`

This is enough to show that evaluation presets are not labels only: they can alter search scores and, on selected positions, the chosen move.

Additional targeted evidence:

- `outputs/phase3_eval_subfeature_probes/report.md`
- `outputs/phase3_eval_subfeature_probes/probe_matrix.csv`

These probes use the `eval` UCI command to isolate static evaluation before also checking the propagated search decision at depth 3.

The newer leaf-oriented probe suite exercises promoted evaluation leaves directly instead of only umbrella presets:

- `bishop_pair`
- `rook_open_file`
- `rook_semi_open_file`
- `doubled_isolated_pawns`
- `connected_pawns`
- `passed_pawn_endgame`
- `king_shelter`
- `king_activity_endgame`

Representative outcomes:

- `bishop_pair`
  - `material_only`: static `660`, best move `d2e3`
  - `coordination`: static `688`, best move `d2e3`
  - `full`: static `706`, best move `e1f2`
- `connected_pawns`
  - `material_only`: static `200`, best move `c3c4`
  - `pawn_terms`: static `224`, best move `c3c4`
  - `full`: static `238`, best move `d3d4`
- `king_activity_endgame`
  - `material_only`: static `0`, best move `e1e2`
  - `king_terms`: static `-56`, best move `e1e2`
  - `full`: static `-56`, best move `e1e2`

This is the current strongest evidence that the promoted evaluation leaves are individually executable and combine with the strong search stack.

At `depth=4`, the feature tree now reflects that structure explicitly:

- `Evaluation`
  - direct leaves such as `Evaluation`, `Piece-Square Tables`, `Mobility`, `Tapered Eval`, `Static Exchange Evaluation`
  - `Pawn Structure`
    - `Passed Pawn`
    - `Isolated Pawn`
    - `Doubled Pawn`
    - `Connected Pawn`
  - `Piece Coordination`
    - `Bishop Pair`
    - `Rook on Open File`
    - `Rook Semi-Open File`
  - `King Terms`
    - `King Pressure`
    - `King Shelter`
    - `King Activity`

## 5. What the Interaction Matrix Proves

The pairwise matrix is useful for three separate questions.

### 5.1 Are the combinations valid?

Yes.

Every tested combination in the search x board cross-product:

- derived
- compiled
- passed perft depth 5

So the architecture is stable enough to support those combinations.

### 5.2 Do search features actually interact with board backends?

Yes.

For a fixed board backend, changing the search stack changes the probe nodes dramatically.

Example on `Bitboards`:

- `minimax`: `1262354`
- `minimax_ab`: `5265`
- `negamax`: `1262340`
- `negamax_ab`: `5265`
- `negamax_ab_pvs_id`: `5541`

This shows search choices remain active after the board split.

### 5.3 Do board backends actually interact with search features?

Yes, but unevenly.

For a fixed search stack, changing the board backend changes probe nodes and, in some cases, best move.

Example for `negamax_ab_pvs_id`:

- `Bitboards`: `5541`, best move `b2b3`
- `0x88`: `3886`, best move `b1d2`
- `10x12`: `3886`, best move `b1d2`

This proves the search stack is not insulated from backend behavior.

However, the matrix also reveals an important current limitation:

- `0x88` and `10x12 Board` are currently indistinguishable on the chosen probe across all five search stacks.

That does not mean they are fake features:

- they compile through different backend code paths;
- they pass perft;
- they are wired through different internal representations;

but it does mean the current probe is not sufficient to separate them behaviorally, or their move ordering is currently equivalent on that workload.

This is exactly the kind of interaction evidence the matrix is supposed to expose.

## 6. What the Multi-Position Suite Adds

The broader suite in `outputs/phase2_multi_probe_suite/` extends the earlier single fixed probe.

It tests:

- 15 board x search variants
- 5 curated positions
- start-position perft depth 5 for every variant

Results:

- `15/15` variants compiled
- `15/15` variants passed perft depth 5
- `75/75` probe rows completed

Important outcome:

- `Bitboards` diverge from `0x88` / `10x12` on several positions and search stacks
- `0x88` and `10x12 Board` still remain observationally identical across the curated five-position suite

So the broader suite strengthens one conclusion and preserves another:

- board/search composition is real and repeatable across multiple workloads
- `0x88` and `10x12` are still not strongly behaviorally separated by current move ordering

## 7. Known Limitations

The architecture is more honest than before, but it is not complete.

### 7.1 Still Partial or Shared

These areas are still less modular than the search, board, and evaluation families:

- opening-book behavior is now real and file-backed, but the book format is intentionally simple and start-position oriented
- time-management options are not yet modeled as deeply independent strategies
- tuning features are mostly represented at the model/configuration level, not as distinct implementation modules
- pondering now supports asynchronous `go ponder` plus `ponderhit`, but it is still a lightweight runtime subsystem rather than a deeply shared continuation search

### 7.2 Canonical State Still Exists

The engine still keeps `board[64]` as canonical state and treats:

- `board_0x88`
- `board_120`
- bitboards

as synchronized backend caches.

This is a reasonable intermediate architecture, but it is not the same as a fully representation-native engine family where each backend owns the canonical state and move application.

### 7.3 Interaction Coverage Is Still Limited

The current interaction evidence is better than before, but still bounded.

It now tests:

- representative search stacks
- representative board encodings
- representative evaluation presets and promoted evaluation leaves
- a curated five-position board/search suite
- a curated leaf-oriented evaluation suite
- start-position perft

That is enough to validate architectural composition more credibly, but not enough to characterize all interactions or playing strength.

## 8. How to Reproduce

### 8.1 Re-run the pairwise interaction matrix

```bash
PYTHONPATH=src python3 scripts/board_search_pairwise.py --probe-depth 3
```

Outputs:

- `outputs/phase2_pairwise_interactions/pairwise_matrix.csv`
- `outputs/phase2_pairwise_interactions/pairwise_matrix.md`
- `outputs/phase2_pairwise_interactions/report.md`
- `outputs/phase2_pairwise_interactions/summary.json`

### 8.2 Re-run the multi-position board/search suite

```bash
PYTHONPATH=src python3 scripts/board_search_multi_probe.py --probe-depth 3
```

Outputs:

- `outputs/phase2_multi_probe_suite/variant_summary.csv`
- `outputs/phase2_multi_probe_suite/probe_matrix.csv`
- `outputs/phase2_multi_probe_suite/report.md`
- `outputs/phase2_multi_probe_suite/summary.json`

### 8.3 Re-run the Phase 2 board backend comparison

```bash
PYTHONPATH=src python3 scripts/derive_variant.py --config c_engine_pl/variants/phase2_bitboards_ab_pvs_id.json --build
PYTHONPATH=src python3 scripts/uci_perft_check.py --config c_engine_pl/variants/phase2_bitboards_ab_pvs_id.json --max-depth 5
```

Equivalent commands can be run with:

- `c_engine_pl/variants/phase2_0x88_ab_pvs_id.json`
- `c_engine_pl/variants/phase2_10x12_ab_pvs_id.json`

### 8.4 Re-run the Phase 3 evaluation assessment

```bash
PYTHONPATH=src python3 scripts/eval_feature_assessment.py --probe-depth 2
```

Outputs:

- `outputs/phase3_eval_assessment/variant_summary.csv`
- `outputs/phase3_eval_assessment/probe_matrix.csv`
- `outputs/phase3_eval_assessment/report.md`
- `outputs/phase3_eval_assessment/summary.json`

Reference presets:

- `c_engine_pl/variants/phase3_material_only.json`
- `c_engine_pl/variants/phase3_pst_pawn.json`
- `c_engine_pl/variants/phase3_full_eval.json`
- `c_engine_pl/variants/phase3_negamax_ab_id_pruning_full_eval.json`

### 8.5 Re-run the Phase 3 subfeature probes

```bash
PYTHONPATH=src python3 scripts/eval_subfeature_probes.py --search-depth 3
```

Outputs:

- `outputs/phase3_eval_subfeature_probes/variant_summary.csv`
- `outputs/phase3_eval_subfeature_probes/probe_matrix.csv`
- `outputs/phase3_eval_subfeature_probes/report.md`
- `outputs/phase3_eval_subfeature_probes/summary.json`

### 8.6 Re-run the Phase 1 search comparison

Use the Phase 1 presets:

- `c_engine_pl/variants/phase1_minimax.json`
- `c_engine_pl/variants/phase1_minimax_ab.json`
- `c_engine_pl/variants/phase1_negamax.json`
- `c_engine_pl/variants/phase1_negamax_ab.json`
- `c_engine_pl/variants/phase1_negamax_ab_pvs_id.json`

### 8.7 Re-run the feature-completion validation set

Use the feature-completion presets:

- `c_engine_pl/variants/phase1_minimax.json`
- `c_engine_pl/variants/phase2_magic_bitboards_ab_pvs_id.json`
- `c_engine_pl/variants/phase2_mailbox_piece_lists_ab_pvs_id.json`
- `c_engine_pl/variants/phase2_runtime_book_ponder.json`

Artifacts:

- `outputs/feature_completion_validation/report.md`
- `outputs/feature_completion_validation/summary.csv`
- `outputs/feature_completion_validation/bin/`

## 9. Recommended Next Work

The natural next steps are:

1. decide whether `0x88` and `10x12` should remain equivalent or be made behaviorally distinct through backend-native move ordering or canonical-state ownership;
2. deepen the evaluation family beyond the current term set, for example richer king-danger and threat terms;
3. strengthen time-management commonality and, only if needed later, split it into genuine alternative strategies;
4. decide whether the external opening-book subsystem should stay text-based or move to a richer exchange format;
5. eventually decide whether board backends should remain synchronized caches or become true canonical state owners.

## 10. Bottom Line

After Phase 1, Phase 2, and Phase 3:

- search features are no longer cosmetic;
- board representation features are no longer cosmetic;
- evaluation presets are no longer cosmetic;
- the three families can be combined into real, legality-correct engine variants;
- the interaction evidence shows both successful composition and remaining convergence points.

That is the current implementation-backed product line.
