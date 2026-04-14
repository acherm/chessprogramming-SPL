# Setup Tournament Report

This tournament compares three `(variant, setup)` pairs rather than three variants under equal external conditions.
It is therefore a best-operating-point comparison, not a controlled Elo comparison.

## Players
- `best`: `phase3_full_eval` with setup `FixedDepth:depth 12-20 (target 14), depth=6`
- `worst`: `phase1_minimax` with setup `FixedDepth:depth 3-4 (target 4), depth=3`
- `random`: `phase2_10x12_ab_pvs_id` with setup `FixedDepth:depth 9-12 (target 10), depth=5`

## Integrity
- perft rows: 3
- all perft passed: True
- illegal markers in cutechess log: []

## Standings
- `best` / `phase3_full_eval`: 4.0/4 (100.0%)
- `random` / `phase2_10x12_ab_pvs_id`: 2.0/4 (50.0%)
- `worst` / `phase1_minimax`: 0.0/4 (0.0%)