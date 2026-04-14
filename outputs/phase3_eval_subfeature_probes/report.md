# Phase 3 Subfeature Probes

## Summary

- variants tested: 5
- compiled successfully: 5
- passed perft depth 5: 5
- probe rows: 40/40
- search depth for reference move: 3

## Position Signals

- `bishop_pair` produced 5 distinct static-eval outcomes and 5 distinct search outcomes across presets.
- `rook_open_file` produced 5 distinct static-eval outcomes and 5 distinct search outcomes across presets.
- `rook_semi_open_file` produced 5 distinct static-eval outcomes and 5 distinct search outcomes across presets.
- `doubled_isolated_pawns` produced 5 distinct static-eval outcomes and 5 distinct search outcomes across presets.
- `connected_pawns` produced 5 distinct static-eval outcomes and 5 distinct search outcomes across presets.
- `passed_pawn_endgame` produced 5 distinct static-eval outcomes and 5 distinct search outcomes across presets.
- `king_shelter` produced 5 distinct static-eval outcomes and 5 distinct search outcomes across presets.
- `king_activity_endgame` produced 5 distinct static-eval outcomes and 5 distinct search outcomes across presets.

## Interpretation

- These probes use the strong engine stack: negamax + alpha-beta + pruning + iterative deepening.
- `eval` isolates the evaluator itself; `go depth N` shows how those promoted evaluation leaves propagate into move choice.
- The presets are leaf-oriented rather than umbrella-oriented, so the matrix directly exercises bishop-pair, rook-file, pawn, shelter, and king-activity options.
