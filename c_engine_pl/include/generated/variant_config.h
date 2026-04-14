#ifndef C_ENGINE_PL_VARIANT_CONFIG_H
#define C_ENGINE_PL_VARIANT_CONFIG_H

#define PL_VARIANT_NAME "stratified_variant_28"


/* Compile-time feature toggles derived from feature_model.json */
#define CFG_0X88 1
#define CFG_10X12_BOARD 0
#define CFG_ALPHA_BETA 1
#define CFG_ASPIRATION_WINDOWS 0
#define CFG_BISHOP_PAIR 0
#define CFG_BITBOARDS 0
#define CFG_CASTLING 1
#define CFG_CONNECTED_PAWN 0
#define CFG_COPY_MAKE 0
#define CFG_DELTA_PRUNING 0
#define CFG_DOUBLED_PAWN 1
#define CFG_EN_PASSANT 1
#define CFG_EVALUATION 1
#define CFG_FEN 1
#define CFG_FIFTY_MOVE_RULE 1
#define CFG_FUTILITY_PRUNING 0
#define CFG_HASH_MOVE 0
#define CFG_HISTORY_HEURISTIC 0
#define CFG_ISOLATED_PAWN 1
#define CFG_ITERATIVE_DEEPENING 1
#define CFG_KILLER_HEURISTIC 1
#define CFG_KING_ACTIVITY 0
#define CFG_KING_SAFETY 0
#define CFG_KING_SHELTER 0
#define CFG_LATE_MOVE_REDUCTIONS 1
#define CFG_LEGAL_MOVE_GENERATION 1
#define CFG_MAGIC_BITBOARDS 0
#define CFG_MAILBOX 0
#define CFG_MAKE_MOVE 1
#define CFG_MINIMAX 1
#define CFG_MOBILITY 0
#define CFG_MOVE_GENERATION 1
#define CFG_MOVE_ORDERING 1
#define CFG_NEGAMAX 0
#define CFG_NULL_MOVE_PRUNING 1
#define CFG_OPENING_BOOK 0
#define CFG_PASSED_PAWN 0
#define CFG_PAWN_HASH_TABLE 0
#define CFG_PIECE_LISTS 1
#define CFG_PIECE_SQUARE_TABLES 1
#define CFG_PONDERING 1
#define CFG_PRINCIPAL_VARIATION_SEARCH 0
#define CFG_PSEUDO_LEGAL_MOVE_GENERATION 1
#define CFG_QUIESCENCE_SEARCH 1
#define CFG_RAZORING 1
#define CFG_REPLACEMENT_SCHEMES 0
#define CFG_ROOK_OPEN_FILE 0
#define CFG_ROOK_SEMI_OPEN_FILE 0
#define CFG_STATIC_EXCHANGE_EVALUATION 0
#define CFG_TAPERED_EVAL 0
#define CFG_THREEFOLD_REPETITION 1
#define CFG_TIME_MANAGEMENT 0
#define CFG_TRANSPOSITION_TABLE 0
#define CFG_UCI 1
#define CFG_UNMAKE_MOVE 1
#define CFG_ZOBRIST_HASHING 0

#define PL_SELECTED_OPTION_COUNT 27
static const char *PL_SELECTED_OPTION_NAMES[PL_SELECTED_OPTION_COUNT] = {
    "0x88",
    "Alpha-Beta",
    "Castling",
    "Doubled Pawn",
    "En Passant",
    "Evaluation",
    "FEN",
    "Fifty-Move Rule",
    "Isolated Pawn",
    "Iterative Deepening",
    "Killer Heuristic",
    "Late Move Reductions",
    "Legal Move Generation",
    "Make Move",
    "Minimax",
    "Move Generation",
    "Move Ordering",
    "Null Move Pruning",
    "Piece Lists",
    "Piece-Square Tables",
    "Pondering",
    "Pseudo-Legal Move Generation",
    "Quiescence Search",
    "Razoring",
    "Threefold Repetition",
    "UCI",
    "Unmake Move",
};

#endif
