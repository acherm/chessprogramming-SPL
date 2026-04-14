# Guarded LOC per Compile-Time Feature

| Rank | Feature | Family | CFG | Guarded non-empty LOC |
| --- | --- | --- | --- | ---: |
| 1 | `Magic Bitboards` | `MoveGeneration` | `CFG_MAGIC_BITBOARDS` | 279 |
| 2 | `Pondering` | `TimeManagement` | `CFG_PONDERING` | 242 |
| 3 | `Opening Book` | `Opening` | `CFG_OPENING_BOOK` | 233 |
| 4 | `Castling` | `MoveGeneration` | `CFG_CASTLING` | 120 |
| 5 | `Null Move Pruning` | `PruningReductions` | `CFG_NULL_MOVE_PRUNING` | 108 |
| 6 | `Transposition Table` | `TranspositionTable` | `CFG_TRANSPOSITION_TABLE` | 98 |
| 7 | `Piece Lists` | `BoardRepresentation` | `CFG_PIECE_LISTS` | 86 |
| 8 | `Bitboards` | `BoardRepresentation` | `CFG_BITBOARDS` | 45 |
| 9 | `En Passant` | `MoveGeneration` | `CFG_EN_PASSANT` | 36 |
| 10 | `Piece-Square Tables` | `Evaluation` | `CFG_PIECE_SQUARE_TABLES` | 34 |
| 11 | `Move Ordering` | `Search` | `CFG_MOVE_ORDERING` | 34 |
| 12 | `Late Move Reductions` | `PruningReductions` | `CFG_LATE_MOVE_REDUCTIONS` | 34 |
| 13 | `Aspiration Windows` | `Search` | `CFG_ASPIRATION_WINDOWS` | 29 |
| 14 | `Delta Pruning` | `PruningReductions` | `CFG_DELTA_PRUNING` | 22 |
| 15 | `FEN` | `Protocol` | `CFG_FEN` | 21 |
| 16 | `Fifty-Move Rule` | `Search` | `CFG_FIFTY_MOVE_RULE` | 20 |
| 17 | `Threefold Repetition` | `Search` | `CFG_THREEFOLD_REPETITION` | 20 |
| 18 | `Futility Pruning` | `PruningReductions` | `CFG_FUTILITY_PRUNING` | 18 |
| 19 | `Razoring` | `PruningReductions` | `CFG_RAZORING` | 18 |
| 20 | `Iterative Deepening` | `Search` | `CFG_ITERATIVE_DEEPENING` | 18 |
| 21 | `Hash Move` | `Ordering Heuristics` | `CFG_HASH_MOVE` | 16 |
| 22 | `Zobrist Hashing` | `TT Support` | `CFG_ZOBRIST_HASHING` | 16 |
| 23 | `Pawn Hash Table` | `TT Support` | `CFG_PAWN_HASH_TABLE` | 13 |
| 24 | `10x12 Board` | `BoardRepresentation` | `CFG_10X12_BOARD` | 11 |
| 25 | `Unmake Move` | `BoardRepresentation` | `CFG_UNMAKE_MOVE` | 11 |
| 26 | `Killer Heuristic` | `Ordering Heuristics` | `CFG_KILLER_HEURISTIC` | 11 |
| 27 | `Time Management` | `TimeManagement` | `CFG_TIME_MANAGEMENT` | 10 |
| 28 | `0x88` | `BoardRepresentation` | `CFG_0X88` | 9 |
| 29 | `Replacement Schemes` | `TT Support` | `CFG_REPLACEMENT_SCHEMES` | 9 |
| 30 | `Tapered Eval` | `Evaluation` | `CFG_TAPERED_EVAL` | 8 |
| 31 | `Copy-Make` | `BoardRepresentation` | `CFG_COPY_MAKE` | 7 |
| 32 | `Make Move` | `BoardRepresentation` | `CFG_MAKE_MOVE` | 6 |
| 33 | `Move Generation` | `MoveGeneration` | `CFG_MOVE_GENERATION` | 6 |
| 34 | `Alpha-Beta` | `Search` | `CFG_ALPHA_BETA` | 6 |
| 35 | `Quiescence Search` | `Search` | `CFG_QUIESCENCE_SEARCH` | 6 |
| 36 | `Mailbox` | `BoardRepresentation` | `CFG_MAILBOX` | 5 |
| 37 | `History Heuristic` | `Ordering Heuristics` | `CFG_HISTORY_HEURISTIC` | 4 |
| 38 | `Minimax` | `Search` | `CFG_MINIMAX` | 4 |
| 39 | `Negamax` | `Search` | `CFG_NEGAMAX` | 4 |
| 40 | `Evaluation` | `Evaluation` | `CFG_EVALUATION` | 3 |
| 41 | `UCI` | `Protocol` | `CFG_UCI` | 3 |
| 42 | `Principal Variation Search` | `Search` | `CFG_PRINCIPAL_VARIATION_SEARCH` | 3 |
| 43 | `Mobility` | `Evaluation` | `CFG_MOBILITY` | 2 |
| 44 | `Static Exchange Evaluation` | `Evaluation` | `CFG_STATIC_EXCHANGE_EVALUATION` | 2 |
| 45 | `Bishop Pair` | `Piece Coordination` | `CFG_BISHOP_PAIR` | 1 |
| 46 | `Connected Pawn` | `Pawn Structure` | `CFG_CONNECTED_PAWN` | 1 |
| 47 | `Doubled Pawn` | `Pawn Structure` | `CFG_DOUBLED_PAWN` | 1 |
| 48 | `Isolated Pawn` | `Pawn Structure` | `CFG_ISOLATED_PAWN` | 1 |
| 49 | `King Activity` | `King Terms` | `CFG_KING_ACTIVITY` | 1 |
| 50 | `King Shelter` | `King Terms` | `CFG_KING_SHELTER` | 1 |
| 51 | `Passed Pawn` | `Pawn Structure` | `CFG_PASSED_PAWN` | 1 |
| 52 | `Rook on Open File` | `Piece Coordination` | `CFG_ROOK_OPEN_FILE` | 1 |
| 53 | `Rook Semi-Open File` | `Piece Coordination` | `CFG_ROOK_SEMI_OPEN_FILE` | 1 |
| 54 | `Legal Move Generation` | `MoveGeneration` | `CFG_LEGAL_MOVE_GENERATION` | 1 |
| 55 | `Pseudo-Legal Move Generation` | `MoveGeneration` | `CFG_PSEUDO_LEGAL_MOVE_GENERATION` | 1 |
| 56 | `King Pressure` | `King Terms` | `CFG_KING_SAFETY` | 1 |
