# Best Variant Elo Assessment

## Setup and Rationale

- Source tournament: `outputs/variant_diversity_tournament_n50_realistic_retry/summary.json` with standings in `outputs/variant_diversity_tournament_n50_realistic_retry/standings.csv`.
- Best non-anchor player selected from the `N'=50` realistic round-robin: `stratified_variant_28`.
- Fixed variant config: `outputs/stratified_variant_experiment_n100_perft6/sample_configs/stratified_variant_28.json`.
- Goal: estimate the playing strength of the best discovered variant against a dense Stockfish ladder, rather than only ranking it inside the sampled population.
- Method: anchor-only scheduling plus anchored logistic maximum-likelihood estimation. This concentrates the game budget on the variant-vs-anchor evidence that determines the Elo estimate.
- Search regime: time control 120+1.
- Stockfish ladder: sf2100:20:2100, sf2150:20:2150, sf2200:20:2200, sf2250:20:2250, sf2300:20:2300, sf2350:20:2350, sf2400:20:2400, sf2450:20:2450, sf2500:20:2500.
- Games per anchor: `24`. Total variant-vs-anchor games: `216`.

## Main Result

- Anchored Elo estimate for `stratified_variant_28`: `2176.1 +/- 51.5` Elo (95% CI), i.e. roughly `2125` to `2228`.
- Informative games near the 50% score region: `144` across `6` anchors.
- Detailed anchored estimates are in `outputs/stratified28_stockfish_uci_elo_120p1/tournament/elo_estimates.csv`.

## Direct Scores Versus Anchors

- `sf2100` (2100.0): 12.0/24 = 50.0%
- `sf2150` (2150.0): 12.0/24 = 50.0%
- `sf2200` (2200.0): 9.0/24 = 37.5%
- `sf2250` (2250.0): 4.5/24 = 18.8%
- `sf2300` (2300.0): 10.5/24 = 43.8%
- `sf2350` (2350.0): 12.0/24 = 50.0%
- `sf2400` (2400.0): 3.5/24 = 14.6%
- `sf2450` (2450.0): 6.5/24 = 27.1%
- `sf2500` (2500.0): 5.0/24 = 20.8%

## Interpretation

- This is a local anchored Elo estimate, not a universal absolute rating. It is tied to the current machine, Stockfish build, opening suite, and time-control settings.
- The estimate is much more defensible than the previous diversity tournaments because the game budget is concentrated on the best variant and on multiple anchors around and above the target skill region.
- Plot: `outputs/stratified28_stockfish_uci_elo_120p1/elo_score_curve.png`.

