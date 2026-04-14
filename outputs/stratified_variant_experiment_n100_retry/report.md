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

- requested random variants: `100`
- selected random variants: `100`
- observed strata: `30`

### Coverage by Board

- `0x88`: `23`
- `10x12 Board`: `24`
- `Bitboards`: `25`
- `Mailbox`: `28`

### Coverage by Search Tier

- `alpha_beta`: `22`
- `minimax`: `30`
- `negamax`: `21`
- `pruning_full`: `24`
- `pvs_id`: `3`

### Coverage by Eval Tier

- `material_eval`: `1`
- `pst_eval`: `3`
- `rich_eval`: `85`
- `structural_eval`: `11`

## Correctness and Perft Screen

- variants screened: `104`
- passed perft: `104/104`
- passed correctness probes: `104/104`
- passed full screen: `104/104`
- depth used: `5`
- probe depth used: `2`
- scatter plot: `outputs/stratified_variant_experiment_n100_retry/plots/perft_vs_feature_count.svg`
- board bar plot: `outputs/stratified_variant_experiment_n100_retry/plots/perft_by_board.svg`

## Elo Reuse Plan

- Quick screen: run anchors on the controls plus the full stratified pool with a shallow budget to bracket obvious weak/strong regions.
- Full estimation: run `scripts/proper_elo_tournament.py` on a shortlist chosen for both strength and diversity, not only on the top perft performers.

Suggested quick anchored tournament command:

```bash
PYTHONPATH=src python3 scripts/proper_elo_tournament.py --variant-config /Users/mathieuacher/SANDBOX/chessprogramming-vm/c_engine_pl/variants/phase1_minimax.json --variant-config /Users/mathieuacher/SANDBOX/chessprogramming-vm/c_engine_pl/variants/phase2_10x12_ab_pvs_id.json --variant-config /Users/mathieuacher/SANDBOX/chessprogramming-vm/c_engine_pl/variants/phase3_full_eval.json --variant-config /Users/mathieuacher/SANDBOX/chessprogramming-vm/outputs/improved_variants/strong_variant_02.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_01.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_02.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_03.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_04.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_05.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_06.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_07.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_08.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_09.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_10.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_11.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_12.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_13.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_14.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_15.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_16.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_17.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_18.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_19.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_20.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_21.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_22.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_23.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_24.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_25.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_26.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_27.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_28.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_29.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_30.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_31.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_32.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_33.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_34.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_35.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_36.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_37.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_38.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_39.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_40.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_41.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_42.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_43.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_44.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_45.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_46.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_47.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_48.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_49.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_50.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_51.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_52.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_53.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_54.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_55.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_56.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_57.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_58.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_59.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_60.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_61.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_62.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_63.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_64.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_65.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_66.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_67.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_68.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_69.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_70.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_71.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_72.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_73.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_74.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_75.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_76.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_77.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_78.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_79.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_80.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_81.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_82.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_83.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_84.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_85.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_86.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_87.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_88.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_89.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_90.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_91.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_92.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_93.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_94.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_95.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_96.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_97.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_98.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_99.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_100.json --depth 3 --rounds 1 --games-per-encounter 2 --out-dir outputs/stratified_variant_experiment_n100_retry/elo_screen
```

Suggested full anchored tournament command on the fixed controls only:

```bash
PYTHONPATH=src python3 scripts/proper_elo_tournament.py --variant-config /Users/mathieuacher/SANDBOX/chessprogramming-vm/c_engine_pl/variants/phase1_minimax.json --variant-config /Users/mathieuacher/SANDBOX/chessprogramming-vm/c_engine_pl/variants/phase2_10x12_ab_pvs_id.json --variant-config /Users/mathieuacher/SANDBOX/chessprogramming-vm/c_engine_pl/variants/phase3_full_eval.json --variant-config /Users/mathieuacher/SANDBOX/chessprogramming-vm/outputs/improved_variants/strong_variant_02.json --depth 4 --rounds 2 --games-per-encounter 2 --out-dir outputs/stratified_variant_experiment_n100_retry/elo_controls
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

## N'=20 Game Diversity Stage

- shortlist target: `20`
- shortlist size prepared: `20`
- fixed controls remain in the shortlist
- remaining slots are filled from screen-passing random variants using stratified structural coverage plus fast/mid/slow perft bands

Suggested internal diversity tournament:

```bash
PYTHONPATH=src python3 scripts/variant_diversity_tournament.py --variant-config /Users/mathieuacher/SANDBOX/chessprogramming-vm/c_engine_pl/variants/phase1_minimax.json --variant-config /Users/mathieuacher/SANDBOX/chessprogramming-vm/c_engine_pl/variants/phase2_10x12_ab_pvs_id.json --variant-config /Users/mathieuacher/SANDBOX/chessprogramming-vm/c_engine_pl/variants/phase3_full_eval.json --variant-config /Users/mathieuacher/SANDBOX/chessprogramming-vm/outputs/improved_variants/strong_variant_02.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_94.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_62.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_20.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_04.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_34.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_66.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_49.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_98.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_28.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_81.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_26.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_65.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_87.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_38.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_71.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_92.json --depth 3 --rounds 1 --games-per-encounter 2 --out-dir outputs/stratified_variant_experiment_n100_retry/game_diversity_round_robin
```

Suggested anchor-flavored diversity tournament:

```bash
PYTHONPATH=src python3 scripts/variant_diversity_tournament.py --variant-config /Users/mathieuacher/SANDBOX/chessprogramming-vm/c_engine_pl/variants/phase1_minimax.json --variant-config /Users/mathieuacher/SANDBOX/chessprogramming-vm/c_engine_pl/variants/phase2_10x12_ab_pvs_id.json --variant-config /Users/mathieuacher/SANDBOX/chessprogramming-vm/c_engine_pl/variants/phase3_full_eval.json --variant-config /Users/mathieuacher/SANDBOX/chessprogramming-vm/outputs/improved_variants/strong_variant_02.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_94.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_62.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_20.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_04.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_34.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_66.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_49.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_98.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_28.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_81.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_26.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_65.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_87.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_38.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_71.json --variant-config outputs/stratified_variant_experiment_n100_retry/sample_configs/stratified_variant_92.json --stockfish-profile sf1320:1:1320 --stockfish-profile sf1800:6:1800 --depth 3 --rounds 1 --games-per-encounter 2 --out-dir outputs/stratified_variant_experiment_n100_retry/game_diversity_with_anchors
```
