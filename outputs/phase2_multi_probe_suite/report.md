# Multi-Position Board/Search Interaction Assessment

## Summary

- variants tested: 15
- compiled successfully: 15
- passed start-position perft depth 5: 15
- probe rows collected: 75/75
- probe depth: 3

## Divergence by Search Stack

- `minimax` diverged across board backends on 3/5 positions; `0x88` vs `10x12` diverged on 0/5 positions.
- `minimax_ab` diverged across board backends on 4/5 positions; `0x88` vs `10x12` diverged on 0/5 positions.
- `negamax` diverged across board backends on 3/5 positions; `0x88` vs `10x12` diverged on 0/5 positions.
- `negamax_ab` diverged across board backends on 4/5 positions; `0x88` vs `10x12` diverged on 0/5 positions.
- `negamax_ab_pvs_id` diverged across board backends on 4/5 positions; `0x88` vs `10x12` diverged on 0/5 positions.

## Interpretation

- This suite broadens the earlier single-probe assessment to a small set of opening, middlegame, endgame, and promotion-race positions.
- If `0x88` and `10x12` still match on a given position, that means the current backend implementations expose the same search-facing move order and legality behavior on that workload.
- If they diverge on nodes, score, or best move, that is evidence that board representation is interacting with search rather than only serving as a storage detail.
