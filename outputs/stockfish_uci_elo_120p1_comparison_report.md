# 120+1 Stockfish UCI_Elo Comparison Report

## Goal

Compare the two main candidates selected from the earlier internal tournament under the same long-time-control external calibration protocol.

The compared variants are:

- `phase2_10x12_ab_pvs_id`
- `stratified_variant_28`

## Common Protocol

- opponent family: Stockfish 18 with `UCI_LimitStrength=true`
- time control: `120+1`
- anchor ladder: `2100, 2150, 2200, 2250, 2300, 2350, 2400, 2450, 2500`
- games per anchor: `24`
- total games per candidate: `216`
- estimation method: anchored logistic maximum-likelihood fit

This protocol was chosen to move beyond internal variant-vs-variant rankings and obtain a stronger external strength calibration at the time control used by Stockfish's official `UCI_Elo` documentation.

## Final Results

- `phase2_10x12_ab_pvs_id`: `2301.8 +/- 49.4` Elo
- `stratified_variant_28`: `2176.1 +/- 51.5` Elo

Difference:

- `phase2_10x12_ab_pvs_id` is ahead by about `125.7` Elo

## Interpretation

The internal `N'=50` round-robin had suggested that `stratified_variant_28` was marginally the strongest sampled variant, but the external `120+1` Stockfish calibration tells a different story.
Under the same anchor ladder and game budget, `phase2_10x12_ab_pvs_id` is clearly stronger than `stratified_variant_28`.

So the best-supported conclusion is:

- the strongest externally calibrated variant is `phase2_10x12_ab_pvs_id`, not `stratified_variant_28`

This is exactly why the second-stage calibration mattered: small differences in internal tournament score did not reliably predict strength under a longer and externally anchored protocol.

## Artifacts

`phase2_10x12_ab_pvs_id`:

- `/Users/mathieuacher/SANDBOX/chessprogramming-vm/outputs/phase2_stockfish_uci_elo_120p1/report.md`
- `/Users/mathieuacher/SANDBOX/chessprogramming-vm/outputs/phase2_stockfish_uci_elo_120p1/tournament/elo_estimates.csv`
- `/Users/mathieuacher/SANDBOX/chessprogramming-vm/outputs/phase2_stockfish_uci_elo_120p1/elo_score_curve.png`

`stratified_variant_28`:

- `/Users/mathieuacher/SANDBOX/chessprogramming-vm/outputs/stratified28_stockfish_uci_elo_120p1/report.md`
- `/Users/mathieuacher/SANDBOX/chessprogramming-vm/outputs/stratified28_stockfish_uci_elo_120p1/tournament/elo_estimates.csv`
- `/Users/mathieuacher/SANDBOX/chessprogramming-vm/outputs/stratified28_stockfish_uci_elo_120p1/elo_score_curve.png`
