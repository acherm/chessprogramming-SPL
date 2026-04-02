#ifndef C_ENGINE_PL_VARIANT_CONFIG_H
#define C_ENGINE_PL_VARIANT_CONFIG_H

#define PL_VARIANT_NAME "phase2_bitboards_ab_pvs_id"


/* Compile-time feature toggles derived from feature_model.json */
#define CFG_0X88 0
#define CFG_10X12_BOARD 0
#define CFG_ALPHA_BETA 1
#define CFG_ASPIRATION_WINDOWS 0
#define CFG_BITBOARDS 1
#define CFG_CASTLING 1
#define CFG_COPY_MAKE 0
#define CFG_DELTA_PRUNING 0
#define CFG_EN_PASSANT 1
#define CFG_EVALUATION 1
#define CFG_FEN 1
#define CFG_FIFTY_MOVE_RULE 1
#define CFG_FUTILITY_PRUNING 0
#define CFG_HASH_MOVE 1
#define CFG_HISTORY_HEURISTIC 0
#define CFG_ITERATIVE_DEEPENING 1
#define CFG_KILLER_HEURISTIC 0
#define CFG_KING_SAFETY 0
#define CFG_LATE_MOVE_REDUCTIONS 0
#define CFG_LEGAL_MOVE_GENERATION 1
#define CFG_MAGIC_BITBOARDS 0
#define CFG_MAILBOX 0
#define CFG_MAKE_MOVE 1
#define CFG_MOBILITY 0
#define CFG_MOVE_GENERATION 1
#define CFG_MOVE_ORDERING 1
#define CFG_NEGAMAX 1
#define CFG_NULL_MOVE_PRUNING 0
#define CFG_OPENING_BOOK 0
#define CFG_PAWN_HASH_TABLE 0
#define CFG_PAWN_STRUCTURE 0
#define CFG_PIECE_LISTS 0
#define CFG_PIECE_SQUARE_TABLES 1
#define CFG_PONDERING 0
#define CFG_PRINCIPAL_VARIATION_SEARCH 1
#define CFG_PSEUDO_LEGAL_MOVE_GENERATION 0
#define CFG_QUIESCENCE_SEARCH 1
#define CFG_RAZORING 0
#define CFG_REPLACEMENT_SCHEMES 0
#define CFG_STATIC_EXCHANGE_EVALUATION 0
#define CFG_TAPERED_EVAL 0
#define CFG_THREEFOLD_REPETITION 1
#define CFG_TIME_MANAGEMENT 0
#define CFG_TRANSPOSITION_TABLE 1
#define CFG_UCI 1
#define CFG_UNMAKE_MOVE 1
#define CFG_ZOBRIST_HASHING 1

#define PL_SELECTED_OPTION_COUNT 22
static const char *PL_SELECTED_OPTION_NAMES[PL_SELECTED_OPTION_COUNT] = {
    "Alpha-Beta",
    "Bitboards",
    "Castling",
    "En Passant",
    "Evaluation",
    "FEN",
    "Fifty-Move Rule",
    "Hash Move",
    "Iterative Deepening",
    "Legal Move Generation",
    "Make Move",
    "Move Generation",
    "Move Ordering",
    "Negamax",
    "Piece-Square Tables",
    "Principal Variation Search",
    "Quiescence Search",
    "Threefold Repetition",
    "Transposition Table",
    "UCI",
    "Unmake Move",
    "Zobrist Hashing",
};

#endif
