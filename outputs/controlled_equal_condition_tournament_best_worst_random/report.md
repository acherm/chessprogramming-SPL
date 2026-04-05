# Controlled Equal-Condition Tournament Report

All three variants were run under the same external condition:
- `depth=3`
- `tc=inf`
- same opening suite (`policy=encounter`, `plies=8`)
- same adjudication rules

## Integrity
- all 3 variants passed perft depth 5 before the tournament
- illegal markers in log: []

## Standings
- `best` / `phase3_full_eval`: 7.0/8 (87.5%)
- `random` / `phase2_10x12_ab_pvs_id`: 4.5/8 (56.2%)
- `worst` / `phase1_minimax`: 0.5/8 (6.2%)