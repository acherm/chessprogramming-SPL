#include "engine_eval_internal.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "generated/variant_config.h"

#define WHITE 0
#define BLACK 1

#define EMPTY 0
#define WP 1
#define WN 2
#define WB 3
#define WR 4
#define WQ 5
#define WK 6
#define BP -1
#define BN -2
#define BB -3
#define BR -4
#define BQ -5
#define BK -6

#define PAWN_HASH_SIZE (1u << 14)
#define PAWN_HASH_MASK (PAWN_HASH_SIZE - 1u)
#define EVAL_CACHE_SIZE (1u << 15)
#define EVAL_CACHE_MASK (EVAL_CACHE_SIZE - 1u)

#define FLAG_CAPTURE 1
#define FLAG_PROMOTION 2
#define FLAG_EN_PASSANT 4

#if defined(__clang__) || defined(__GNUC__)
#define EVAL_MAYBE_UNUSED __attribute__((unused))
#else
#define EVAL_MAYBE_UNUSED
#endif

#define EVAL_USE_PASSED_PAWN CFG_PASSED_PAWN
#define EVAL_USE_ISOLATED_PAWN CFG_ISOLATED_PAWN
#define EVAL_USE_DOUBLED_PAWN CFG_DOUBLED_PAWN
#define EVAL_USE_CONNECTED_PAWN CFG_CONNECTED_PAWN
#define EVAL_USE_ANY_PAWN_TERM (EVAL_USE_PASSED_PAWN || EVAL_USE_ISOLATED_PAWN || EVAL_USE_DOUBLED_PAWN || EVAL_USE_CONNECTED_PAWN)
#define EVAL_USE_BISHOP_PAIR CFG_BISHOP_PAIR
#define EVAL_USE_ROOK_OPEN_FILE CFG_ROOK_OPEN_FILE
#define EVAL_USE_ROOK_SEMI_OPEN_FILE CFG_ROOK_SEMI_OPEN_FILE
#define EVAL_USE_ANY_COORD_TERM (EVAL_USE_BISHOP_PAIR || EVAL_USE_ROOK_OPEN_FILE || EVAL_USE_ROOK_SEMI_OPEN_FILE)
#define EVAL_USE_KING_RING_PRESSURE CFG_KING_SAFETY
#define EVAL_USE_KING_SHELTER CFG_KING_SHELTER
#define EVAL_USE_ANY_KING_TERM (EVAL_USE_KING_RING_PRESSURE || EVAL_USE_KING_SHELTER)
#define EVAL_USE_KING_ACTIVITY CFG_KING_ACTIVITY

typedef struct PawnHashEntry {
    uint64_t key;
    int mg;
    int eg;
} PawnHashEntry;

typedef struct EvalScore {
    int mg;
    int eg;
} EvalScore;

typedef struct EvalCacheEntry {
    uint64_t key;
    int score;
} EvalCacheEntry;

typedef struct EvalAccumulator {
    int mg;
    int eg;
    int phase;
} EvalAccumulator;

static const int PIECE_VALUE[7] = {0, 100, 320, 330, 500, 900, 0};

static EVAL_MAYBE_UNUSED const int PST_PAWN[64] = {
    0, 0, 0, 0, 0, 0, 0, 0,
    5, 10, 10, -20, -20, 10, 10, 5,
    5, -5, -10, 0, 0, -10, -5, 5,
    0, 0, 0, 20, 20, 0, 0, 0,
    5, 5, 10, 25, 25, 10, 5, 5,
    10, 10, 20, 30, 30, 20, 10, 10,
    50, 50, 50, 50, 50, 50, 50, 50,
    0, 0, 0, 0, 0, 0, 0, 0,
};

static EVAL_MAYBE_UNUSED const int PST_KNIGHT[64] = {
    -50, -40, -30, -30, -30, -30, -40, -50,
    -40, -20, 0, 0, 0, 0, -20, -40,
    -30, 0, 10, 15, 15, 10, 0, -30,
    -30, 5, 15, 20, 20, 15, 5, -30,
    -30, 0, 15, 20, 20, 15, 0, -30,
    -30, 5, 10, 15, 15, 10, 5, -30,
    -40, -20, 0, 5, 5, 0, -20, -40,
    -50, -40, -30, -30, -30, -30, -40, -50,
};

static EVAL_MAYBE_UNUSED const int PST_BISHOP[64] = {
    -20, -10, -10, -10, -10, -10, -10, -20,
    -10, 5, 0, 0, 0, 0, 5, -10,
    -10, 10, 10, 10, 10, 10, 10, -10,
    -10, 0, 10, 10, 10, 10, 0, -10,
    -10, 5, 5, 10, 10, 5, 5, -10,
    -10, 0, 5, 10, 10, 5, 0, -10,
    -10, 0, 0, 0, 0, 0, 0, -10,
    -20, -10, -10, -10, -10, -10, -10, -20,
};

static EVAL_MAYBE_UNUSED const int PST_ROOK[64] = {
    0, 0, 5, 10, 10, 5, 0, 0,
    -5, 0, 0, 0, 0, 0, 0, -5,
    -5, 0, 0, 0, 0, 0, 0, -5,
    -5, 0, 0, 0, 0, 0, 0, -5,
    -5, 0, 0, 0, 0, 0, 0, -5,
    -5, 0, 0, 0, 0, 0, 0, -5,
    5, 10, 10, 10, 10, 10, 10, 5,
    0, 0, 0, 0, 0, 0, 0, 0,
};

static EVAL_MAYBE_UNUSED const int PST_QUEEN[64] = {
    -20, -10, -10, -5, -5, -10, -10, -20,
    -10, 0, 0, 0, 0, 0, 0, -10,
    -10, 0, 5, 5, 5, 5, 0, -10,
    -5, 0, 5, 5, 5, 5, 0, -5,
    0, 0, 5, 5, 5, 5, 0, -5,
    -10, 5, 5, 5, 5, 5, 0, -10,
    -10, 0, 5, 0, 0, 0, 0, -10,
    -20, -10, -10, -5, -5, -10, -10, -20,
};

static EVAL_MAYBE_UNUSED const int PST_KING_MG[64] = {
    -30, -40, -40, -50, -50, -40, -40, -30,
    -30, -40, -40, -50, -50, -40, -40, -30,
    -30, -40, -40, -50, -50, -40, -40, -30,
    -30, -40, -40, -50, -50, -40, -40, -30,
    -20, -30, -30, -40, -40, -30, -30, -20,
    -10, -20, -20, -20, -20, -20, -20, -10,
    20, 20, 0, 0, 0, 0, 20, 20,
    20, 30, 10, 0, 0, 10, 30, 20,
};

static EVAL_MAYBE_UNUSED const int PST_KING_EG[64] = {
    -50, -40, -30, -20, -20, -30, -40, -50,
    -30, -20, -10, 0, 0, -10, -20, -30,
    -30, -10, 20, 30, 30, 20, -10, -30,
    -30, -10, 30, 40, 40, 30, -10, -30,
    -30, -10, 30, 40, 40, 30, -10, -30,
    -30, -10, 20, 30, 30, 20, -10, -30,
    -30, -30, 0, 0, 0, 0, -30, -30,
    -50, -30, -30, -30, -30, -30, -30, -50,
};

static const int KING_OFFSETS[8] = {8, -8, 1, -1, 9, 7, -9, -7};

static PawnHashEntry g_pawn_hash[PAWN_HASH_SIZE];
static EvalCacheEntry g_eval_cache[EVAL_CACHE_SIZE];

static inline int piece_abs(int piece) {
    return piece >= 0 ? piece : -piece;
}

static inline int piece_side(int piece) {
    if (piece > 0) {
        return WHITE;
    }
    if (piece < 0) {
        return BLACK;
    }
    return -1;
}

static inline int promotion_piece(int side, uint8_t promotion) {
    if (side == WHITE) {
        switch (promotion) {
            case 1:
                return WN;
            case 2:
                return WB;
            case 3:
                return WR;
            default:
                return WQ;
        }
    }

    switch (promotion) {
        case 1:
            return BN;
        case 2:
            return BB;
        case 3:
            return BR;
        default:
            return BQ;
    }
}

static inline int rank_of(int sq) {
    return sq / 8;
}

static inline int file_of(int sq) {
    return sq % 8;
}

static EVAL_MAYBE_UNUSED inline int mirror_sq(int sq) {
    int rank = rank_of(sq);
    int file = file_of(sq);
    return (7 - rank) * 8 + file;
}

static inline bool on_board64(int sq) {
    return sq >= 0 && sq < 64;
}

static inline bool on_board_rf(int rank, int file) {
    return rank >= 0 && rank < 8 && file >= 0 && file < 8;
}

static bool attacks_square_on_board(const int board[64], int from, int to, int piece) {
    int from_rank;
    int from_file;
    int to_rank;
    int to_file;
    int dr;
    int df;
    int step;
    int sq;

    if (!on_board64(from) || !on_board64(to) || piece == EMPTY || from == to) {
        return false;
    }

    from_rank = rank_of(from);
    from_file = file_of(from);
    to_rank = rank_of(to);
    to_file = file_of(to);
    dr = to_rank - from_rank;
    df = to_file - from_file;

    switch (piece_abs(piece)) {
        case WP:
            if (piece > 0) {
                return dr == 1 && abs(df) == 1;
            }
            return dr == -1 && abs(df) == 1;
        case WN:
            return (abs(dr) == 2 && abs(df) == 1) || (abs(dr) == 1 && abs(df) == 2);
        case WB:
            if (abs(dr) != abs(df)) {
                return false;
            }
            step = (dr > 0 ? 8 : -8) + (df > 0 ? 1 : -1);
            for (sq = from + step; sq != to; sq += step) {
                if (board[sq] != EMPTY) {
                    return false;
                }
            }
            return true;
        case WR:
            if (dr != 0 && df != 0) {
                return false;
            }
            if (dr == 0) {
                step = df > 0 ? 1 : -1;
            } else {
                step = dr > 0 ? 8 : -8;
            }
            for (sq = from + step; sq != to; sq += step) {
                if (board[sq] != EMPTY) {
                    return false;
                }
            }
            return true;
        case WQ:
            if (dr == 0 || df == 0) {
                if (dr == 0 && df == 0) {
                    return false;
                }
                if (dr == 0) {
                    step = df > 0 ? 1 : -1;
                } else {
                    step = dr > 0 ? 8 : -8;
                }
            } else if (abs(dr) == abs(df)) {
                step = (dr > 0 ? 8 : -8) + (df > 0 ? 1 : -1);
            } else {
                return false;
            }
            for (sq = from + step; sq != to; sq += step) {
                if (board[sq] != EMPTY) {
                    return false;
                }
            }
            return true;
        case WK:
            return abs(dr) <= 1 && abs(df) <= 1;
        default:
            return false;
    }
}

static int find_king_on_board(const int board[64], int side) {
    int target = side == WHITE ? WK : BK;
    int sq;

    for (sq = 0; sq < 64; ++sq) {
        if (board[sq] == target) {
            return sq;
        }
    }
    return -1;
}

static bool is_square_attacked_on_board(const int board[64], int sq, int attacker_side) {
    int from;

    for (from = 0; from < 64; ++from) {
        int piece = board[from];
        if (piece == EMPTY || piece_side(piece) != attacker_side) {
            continue;
        }
        if (attacks_square_on_board(board, from, sq, piece)) {
            return true;
        }
    }
    return false;
}

static int piece_after_capture(int piece, int target_sq, uint8_t promotion) {
    if (promotion != 0 && piece_abs(piece) == WP) {
        return promotion_piece(piece_side(piece), promotion);
    }
    if (piece == WP && rank_of(target_sq) == 7) {
        return WQ;
    }
    if (piece == BP && rank_of(target_sq) == 0) {
        return BQ;
    }
    return piece;
}

static bool see_capture_is_legal(int board[64], int from, int to, int side) {
    int piece = board[from];
    int captured = board[to];
    int moved_piece = piece_after_capture(piece, to, 0);
    int king_sq;
    bool legal;

    board[from] = EMPTY;
    board[to] = moved_piece;
    king_sq = piece_abs(piece) == WK ? to : find_king_on_board(board, side);
    legal = king_sq >= 0 && !is_square_attacked_on_board(board, king_sq, side ^ 1);
    board[from] = piece;
    board[to] = captured;
    return legal;
}

static int see_best_response(int board[64], int target_sq, int side) {
    int current_piece = board[target_sq];
    int captured_value;
    int best = 0;
    int from;

    if (current_piece == EMPTY) {
        return 0;
    }

    captured_value = PIECE_VALUE[piece_abs(current_piece)];
    for (from = 0; from < 64; ++from) {
        int piece = board[from];
        int moved_piece;
        int reply;

        if (piece == EMPTY || piece_side(piece) != side) {
            continue;
        }
        if (!attacks_square_on_board(board, from, target_sq, piece)) {
            continue;
        }
        if (!see_capture_is_legal(board, from, target_sq, side)) {
            continue;
        }

        moved_piece = piece_after_capture(piece, target_sq, 0);
        board[from] = EMPTY;
        board[target_sq] = moved_piece;
        reply = captured_value - see_best_response(board, target_sq, side ^ 1);
        board[from] = piece;
        board[target_sq] = current_piece;

        if (reply > best) {
            best = reply;
        }
    }

    return best;
}

static inline EvalScore eval_score_make(int mg, int eg) {
    EvalScore score;
    score.mg = mg;
    score.eg = eg;
    return score;
}

static inline void eval_score_add(EvalScore *target, int mg, int eg) {
    target->mg += mg;
    target->eg += eg;
}

static EVAL_MAYBE_UNUSED inline void accumulator_add(EvalAccumulator *acc, EvalScore score) {
    acc->mg += score.mg;
    acc->eg += score.eg;
}

static bool has_friendly_pawn_on_file(const EngineState *state, int side, int file) {
    int rank;
    int pawn = side == WHITE ? WP : BP;

    for (rank = 0; rank < 8; ++rank) {
        if (state->board[rank * 8 + file] == pawn) {
            return true;
        }
    }
    return false;
}

static EVAL_MAYBE_UNUSED bool is_passed_pawn(const EngineState *state, int sq, int side) {
    int pawn = side == WHITE ? WP : BP;
    int enemy_pawn = -pawn;
    int file = file_of(sq);
    int rank = rank_of(sq);
    int enemy_rank;
    int probe_file;

    for (probe_file = file - 1; probe_file <= file + 1; ++probe_file) {
        if (probe_file < 0 || probe_file > 7) {
            continue;
        }
        if (side == WHITE) {
            for (enemy_rank = rank + 1; enemy_rank < 8; ++enemy_rank) {
                if (state->board[enemy_rank * 8 + probe_file] == enemy_pawn) {
                    return false;
                }
            }
        } else {
            for (enemy_rank = rank - 1; enemy_rank >= 0; --enemy_rank) {
                if (state->board[enemy_rank * 8 + probe_file] == enemy_pawn) {
                    return false;
                }
            }
        }
    }

    return state->board[sq] == pawn;
}

static EVAL_MAYBE_UNUSED bool has_connected_pawn(const EngineState *state, int sq, int side) {
    int pawn = side == WHITE ? WP : BP;
    int rank = rank_of(sq);
    int file = file_of(sq);
    int df;
    int dr;

    for (df = -1; df <= 1; df += 2) {
        int other_file = file + df;
        if (other_file < 0 || other_file > 7) {
            continue;
        }
        for (dr = -1; dr <= 1; ++dr) {
            int other_rank = rank + dr;
            if (other_rank < 0 || other_rank > 7) {
                continue;
            }
            if (state->board[other_rank * 8 + other_file] == pawn) {
                return true;
            }
        }
    }
    return false;
}

static EVAL_MAYBE_UNUSED int king_centralization_bonus(int sq) {
    int rank = rank_of(sq);
    int file = file_of(sq);
    int file_dist = abs(file - 3) < abs(file - 4) ? abs(file - 3) : abs(file - 4);
    int rank_dist = abs(rank - 3) < abs(rank - 4) ? abs(rank - 3) : abs(rank - 4);
    return 14 - 3 * (file_dist + rank_dist);
}

static EVAL_MAYBE_UNUSED EvalScore evaluate_pawn_terms(const EngineState *state) {
    static EVAL_MAYBE_UNUSED const int PASSED_PAWN_MG[8] = {0, 0, 8, 18, 32, 52, 78, 0};
    static EVAL_MAYBE_UNUSED const int PASSED_PAWN_EG[8] = {0, 0, 16, 32, 56, 92, 140, 0};
    int file_counts_white[8] = {0};
    int file_counts_black[8] = {0};
    int sq;
    EvalScore score = eval_score_make(0, 0);

    for (sq = 0; sq < 64; ++sq) {
        if (state->board[sq] == WP) {
            file_counts_white[file_of(sq)] += 1;
        } else if (state->board[sq] == BP) {
            file_counts_black[file_of(sq)] += 1;
        }
    }

    for (sq = 0; sq < 8; ++sq) {
#if EVAL_USE_DOUBLED_PAWN
        if (file_counts_white[sq] > 1) {
            eval_score_add(&score, -10 * (file_counts_white[sq] - 1), -16 * (file_counts_white[sq] - 1));
        }
        if (file_counts_black[sq] > 1) {
            eval_score_add(&score, 10 * (file_counts_black[sq] - 1), 16 * (file_counts_black[sq] - 1));
        }
#endif
    }

    for (sq = 0; sq < 64; ++sq) {
        int piece = state->board[sq];
        int side;
        int file;
        int rank_index EVAL_MAYBE_UNUSED = 0;
        bool isolated;

        if (piece != WP && piece != BP) {
            continue;
        }

        side = piece_side(piece);
        file = file_of(sq);
        isolated = true;

        if (file > 0) {
            isolated = isolated && ((side == WHITE ? file_counts_white[file - 1] : file_counts_black[file - 1]) == 0);
        }
        if (file < 7) {
            isolated = isolated && ((side == WHITE ? file_counts_white[file + 1] : file_counts_black[file + 1]) == 0);
        }

#if EVAL_USE_ISOLATED_PAWN
        if (isolated) {
            if (side == WHITE) {
                eval_score_add(&score, -12, -10);
            } else {
                eval_score_add(&score, 12, 10);
            }
        }
#endif

#if EVAL_USE_CONNECTED_PAWN
        if (has_connected_pawn(state, sq, side)) {
            if (side == WHITE) {
                eval_score_add(&score, 4, 8);
            } else {
                eval_score_add(&score, -4, -8);
            }
        }
#endif

#if EVAL_USE_PASSED_PAWN
        if (is_passed_pawn(state, sq, side)) {
            rank_index = side == WHITE ? rank_of(sq) : (7 - rank_of(sq));
            if (side == WHITE) {
                eval_score_add(&score, PASSED_PAWN_MG[rank_index], PASSED_PAWN_EG[rank_index]);
            } else {
                eval_score_add(&score, -PASSED_PAWN_MG[rank_index], -PASSED_PAWN_EG[rank_index]);
            }
        }
#endif
    }

    return score;
}

static int mobility_weight(int abs_piece) {
    switch (abs_piece) {
        case WN:
            return 4;
        case WB:
            return 5;
        case WR:
            return 3;
        case WQ:
            return 2;
        default:
            return 0;
    }
}

static int count_knight_mobility(const EngineState *state, int from, int side) {
    static const int KNIGHT_DR[8] = {2, 2, 1, 1, -1, -1, -2, -2};
    static const int KNIGHT_DF[8] = {1, -1, 2, -2, 2, -2, 1, -1};
    int from_rank = rank_of(from);
    int from_file = file_of(from);
    int count = 0;
    int i;

    for (i = 0; i < 8; ++i) {
        int to_rank = from_rank + KNIGHT_DR[i];
        int to_file = from_file + KNIGHT_DF[i];
        int to_sq;
        int target;
        if (!on_board_rf(to_rank, to_file)) {
            continue;
        }
        to_sq = to_rank * 8 + to_file;
        target = state->board[to_sq];
        if (target == EMPTY || piece_side(target) != side) {
            count += 1;
        }
    }
    return count;
}

static int count_slider_mobility(const EngineState *state, int from, int side, const int dr[], const int df[], int count_dirs) {
    int from_rank = rank_of(from);
    int from_file = file_of(from);
    int count = 0;
    int dir;

    for (dir = 0; dir < count_dirs; ++dir) {
        int to_rank = from_rank + dr[dir];
        int to_file = from_file + df[dir];
        while (on_board_rf(to_rank, to_file)) {
            int to_sq = to_rank * 8 + to_file;
            int target = state->board[to_sq];
            if (target == EMPTY) {
                count += 1;
            } else {
                if (piece_side(target) != side) {
                    count += 1;
                }
                break;
            }
            to_rank += dr[dir];
            to_file += df[dir];
        }
    }

    return count;
}

static int mobility_from_square(const EngineState *state, int sq, int piece, int side) {
    static const int BISHOP_DR[4] = {1, 1, -1, -1};
    static const int BISHOP_DF[4] = {1, -1, 1, -1};
    static const int ROOK_DR[4] = {1, -1, 0, 0};
    static const int ROOK_DF[4] = {0, 0, 1, -1};

    switch (piece_abs(piece)) {
        case WN:
            return count_knight_mobility(state, sq, side);
        case WB:
            return count_slider_mobility(state, sq, side, BISHOP_DR, BISHOP_DF, 4);
        case WR:
            return count_slider_mobility(state, sq, side, ROOK_DR, ROOK_DF, 4);
        case WQ:
            return count_slider_mobility(state, sq, side, BISHOP_DR, BISHOP_DF, 4) +
                   count_slider_mobility(state, sq, side, ROOK_DR, ROOK_DF, 4);
        default:
            return 0;
    }
}

static int mobility_for_side(const EngineState *state, int side) {
    int sq;
    int score = 0;

    for (sq = 0; sq < 64; ++sq) {
        int piece = state->board[sq];
        int weight;
        if (piece == EMPTY || piece_side(piece) != side) {
            continue;
        }
        weight = mobility_weight(piece_abs(piece));
        if (weight == 0) {
            continue;
        }
        score += mobility_from_square(state, sq, piece, side) * weight;
    }
    return score;
}

static __attribute__((unused)) int evaluate_mobility(EngineState *state) {
    return mobility_for_side(state, WHITE) - mobility_for_side(state, BLACK);
}

static __attribute__((unused)) int evaluate_king_ring_pressure(const EngineState *state) {
    int wk = engine_find_king_square_internal(state, WHITE);
    int bk = engine_find_king_square_internal(state, BLACK);
    int score = 0;

    if (wk >= 0) {
        int attacks = 0;
        int i;
        for (i = 0; i < 8; ++i) {
            int sq = wk + KING_OFFSETS[i];
            if (!on_board64(sq) || abs(file_of(sq) - file_of(wk)) > 1) {
                continue;
            }
            if (engine_is_square_attacked_internal(state, sq, BLACK)) {
                attacks += 1;
            }
        }
        score -= attacks * 6;
    }

    if (bk >= 0) {
        int attacks = 0;
        int i;
        for (i = 0; i < 8; ++i) {
            int sq = bk + KING_OFFSETS[i];
            if (!on_board64(sq) || abs(file_of(sq) - file_of(bk)) > 1) {
                continue;
            }
            if (engine_is_square_attacked_internal(state, sq, WHITE)) {
                attacks += 1;
            }
        }
        score += attacks * 6;
    }

    return score;
}

static __attribute__((unused)) int evaluate_king_shelter(const EngineState *state) {
    int wk = engine_find_king_square_internal(state, WHITE);
    int bk = engine_find_king_square_internal(state, BLACK);
    int score = 0;

    if (wk >= 0) {
        int front_rank = rank_of(wk) + 1;
        int file;
        for (file = file_of(wk) - 1; file <= file_of(wk) + 1; ++file) {
            if (file < 0 || file > 7) {
                continue;
            }
            if (front_rank < 8 && state->board[front_rank * 8 + file] != WP) {
                score -= 8;
            }
            if (!has_friendly_pawn_on_file(state, WHITE, file)) {
                score -= 10;
            }
        }
    }

    if (bk >= 0) {
        {
            int front_rank = rank_of(bk) - 1;
            int file;
            for (file = file_of(bk) - 1; file <= file_of(bk) + 1; ++file) {
                if (file < 0 || file > 7) {
                    continue;
                }
                if (front_rank >= 0 && state->board[front_rank * 8 + file] != BP) {
                    score += 8;
                }
                if (!has_friendly_pawn_on_file(state, BLACK, file)) {
                    score += 10;
                }
            }
        }
    }

    return score;
}

static __attribute__((unused)) int static_exchange_eval(const EngineState *state, const EngineMove *move) {
    int board[64];
    int attacker;
    int victim_sq;
    int victim;
    int placed_piece;
    int immediate_gain = 0;
    int side;

    if (state == NULL || move == NULL || !on_board64(move->from) || !on_board64(move->to)) {
        return 0;
    }

    memcpy(board, state->board, sizeof(board));
    attacker = board[move->from];
    if (attacker == EMPTY) {
        return 0;
    }

    side = piece_side(attacker);
    victim_sq = move->to;
    victim = board[victim_sq];

    if ((move->flags & FLAG_EN_PASSANT) != 0 && victim == EMPTY) {
        victim_sq = side == WHITE ? ((int)move->to - 8) : ((int)move->to + 8);
        if (!on_board64(victim_sq)) {
            return 0;
        }
        victim = board[victim_sq];
    }

    if (victim != EMPTY) {
        immediate_gain += PIECE_VALUE[piece_abs(victim)];
    }

    placed_piece = piece_after_capture(attacker, move->to, move->promotion);
    if (move->promotion != 0 && piece_abs(attacker) == WP) {
        immediate_gain += PIECE_VALUE[piece_abs(placed_piece)] - PIECE_VALUE[piece_abs(attacker)];
    }

    board[move->from] = EMPTY;
    board[victim_sq] = EMPTY;
    board[move->to] = placed_piece;

    return immediate_gain - see_best_response(board, move->to, side ^ 1);
}

static void accumulate_material_and_tables(const EngineState *state, EvalAccumulator *acc) {
    int sq;

    for (sq = 0; sq < 64; ++sq) {
        int piece = state->board[sq];
        int side;
        int abs_piece;

        if (piece == EMPTY) {
            continue;
        }

        side = piece_side(piece);
        abs_piece = piece_abs(piece);

#if CFG_EVALUATION
        acc->mg += (side == WHITE ? 1 : -1) * PIECE_VALUE[abs_piece];
        acc->eg += (side == WHITE ? 1 : -1) * PIECE_VALUE[abs_piece];
#endif

#if CFG_PIECE_SQUARE_TABLES
        int psq = side == WHITE ? sq : mirror_sq(sq);
        switch (abs_piece) {
            case WP:
                acc->mg += (side == WHITE ? 1 : -1) * PST_PAWN[psq];
                acc->eg += (side == WHITE ? 1 : -1) * PST_PAWN[psq];
                break;
            case WN:
                acc->mg += (side == WHITE ? 1 : -1) * PST_KNIGHT[psq];
                acc->eg += (side == WHITE ? 1 : -1) * PST_KNIGHT[psq];
                acc->phase += 1;
                break;
            case WB:
                acc->mg += (side == WHITE ? 1 : -1) * PST_BISHOP[psq];
                acc->eg += (side == WHITE ? 1 : -1) * PST_BISHOP[psq];
                acc->phase += 1;
                break;
            case WR:
                acc->mg += (side == WHITE ? 1 : -1) * PST_ROOK[psq];
                acc->eg += (side == WHITE ? 1 : -1) * PST_ROOK[psq];
                acc->phase += 2;
                break;
            case WQ:
                acc->mg += (side == WHITE ? 1 : -1) * PST_QUEEN[psq];
                acc->eg += (side == WHITE ? 1 : -1) * PST_QUEEN[psq];
                acc->phase += 4;
                break;
            case WK:
                acc->mg += (side == WHITE ? 1 : -1) * PST_KING_MG[psq];
                acc->eg += (side == WHITE ? 1 : -1) * PST_KING_EG[psq];
                break;
            default:
                break;
        }
#endif
    }
}

static EVAL_MAYBE_UNUSED EvalScore evaluate_piece_coordination(const EngineState *state) {
    EvalScore score = eval_score_make(0, 0);
    int white_bishops EVAL_MAYBE_UNUSED = 0;
    int black_bishops EVAL_MAYBE_UNUSED = 0;
    int sq;

    for (sq = 0; sq < 64; ++sq) {
        int piece = state->board[sq];
        if (piece == WB) {
            white_bishops += 1;
        } else if (piece == BB) {
            black_bishops += 1;
        } else if (piece == WR || piece == BR) {
            int side = piece_side(piece);
            int file = file_of(sq);
            bool own_pawns EVAL_MAYBE_UNUSED = has_friendly_pawn_on_file(state, side, file);
            bool enemy_pawns EVAL_MAYBE_UNUSED = has_friendly_pawn_on_file(state, side ^ 1, file);

#if EVAL_USE_ROOK_OPEN_FILE
            if (!own_pawns && !enemy_pawns) {
                if (side == WHITE) {
                    eval_score_add(&score, 18, 10);
                } else {
                    eval_score_add(&score, -18, -10);
                }
            }
#endif
#if EVAL_USE_ROOK_SEMI_OPEN_FILE
            if (!own_pawns && enemy_pawns) {
                if (side == WHITE) {
                    eval_score_add(&score, 10, 6);
                } else {
                    eval_score_add(&score, -10, -6);
                }
            }
#endif
        }
    }

#if EVAL_USE_BISHOP_PAIR
    if (white_bishops >= 2) {
        eval_score_add(&score, 28, 40);
    }
    if (black_bishops >= 2) {
        eval_score_add(&score, -28, -40);
    }
#endif

    return score;
}

static EVAL_MAYBE_UNUSED EvalScore evaluate_king_activity(const EngineState *state) {
    EvalScore score = eval_score_make(0, 0);
    int white_king = engine_find_king_square_internal(state, WHITE);
    int black_king = engine_find_king_square_internal(state, BLACK);

    if (white_king >= 0) {
#if CFG_TAPERED_EVAL
        eval_score_add(&score, 0, king_centralization_bonus(white_king));
#else
        eval_score_add(&score, king_centralization_bonus(white_king), 0);
#endif
    }
    if (black_king >= 0) {
#if CFG_TAPERED_EVAL
        eval_score_add(&score, 0, -king_centralization_bonus(black_king));
#else
        eval_score_add(&score, -king_centralization_bonus(black_king), 0);
#endif
    }

    return score;
}

static void accumulate_pawn_terms(const EngineState *state, EvalAccumulator *acc) {
#if CFG_PAWN_HASH_TABLE && EVAL_USE_ANY_PAWN_TERM
    uint64_t key = engine_pawn_key_internal(state);
    PawnHashEntry *entry = &g_pawn_hash[key & PAWN_HASH_MASK];
    if (entry->key == key) {
        acc->mg += entry->mg;
        acc->eg += entry->eg;
    } else {
        EvalScore pawn_score = evaluate_pawn_terms(state);
        entry->key = key;
        entry->mg = pawn_score.mg;
        entry->eg = pawn_score.eg;
        accumulator_add(acc, pawn_score);
    }
#elif EVAL_USE_ANY_PAWN_TERM
    accumulator_add(acc, evaluate_pawn_terms(state));
#else
    (void)state;
    (void)acc;
#endif
}

static void accumulate_piece_coordination_terms(const EngineState *state, EvalAccumulator *acc) {
#if EVAL_USE_ANY_COORD_TERM
    accumulator_add(acc, evaluate_piece_coordination(state));
#else
    (void)state;
    (void)acc;
#endif
}

static void accumulate_mobility_term(EngineState *state, EvalAccumulator *acc) {
#if CFG_MOBILITY
    acc->mg += evaluate_mobility(state);
#else
    (void)state;
    (void)acc;
#endif
}

static void accumulate_king_safety_term(const EngineState *state, EvalAccumulator *acc) {
#if EVAL_USE_KING_RING_PRESSURE
    acc->mg += evaluate_king_ring_pressure(state);
#endif
#if EVAL_USE_KING_SHELTER
    acc->mg += evaluate_king_shelter(state);
#endif
#if EVAL_USE_ANY_KING_TERM
#else
    (void)state;
    (void)acc;
#endif
}

static void accumulate_king_activity_term(const EngineState *state, EvalAccumulator *acc) {
#if EVAL_USE_KING_ACTIVITY
    accumulator_add(acc, evaluate_king_activity(state));
#else
    (void)state;
    (void)acc;
#endif
}

static int finalize_score(const EngineState *state, const EvalAccumulator *acc) {
    int score;

#if CFG_TAPERED_EVAL
    int phase = acc->phase;
    if (phase > 24) {
        phase = 24;
    }
    score = (acc->mg * phase + acc->eg * (24 - phase)) / 24;
#else
    (void)acc->eg;
    (void)acc->phase;
    score = acc->mg;
#endif

    return state->side_to_move == WHITE ? score : -score;
}

int engine_evaluate_position_internal(EngineState *state) {
    uint64_t key;
    EvalCacheEntry *entry;
    EvalAccumulator acc = {0, 0, 0};
    int score;

    engine_note_eval_call_internal();
    key = engine_state_key_internal(state);
    entry = &g_eval_cache[key & EVAL_CACHE_MASK];
    if (entry->key == key) {
        engine_note_eval_cache_hit_internal();
        return entry->score;
    }

    accumulate_material_and_tables(state, &acc);
    accumulate_piece_coordination_terms(state, &acc);
    accumulate_pawn_terms(state, &acc);
    accumulate_mobility_term(state, &acc);
    accumulate_king_safety_term(state, &acc);
    accumulate_king_activity_term(state, &acc);

    score = finalize_score(state, &acc);
    entry->key = key;
    entry->score = score;
    return score;
}

int engine_score_capture_internal(const EngineState *state, const EngineMove *move) {
    int victim_sq;
    int victim;
    int attacker;
    int score = 0;

    if (state == NULL || move == NULL) {
        return 0;
    }

    attacker = state->board[move->from];

    victim_sq = move->to;
    victim = state->board[victim_sq];
    if ((move->flags & FLAG_EN_PASSANT) != 0 && victim == EMPTY) {
        int side = piece_side(attacker);
        victim_sq = side == WHITE ? ((int)move->to - 8) : ((int)move->to + 8);
        if (on_board64(victim_sq)) {
            victim = state->board[victim_sq];
        }
    }

    if (victim != EMPTY) {
        score += 10 * PIECE_VALUE[piece_abs(victim)] - PIECE_VALUE[piece_abs(attacker)];
#if CFG_STATIC_EXCHANGE_EVALUATION
        score += static_exchange_eval(state, move);
#endif
    }
    return score;
}

void engine_reset_evaluation_tables(void) {
    memset(g_pawn_hash, 0, sizeof(g_pawn_hash));
    memset(g_eval_cache, 0, sizeof(g_eval_cache));
}

static void append_profile_token(char *profile, size_t profile_size, const char *token) {
    size_t current;

    if (profile == NULL || profile_size == 0 || token == NULL || token[0] == '\0') {
        return;
    }

    current = strlen(profile);
    if (current >= profile_size - 1) {
        return;
    }

    if (current != 0) {
        snprintf(profile + current, profile_size - current, "+%s", token);
    } else {
        snprintf(profile, profile_size, "%s", token);
    }
}

const char *engine_eval_profile_name(void) {
    static char profile[128];
    static bool ready = false;

    if (ready) {
        return profile;
    }

#if CFG_EVALUATION
    append_profile_token(profile, sizeof(profile), "Material");
#endif
#if CFG_PIECE_SQUARE_TABLES
    append_profile_token(profile, sizeof(profile), "PST");
#endif
#if CFG_PASSED_PAWN
    append_profile_token(profile, sizeof(profile), "PassedPawn");
#endif
#if CFG_ISOLATED_PAWN
    append_profile_token(profile, sizeof(profile), "IsolatedPawn");
#endif
#if CFG_DOUBLED_PAWN
    append_profile_token(profile, sizeof(profile), "DoubledPawn");
#endif
#if CFG_CONNECTED_PAWN
    append_profile_token(profile, sizeof(profile), "ConnectedPawn");
#endif
#if CFG_PAWN_HASH_TABLE
    append_profile_token(profile, sizeof(profile), "PawnHash");
#endif
#if CFG_BISHOP_PAIR
    append_profile_token(profile, sizeof(profile), "BishopPair");
#endif
#if CFG_ROOK_OPEN_FILE
    append_profile_token(profile, sizeof(profile), "RookOpen");
#endif
#if CFG_ROOK_SEMI_OPEN_FILE
    append_profile_token(profile, sizeof(profile), "RookSemiOpen");
#endif
#if CFG_MOBILITY
    append_profile_token(profile, sizeof(profile), "Mobility");
#endif
#if CFG_KING_SAFETY
    append_profile_token(profile, sizeof(profile), "KingPressure");
#endif
#if CFG_KING_SHELTER
    append_profile_token(profile, sizeof(profile), "KingShelter");
#endif
#if CFG_KING_ACTIVITY
    append_profile_token(profile, sizeof(profile), "KingActivity");
#endif
#if CFG_TAPERED_EVAL
    append_profile_token(profile, sizeof(profile), "Tapered");
#endif
#if CFG_STATIC_EXCHANGE_EVALUATION
    append_profile_token(profile, sizeof(profile), "SEE");
#endif

    if (profile[0] == '\0') {
        append_profile_token(profile, sizeof(profile), "None");
    }

    ready = true;
    return profile;
}
