# Stratified Variant Experiment Design

This note turns the current repo state into a single experiment plan for:

- broad random-variant diversity
- legality and perft screening
- anchored Elo assessment
- controlled ablations that separate configurable feature effects from commonality effects

It is intentionally based on artifacts and scripts that already exist in this repository.

## 1. Existing Pieces To Reuse

The repo already has the right ingredients, but they are split across several scripts and outputs.

### 1.1 Random sampling and perft

- `scripts/perft_random_variants.py`
- `scripts/random_tournament_then_perft.py`
- `outputs/perft_random_variants.csv`
- `outputs/perft_random_variants.json`

These established that:

- random legal selection from `outputs/feature_model.json` works
- legality and perft are the first gate
- many random legal variants still fail correctness if the feature combination is too weak or incomplete

### 1.2 Fixed control variants

The repo already has meaningful fixed controls:

- worst preset: `c_engine_pl/variants/phase1_minimax.json`
- canonical random/reference preset: `c_engine_pl/variants/phase2_10x12_ab_pvs_id.json`
- best preset: `c_engine_pl/variants/phase3_full_eval.json`
- strongest empirical variant so far: `outputs/improved_variants/strong_variant_02.json`

The first three are the minimum fixed trio that should always be included in the study.

### 1.3 Anchored Elo

- `scripts/proper_elo_tournament.py`
- `scripts/sf_anchor_match.py`
- `outputs/proper_elo_tournament_strong_v1/`
- `outputs/sf2500_best_variant_st2_4g/`
- `outputs/sf2500_after_commonality_opt_clean/`

This already gives:

- Stockfish anchor profiles
- an anchored logistic Elo estimator
- opening-suite handling
- equal-condition tournament infrastructure

### 1.4 Controlled family experiments already present

- board family: `outputs/phase2_multi_probe_suite/`
- eval family: `outputs/phase3_eval_assessment/`
- fixed equal-condition best/worst/random: `outputs/controlled_equal_condition_tournament_best_worst_random/`
- setup-vs-controlled contrast: `outputs/setup_vs_controlled_comparison.csv`

### 1.5 Commonality evidence already present

- `outputs/commonality_opt_baseline_before.json`
- `outputs/commonality_opt_round3_comparison.csv`
- `outputs/commonality_opt_report.md`
- `outputs/sf2500_best_variant_st2_4g/summary.json`
- `outputs/sf2500_after_commonality_opt_clean/summary.json`

This is the key material for separating shared-engine commonality improvements from selectable feature effects.

## 2. Recommended Experiment Structure

The experiment should be staged, not monolithic.

### Stage A. Stratified random sample

Sample `N` legal random variants from `outputs/feature_model.json`, but do not keep a plain iid sample. Instead stratify by the three main variability axes already implemented in the C engine:

- board family
  - `Bitboards`
  - `0x88`
  - `Mailbox`
  - `10x12 Board`
- search tier
  - `minimax`
  - `negamax`
  - `alpha_beta`
  - `pvs_id`
  - `pruning_full`
- eval tier
  - `material_eval`
  - `pst_eval`
  - `structural_eval`
  - `rich_eval`

Recommended large-screen default:

- `N = 100` random variants
- plus the fixed controls

Rationale:

- 100 is large enough to show real structural diversity across strata
- it supports a later `N' = 20` game-stage shortlist without collapsing back to a toy sample

### Stage B. Legality and perft gate

For every sampled and fixed variant:

1. derive
2. build
3. UCI smoke
4. start-position perft through depth 5
5. legal-bestmove probes on a small curated position suite

Depth 5 is the right default because it is already the repo-wide correctness threshold used in earlier reports.

The curated probe suite should include at least:

- `startpos`
- a castling-sensitive middlegame FEN
- an en-passant window FEN
- a promotion-race FEN

Only variants that pass the full screen should go to the game stage.

### Stage C. Small game-diversity stage

Use a shortlist `N' = 20`, chosen from the screened pool.

Recommended composition:

- 4 fixed controls
- 16 sampled variants chosen for structural diversity and perft-band diversity

The goal here is not reliable Elo. The goal is to show a spread of playing strength.

Two good low-cost options are:

1. internal round-robin among the 20 variants
2. the same 20 variants plus 1 or 2 weak/mid Stockfish anchors such as `1320` and `1800`

This gives a diversity picture without pretending to deliver stable ratings.

### Stage D. Optional anchored Elo follow-up

If later needed, reuse `scripts/proper_elo_tournament.py` on a much smaller shortlist with the existing four anchors:

- `1320`
- `1800`
- `2150`
- `2500`

That stage is optional here. It is not required for the diversity claim.

## 3. Controlled Ablations

The controlled part should be split into feature-family ablations and commonality comparisons.

### 3.1 Feature-family ablations

These can reuse committed configs directly.

#### Search core ladder

- `c_engine_pl/variants/phase1_minimax.json`
- `c_engine_pl/variants/phase1_negamax.json`
- `c_engine_pl/variants/phase1_negamax_ab.json`
- `c_engine_pl/variants/phase1_negamax_ab_pvs_id.json`

Interpretation:

- isolates search-stack enrichment on a relatively simple engine baseline

#### Board backend family

- `c_engine_pl/variants/phase2_bitboards_ab_pvs_id.json`
- `c_engine_pl/variants/phase2_magic_bitboards_ab_pvs_id.json`
- `c_engine_pl/variants/phase2_0x88_ab_pvs_id.json`
- `c_engine_pl/variants/phase2_mailbox_piece_lists_ab_pvs_id.json`
- `c_engine_pl/variants/phase2_10x12_ab_pvs_id.json`

Interpretation:

- isolates backend effects with a shared search/eval profile

#### Evaluation ladder

- `c_engine_pl/variants/phase3_material_only.json`
- `c_engine_pl/variants/phase3_pst_pawn.json`
- `c_engine_pl/variants/phase3_full_eval.json`

Interpretation:

- isolates evaluation richness on a shared search/board profile

#### Search refinements on a strong baseline

- `c_engine_pl/variants/phase3_full_eval.json`
- `c_engine_pl/variants/phase3_negamax_ab_id_pruning_full_eval.json`

Interpretation:

- isolates pruning and advanced ordering on top of a strong board/eval stack

### 3.2 Commonality comparisons

These should not be rerun as if they were feature toggles. The repo already contains the correct before/after evidence on the same feature profile.

Use:

- `outputs/commonality_opt_baseline_before.json`
- `outputs/commonality_opt_round3_comparison.csv`
- `outputs/sf2500_best_variant_st2_4g/summary.json`
- `outputs/sf2500_after_commonality_opt_clean/summary.json`

Interpretation:

- same feature profile
- shared-engine implementation changed
- therefore the delta is commonality, not a selectable feature effect

That is the clean separation the paper-style analysis needs.

## 4. Plots To Produce

The useful plots are not generic dashboards. They should answer specific questions.

### 4.1 Diversity plots on the random pool

1. `perft_sec` vs `selected_feature_count`
   - color by `board_family`
   - label the fixed controls

2. board-family mean or distribution of `perft_sec`
   - shows backend-dependent cost structure

3. stratum occupancy heatmap
   - rows = board family
   - columns = search tier
   - cell annotation = count or mean eval tier richness

### 4.2 Strength plots after Elo

4. anchored Elo vs `perft_sec`
   - answers whether faster perft correlates with strength in this SPL

5. anchored Elo by search tier
   - box/strip plot

6. anchored Elo by eval tier
   - box/strip plot

7. anchored Elo ladder plots for:
   - search core ladder
   - board family
   - eval ladder

### 4.3 Commonality separation plots

8. before/after commonality timed-search depth and nps
   - same feature profile

9. before/after commonality anchor score
   - same feature profile

This pair is what prevents feature and commonality effects from being conflated.

## 5. Practical Run Order

Recommended order:

1. prepare `N=100` stratified sample and manifests
2. run correctness + perft on the whole pool
3. discard failures
4. choose a diverse `N'=20` shortlist
5. run a low-cost diversity tournament on that shortlist
6. optionally run a smaller anchored Elo follow-up
7. run the committed feature-family ablations
8. analyze commonality using archived before/after outputs

## 6. Lightweight Repo Support

The repo now includes:

- `scripts/stratified_variant_experiment.py`
- `scripts/variant_diversity_tournament.py`

The preparation helper does four things:

- prepares a stratified sample manifest
- records the fixed controls and the ablation families
- optionally runs derive/build/correctness/perft and emits simple plot-ready SVGs
- prepares a `game_shortlist.csv` for the `N'=20` stage

Example:

```bash
PYTHONPATH=src python3 scripts/stratified_variant_experiment.py \
  --count 100 \
  --build-perft \
  --perft-depth 5 \
  --correctness-depth 2 \
  --shortlist-count 20 \
  --out-dir outputs/stratified_variant_experiment
```

Generated artifacts include:

- `sample_manifest.csv`
- `controls_manifest.csv`
- `ablation_manifest.csv`
- `perft_screen.csv` when requested
- `correctness_probes.csv` when requested
- `game_shortlist.csv` when requested
- `plots/perft_vs_feature_count.svg`
- `plots/perft_by_board.svg`
- `report.md`

Then run the shortlist diversity tournament:

```bash
PYTHONPATH=src python3 scripts/variant_diversity_tournament.py \
  --variant-config path/to/shortlist_variant_01.json \
  --variant-config path/to/shortlist_variant_02.json \
  --variant-config path/to/shortlist_variant_03.json \
  --depth 3 \
  --rounds 1 \
  --games-per-encounter 2 \
  --out-dir outputs/variant_diversity_tournament
```

## 7. Main Analytical Rule

Use this rule consistently:

- if the feature set changes, read the effect as configurable feature variability
- if the feature set is constant and only the shared engine implementation changed, read the effect as commonality

That is the core distinction this experiment should preserve.
