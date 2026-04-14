# Batch A Stockfish 2200 Recheck

## Setup
- Engine: `phase3_pruning_full_post_batch_a`
- Opponent: `stockfish_2200`
- Stockfish options: `Threads=1`, `Hash=64`, `UCI_LimitStrength=true`, `UCI_Elo=2200`
- Time control: `120+1`
- Games: `10`
- Openings: `outputs/proper_elo_tournament_strong_v1/openings.pgn`

## Result
- Updated pruning variant: `2.5/10`
- Old pruning baseline: `3.0/10`
- Old full baseline: `4.0/10`
- Illegal/disconnect terminations detected: `0`

## Color Split
- As White: `0` wins in `5` games
- As Black: `2` wins in `5` games

## Files
- [summary.csv](/Users/mathieuacher/SANDBOX/chessprogramming-vm/outputs/batch_a_validation/sf2200_recheck/summary.csv)
- [games.pgn](/Users/mathieuacher/SANDBOX/chessprogramming-vm/outputs/batch_a_validation/sf2200_recheck/games.pgn)
- [cutechess.log](/Users/mathieuacher/SANDBOX/chessprogramming-vm/outputs/batch_a_validation/sf2200_recheck/cutechess.log)
