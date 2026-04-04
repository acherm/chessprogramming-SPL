# Setup Variability Report

## Scope
- This setup model captures runtime and harness choices layered on top of a compile-time engine variant.
- It intentionally models only implemented variability: search budget, opening-book control, and pondering control.
- It intentionally excludes fictive runtime knobs such as `Threads` and `Hash`, because the engine does not expose them as real setup options here.

## Counts
- setup features: 21
- setup constraints: 10
- variant recommendations: 17
- feature recommendations: 56

## Warnings
- Skipped variant 'invalid_excludes' while building setup recommendations: Feature 'Castling' must be selected for tournament legality; Feature 'En Passant' must be selected for tournament legality; Feature 'Threefold Repetition' must be selected for tournament legality; Feature 'Fifty-Move Rule' must be selected for tournament legality; Select exactly one primary board representation: Bitboards | 0x88 | Mailbox | 10x12 Board; Constraint violation: 'Minimax' requires 'Make Move'; Constraint violation: 'Minimax' requires 'Unmake Move'; Constraint violation: 'Alpha-Beta' requires 'Make Move'; Constraint violation: 'Alpha-Beta' requires 'Unmake Move'; Constraint violation: 'Alpha-Beta' requires 'Castling'; Constraint violation: 'Alpha-Beta' requires 'En Passant'; Constraint violation: 'Alpha-Beta' requires 'Threefold Repetition'; Constraint violation: 'Alpha-Beta' requires 'Fifty-Move Rule'; Constraint violation: 'Bitboards' excludes 'Mailbox'