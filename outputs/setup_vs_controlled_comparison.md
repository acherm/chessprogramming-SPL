# Setup vs Controlled Comparison

| role | variant_name | best_setup_condition | best_setup_score | best_setup_score_pct | controlled_condition | controlled_score | controlled_score_pct |
| --- | --- | --- | --- | --- | --- | --- | --- |
| best | phase3_full_eval | FixedDepth:depth 12-20 (target 14), depth=6 | 4.0 | 100.0 | depth=3 tc=inf | 7.0 | 87.5 |
| random | phase2_10x12_ab_pvs_id | FixedDepth:depth 9-12 (target 10), depth=5 | 2.0 | 50.0 | depth=3 tc=inf | 4.5 | 56.2 |
| worst | phase1_minimax | FixedDepth:depth 3-4 (target 4), depth=3 | 0.0 | 0.0 | depth=3 tc=inf | 0.5 | 6.2 |

Interpretation:
- The best-setup run uses per-variant tuned conditions.
- The controlled run uses one shared condition for all players.
- If a ranking changes between the two, the earlier result was at least partly driven by setup rather than variant strength.