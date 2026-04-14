# CCRL-Style Elo Calibration at 120+1

This repository can now run a local anchored Elo calibration at `120+1` using external anchor engines with published ratings.

Important interpretation rule:

- A run at `120+1` can be described as CCRL-blitz-style only if the anchors are exact CCRL-listed engines with their published CCRL Blitz ratings.
- It should not be described as "anchored to CCRL 40/4" unless the anchors and protocol actually correspond to that list.
- Using Stockfish `UCI_Elo` values is a local anchor ladder, not a CCRL anchor.

Expected anchor CSV format:

- `name`: engine label used in reports
- `cmd`: executable path
- `elo`: published external rating used as the fixed anchor value
- `uci_options`: optional `|`-separated UCI options
- `selected_features`: optional `|`-separated descriptive tags

Template:

- [configs/ccrl_blitz_anchors_template.csv](/Users/mathieuacher/SANDBOX/chessprogramming-vm/configs/ccrl_blitz_anchors_template.csv)

Recommended command for the best variant:

```bash
PYTHONPATH=src python3 scripts/best_variant_elo_assessment.py \
  --tc 120+1 \
  --anchor-spec-csv configs/ccrl_blitz_anchors.csv \
  --out-dir outputs/best_variant_ccrl_blitz_120p1
```

If exact CCRL anchor binaries are not available locally, the honest fallback is:

- run at `120+1`
- use Stockfish `UCI_Elo` or other local anchors
- report the result as a local anchored Elo, not as a CCRL-anchored Elo
