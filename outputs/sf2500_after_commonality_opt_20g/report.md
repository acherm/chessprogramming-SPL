# phase3_full_eval_after_commonality_opt vs stockfish_2500

## Setup
- Variant: `phase3_full_eval_after_commonality_opt`
- Opponent: `stockfish_2500`
- Move time: `2000 ms` per move
- Games: `20`
- Opening seeds: `10` with color swap

## Result
- Score: `13.0/20` (65.0%)
- Record: `10W 6D 4L`
- Illegal moves: `0`

## Depth
- Variant average depth across games: `7.99`
- Variant max depth seen: `29`
- Stockfish average depth across games: `36.7`
- Stockfish max depth seen: `245`

## TT / Search Observability
- TT probes / hits / cutoffs / stores: `929223757` / `417654431` / `328723018` / `343287294`
- TT hit rate: `0.4495`
- TT cutoff rate: `0.3538`
- Eval calls / eval cache hits: `1604379410` / `462872472`
- Eval cache hit rate: `0.2885`
- Movegen total: `962580481`
- Attack total: `21443715715`
- Attack per node: `9.1457`
- Movegen per node: `0.4105`
