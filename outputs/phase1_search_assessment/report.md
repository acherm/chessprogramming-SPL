# Phase 1 Search Modularization

## What changed
- Search moved out of `c_engine_pl/src/engine.c` into `c_engine_pl/src/search.c`.
- `engine.c` now exposes search primitives through an internal ops interface in `c_engine_pl/include/engine_search_internal.h`.
- Search summary strings now reflect the actual selected search stack:
  - `Minimax`
  - `Minimax+AlphaBeta`
  - `Negamax`
  - `Negamax+AlphaBeta`
  - `Negamax+AlphaBeta+PVS+ID`

## What is now truly implemented
- `Negamax`: real recursive negamax core.
- `Alpha-Beta`: real pruning layer that can be combined with either minimax or negamax.
- `Principal Variation Search`: real root/node refinement on alpha-beta cores.
- `Iterative Deepening`: real root driver refinement.
- Existing search refinements remain active on the modular search stack:
  - `Quiescence Search`
  - `Null Move Pruning`
  - `Late Move Reductions`
  - `Futility Pruning`
  - `Razoring`
  - `Delta Pruning`
  - `Transposition Table`
  - `Hash Move`
  - `Replacement Schemes`
  - `Move Ordering`
  - `History Heuristic`
  - `Killer Heuristic`

## Quick combination assessment
Search probe artifact: `outputs/phase1_search_assessment/search_probe.csv`

Fixed position:
- `startpos moves e2e4 e7e5 g1f3 b8c6 f1c4 g8f6 d2d3 f8c5`
- search depth `4`

Results:
- `phase1_minimax`: `63,338,044` nodes
- `phase1_minimax_ab`: `80,070` nodes
- `phase1_negamax`: `63,336,631` nodes
- `phase1_negamax_ab`: `80,070` nodes
- `phase1_negamax_ab_pvs_id`: `53,577` nodes

Observations:
- `Negamax` and `Minimax` now compile as distinct search cores.
- `Alpha-Beta` cuts node count by roughly three orders of magnitude on the same position.
- `PVS + Iterative Deepening` reduces nodes further on top of `Negamax + Alpha-Beta`.
- All tested combinations compiled and returned the same best move on the probe position, which is expected for semantically equivalent search cores.

## Tiny gameplay sanity check
Artifacts:
- `outputs/phase1_search_assessment/minimax_vs_negamaxabpvsid.log`
- `outputs/phase1_search_assessment/minimax_vs_negamaxabpvsid.pgn`

Result:
- `phase1_negamax_ab_pvs_id` scored `3.0/4`
- `phase1_minimax` scored `1.0/4`
- no illegal moves were observed

## Still partial after Phase 1
- Search refinements are now modular, but the engine still shares one position/movegen/eval substrate.
- Board representation features remain only partially honest because the state shape is still `board[64]`.
- `Bitboards`, `0x88`, `Mailbox`, `10x12` are not yet first-class interchangeable state backends.
- Evaluation features still live in one monolithic evaluator.
