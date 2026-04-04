#ifndef C_ENGINE_PL_VARIANT_CONFIG_H
#define C_ENGINE_PL_VARIANT_CONFIG_H

#define PL_VARIANT_NAME "phase3_full_eval"


/* Compile-time feature toggles derived from feature_model.json */
#define CFG_0X88 0
#define CFG_10X12_BOARD 0
#define CFG_ALPHA_BETA 1
#define CFG_ASPIRATION_WINDOWS 0
#define CFG_BISHOP_PAIR 1
#define CFG_BITBOARDS 1
#define CFG_CASTLING 1
#define CFG_CONNECTED_PAWN 1
#define CFG_COPY_MAKE 0
#define CFG_DELTA_PRUNING 0
#define CFG_DOUBLED_PAWN 1
#define CFG_EN_PASSANT 1
#define CFG_EVALUATION 1
#define CFG_FEN 1
#define CFG_FIFTY_MOVE_RULE 1
#define CFG_FUTILITY_PRUNING 0
#define CFG_HASH_MOVE 1
#define CFG_HISTORY_HEURISTIC 0
#define CFG_ISOLATED_PAWN 1
#define CFG_ITERATIVE_DEEPENING 1
#define CFG_KILLER_HEURISTIC 0
#define CFG_KING_ACTIVITY 1
#define CFG_KING_SAFETY 1
#define CFG_KING_SHELTER 1
#define CFG_LATE_MOVE_REDUCTIONS 0
#define CFG_LEGAL_MOVE_GENERATION 1
#define CFG_MAGIC_BITBOARDS 0
#define CFG_MAILBOX 0
#define CFG_MAKE_MOVE 1
#define CFG_MINIMAX 0
#define CFG_MOBILITY 1
#define CFG_MOVE_GENERATION 1
#define CFG_MOVE_ORDERING 1
#define CFG_NEGAMAX 1
#define CFG_NULL_MOVE_PRUNING 0
#define CFG_OPENING_BOOK 0
#define CFG_PASSED_PAWN 1
#define CFG_PAWN_HASH_TABLE 1
#define CFG_PIECE_LISTS 0
#define CFG_PIECE_SQUARE_TABLES 1
#define CFG_PONDERING 0
#define CFG_PRINCIPAL_VARIATION_SEARCH 1
#define CFG_PSEUDO_LEGAL_MOVE_GENERATION 0
#define CFG_QUIESCENCE_SEARCH 1
#define CFG_RAZORING 0
#define CFG_REPLACEMENT_SCHEMES 1
#define CFG_ROOK_OPEN_FILE 1
#define CFG_ROOK_SEMI_OPEN_FILE 1
#define CFG_STATIC_EXCHANGE_EVALUATION 1
#define CFG_TAPERED_EVAL 1
#define CFG_THREEFOLD_REPETITION 1
#define CFG_TIME_MANAGEMENT 0
#define CFG_TRANSPOSITION_TABLE 1
#define CFG_UCI 1
#define CFG_UNMAKE_MOVE 1
#define CFG_ZOBRIST_HASHING 1

#define PL_SELECTED_OPTION_COUNT 37
static const char *PL_SELECTED_OPTION_NAMES[PL_SELECTED_OPTION_COUNT] = {
    "Alpha-Beta",
    "Bishop Pair",
    "Bitboards",
    "Castling",
    "Connected Pawn",
    "Doubled Pawn",
    "En Passant",
    "Evaluation",
    "FEN",
    "Fifty-Move Rule",
    "Hash Move",
    "Isolated Pawn",
    "Iterative Deepening",
    "King Activity",
    "King Pressure",
    "King Shelter",
    "Legal Move Generation",
    "Make Move",
    "Mobility",
    "Move Generation",
    "Move Ordering",
    "Negamax",
    "Passed Pawn",
    "Pawn Hash Table",
    "Piece-Square Tables",
    "Principal Variation Search",
    "Quiescence Search",
    "Replacement Schemes",
    "Rook on Open File",
    "Rook Semi-Open File",
    "Static Exchange Evaluation",
    "Tapered Eval",
    "Threefold Repetition",
    "Transposition Table",
    "UCI",
    "Unmake Move",
    "Zobrist Hashing",
};

#endif
