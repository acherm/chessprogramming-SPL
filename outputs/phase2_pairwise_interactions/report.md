# Pair-wise Board/Search Interaction Assessment

## Scope

This assessment checks the valid cross-product of representative search stacks from Phase 1 and board representations from Phase 2.

## Summary

- combinations tested: 15
- compiled successfully: 15
- passed start-position perft depth 5: 15

## Interaction observations

- board `0x88` produced 4 distinct probe-node counts across search stacks: [3886, 4383, 1389358, 1389362]
- board `10x12 Board` produced 4 distinct probe-node counts across search stacks: [3886, 4383, 1389358, 1389362]
- board `Bitboards` produced 4 distinct probe-node counts across search stacks: [5265, 5541, 1262340, 1262354]
- search `minimax` produced 2 distinct probe-node counts across board backends: [1262354, 1389362]; best moves: ['b1d2', 'b2b3']
- search `minimax_ab` produced 2 distinct probe-node counts across board backends: [4383, 5265]; best moves: ['b1d2', 'b2b3']
- search `negamax` produced 2 distinct probe-node counts across board backends: [1262340, 1389358]; best moves: ['b1d2', 'b2b3']
- search `negamax_ab` produced 2 distinct probe-node counts across board backends: [4383, 5265]; best moves: ['b1d2', 'b2b3']
- search `negamax_ab_pvs_id` produced 2 distinct probe-node counts across board backends: [3886, 5541]; best moves: ['b1d2', 'b2b3']

## Interpretation

- Search backends and board backends are combinable because the variants compile and remain perft-correct.
- Equal results for some combinations are not automatically suspicious. For example, plain minimax and plain negamax can legitimately traverse equivalent trees and return the same best move.
- Distinct node counts under alpha-beta/PVS combinations are expected because move ordering and backend-specific generation order interact with pruning.
- The fixed probe was run at depth 3 so the complete cross-product remains practical, including unpruned minimax variants.
