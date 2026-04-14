# Realistic Tournament Analysis

## Design

- Candidate pool: `N=100` stratified variants were screened earlier with legality checks and perft-6; this run evaluates the resulting `N'=50` shortlist under real games.
- Goal: measure diversity of *playing strength*, not just move-generation cost, via a full round-robin that exposes internal matchup structure.
- Tournament setup: `53` total players (`50` variants + `3` Stockfish anchors), pairing mode `full`, `1378` unique pairings, `4` games per pairing.
- Search mode: `time control 10+0.1`.
- Schedule: `5512` finished games, `208` games per player.
- Opening suite: `8` fixed opening lines repeated across encounters.

## Rationale

- The earlier anchor-only screen was cheaper, but it could only place variants relative to Stockfish profiles.
- This full round-robin is much more expensive, but it supports stronger claims about internal strength structure, matchup-specific behavior, and representative weak/mid/strong selection.

## Key Findings

- Strength diversity is large: variant scores range from `2.4%` to `93.5%`.
- The strongest variant is `stratified_variant_28` at `93.5%`; the weakest is `stratified_variant_98` at `2.4%`.
- `14` variants finished above `sf1500` in the overall table, `3` finished above `sf2000`, and `0` finished above `sf2500`.
- Head-to-head anchor results are also diverse: `10` variants scored above 50% against `sf1500`, `2` against `sf2000`, `0` against `sf2500`, and `1` drew `sf2500` exactly.
- Perft-6 runtime remains only weakly related to playing strength (`r = -0.360`), so move-generation speed is not a reliable proxy for tournament performance.
- The strongest mean board family in this shortlist is `Bitboards` (`53.3%` mean score); the strongest mean search tier is `pvs_id` (`85.5%`).
- Among the fixed controls, `phase2_10x12_ab_pvs_id` is best at `93.3%`.

## Buckets

- strong (`>88.0%`, above `sf2000` overall): `stratified_variant_28`, `phase2_10x12_ab_pvs_id`, `phase3_full_eval`
- mid (`74.0%` to `88.0%`): `stratified_variant_31`, `strong_variant_02`, `stratified_variant_61`, `stratified_variant_13`, `stratified_variant_09`, `stratified_variant_72`, `stratified_variant_90`, `stratified_variant_33`, `stratified_variant_82`, `stratified_variant_18`, `stratified_variant_02`
- weak (`<74.0%`, below `sf1500` overall): `stratified_variant_27`, `stratified_variant_100`, `stratified_variant_65`, `stratified_variant_64`, `stratified_variant_46`, `stratified_variant_57`, `stratified_variant_70`, `stratified_variant_58`, `phase1_minimax`, `stratified_variant_97`, `stratified_variant_43`, `stratified_variant_21`, `stratified_variant_60`, `stratified_variant_11`, `stratified_variant_07`, `stratified_variant_52`, `stratified_variant_04`, `stratified_variant_63`, `stratified_variant_29`, `stratified_variant_87`, `stratified_variant_23`, `stratified_variant_42`, `stratified_variant_45`, `stratified_variant_50`, `stratified_variant_69`, `stratified_variant_78`, `stratified_variant_93`, `stratified_variant_59`, `stratified_variant_03`, `stratified_variant_66`, `stratified_variant_39`, `stratified_variant_55`, `stratified_variant_10`, `stratified_variant_17`, `stratified_variant_91`, `stratified_variant_98`

## Top Variants

- `stratified_variant_28`: `93.5%`, `0x88`, `minimax`, `structural_eval`, `perft6=1.582s`
- `phase2_10x12_ab_pvs_id`: `93.3%`, `10x12 Board`, `pvs_id`, `pst_eval`, `perft6=1.745s`
- `phase3_full_eval`: `93.3%`, `Bitboards`, `pvs_id`, `rich_eval`, `perft6=3.285s`
- `stratified_variant_31`: `86.8%`, `Mailbox`, `minimax`, `structural_eval`, `perft6=1.759s`
- `strong_variant_02`: `84.6%`, `Bitboards`, `pruning_full`, `rich_eval`, `perft6=2.994s`

## Weak Tail

- `stratified_variant_55`: `9.9%`, `0x88`, `pruning_full`, `rich_eval`, `perft6=1.916s`
- `stratified_variant_10`: `3.4%`, `Bitboards`, `minimax`, `structural_eval`, `perft6=25.467s`
- `stratified_variant_17`: `2.9%`, `10x12 Board`, `alpha_beta`, `rich_eval`, `perft6=10.966s`
- `stratified_variant_91`: `2.9%`, `Mailbox`, `alpha_beta`, `rich_eval`, `perft6=11.702s`
- `stratified_variant_98`: `2.4%`, `0x88`, `minimax`, `rich_eval`, `perft6=2.808s`

## Figure Set

- `plots/strength_vs_perft6_publication.png`: final publication-oriented version with numbered callouts and a compact key.
- `plots/score_ladder.png`: full 53-player score ladder with anchors and weak/mid/strong variant bands.
- `plots/strength_vs_perft6.png`: tournament score versus perft-6 runtime, with anchor score lines.
- `plots/anchor_matchup_heatmap.png`: direct head-to-head scores against `sf1500`, `sf2000`, and `sf2500`.
- `plots/representative_pairwise_heatmap.png`: representative pairwise matrix showing internal matchup structure beyond anchors.
- `plots/score_by_board_family.png`: mean score by board family.
- `plots/score_by_search_tier.png`: mean score by search tier.
- `plots/score_by_eval_tier.png`: mean score by eval tier.
- `plots_gray/*.png`: grayscale journal-style versions of the PNG figures.

## Representative Set

- `representative_variants.csv`: nine representative variants selected from the full round-robin (`3` strong, `3` mid, `3` weak).
- Selection rule: top / median / bottom within each bucket, with light diversity preference across board family, search tier, and eval tier.

## Caveats

- This is a strong diversity benchmark, but it is still not a formal Elo study.
- The bucket labels are relative to overall round-robin score, not calibrated rating intervals.
- The anchor trio improves interpretability, but conclusions about strength should rely on the full interaction graph, not on any single anchor alone.
