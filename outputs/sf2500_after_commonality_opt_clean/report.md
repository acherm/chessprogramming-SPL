# phase3_full_eval_after_commonality_opt vs stockfish_2500

## Setup
- Variant: `phase3_full_eval_after_commonality_opt`
- Opponent: `stockfish_2500`
- Move time: `2000 ms` per move
- Games: `4`
- Opening seeds: `2` with color swap

## Result
- Score: `1.0/4` (25.0%)
- Record: `0W 2D 2L`
- Illegal moves: `0`

## Depth
- Variant average depth across games: `9.37`
- Variant max depth seen: `24`
- Stockfish average depth across games: `40.95`
- Stockfish max depth seen: `245`

## TT / Search Observability
- TT probes / hits / cutoffs / stores: `404593108` / `268885620` / `234726241` / `101206691`
- TT hit rate: `0.6646`
- TT cutoff rate: `0.5802`
- Eval calls / eval cache hits: `375173827` / `128073594`
- Eval cache hit rate: `0.3414`
- Movegen total: `262816530`
- Attack total: `5310196126`
- Attack per node: `7.3158`
- Movegen per node: `0.3621`
