# Product-Line Architecture and Feature Interactions

This note documents the current implementation-backed chess engine product line after Phase 1 and Phase 2.

It is intentionally narrower than the mined CPW feature model. The CPW model is broader and descriptive; this document describes the subset that is actually realized as executable variation points in the C engine.

Related notes:

- `docs/variant_constraints_and_perft.md`
- `outputs/phase1_search_assessment/report.md`
- `outputs/phase2_board_assessment/report.md`
- `outputs/phase2_pairwise_interactions/report.md`

## 1. Scope

The key design objective is honesty:

- a feature should not only change labels or metadata;
- enabling a feature should select a concrete implementation path;
- combinations of features should compile into real engine variants;
- those variants should remain legality-correct, at least as checked by perft and UCI smoke behavior.

The work completed so far covers two major variation families:

- Phase 1: search architecture
- Phase 2: board representation architecture

This means the current implementation profile already supports meaningful combinations of:

- search core and search refinements
- board representation backend

but does not yet give the same level of modular honesty to all evaluation, time-management, opening, tuning, and protocol-adjacent features.

## 2. Executable Profile vs. Mined Model

The mined CPW model contains many features that are useful for software product-line analysis, but not all of them are currently backed by a dedicated implementation in the engine.

The executable derivation profile is enforced by:

- `src/cpw_variability/pl_codegen.py`
- `src/cpw_variability/constraints.py`

Important consequences:

- exactly one primary board representation must be selected;
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
  - board encodings exclude one another

This separation matters because the mined feature model is a conceptual space, while the executable profile is a derivable implementation space.

## 3. Architecture After Phase 1 and Phase 2

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
- `Hash Move`
- `Transposition Table`
- `Replacement Schemes`
- `Aspiration Windows`
- `Null Move Pruning`
- `Late Move Reductions`
- `Futility Pruning`
- `Razoring`
- `Delta Pruning`

These are not all equally mature, but they are no longer purely cosmetic toggles.

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
- `0x88`
- `10x12 Board`

`Mailbox` is still modeled but currently reuses the `10x12` backend family in the backend dispatcher.

### 3.3 How the Two Variation Points Compose

The architectural boundary is now:

- search code calls engine operations;
- engine operations delegate move generation and attack logic to the selected board backend;
- legal-move generation still wraps pseudo-legal move generation plus `make_move` / `unmake_move` and in-check validation.

So a search configuration does not need to know whether it is exploring moves from:

- bitboards
- 0x88
- 10x12

It consumes the same engine-level move interface.

That is the core reason why Phase 1 and Phase 2 combinations are possible.

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
- `0x88`
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

## 6. Known Limitations

The architecture is more honest than before, but it is not complete.

### 6.1 Still Partial or Shared

These areas are still less modular than the search and board families:

- evaluation terms still live in one shared evaluator in `c_engine_pl/src/engine.c`
- opening-book behavior is not yet a first-class modular family
- time-management options are not yet modeled as deeply independent strategies
- tuning features are mostly represented at the model/configuration level, not as distinct implementation modules

### 6.2 Canonical State Still Exists

The engine still keeps `board[64]` as canonical state and treats:

- `board_0x88`
- `board_120`
- bitboards

as synchronized backend caches.

This is a reasonable intermediate architecture, but it is not the same as a fully representation-native engine family where each backend owns the canonical state and move application.

### 6.3 Interaction Coverage Is Still Limited

The current pairwise interaction matrix only tests:

- representative search stacks
- representative board encodings
- one fixed tactical probe
- start-position perft

That is enough to validate architectural composition, but not enough to characterize all interactions or all strengths.

## 7. How to Reproduce

### 7.1 Re-run the pairwise interaction matrix

```bash
PYTHONPATH=src python3 scripts/board_search_pairwise.py --probe-depth 3
```

Outputs:

- `outputs/phase2_pairwise_interactions/pairwise_matrix.csv`
- `outputs/phase2_pairwise_interactions/pairwise_matrix.md`
- `outputs/phase2_pairwise_interactions/report.md`
- `outputs/phase2_pairwise_interactions/summary.json`

### 7.2 Re-run the Phase 2 board backend comparison

```bash
PYTHONPATH=src python3 scripts/derive_variant.py --config c_engine_pl/variants/phase2_bitboards_ab_pvs_id.json --build
PYTHONPATH=src python3 scripts/uci_perft_check.py --config c_engine_pl/variants/phase2_bitboards_ab_pvs_id.json --max-depth 5
```

Equivalent commands can be run with:

- `c_engine_pl/variants/phase2_0x88_ab_pvs_id.json`
- `c_engine_pl/variants/phase2_10x12_ab_pvs_id.json`

### 7.3 Re-run the Phase 1 search comparison

Use the Phase 1 presets:

- `c_engine_pl/variants/phase1_minimax.json`
- `c_engine_pl/variants/phase1_minimax_ab.json`
- `c_engine_pl/variants/phase1_negamax.json`
- `c_engine_pl/variants/phase1_negamax_ab.json`
- `c_engine_pl/variants/phase1_negamax_ab_pvs_id.json`

## 8. Recommended Next Work

The natural next steps are:

1. remove the legacy backend-local move generation code still left in `engine.c`, since the real backend implementation now lives in `board_backend.c`;
2. extend interaction testing from one probe to a curated multi-position suite;
3. make evaluation features as modular and honest as search and board features;
4. eventually decide whether board backends should remain synchronized caches or become true canonical state owners.

## 9. Bottom Line

After Phase 1 and Phase 2:

- search features are no longer cosmetic;
- board representation features are no longer cosmetic;
- the two families can be combined into real, legality-correct engine variants;
- the interaction matrix shows both successful composition and remaining convergence points.

That is the current implementation-backed product line.
