# Phase 2 Board Backend Assessment

## Scope

Phase 2 makes board-representation features executable variation points rather than metadata.
The engine now maintains backend-specific state in `EngineState` and routes attack detection and pseudo-legal move generation through the selected backend.

Implemented backends:
- `Bitboards`
- `0x88`
- `10x12 Board`

## Quick validation

Variants assessed with the same search stack:
- `Negamax`
- `Alpha-Beta`
- `Principal Variation Search`
- `Iterative Deepening`

Results are recorded in `search_probe.csv`.

## Findings

- All three variants compile successfully.
- All three variants pass start-position perft through depth 5.
- The board backend changes observable behavior in search, not just labels.
- `Bitboards` searches the fixed probe in fewer nodes (`93708`) than `0x88` and `10x12` (`161628`), with the same best move (`b1c3`).
- Raw perft throughput is currently faster in `0x88`/`10x12` than in `Bitboards`, which indicates the bitboard backend is functionally real but still less optimized for exhaustive move counting.

## Interpretation

The modularization pays off in two ways:
- feature combinations are now real: the same search stack can be combined with different board encodings and all variants remain valid and correct;
- board representation now affects attack detection, move generation, search node counts, and runtime.

This is the Phase 2 architectural objective. The next improvement is optimization, not architectural honesty.
