# phase3_full_eval_after_commonality_opt vs stockfish_2700

## Setup
- Variant: `phase3_full_eval_after_commonality_opt`
- Opponent: `stockfish_2700`
- Move time: `2000 ms` per move
- Games: `20`
- Opening seeds: `10` with color swap

## Result
- Score: `6.0/20` (30.0%)
- Record: `2W 8D 10L`
- Illegal moves: `0`

## Depth
- Variant average depth across games: `7.14`
- Variant max depth seen: `14`
- Stockfish average depth across games: `36.29`
- Stockfish max depth seen: `245`

## TT / Search Observability
- TT probes / hits / cutoffs / stores: `428587064` / `169708495` / `124445927` / `174264514`
- TT hit rate: `0.396`
- TT cutoff rate: `0.2904`
- Eval calls / eval cache hits: `1043832831` / `272381288`
- Eval cache hit rate: `0.2609`
- Movegen total: `576014587`
- Attack total: `13663826706`
- Attack per node: `9.7328`
- Movegen per node: `0.4103`
