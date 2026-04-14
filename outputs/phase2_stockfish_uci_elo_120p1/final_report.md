# Final Report: 120+1 Stockfish UCI_Elo Calibration

## Objective

Estimate the playing strength of the strongest currently identified SPL variant under a realistic long time control, using Stockfish's official weakening mechanism (`UCI_LimitStrength=true`, `UCI_Elo=<target>`) rather than shallow internal tournaments.

The calibrated target variant was:

- `phase2_10x12_ab_pvs_id`
- config: `/Users/mathieuacher/SANDBOX/chessprogramming-vm/c_engine_pl/variants/phase2_10x12_ab_pvs_id.json`

## Experimental Setup

- Opponent family: Stockfish 18
- Time control: `120+1`
- Anchor ladder: `sf2100`, `sf2150`, `sf2200`, `sf2250`, `sf2300`, `sf2350`, `sf2400`, `sf2450`, `sf2500`
- Stockfish settings: `Skill Level=20`, `UCI_LimitStrength=true`, `UCI_Elo=<anchor>`
- Schedule: anchor-only matches
- Games per anchor: `24`
- Total games: `216`
- Estimation method: anchored logistic maximum-likelihood fit over all games

This setup follows the official Stockfish documentation stating that `UCI_Elo` is the relevant control for approximate Elo-limited play, and that its calibration target is the `120+1` regime.

## Main Result

The final anchored estimate is:

- `phase2_10x12_ab_pvs_id = 2301.8 +/- 49.4 Elo (95% CI)`

So the best current estimate is that this variant is roughly in the:

- `2252` to `2351` Elo band

on this machine, with this Stockfish build, this opening suite, and this match protocol.

## Direct Match Results

- vs `sf2100`: `18.0/24` = `75.0%`
- vs `sf2150`: `14.0/24` = `58.3%`
- vs `sf2200`: `13.0/24` = `54.2%`
- vs `sf2250`: `8.5/24` = `35.4%`
- vs `sf2300`: `15.0/24` = `62.5%`
- vs `sf2350`: `10.5/24` = `43.8%`
- vs `sf2400`: `11.0/24` = `45.8%`
- vs `sf2450`: `8.5/24` = `35.4%`
- vs `sf2500`: `10.0/24` = `41.7%`

Overall score against the full ladder:

- `108.5/216` = `50.23%`

## Interpretation

The central conclusion is that the strongest currently identified variant is materially stronger than the earlier short-time-control estimate around `~2190`, and lands instead around `~2300` on Stockfish's `UCI_Elo` scale at `120+1`.

The per-anchor scores are not perfectly monotonic. This is expected at this budget and with Stockfish's internal weakening model: `24` games per anchor still leaves noticeable sampling noise, and `UCI_Elo` is only an approximate external calibration. The anchored logistic fit is therefore more informative than reading each anchor row independently.

The result should be treated as:

- a local anchored Elo estimate
- meaningful for this exact hardware/software/time-control setup
- stronger than the previous diversity-only evidence
- not equivalent to a universal published rating

## Practical Conclusion

For the current SPL and current implementation state, the best supported claim is:

- the strongest discovered variant reaches about `2300` Elo under `120+1` against Stockfish's official `UCI_Elo` ladder

This is a credible, non-trivial playing level for a generated chess-engine variant family, even though it remains far below modern top-engine strength.

## Artifacts

- auto report: `/Users/mathieuacher/SANDBOX/chessprogramming-vm/outputs/phase2_stockfish_uci_elo_120p1/report.md`
- Elo estimates: `/Users/mathieuacher/SANDBOX/chessprogramming-vm/outputs/phase2_stockfish_uci_elo_120p1/tournament/elo_estimates.csv`
- standings: `/Users/mathieuacher/SANDBOX/chessprogramming-vm/outputs/phase2_stockfish_uci_elo_120p1/tournament/standings.csv`
- per-anchor scores: `/Users/mathieuacher/SANDBOX/chessprogramming-vm/outputs/phase2_stockfish_uci_elo_120p1/anchor_scores.csv`
- score curve plot: `/Users/mathieuacher/SANDBOX/chessprogramming-vm/outputs/phase2_stockfish_uci_elo_120p1/elo_score_curve.png`
