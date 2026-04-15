# Feature Model Artefacts

The repository ships a 74-feature implementation-backed feature model of the chess engine product line — mined from a 1,316-page chessprogramming.org snapshot and from the C engine product line itself — plus tooling to visualize it and export it to alternative textual formats. The model drives variant derivation, constraint validation, and the experimental infrastructure. Like any model of a real system at this scale it is not final; see *Known limitations and evolution* below for the areas currently under active work.

## Raw artefacts

All under `outputs/`:

| File | Format | Role |
|---|---|---|
| `feature_model.json` | JSON | Canonical mined model (source of truth used by the rest of the pipeline — constraint validator, C variant derivation, setup layer, etc.). |
| `feature_model.featureide.xml` | FeatureIDE XML | Same model exported to FeatureIDE's native schema, consumable by FeatureIDE-compatible tools. |
| `feature_model.uvl` | UVL (Universal Variability Language) | Textual feature-model format. |
| `feature_model.fml` | FAMILIAR FML | Textual feature-model syntax used by the FAMILIAR tool. |
| `feature_model.svg` | SVG | Visual depiction of the tree (left-to-right) with cross-tree constraints panel. |
| `feature_model.svg.png` | PNG | Rasterised preview of the SVG. |

The **canonical representation** for tooling (code generation, variant validation, etc.) is `feature_model.json`. The FeatureIDE XML, UVL, FML, and SVG are all derived views — regenerate them from the JSON/XML whenever the canonical model changes.

## Regenerating the derived artefacts

Two standalone scripts, pure Python, no dependencies:

```bash
# SVG visualization (outputs/feature_model.svg)
python3 scripts/render_feature_model.py

# UVL and FML exports (outputs/feature_model.uvl, outputs/feature_model.fml)
python3 scripts/export_feature_model.py
```

Both scripts read `outputs/feature_model.featureide.xml` and apply the same normalization pipeline (see below), so the textual and graphical views stay in sync.

## Normalization pipeline (subject to discussion)

The mined XML contains some structural artefacts that make the raw tree hard to read. The scripts apply two normalization passes before rendering or exporting. Both are **opinionated** and may not reflect the original modeler's intent.

### 1. Collapse `group "X" / feature "X"` duplicates

Several groups have a child feature whose name matches the group name (modulo case/whitespace):

- `alt name="Evaluation"` contains a `feature name="Evaluation"` child.
- `or name="TranspositionTable"` contains a `feature name="Transposition Table"` child.
- `or name="TimeManagement"` contains a `feature name="Time Management"` child.

The collapse step removes the duplicate child and uses the feature's display name as the group's name. This produces a cleaner tree but **changes the model's semantics**: in the original, the duplicated feature was an alternative of the group (so e.g. you could previously "pick Evaluation standalone" as one of the alternatives); after collapse you must pick one of the remaining children.

### 2. Singleton OR/alt → mandatory

An `or` or `alt` group with exactly one child is semantically equivalent to a mandatory child (*at-least-one of {X}* and *exactly-one of {X}* both force X). The second pass converts such groups into an `and` relationship with the child marked mandatory.

This affects, after the first pass:

- `Opening → Opening Book` (single-child OR already in the source XML).
- `Time Management → Pondering` (singleton after duplicate collapse).
- `Transposition Table → TT Support` (singleton after duplicate collapse).

The visualization then shows a plain mandatory edge (filled circle, no triangle), and UVL / FML emit a `mandatory` block / bare token rather than `or { X }` / `(X)+`.

### Visual conventions used in the SVG

- Rectangle = feature (white) or group node (light blue).
- Filled circle on an edge = mandatory child; empty circle = optional child (applies to `and` parents, including the root).
- Filled triangle = OR group (≥1).
- Empty triangle = alternative / XOR group (exactly one).
- Left-to-right layout; groups with many children are wrapped into a 2-column grid.

## Known limitations and evolution

The model is expected to evolve as mining heuristics, manual curation, and implementation coverage improve. Current known items worth reviewing:

- The `alt`/`or` choice in the mined XML does not always reflect the most natural modeling choice — some groups modeled as `alt` (XOR) may be more faithfully rendered as `or` or even `and` after manual review.
- The duplicate-name artefact described above is a mining artefact; the "right" interpretation is still under discussion.
- Single-child groups (like `Opening → Opening Book`) may or may not be the intent of the miner.
- Cross-tree constraints are extracted heuristically and may be incomplete or overly tight.
- Feature naming mixes CamelCase, hyphenated, and space-separated conventions depending on the source.

Several of these items are already tracked as open issues alongside other improvements to the C engine and the experimental pipeline.
