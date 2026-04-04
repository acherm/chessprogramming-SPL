# CPW Variability Pipeline

Automated pipeline that mines chessprogramming.org into a traceable SPL feature model and engine/feature matrix.

## Implementation-Oriented Model

The feature model is mined with a product-line implementation objective:

- Features represent configurable engine variability points, not generic wiki topics.
- Modeled options are implementation-backed (each option maps to concrete code paths in `c_engine_pl/src/search.c`, `c_engine_pl/src/board_backend.c`, `c_engine_pl/src/eval.c`, or `c_engine_pl/src/engine.c`).
- Tournament-legality options are explicitly modeled and implemented (`Castling`, `En Passant`, `Threefold Repetition`, `Fifty-Move Rule`).
- Most options are marked as compile-time variability (`compile_flag`).
- A small subset is marked runtime or mixed (`runtime_flag`).
- Structural groups model variation-point semantics (for example, `BoardRepresentation` is `xor`).

Each feature record in `outputs/feature_model.json` includes:

- `variation_role`: `root`, `group`, or `option`
- `variability_stage`: `compile_time`, `runtime`, or `mixed`
- `compile_flag`: suggested compile-time symbol (for example, `CFG_ALPHA_BETA`)
- `runtime_flag`: suggested runtime switch when relevant

Depth behavior:

- `--depth 1`: root + top-level variation points only
- `--depth 3` (default): root + groups + configurable options
- `--depth 4`: adds intermediate groups such as `Pawn Structure`, `Piece Coordination`, `King Terms`, `Ordering Heuristics`, and `TT Support`
- `--depth 5`: adds binding subfeatures under options (compile/runtime flag layer)

## Safe Crawling and Resume

- Cache-first strategy: pages already in `data/chessprogramming_cache/` are never fetched again.
- Polite requests: crawl delay + retries with exponential backoff.
- `robots.txt` respected by default.
- Discovery state persisted to `data/chessprogramming_cache/discovery_state.json` for resumable runs.

Recommended crawl command:

```bash
PYTHONPATH=src python3 -m cpw_variability.cli fetch \
  --seed implementation \
  --mode snapshot \
  --max-pages 1200 \
  --crawl-delay 2.0 \
  --http-retries 3 \
  --http-backoff 2.0
```

Resume behavior:

- Re-run the same `fetch` command to continue from saved queue/visited state.
- Use `--fresh` to discard previous discovery state and restart traversal.
- Use `--offline` to operate strictly from cache.

Then generate model + matrix from the expanded cache:

```bash
PYTHONPATH=src python3 -m cpw_variability.cli run-all \
  --seed implementation \
  --max-pages 1200 \
  --depth 3 \
  --target-features 200
```

## C Engine Product Line (Compile-Time Derivation)

The repository includes a C product-line implementation in `c_engine_pl/` driven by `outputs/feature_model.json`.

Derive + build + smoke-test a variant from a valid configuration:

```bash
PYTHONPATH=src python3 scripts/derive_variant.py \
  --config c_engine_pl/variants/bitboards_alpha.json \
  --build \
  --smoke
```

Second example variant:

```bash
PYTHONPATH=src python3 scripts/derive_variant.py \
  --config c_engine_pl/variants/alphabeta_0x88.json \
  --build \
  --smoke
```

What this does:

- Resolves selected features against the mined feature model.
- Validates cross-tree constraints (`requires` / `excludes`) and required variation points.
- Enforces implementation constraints for executable variants (for example `Alpha-Beta` requires `Make Move` + `Unmake Move`).
- Enforces tournament-legality requirements for this implementation profile (`Castling`, `En Passant`, `Threefold Repetition`, `Fifty-Move Rule`).
- Generates `c_engine_pl/include/generated/variant_config.h` with compile-time flags.
- Builds `c_engine_pl/build/engine_pl`.
- Runs a UCI smoke flow (`uci`, `isready`, `go`, `quit`).

## Executable Feature Status

The current C engine product line supports real, implementation-backed variability in these families:

- Search core:
  - `Minimax`
  - `Negamax`
  - `Alpha-Beta`
  - `Principal Variation Search`
  - `Iterative Deepening`
  - `Quiescence Search`
- Search refinements:
  - `Move Ordering`
  - `Hash Move`
  - `Killer Heuristic`
  - `History Heuristic`
  - `Aspiration Windows`
  - `Null Move Pruning`
  - `Late Move Reductions`
  - `Futility Pruning`
  - `Razoring`
  - `Delta Pruning`
  - `Transposition Table`
  - `Zobrist Hashing`
  - `Replacement Schemes`
- Board representation:
  - `Bitboards`
  - `Magic Bitboards`
  - `0x88`
  - `Mailbox`
  - `10x12 Board`
  - `Piece Lists`
- Evaluation:
  - `Piece-Square Tables`
  - `Passed Pawn`
  - `Isolated Pawn`
  - `Doubled Pawn`
  - `Connected Pawn`
  - `Bishop Pair`
  - `Rook on Open File`
  - `Rook Semi-Open File`
  - `Mobility`
  - `King Pressure`
  - `King Shelter`
  - `King Activity`
  - `Tapered Eval`
  - `Static Exchange Evaluation`
- Runtime/UCI-exposed behavior:
  - `OwnBook`
  - `BookFile`
  - `Ponder`
  - `go ponder`
  - `ponderhit`

Main architectural and status notes:

- [docs/product_line_architecture_and_interactions.md](docs/product_line_architecture_and_interactions.md)
- [docs/feature_taxonomy_and_strengthening_roadmap.md](docs/feature_taxonomy_and_strengthening_roadmap.md)

Representative validation artifacts:

- `outputs/feature_completion_validation/`
- `outputs/runtime_feature_validation/`

## Runtime Book and Ponder Example

Derive the runtime-feature variant:

```bash
PYTHONPATH=src python3 scripts/derive_variant.py \
  --config c_engine_pl/variants/phase2_runtime_book_ponder.json \
  --build
```

Then exercise external opening-book and asynchronous pondering behavior:

```text
uci
isready
setoption name OwnBook value true
setoption name BookFile value c_engine_pl/books/default_openings.txt
position startpos
go depth 4

setoption name Ponder value true
position startpos moves e2e4 c7c5 g1f3
go ponder depth 6
isready
ponderhit
quit
```

Notes:

- `OwnBook` and `BookFile` are only exposed in variants that select `Opening Book`.
- `Ponder`, `go ponder`, and `ponderhit` are only meaningful in variants that select `Pondering`.
- The default book format is a simple text format with one line per opening:
  - `startpos moves e2e4 e7e5 g1f3 ...`

## Tournament-Legality Scenario Pack

Run the full legality regression pack (castling, en-passant, threefold, 50-move):

```bash
PYTHONPATH=src python3 scripts/uci_legality_scenarios.py
```

This command:

- Derives the selected variant (`bitboards_alpha` by default).
- Builds the engine.
- Runs automated UCI scenarios and fails fast if a legality rule is broken.
- Prints JSON with per-scenario pass/fail details.

Debug helper in UCI:

- `legalmoves` prints all current legal moves as `info string legalmove <uci_move>`.

## Perft Validation On Derived Variant

Run a perft reference check after deriving/building a variant:

```bash
PYTHONPATH=src python3 scripts/uci_perft_check.py --max-depth 4
```

This validates start-position perft counts against known references:

- depth 1: `20`
- depth 2: `400`
- depth 3: `8902`
- depth 4: `197281`

You can extend to depth 5 (`4865609`) with `--max-depth 5`.

Constraint and perft rationale note:

- See [docs/variant_constraints_and_perft.md](docs/variant_constraints_and_perft.md) for:
  - why `Move Generation` is mandatory in executable variants,
  - justification of key cross-tree constraints,
  - expected perft impact/correctness implications of major features.
