# Feature Implementation Span

This heuristic complements guarded LOC. It seeds each feature from functions that mention the `CFG_*` flag or are lexically enclosed by it, then expands one step through the static call graph (callers, callees, and callers' callees).

| Rank | Feature | CFG | Guarded LOC | Seed funcs | Seed LOC | Span funcs | Span files | Span LOC | Span/Guard |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | `Bitboards` | `CFG_BITBOARDS` | 45 | 8 | 208 | 65 | 4 | 2641 | 58.69 |
| 2 | `10x12 Board` | `CFG_10X12_BOARD` | 11 | 8 | 208 | 65 | 4 | 2641 | 240.09 |
| 3 | `0x88` | `CFG_0X88` | 9 | 8 | 208 | 65 | 4 | 2641 | 293.44 |
| 4 | `Mailbox` | `CFG_MAILBOX` | 5 | 5 | 81 | 38 | 4 | 2071 | 414.2 |
| 5 | `Fifty-Move Rule` | `CFG_FIFTY_MOVE_RULE` | 20 | 5 | 731 | 57 | 3 | 1930 | 96.5 |
| 6 | `Threefold Repetition` | `CFG_THREEFOLD_REPETITION` | 20 | 5 | 731 | 57 | 3 | 1930 | 96.5 |
| 7 | `En Passant` | `CFG_EN_PASSANT` | 36 | 3 | 469 | 51 | 3 | 1908 | 53.0 |
| 8 | `Piece Lists` | `CFG_PIECE_LISTS` | 86 | 12 | 930 | 50 | 2 | 1773 | 20.62 |
| 9 | `Move Generation` | `CFG_MOVE_GENERATION` | 6 | 2 | 26 | 52 | 3 | 1760 | 293.33 |
| 10 | `Legal Move Generation` | `CFG_LEGAL_MOVE_GENERATION` | 1 | 1 | 15 | 50 | 2 | 1719 | 1719.0 |
| 11 | `Pseudo-Legal Move Generation` | `CFG_PSEUDO_LEGAL_MOVE_GENERATION` | 1 | 1 | 15 | 50 | 2 | 1719 | 1719.0 |
| 12 | `Magic Bitboards` | `CFG_MAGIC_BITBOARDS` | 279 | 11 | 530 | 36 | 4 | 1688 | 6.05 |
| 13 | `Unmake Move` | `CFG_UNMAKE_MOVE` | 11 | 4 | 122 | 40 | 2 | 1510 | 137.27 |
| 14 | `Transposition Table` | `CFG_TRANSPOSITION_TABLE` | 98 | 3 | 128 | 45 | 2 | 1383 | 14.11 |
| 15 | `Copy-Make` | `CFG_COPY_MAKE` | 7 | 3 | 60 | 32 | 2 | 1261 | 180.14 |
| 16 | `Castling` | `CFG_CASTLING` | 120 | 2 | 352 | 30 | 2 | 1260 | 10.5 |
| 17 | `Opening Book` | `CFG_OPENING_BOOK` | 233 | 10 | 402 | 46 | 3 | 1247 | 5.35 |
| 18 | `Hash Move` | `CFG_HASH_MOVE` | 16 | 4 | 529 | 33 | 3 | 1140 | 71.25 |
| 19 | `Iterative Deepening` | `CFG_ITERATIVE_DEEPENING` | 18 | 2 | 182 | 40 | 5 | 1125 | 62.5 |
| 20 | `Killer Heuristic` | `CFG_KILLER_HEURISTIC` | 11 | 2 | 75 | 32 | 3 | 1077 | 97.91 |
| 21 | `History Heuristic` | `CFG_HISTORY_HEURISTIC` | 4 | 2 | 75 | 32 | 3 | 1077 | 269.25 |
| 22 | `Move Ordering` | `CFG_MOVE_ORDERING` | 34 | 1 | 53 | 31 | 3 | 1074 | 31.59 |
| 23 | `Time Management` | `CFG_TIME_MANAGEMENT` | 10 | 1 | 152 | 37 | 3 | 1018 | 101.8 |
| 24 | `Replacement Schemes` | `CFG_REPLACEMENT_SCHEMES` | 9 | 1 | 53 | 28 | 2 | 987 | 109.67 |
| 25 | `Null Move Pruning` | `CFG_NULL_MOVE_PRUNING` | 108 | 7 | 454 | 26 | 2 | 971 | 8.99 |
| 26 | `FEN` | `CFG_FEN` | 21 | 3 | 84 | 26 | 4 | 960 | 45.71 |
| 27 | `Delta Pruning` | `CFG_DELTA_PRUNING` | 22 | 3 | 172 | 25 | 2 | 959 | 43.59 |
| 28 | `Late Move Reductions` | `CFG_LATE_MOVE_REDUCTIONS` | 34 | 3 | 416 | 24 | 2 | 956 | 28.12 |
| 29 | `Futility Pruning` | `CFG_FUTILITY_PRUNING` | 18 | 2 | 410 | 24 | 2 | 956 | 53.11 |
| 30 | `Razoring` | `CFG_RAZORING` | 18 | 2 | 410 | 24 | 2 | 956 | 53.11 |
| 31 | `Quiescence Search` | `CFG_QUIESCENCE_SEARCH` | 6 | 2 | 410 | 24 | 2 | 956 | 159.33 |
| 32 | `Zobrist Hashing` | `CFG_ZOBRIST_HASHING` | 16 | 7 | 66 | 40 | 3 | 915 | 57.19 |
| 33 | `Pondering` | `CFG_PONDERING` | 242 | 11 | 404 | 23 | 4 | 841 | 3.48 |
| 34 | `UCI` | `CFG_UCI` | 3 | 1 | 207 | 19 | 4 | 773 | 257.67 |
| 35 | `Negamax` | `CFG_NEGAMAX` | 4 | 2 | 37 | 29 | 4 | 742 | 185.5 |
| 36 | `Make Move` | `CFG_MAKE_MOVE` | 6 | 2 | 128 | 29 | 3 | 730 | 121.67 |
| 37 | `Alpha-Beta` | `CFG_ALPHA_BETA` | 6 | 2 | 39 | 21 | 4 | 460 | 76.67 |
| 38 | `Minimax` | `CFG_MINIMAX` | 4 | 2 | 37 | 21 | 4 | 460 | 115.0 |
| 39 | `Principal Variation Search` | `CFG_PRINCIPAL_VARIATION_SEARCH` | 3 | 2 | 39 | 21 | 4 | 460 | 153.33 |
| 40 | `Aspiration Windows` | `CFG_ASPIRATION_WINDOWS` | 29 | 1 | 50 | 19 | 2 | 421 | 14.52 |
| 41 | `Pawn Hash Table` | `CFG_PAWN_HASH_TABLE` | 13 | 2 | 81 | 19 | 4 | 381 | 29.31 |
| 42 | `Tapered Eval` | `CFG_TAPERED_EVAL` | 8 | 3 | 95 | 22 | 4 | 344 | 43.0 |
| 43 | `Piece-Square Tables` | `CFG_PIECE_SQUARE_TABLES` | 34 | 2 | 112 | 19 | 4 | 314 | 9.24 |
| 44 | `Evaluation` | `CFG_EVALUATION` | 3 | 2 | 112 | 19 | 4 | 314 | 104.67 |
| 45 | `Mobility` | `CFG_MOBILITY` | 2 | 2 | 68 | 16 | 4 | 297 | 148.5 |
| 46 | `Static Exchange Evaluation` | `CFG_STATIC_EXCHANGE_EVALUATION` | 2 | 2 | 86 | 12 | 4 | 236 | 118.0 |
| 47 | `Bishop Pair` | `CFG_BISHOP_PAIR` | 1 | 1 | 60 | 5 | 4 | 136 | 136.0 |
| 48 | `Connected Pawn` | `CFG_CONNECTED_PAWN` | 1 | 1 | 60 | 5 | 4 | 136 | 136.0 |
| 49 | `Doubled Pawn` | `CFG_DOUBLED_PAWN` | 1 | 1 | 60 | 5 | 4 | 136 | 136.0 |
| 50 | `Isolated Pawn` | `CFG_ISOLATED_PAWN` | 1 | 1 | 60 | 5 | 4 | 136 | 136.0 |
| 51 | `King Activity` | `CFG_KING_ACTIVITY` | 1 | 1 | 60 | 5 | 4 | 136 | 136.0 |
| 52 | `King Pressure` | `CFG_KING_SAFETY` | 1 | 1 | 60 | 5 | 4 | 136 | 136.0 |
| 53 | `King Shelter` | `CFG_KING_SHELTER` | 1 | 1 | 60 | 5 | 4 | 136 | 136.0 |
| 54 | `Passed Pawn` | `CFG_PASSED_PAWN` | 1 | 1 | 60 | 5 | 4 | 136 | 136.0 |
| 55 | `Rook on Open File` | `CFG_ROOK_OPEN_FILE` | 1 | 1 | 60 | 5 | 4 | 136 | 136.0 |
| 56 | `Rook Semi-Open File` | `CFG_ROOK_SEMI_OPEN_FILE` | 1 | 1 | 60 | 5 | 4 | 136 | 136.0 |

## Selected Cases

### `CFG_NEGAMAX`
- Feature: `Negamax`
- Guarded non-empty LOC: **4**
- Seed functions (2): `engine_search_core_name, search_use_negamax`
- Seed files (1): `c_engine_pl/src/search.c`
- Span functions (29): `engine_board_backend_name, engine_get_instrumentation_internal, engine_reset_instrumentation_internal, engine_variant_summary, generate_moves, in_check, now_ms, order_moves, repetition_count, tt_new_search, tt_probe, engine_eval_profile_name, engine_search, engine_search_core_name, mate_score_absolute, root_score_to_cp, ...`
- Span files (4): `c_engine_pl/src/board_backend.c, c_engine_pl/src/engine.c, c_engine_pl/src/eval.c, c_engine_pl/src/search.c`
- Span non-empty LOC: **742**

### `CFG_MAGIC_BITBOARDS`
- Feature: `Magic Bitboards`
- Guarded non-empty LOC: **279**
- Seed functions (11): `bishop_attacks_magic, bishop_attacks_on_the_fly, bishop_mask_magic, engine_board_backend_name, generate_moves_bitboards, init_backend_maps, init_magic_tables, is_square_attacked_bitboards, rook_attacks_magic, rook_attacks_on_the_fly, rook_mask_magic`
- Seed files (1): `c_engine_pl/src/board_backend.c`
- Span functions (36): `add_special_moves, attack_mask_from_offsets, bishop_attacks_magic, bishop_attacks_on_the_fly, bishop_mask_magic, engine_backend_generate_pseudo_moves, engine_backend_is_square_attacked, engine_board_backend_name, engine_sync_backend_state, file_of, generate_moves_0x88, generate_moves_120, generate_moves_bitboards, generate_moves_mailbox, init_backend_maps, init_magic_tables, ...`
- Span files (4): `c_engine_pl/src/board_backend.c, c_engine_pl/src/engine.c, c_engine_pl/src/eval.c, c_engine_pl/src/search.c`
- Span non-empty LOC: **1688**

### `CFG_OPENING_BOOK`
- Feature: `Opening Book`
- Guarded non-empty LOC: **233**
- Seed functions (10): `engine_print_compiled_features, engine_search, search_book_add_candidate, search_book_trim, search_init_book_state, search_match_book_line, search_opening_book_move, search_opening_book_path, search_split_book_moves, handle_setoption`
- Seed files (3): `c_engine_pl/src/engine.c, c_engine_pl/src/search.c, c_engine_pl/src/uci.c`
- Span functions (46): `engine_apply_move_uci, engine_get_instrumentation_internal, engine_init, engine_move_to_uci, engine_print_compiled_features, engine_reset_instrumentation_internal, engine_set_startpos, engine_variant_summary, find_move_in_list, generate_moves, in_check, now_ms, parse_move_uci, repetition_count, tt_new_search, engine_search, ...`
- Span files (3): `c_engine_pl/src/engine.c, c_engine_pl/src/search.c, c_engine_pl/src/uci.c`
- Span non-empty LOC: **1247**

### `CFG_PONDERING`
- Feature: `Pondering`
- Guarded non-empty LOC: **242**
- Seed functions (11): `engine_print_compiled_features, handle_setoption, ponder_session_destroy, ponder_session_init, ponder_session_join, ponder_session_publish, ponder_session_should_stop, ponder_session_start, ponder_session_stop, ponder_session_worker, uci_loop`
- Seed files (2): `c_engine_pl/src/engine.c, c_engine_pl/src/uci.c`
- Span functions (23): `engine_init, engine_move_to_uci, engine_print_compiled_features, engine_set_startpos, engine_variant_summary, main, engine_search, handle_eval, handle_legalmoves, handle_perft, handle_position, handle_setoption, parse_movetime, ponder_session_destroy, ponder_session_init, ponder_session_join, ...`
- Span files (4): `c_engine_pl/src/engine.c, c_engine_pl/src/main.c, c_engine_pl/src/search.c, c_engine_pl/src/uci.c`
- Span non-empty LOC: **841**

