# Setup Variability Model

This note separates compile-time variability from runtime setup variability.

## 1. Variant vs Setup

- `variant`: a compile-time selection of engine features such as `Negamax`, `Alpha-Beta`, `Bitboards`, or `Opening Book`
- `setup`: runtime and harness choices applied after the variant is compiled

The practical evaluation target is therefore:

- `(variant, setup)`

not only `variant`.

## 2. What Counts As Setup Here

Only implemented setup variability is modeled.

Included:

- search-limit mode:
  - `Fixed Depth`
  - `Fixed MoveTime`
  - `Clock Managed`
- search-limit refinements:
  - depth bands: shallow / medium / deep
  - movetime bands: short / medium / long
  - clock refinements: increment-aware / moves-to-go-aware
- opening-book runtime control:
  - `Own Book Disabled`
  - `Own Book Enabled`
  - `Default Book File`
  - `Custom Book File`
- pondering runtime control:
  - `Ponder Disabled`
  - `Ponder Enabled`

Excluded on purpose:

- `Threads`
- `Hash`
- SMP / parallel runtime knobs

Those are excluded because the current engine does not expose them as real setup options.

## 3. Why This Is A Feature Model

Runtime setup still exhibits structured variability:

- some choices are alternatives:
  - `Fixed Depth` vs `Fixed MoveTime` vs `Clock Managed`
- some are refinements:
  - shallow / medium / deep depth
- some have dependencies:
  - `Custom Book File -> Own Book Enabled`
  - `Increment Aware -> Clock Managed`

The generated setup model is exported to:

- `/Users/mathieuacher/SANDBOX/chessprogramming-vm/outputs/setup_feature_model.json`
- `/Users/mathieuacher/SANDBOX/chessprogramming-vm/outputs/setup_feature_model.featureide.xml`

## 4. Recommendation Policy

Recommendations are scenario-oriented rather than pretending that one setup is globally best.

Per variant, the generator recommends:

- an analysis setup
- a match setup
- a runtime book policy
- a runtime ponder policy

The main heuristic is:

- weak search stacks such as plain `Minimax` should stay on shallow fixed depth or small exact movetime
- stronger search stacks with `Alpha-Beta`, `PVS`, `TT`, and ordering features can justify deeper depth bands
- `Clock Managed` is recommended only when the compile-time variant actually selects `Time Management`
- `Opening Book` should usually be enabled in match play and disabled in perft / search analysis
- `Pondering` should only be enabled when the GUI supports `go ponder` / `ponderhit` and the time control is long enough

## 5. Generated Tables

The current recommendation tables are exported to:

- `/Users/mathieuacher/SANDBOX/chessprogramming-vm/outputs/setup_recommendations_by_variant.csv`
- `/Users/mathieuacher/SANDBOX/chessprogramming-vm/outputs/setup_recommendations_by_variant.md`
- `/Users/mathieuacher/SANDBOX/chessprogramming-vm/outputs/setup_recommendations_by_feature.csv`
- `/Users/mathieuacher/SANDBOX/chessprogramming-vm/outputs/setup_recommendations_by_feature.md`

The per-feature table is intentionally conservative:

- it gives strong guidance only for features that truly affect setup policy
- it marks many evaluation leaves as `no direct setup-specific change`

That is deliberate. Most evaluation terms change engine behavior, not runtime setup policy.
