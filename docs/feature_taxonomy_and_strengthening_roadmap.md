# Feature Taxonomy and Strengthening Roadmap

This note separates three concepts that were previously mixed together under the word "feature".

## 1. Taxonomy

### 1.1 Configurable Features

These are real SPL variation points. They are selectable in a variant configuration and should produce a meaningful implementation difference.

Examples already modeled in the executable product line:

- board representation: `Bitboards`, `Magic Bitboards`, `0x88`, `Mailbox`, `10x12 Board`
- search core: `Minimax`, `Negamax`, `Alpha-Beta`, `Principal Variation Search`, `Iterative Deepening`
- search refinements: `Quiescence Search`, `Aspiration Windows`, `Null Move Pruning`, `Late Move Reductions`
- move ordering family: `Move Ordering`, `Hash Move`, `Killer Heuristic`, `History Heuristic`
- TT family: `Transposition Table`, `Zobrist Hashing`, `Replacement Schemes`, `Pawn Hash Table`
- evaluation leaves: `Passed Pawn`, `Bishop Pair`, `King Pressure`, `King Shelter`, `King Activity`, `Static Exchange Evaluation`
- runtime-selectable behavior: `Opening Book`, `Pondering`

### 1.2 Commonality

These are shared engine services or quality improvements. They matter for strength, but they should not automatically become selectable features.

Examples:

- time-allocation policy and time-manager quality
- TT storage quality, aging, and mate-score normalization
- move-ordering framework quality
- attack-detection and search instrumentation support
- evaluation-support utilities and caches

If a change only makes the baseline engine less naive, it belongs in commonality.

### 1.3 Feature Implementation Debt

These are modeled features whose current implementation is still too weak, partial, or naive.

Current debt items:

- `Opening Book`: now external and runtime-configurable, but still uses a simple text line format rather than a richer exchange format
- `Pondering`: now asynchronous and UCI-visible, but still implemented as repeated background search slices rather than a tighter shared continuation model

This category is important because "the feature exists" and "the feature is correctly implemented" are not the same thing.

## 2. Executable Hierarchy

The executable model is now read with this intent:

- parent feature families explain the implementation area
- optional leaf features are the selectable units
- some intermediate groups exist only to structure the feature space and are not directly selectable

Examples:

- `Move Ordering` is a selectable master feature for the ordering framework
- `Ordering Heuristics` is an intermediate group under `Move Ordering`
  - `Hash Move`
  - `Killer Heuristic`
  - `History Heuristic`

- `Transposition Table` remains a selectable feature
- `TT Support` is an intermediate group for support mechanisms and policies
  - `Zobrist Hashing`
  - `Replacement Schemes`
  - `Pawn Hash Table`

- `King Terms` is an intermediate evaluation group
  - `King Pressure`
  - `King Shelter`
  - `King Activity`

## 3. Priority Roadmap

### 3.1 Configurable Features To Make Real

These are already in the model and should now be strengthened as actual implementation work:

1. `Opening Book`
2. `Pondering`

The goal is not to add new labels, but to make these existing selectable features deserving of their names.

### 3.2 Commonality To Improve

These should improve the baseline engine shared by all variants:

1. time management
2. move-ordering framework quality
3. transposition-table internals
4. king-safety evaluation quality
5. backend ownership strategy for canonical board state

These improvements will benefit both `full` and `full+pruning` style variants.

## 4. Near-Term Engineering Plan

### Batch A: Feature Implementation Debt

Completed:

1. implemented real SEE
2. implemented proper LMR with re-search behavior
3. implemented proper aspiration windows with fail-low / fail-high widening
4. hardened null-move pruning with stronger guards
5. made `Minimax` explicit in the executable model
6. implemented `Magic Bitboards`
7. made `Mailbox` distinct from `10x12 Board`
8. made `Piece Lists` a maintained state structure used by non-bitboard backends
9. made `Opening Book` external and runtime-configurable through `OwnBook` / `BookFile`
10. made `Pondering` asynchronous with `go ponder`, `ponderhit`, and `stop`

### Batch B: Commonality

1. improve time allocation under UCI clocks
2. improve TT quality without changing the feature model
3. strengthen king-safety scoring and threat support
4. keep move-ordering support strong enough that optional ordering features remain meaningful

Current implementation status:

- time allocation now uses `movestogo`, reserve, and increment-aware budgeting instead of a fixed `time/30 + inc/2` rule
- search now uses a soft deadline between completed iterations and a hard deadline inside the tree
- TT storage now uses bucketed replacement with generation aging and mate-score normalization
- move ordering now benefits from real SEE under the `Static Exchange Evaluation` feature
- timed search is no longer implicitly capped at depth `5`
- bitboard attack/movegen hot paths now use precomputed knight/king masks
- legal-move generation now has a king-square cache and a pin/check-aware fast path

### Batch C: Reassessment

After Batch A and Batch B:

1. rerun perft and legality checks
2. rerun external-anchor matches, not only self-play
3. keep the stronger preset as the new baseline best variant
4. maintain a small feature-completion regression set for weak-feature regressions

Current reading after the recent commonality batch:

- the technical objective was met: the best variant now reaches depth `6-7` on the timed probes instead of being stuck near `5`
- however, a 4-game rerun against the Stockfish `~2500` anchor did not improve match score despite the much deeper search
- this means the next priority is search-quality tuning on top of the faster baseline, not further raw-depth chasing

## 5. Modeling Rule Of Thumb

A good configurable feature should answer "yes" to both questions:

- can a user reasonably choose it on or off?
- does toggling it change the derived engine in a meaningful way?

If not, it is probably commonality rather than a feature.
