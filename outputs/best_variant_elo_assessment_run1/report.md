# Best Variant Elo Assessment

## Setup and Rationale

- Source tournament: `outputs/variant_diversity_tournament_n50_realistic_retry/summary.json` with standings in `outputs/variant_diversity_tournament_n50_realistic_retry/standings.csv`.
- Best non-anchor player selected from the `N'=50` realistic round-robin: `stratified_variant_28`.
- Fixed variant config: `outputs/stratified_variant_experiment_n100_perft6/sample_configs/stratified_variant_28.json`.
- Goal: estimate the playing strength of the best discovered variant against a dense Stockfish ladder, rather than only ranking it inside the sampled population.
- Method: anchor-only scheduling plus anchored logistic maximum-likelihood estimation. This concentrates the game budget on the variant-vs-anchor evidence that determines the Elo estimate.
- Search regime: time control 10+0.1.
- Stockfish ladder: sf2400:20:2400, sf2450:20:2450, sf2500:20:2500, sf2550:20:2550, sf2600:20:2600, sf2650:20:2650, sf2700:20:2700, sf2800:20:2800.
- Games per anchor: `32`. Total variant-vs-anchor games: `256`.

## Main Result

- Anchored Elo estimate for `stratified_variant_28`: `2176.8 +/- 70.7` Elo (95% CI), i.e. roughly `2106` to `2248`.
- Informative games near the 50% score region: `0` across `0` anchors.
- Detailed anchored estimates are in `outputs/best_variant_elo_assessment_run1/tournament/elo_estimates.csv`.

## Direct Scores Versus Anchors

- `sf2400` (2400): 6.5/32 = 20.3%
- `sf2450` (2450): 2.0/32 = 6.2%
- `sf2500` (2500): 6.0/32 = 18.8%
- `sf2550` (2550): 2.0/32 = 6.2%
- `sf2600` (2600): 5.5/32 = 17.2%
- `sf2650` (2650): 3.5/32 = 10.9%
- `sf2700` (2700): 1.5/32 = 4.7%
- `sf2800` (2800): 0.0/32 = 0.0%

## Interpretation

- This is a local anchored Elo estimate, not a universal absolute rating. It is tied to the current machine, Stockfish build, opening suite, and time-control settings.
- The estimate is much more defensible than the previous diversity tournaments because the game budget is concentrated on the best variant and on multiple anchors around and above the target skill region.
- Plot: `outputs/best_variant_elo_assessment_run1/elo_score_curve.png`.

