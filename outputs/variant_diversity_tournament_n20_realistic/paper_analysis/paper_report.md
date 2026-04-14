# Realistic Tournament Analysis

## Setup

- players: `23` total (`20` variants + `3` Stockfish anchors)
- schedule: `1012` finished games, `88` games per player
- search mode: `tc=10+0.1`
- openings: fixed 8-line curated suite, repeated across encounters

## Key Findings

- Strength diversity is large: variant scores range from `2.3%` to `92.0%`.
- The strongest variant is `phase3_full_eval` at `92.0%`; it finished above `sf2500` (`91.5%`) in overall table position.
- `5` variants scored above 50% against `sf1500`; `3` variants scored above 50% against `sf2000`; `0` variants scored above 50% against `sf2500` and `1` drew it head-to-head.
- Perft-6 runtime is only weakly related to playing strength in this shortlist (`r = -0.302`); fast move generation does not predict stronger play.
- Realistic time control substantially reorders the shallow ranking: biggest drop is `stratified_variant_87` (`-55.1` points), biggest gain is `stratified_variant_65` (`+41.5` points).

## Buckets

- strong (`>80.7%`, above `sf2000` overall): `phase3_full_eval`, `stratified_variant_28`, `phase2_10x12_ab_pvs_id`
- mid (`71.6%` to `80.7%`): `stratified_variant_82`, `stratified_variant_61`
- weak (`<71.6%`, below `sf1500` overall): `stratified_variant_09`, `strong_variant_02`, `stratified_variant_65`, `phase1_minimax`, `stratified_variant_97`, `stratified_variant_04`, `stratified_variant_43`, `stratified_variant_87`, `stratified_variant_60`, `stratified_variant_45`, `stratified_variant_78`, `stratified_variant_66`, `stratified_variant_55`, `stratified_variant_17`, `stratified_variant_98`

## Top Variants

- `phase3_full_eval`: `92.0%`, `Bitboards`, `pvs_id`, `rich_eval`, `perft6=3.285s`
- `stratified_variant_28`: `87.5%`, `0x88`, `minimax`, `structural_eval`, `perft6=1.582s`
- `phase2_10x12_ab_pvs_id`: `83.5%`, `10x12 Board`, `pvs_id`, `pst_eval`, `perft6=1.745s`
- `stratified_variant_82`: `75.6%`, `0x88`, `minimax`, `rich_eval`, `perft6=1.546s`
- `stratified_variant_61`: `72.7%`, `10x12 Board`, `minimax`, `rich_eval`, `perft6=1.714s`

## Weak Tail

- `stratified_variant_78`: `27.8%`, `0x88`, `alpha_beta`, `rich_eval`, `perft6=1.885s`
- `stratified_variant_66`: `24.4%`, `0x88`, `minimax`, `rich_eval`, `perft6=1.874s`
- `stratified_variant_55`: `10.8%`, `0x88`, `pruning_full`, `rich_eval`, `perft6=1.916s`
- `stratified_variant_17`: `2.3%`, `10x12 Board`, `alpha_beta`, `rich_eval`, `perft6=10.966s`
- `stratified_variant_98`: `2.3%`, `0x88`, `minimax`, `rich_eval`, `perft6=2.808s`

## Figure Set

- `plots/strength_vs_perft6.svg`: overall strength vs perft-6 runtime, with anchor score lines.
- `plots/anchor_matchup_heatmap.svg`: direct head-to-head scores against `sf1500`, `sf2000`, `sf2500`.
- `plots/rank_shift_shallow_vs_realistic.svg`: score change from the shallow depth-3 run to the realistic time-control run.

## Caveats

- The benchmark is much more realistic than fixed-depth diversity screening, but it still uses limited anchors and a modest opening suite.
- The bucket labels are relative to overall round-robin score, not formal Elo estimation.
- Head-to-head anchor results should be interpreted together with the full table because only four games were played against each anchor per variant.
