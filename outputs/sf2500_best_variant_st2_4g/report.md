# Best Variant vs Stockfish 2500

## Setup
- Variant: `phase3_full_eval`
- Opponent: `stockfish_2500`
- Referee: `python-chess` UCI controller
- Move time: `2000 ms` per move
- Openings: `2` opening seeds from `outputs/proper_elo_tournament_strong_v1/openings.pgn`, each with color swap
- Max fullmoves per game: `80`

## Result
- Score: `1.5/4` (37.5%)
- Record: `1W 1D 2L`
- White wins: `0/2`
- Black wins: `1/2`
- Illegal moves: `0`
- Move-cap draws: `0`

## Depth
- Variant average depth across games: `4.96`
- Variant max depth seen: `5`
- Stockfish average depth across games: `37.66`
- Stockfish max depth seen: `245`

## Files
- `games.pgn`
- `games.csv`
- `summary.csv`
- `summary.json`
