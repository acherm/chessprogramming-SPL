# TT And Time Validation

## Build
- New binary: `/Users/mathieuacher/SANDBOX/chessprogramming-vm/outputs/tt_time_validation/phase3_full_post_tt_time`
- Baseline binary: `/Users/mathieuacher/SANDBOX/chessprogramming-vm/outputs/batch_a_validation/phase3_full_post_batch_a`

## Correctness
- startpos perft depth 5: `4865609`

## Clock Smoke
- command: `go wtime 3000 btime 3000 winc 100 binc 100 movestogo 10`
- elapsed wall time: `0.246s`
- last info: `info depth 5 score cp 61 nodes 56269 pv d2d4`
- bestmove: `bestmove d2d4`

## A/B Match
- matchup: `phase3_full_post_batch_a` vs `phase3_full_post_tt_time`
- time control: `10+0.1`
- games: `6`
- result: `phase3_full_post_tt_time` scored `3.0/6`
- illegal/disconnect terminations detected from PGN headers: `0`

## Files
- [summary.csv](/Users/mathieuacher/SANDBOX/chessprogramming-vm/outputs/tt_time_validation/summary.csv)
- [match PGN](/Users/mathieuacher/SANDBOX/chessprogramming-vm/outputs/tt_time_validation/match/tt_time_head_to_head.pgn)
