# Setup Tournament Report

This tournament compares three `(variant, setup)` pairs rather than three variants under equal external conditions.
It is therefore a best-operating-point comparison, not a controlled Elo comparison.

## Players
- `best`: `phase3_full_eval` with setup `FixedMoveTime:1500-2000 ms/move, st=2.0`
- `worst`: `phase1_minimax` with setup `FixedMoveTime:100-250 ms/move, st=0.25`
- `random`: `phase2_10x12_ab_pvs_id` with setup `FixedMoveTime:750-1000 ms/move, st=1.0`

## Integrity
- perft rows: 3
- all perft passed: True
- illegal markers in cutechess log: []

## Standings
- `random` / `phase2_10x12_ab_pvs_id`: 4.0/4 (100.0%)
- `best` / `phase3_full_eval`: 2.0/4 (50.0%)
- `worst` / `phase1_minimax`: 0.0/4 (0.0%)