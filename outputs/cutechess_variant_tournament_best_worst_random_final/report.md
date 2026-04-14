# Variant Tournament

Three-variant cutechess round-robin across committed engine presets.

## Roles

- best: `phase3_full_eval.json`
- worst: `phase1_minimax.json`
- random: `phase2_10x12_ab_pvs_id.json`

## Preconditions

- Each variant was derived and rebuilt separately.
- Each variant passed start-position perft depth 5 (`4865609`).

## Tournament

- driver: `cutechess-cli`
- format: `round-robin`
- search: `depth=2`
- schedule: `1` round, `2` games per pairing
- openings: curated PGN, random order, color-swapped repeats

## Integrity

- illegal/runtime tokens in cutechess log: `[]`
