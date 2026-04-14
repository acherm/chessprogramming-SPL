# Strength Improvement Assessment (March 5, 2026)

## Code Changes
- Search quality improved in `c_engine_pl/src/engine.c`:
  - check-aware quiescence (evasion search + mate fallback)
  - root move promotion across iterative deepening passes
  - cleanup for feature-gated parameters
- UCI time parsing improved in `c_engine_pl/src/uci.c`:
  - side-aware `wtime/btime` handling
  - explicit `movetime` precedence
  - depth-only mode disables implicit 150ms cap (`go depth N` searches full depth)

## New Variant Configurations
- `outputs/improved_variants/strong_variant_01.json` (43 selected features)
- `outputs/improved_variants/strong_variant_02.json` (34 selected features)

## Experiments
### 1. Internal mini round-robin (4 variants, depth=3)
Artifacts:
- `outputs/improved_variants/mini_strength_d3.log`
- `outputs/improved_variants/mini_strength_d3.pgn`

Result highlights:
- `strong_01`: 11.5/12
- `strong_02`: 7.0/12
- `candidate_02`: 5.0/12
- `candidate_01`: 0.5/12

### 2. Head-to-head: candidate_01 vs strong_01 (depth=3)
Artifacts:
- `outputs/improved_variants/candidate01_vs_strong01_d3.log`
- `outputs/improved_variants/candidate01_vs_strong01_d3.pgn`

Result:
- `strong_01` wins 8-0.

### 3. Versus Stockfish 1320 (depth=3)
Artifacts:
- `outputs/improved_variants/candidate01_vs_sf1320_d3.log`
- `outputs/improved_variants/candidate01_vs_sf1320_d3.pgn`
- `outputs/improved_variants/strong01_vs_sf1320_d3.log`
- `outputs/improved_variants/strong01_vs_sf1320_d3.pgn`
- `outputs/improved_variants/strength_assessment.csv`

Result:
- `candidate_01`: 5.5/8
- `strong_01`: 8.0/8

### 4. Calibrated tournament with Stockfish anchors
Artifacts:
- `outputs/proper_elo_tournament_strong_v1/summary.json`
- `outputs/proper_elo_tournament_strong_v1/standings.csv`
- `outputs/proper_elo_tournament_strong_v1/elo_estimates.csv`
- `outputs/proper_elo_tournament_strong_v1/games.csv`
- `outputs/proper_elo_tournament_strong_v1/cutechess.log`

Setup:
- Players: strong variants + Stockfish (1320/1800/2150/2500)
- 60 games total (rounds=2, games-per-encounter=2, depth=4)

Standings (score / 20):
- `stockfish_2500`: 14.0
- `stockfish_2150`: 12.5
- `strong_variant_02`: 11.5
- `stockfish_1800`: 10.5
- `strong_variant_01`: 9.0
- `stockfish_1320`: 2.5

Anchored Elo estimates:
- `strong_variant_02`: 2046.9 +/- 205.1
- `strong_variant_01`: 1931.6 +/- 206.9

## Legality/Correctness
- No illegal moves observed in the above tournament logs.
- Perft start position passes through depth 5 for strong variants.
