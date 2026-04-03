# Variant Constraints and Perft Impact

This note documents why key constraints exist in the implementation profile and how selected features affect perft behavior and speed.

## Scope

- The mined SPL model is broader than executable engines.
- `src/cpw_variability/pl_codegen.py` enforces an executable profile during derivation.
- In that profile, `Move Generation` is mandatory.

## Why `Move Generation` Is Mandatory

Without `Move Generation`, a derived variant may compile but cannot enumerate chess moves.

Implementation guards:

- `engine_perft()` returns `0` if `CFG_MOVE_GENERATION==0` or `CFG_MAKE_MOVE==0`.
- Move listing is disabled when `CFG_MOVE_GENERATION==0`.

So a variant without move generation is not a meaningful playable/benchmarkable chess engine configuration.

## Constraint Justification (Key Examples)

Source of constraints: `src/cpw_variability/constraints.py`.

- `Legal Move Generation -> Move Generation`
  - Legal generation is a refinement of baseline move generation.
- `Pseudo-Legal Move Generation -> Move Generation`
  - Pseudo-legal generation still relies on base move production.
- `Castling -> Legal Move Generation`
  - Castling legality depends on attack-aware validation.
- `En Passant -> Legal Move Generation`
  - En-passant legality requires move legality checks.
- `Unmake Move -> Make Move`
  - Unmake is the inverse of make-move.
- `Copy-Make -> Make Move`
  - Copy-make variants still require deterministic move application.
- `Magic Bitboards -> Bitboards`
  - Magic indexing is specific to bitboard representation.
- Board representation excludes (`Bitboards`, `Mailbox`, `0x88`, `10x12 Board`)
  - Encodings are modeled as alternatives.

## Perft Correctness Notes

Standard start-position references used in this project:

- depth 1: `20`
- depth 2: `400`
- depth 3: `8902`
- depth 4: `197281`
- depth 5: `4865609`
- depth 6: `119060324`

Important interpretation detail:

- Excluding `Castling` does not necessarily change start-position perft up to depth 6.
- Castling-sensitive FEN positions are needed to observe castling-specific divergence.

## Feature Impact on Perft

Correctness-critical:

- `Move Generation`
- `Make Move`
- `Unmake Move` (or `Copy-Make`)
- `Legal Move Generation`
- Board representation choice (`Bitboards`/`0x88`/`Mailbox`/`10x12`)
- `Castling`, `En Passant` (rule-specific correctness in relevant positions)

Mostly performance-impacting for perft:

- `Bitboards`, `Magic Bitboards`
- `Copy-Make` vs `Unmake Move`
- `Zobrist Hashing` (if used by perft/path features)

Mostly search-strength oriented (limited direct perft impact):

- `Alpha-Beta`, `PVS`, `LMR`, `Null Move Pruning`, `Aspiration Windows`
- evaluation features (`Piece-Square Tables`, `King Pressure`, `King Shelter`, `Mobility`, etc.)

Perft is a move-generation correctness benchmark, not a playing-strength benchmark.
