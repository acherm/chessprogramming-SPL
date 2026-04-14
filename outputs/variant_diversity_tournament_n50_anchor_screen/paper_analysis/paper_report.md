# N'=50 Anchor-Screen Analysis

## Design Setup

- screened population: `50` variants selected from the perft-6 stratified pool (`4` fixed controls + `46` sampled variants)
- anchors: `sf1500`, `sf2000`, `sf2500`
- time control: `10+0.1`
- schedule: each variant plays `4` games against each anchor (`12` games total per variant), for `600` games overall

## Rationale

- A full `53`-player round-robin at the same `rounds=2`, `games-per-encounter=2` setting would require `5512` games.
- The anchor-only screen uses `600` games instead, a reduction of `89.1%`.
- This stage is intentionally a harsh screening phase: it is designed to prune clearly weak variants, keep a compact set of promising survivors, and retain some diverse weak/mid representatives for a later full round-robin.

## Key Findings

- Only `3/50` variants scored above `50%` against the anchor ensemble.
- `14/50` variants scored at least one point but stayed at or below `50%` overall.
- `33/50` variants collapsed to `0/12` against the anchor trio.
- Against individual anchors: `5` variants beat `sf1500`, `2` beat `sf2000`, `0` beat `sf2500`; `2` variants drew `sf2500` head-to-head.
- Perft-6 runtime remains a weak proxy for strength in this stage (`r = -0.107`).
- Search-tier signal is strong in this sample: every `alpha_beta` variant scored `0`, while the `pvs_id` family had the highest mean score.

## Interpretation

- The screen clearly separates a tiny top tier, a small positive middle, and a large collapsed weak tail.
- The surviving top tier is architecturally diverse rather than monolithic: the three best variants come from `Bitboards/pvs_id/rich_eval`, `10x12 Board/pvs_id/pst_eval`, and `0x88/minimax/structural_eval` respectively.
- The result is useful for selection, not Elo calibration: twelve games per variant are enough to identify obviously weak and obviously promising candidates, but not enough to fully resolve the positive middle.

## Top Variants

- `phase3_full_eval`: `10.0/12` (`83.3%`), `sf1500=4.0/4`, `sf2000=4.0/4`, `sf2500=2.0/4`, `Bitboards`, `pvs_id`, `rich_eval`, `perft6=3.285s`
- `phase2_10x12_ab_pvs_id`: `7.5/12` (`62.5%`), `sf1500=4.0/4`, `sf2000=1.5/4`, `sf2500=2.0/4`, `10x12 Board`, `pvs_id`, `pst_eval`, `perft6=1.745s`
- `stratified_variant_28`: `7.5/12` (`62.5%`), `sf1500=4.0/4`, `sf2000=2.5/4`, `sf2500=1.0/4`, `0x88`, `minimax`, `structural_eval`, `perft6=1.582s`
- `stratified_variant_09`: `4.0/12` (`33.3%`), `sf1500=4.0/4`, `sf2000=0.0/4`, `sf2500=0.0/4`, `0x88`, `pruning_full`, `rich_eval`, `perft6=2.888s`
- `strong_variant_02`: `4.0/12` (`33.3%`), `sf1500=2.0/4`, `sf2000=2.0/4`, `sf2500=0.0/4`, `Bitboards`, `pruning_full`, `rich_eval`, `perft6=2.994s`
- `stratified_variant_90`: `3.5/12` (`29.2%`), `sf1500=2.0/4`, `sf2000=1.5/4`, `sf2500=0.0/4`, `Mailbox`, `pruning_full`, `rich_eval`, `perft6=2.240s`
- `stratified_variant_31`: `3.0/12` (`25.0%`), `sf1500=3.0/4`, `sf2000=0.0/4`, `sf2500=0.0/4`, `Mailbox`, `minimax`, `structural_eval`, `perft6=1.759s`
- `stratified_variant_61`: `3.0/12` (`25.0%`), `sf1500=2.0/4`, `sf2000=1.0/4`, `sf2500=0.0/4`, `10x12 Board`, `minimax`, `rich_eval`, `perft6=1.714s`

## Weak Tail

- zero-score variants: `33`
- `phase1_minimax`: `Bitboards`, `minimax`, `material_eval`, `perft6=3.470s`
- `stratified_variant_03`: `10x12 Board`, `pruning_full`, `rich_eval`, `perft6=1.592s`
- `stratified_variant_04`: `0x88`, `minimax`, `pst_eval`, `perft6=1.632s`
- `stratified_variant_07`: `10x12 Board`, `minimax`, `structural_eval`, `perft6=1.917s`
- `stratified_variant_10`: `Bitboards`, `minimax`, `structural_eval`, `perft6=25.467s`
- `stratified_variant_11`: `Mailbox`, `minimax`, `rich_eval`, `perft6=1.618s`
- `stratified_variant_17`: `10x12 Board`, `alpha_beta`, `rich_eval`, `perft6=10.966s`
- `stratified_variant_21`: `Bitboards`, `alpha_beta`, `structural_eval`, `perft6=4.039s`
- `stratified_variant_23`: `Mailbox`, `minimax`, `material_eval`, `perft6=1.847s`
- `stratified_variant_29`: `Mailbox`, `alpha_beta`, `structural_eval`, `perft6=2.343s`

## Recommended Stage 2

- recommended subset size: `16` variants plus the same three anchors
- estimated full round-robin cost for that stage: `684` games
- prepared subset file: `stage2_round_robin_subset_16.csv`
- selection rule: keep the four controls, include all non-control survivors, then add diverse positive-middle variants and a few diverse zero-score weak variants so the later round-robin can still expose internal structure among the weak tail.

## Figure Set

- `plots/anchor_screen_score_ladder.png`: overall sorted ladder with anchor reference lines.
- `plots/anchor_matchup_heatmap.png`: direct scores against `sf1500`, `sf2000`, `sf2500`.
- `plots/score_vs_perft6.png`: anchor-screen score vs perft-6 runtime.
- `plots/screen_outcome_bands.png`: survivor / positive / zero counts.
- `plots/score_by_search_tier.png`: mean score by search tier.
- `plots/score_by_board_family.png`: mean score by board family.
