# Commonality Optimization and 2500-Anchor Assessment

This note documents the recent commonality optimization work on the shared engine path and the follow-up reassessment against the Stockfish `~2500` anchor.

It is intentionally separate from the SPL feature-model notes because these changes are mainly in the commonality space rather than in the configurable feature space.

## 1. Objective

The immediate objective was to remove the practical limit where the best current variant only reached about depth `5` at `2s/move`.

The important modeling point is:

- this was not a new feature request
- this was shared infrastructure work intended to benefit many variants at once

## 2. Optimization Batches

### 2.1 Batch 1: Remove Avoidable Shared Overhead

Implemented in the shared engine/search path:

- removed the implicit timed-search cap at depth `5`
- cached position and pawn keys in engine state
- replaced full backend rebuild on every `make_move` / `unmake_move` with incremental updates
- made backend synchronization selective
- removed full-state copy per candidate in legal-move filtering
- replaced mobility-by-pseudo-move-generation with direct mobility counting
- made the pawn hash use a real pawn-only key

Main files:

- `c_engine_pl/src/search.c`
- `c_engine_pl/src/engine.c`
- `c_engine_pl/src/eval.c`
- `c_engine_pl/src/board_backend.c`
- `c_engine_pl/src/uci.c`

### 2.2 Batch 2: Bitboard Attack/Movegen Hot Path

Implemented:

- precomputed knight attack masks
- precomputed king attack masks
- reused those masks in bitboard attack testing
- reused those masks in bitboard knight and king move generation

Main file:

- `c_engine_pl/src/board_backend.c`

### 2.3 Batch 3: Legality Fast Path

Implemented:

- cached king squares in `EngineState`
- maintained king-square cache during board sync and incremental piece updates
- added a pin/check-aware legality fast path
- only tricky cases still fall back to `make/check/unmake`
  - king moves
  - en passant
  - double-check situations

Main files:

- `c_engine_pl/include/engine.h`
- `c_engine_pl/src/engine.c`
- `c_engine_pl/src/board_backend.c`

## 3. Timed Search Results

### 3.1 Before vs After Commonality Work

At `movetime=2000`:

| position | before depth | after depth | before nodes | after nodes | before move | after move |
| --- | --- | --- | --- | --- | --- | --- |
| `startpos` | `5` | `7` | `56,269` | `1,287,168` | `d2d4` | `d2d4` |
| `italian_dev` | `5` | `7` | `182,975` | `1,209,344` | `d2d3` | `d2d3` |
| `queens_gambit` | `5` | `6` | `154,676` | `1,154,048` | `f8b4` | `b8c6` |

Artifacts:

- `outputs/commonality_opt_report.md`
- `outputs/commonality_opt_round2_report.md`
- `outputs/commonality_opt_round3_report.md`
- `outputs/commonality_opt_stats_after.json`
- `outputs/commonality_opt_stats_after_masks.json`
- `outputs/commonality_opt_stats_after_legality.json`

### 3.2 Reading

The main conclusion is specific:

- the depth-`5` ceiling was real and was partly caused by a policy bug
- after fixing that and reducing shared overhead, timed search now reaches depth `6-7` on the benchmark positions
- the legality fast path reduced attack-pressure per node while also increasing node throughput

This means the original objective was met in the narrow technical sense:

- the best variant is no longer artificially stuck around depth `5` at `2s/move`

## 4. Stockfish 2500 Reassessment

The reassessment was rerun with a dedicated UCI referee harness:

- `scripts/sf_anchor_match.py`

Output directory:

- `outputs/sf2500_after_commonality_opt_clean/`

Setup:

- variant: `phase3_full_eval_after_commonality_opt`
- opponent: Stockfish with `UCI_Elo=2500`, `Skill Level=20`, `Threads=1`, `Hash=64`
- budget: `movetime=2000 ms`
- `2` opening seeds with color swap
- `4` games total

### 4.1 Match Result

Result:

- score: `1.0/4` = `25.0%`
- record: `0W 2D 2L`
- illegal moves: `0`

Compared with the earlier pre-optimization anchor run:

- old score: `1.5/4` = `37.5%`
- new score: `1.0/4` = `25.0%`

So the deeper search did **not** translate into a better result in this small sample.

### 4.2 Search Profile Shift

What did improve clearly:

- old average depth across games: `4.96`
- new average depth across games: `9.37`
- old max depth seen: `5`
- new max depth seen: `24`

This is a major shift in search regime.

### 4.3 TT and Search Observability

Aggregate observability from the rerun:

- TT probes: `404,593,108`
- TT hits: `268,885,620`
- TT cutoff hits: `234,726,241`
- TT stores: `101,206,691`
- TT hit rate: `0.6646`
- TT cutoff rate: `0.5802`
- eval cache hit rate: `0.3414`
- attack per node: `7.3158`
- movegen per node: `0.3621`

Interpretation:

- TT is being used heavily and effectively
- eval caching is helping materially
- attack/in-check work is still a dominant residual cost center

## 5. Current Conclusion

The current state should be read carefully:

- commonality optimization succeeded on its own technical objective
- the best variant now searches much deeper at the same move budget
- legality remained intact
- but the new search regime did not yet improve the 2500-anchor match score in this small sample

So the next work should not be "add more depth".

The next work should be quality-oriented search work on top of the stronger baseline:

1. inspect the two losses from the anchor rerun
2. improve move-ordering quality further
3. improve SEE usage/calibration
4. tune null move / LMR / aspiration behavior for the deeper regime
5. rerun a longer `8-12` game anchor match before making rating claims
