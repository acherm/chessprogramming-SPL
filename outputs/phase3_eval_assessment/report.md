# Phase 3 Evaluation Assessment

## Summary

- variants tested: 12
- compiled successfully: 12
- passed start-position perft depth 5: 12
- successful probes: 48/48
- probe depth: 2

## Divergence by Position

- `knight_activation` produced 4 distinct evaluation outcomes across presets and boards (5 labeled rows).
- `doubled_pawns` produced 5 distinct evaluation outcomes across presets and boards (6 labeled rows).
- `king_attack` produced 1 distinct evaluation outcomes across presets and boards (4 labeled rows).
- `passed_pawn_endgame` produced 4 distinct evaluation outcomes across presets and boards (4 labeled rows).

## Divergence by Board Backend

- `Bitboards` showed distinct bestmove/score outcomes across evaluation presets on 3/4 positions.
- `0x88` showed distinct bestmove/score outcomes across evaluation presets on 3/4 positions.
- `10x12 Board` showed distinct bestmove/score outcomes across evaluation presets on 3/4 positions.

## Interpretation

- Evaluation is now its own module and the presets in this assessment exercise different combinations of material, PST, pawn subfeatures, bishop-pair/open-file terms, mobility, king-pressure, king-shelter, king-activity, tapered-eval, and SEE.
- Perft equality across presets is expected because evaluation does not change legality; search scores and best moves are the relevant observation point here.
- If presets change scores or best moves on the same position while remaining perft-correct, they are behaving as real combinable implementation features rather than labels.
