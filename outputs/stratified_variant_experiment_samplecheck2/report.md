# Stratified Variant Experiment Plan

## Goal

- Draw a diverse legal sample of random variants.
- Keep fixed controls for the presumed worst, canonical random, and best presets.
- Screen everything for legality/perft first.
- Then reuse the existing anchored Elo harness on the screened pool or a selected shortlist.

## Fixed Controls

- `worst_preset`: `phase1_minimax` -> `/Users/mathieuacher/SANDBOX/chessprogramming-vm/c_engine_pl/variants/phase1_minimax.json`
- `reference_random`: `phase2_10x12_ab_pvs_id` -> `/Users/mathieuacher/SANDBOX/chessprogramming-vm/c_engine_pl/variants/phase2_10x12_ab_pvs_id.json`
- `best_preset`: `phase3_full_eval` -> `/Users/mathieuacher/SANDBOX/chessprogramming-vm/c_engine_pl/variants/phase3_full_eval.json`
- `best_empirical`: `strong_variant_02` -> `/Users/mathieuacher/SANDBOX/chessprogramming-vm/outputs/improved_variants/strong_variant_02.json`

## Random Sample

- requested random variants: `10`
- selected random variants: `10`
- observed strata: `10`

### Coverage by Board

- `0x88`: `3`
- `10x12 Board`: `3`
- `Bitboards`: `1`
- `Mailbox`: `3`

### Coverage by Search Tier

- `alpha_beta`: `1`
- `minimax`: `3`
- `negamax`: `2`
- `pruning_full`: `4`

### Coverage by Eval Tier

- `rich_eval`: `10`

## Elo Reuse Plan

- Quick screen: run anchors on the controls plus the full stratified pool with a shallow budget to bracket obvious weak/strong regions.
- Full estimation: run `scripts/proper_elo_tournament.py` on a shortlist chosen for both strength and diversity, not only on the top perft performers.

Suggested quick anchored tournament command:

```bash
PYTHONPATH=src python3 scripts/proper_elo_tournament.py --variant-config /Users/mathieuacher/SANDBOX/chessprogramming-vm/c_engine_pl/variants/phase1_minimax.json --variant-config /Users/mathieuacher/SANDBOX/chessprogramming-vm/c_engine_pl/variants/phase2_10x12_ab_pvs_id.json --variant-config /Users/mathieuacher/SANDBOX/chessprogramming-vm/c_engine_pl/variants/phase3_full_eval.json --variant-config /Users/mathieuacher/SANDBOX/chessprogramming-vm/outputs/improved_variants/strong_variant_02.json --variant-config outputs/stratified_variant_experiment_samplecheck2/sample_configs/stratified_variant_01.json --variant-config outputs/stratified_variant_experiment_samplecheck2/sample_configs/stratified_variant_02.json --variant-config outputs/stratified_variant_experiment_samplecheck2/sample_configs/stratified_variant_03.json --variant-config outputs/stratified_variant_experiment_samplecheck2/sample_configs/stratified_variant_04.json --variant-config outputs/stratified_variant_experiment_samplecheck2/sample_configs/stratified_variant_05.json --variant-config outputs/stratified_variant_experiment_samplecheck2/sample_configs/stratified_variant_06.json --variant-config outputs/stratified_variant_experiment_samplecheck2/sample_configs/stratified_variant_07.json --variant-config outputs/stratified_variant_experiment_samplecheck2/sample_configs/stratified_variant_08.json --variant-config outputs/stratified_variant_experiment_samplecheck2/sample_configs/stratified_variant_09.json --variant-config outputs/stratified_variant_experiment_samplecheck2/sample_configs/stratified_variant_10.json --depth 3 --rounds 1 --games-per-encounter 2 --out-dir outputs/stratified_variant_experiment_samplecheck2/elo_screen
```

Suggested full anchored tournament command on the fixed controls only:

```bash
PYTHONPATH=src python3 scripts/proper_elo_tournament.py --variant-config /Users/mathieuacher/SANDBOX/chessprogramming-vm/c_engine_pl/variants/phase1_minimax.json --variant-config /Users/mathieuacher/SANDBOX/chessprogramming-vm/c_engine_pl/variants/phase2_10x12_ab_pvs_id.json --variant-config /Users/mathieuacher/SANDBOX/chessprogramming-vm/c_engine_pl/variants/phase3_full_eval.json --variant-config /Users/mathieuacher/SANDBOX/chessprogramming-vm/outputs/improved_variants/strong_variant_02.json --depth 4 --rounds 2 --games-per-encounter 2 --out-dir outputs/stratified_variant_experiment_samplecheck2/elo_controls
```

## Controlled Ablations

- Feature-family ablations reuse existing committed configs rather than inventing new ladders.
- Commonality is separated by comparing archived before/after outputs on the same feature profile.

### Families

- `board_backend_family`: `phase2_bitboards_ab_pvs_id`, `phase2_magic_bitboards_ab_pvs_id`, `phase2_0x88_ab_pvs_id`, `phase2_mailbox_piece_lists_ab_pvs_id`, `phase2_10x12_ab_pvs_id`
- `evaluation_ladder`: `phase3_material_only`, `phase3_pst_pawn`, `phase3_full_eval`
- `search_core_ladder`: `phase1_minimax`, `phase1_negamax`, `phase1_negamax_ab`, `phase1_negamax_ab_pvs_id`
- `search_refinement_pair`: `phase3_full_eval`, `phase3_negamax_ab_id_pruning_full_eval`

### Commonality Comparison Inputs

- `outputs/commonality_opt_baseline_before.json`
- `outputs/commonality_opt_round3_comparison.csv`
- `outputs/sf2500_best_variant_st2_4g/summary.json`
- `outputs/sf2500_after_commonality_opt_clean/summary.json`

## Plot Set

- `perft_vs_feature_count.svg`: fast diversity view for the screened pool.
- `perft_by_board.svg`: board-family throughput differences.
- After Elo: plot `anchored_elo` vs `perft_sec`, color by `board_family`, shape by `search_tier`, and label the fixed controls.
- For the ablations: use ladder plots for search, board, evaluation, and commonality before/after.
