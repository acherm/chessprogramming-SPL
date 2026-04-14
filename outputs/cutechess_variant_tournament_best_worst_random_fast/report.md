# Variant Tournament

Three-variant cutechess round-robin using committed engine presets.

## Roles

- best: `phase3_full_eval.json`
- worst: `phase1_minimax.json`
- random: `phase2_10x12_ab_pvs_id.json` (sample seed `20260404` from committed legal presets)

## Preconditions

- Each variant was derived and rebuilt separately.
- Each variant passed start-position perft depth 5 (`4865609`).

## Tournament

- Engine driver: `cutechess-cli`
- Format: `round-robin`
- Players: 3
- Search: `depth=3`
- Rounds: `1`
- Games per encounter: `2`
- Openings: curated PGN, random order, color-swapped repeats

## Integrity

- Illegal/runtime tokens in cutechess log: `[]`

## Artifacts

- `players.csv`
- `perft.csv`
- `standings.csv`
- `games.csv`
- `games.pgn`
- `cutechess.log`
- `summary.json`
