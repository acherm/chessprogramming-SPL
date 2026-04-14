# Best Variant Elo Assessment

## Setup and Rationale

- Source tournament: `outputs/variant_diversity_tournament_n50_realistic_retry/summary.json` with standings in `outputs/variant_diversity_tournament_n50_realistic_retry/standings.csv`.
- Best non-anchor player selected from the `N'=50` realistic round-robin: `stratified_variant_28`.
- Fixed variant config: `outputs/stratified_variant_experiment_n100_perft6/sample_configs/stratified_variant_28.json`.
- Goal: estimate the playing strength of the best discovered variant against a dense Stockfish ladder, rather than only ranking it inside the sampled population.
- Method: anchor-only scheduling plus anchored logistic maximum-likelihood estimation. This concentrates the game budget on the variant-vs-anchor evidence that determines the Elo estimate.
- Search regime: fixed move time 0.05s.
- Stockfish ladder: sf2400:20:2400, sf2500:20:2500.
- Games per anchor: `2`. Total variant-vs-anchor games: `4`.

## Main Result

- Anchored Elo estimate for `stratified_variant_28` is currently unstable (`-10350.0 +/- 1668005260528270848.0` in the raw fit), which means the anchor ladder or game budget does not yet bracket the true score curve tightly enough.
- Informative games near the 50% score region: `0` across `0` anchors.
- Detailed anchored estimates are in `outputs/best_variant_elo_assessment_smoke_v3/tournament/elo_estimates.csv`.

## Direct Scores Versus Anchors

- `sf2400` (2400): 0.0/2 = 0.0%
- `sf2500` (2500): 0.0/2 = 0.0%

## Interpretation

- This is a local anchored Elo estimate, not a universal absolute rating. It is tied to the current machine, Stockfish build, opening suite, and time-control settings.
- The estimate is much more defensible than the previous diversity tournaments because the game budget is concentrated on the best variant and on multiple anchors around and above the target skill region.
- Plot: `outputs/best_variant_elo_assessment_smoke_v3/elo_score_curve.png`.

