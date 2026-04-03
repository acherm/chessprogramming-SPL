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

static int mobility_for_side(const EngineState *state, int side) {
    EngineMoveList list;
    EngineState copy = *state;
    int i;
    int score = 0;

    copy.side_to_move = side;
    engine_generate_pseudo_moves_internal(&copy, &list, false);
    for (i = 0; i < list.count; ++i) {
        int piece = copy.board[list.moves[i].from];
        score += mobility_weight(piece_abs(piece));
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
    int target = state->board[move->to];
    int attacker = state->board[move->from];
    return PIECE_VALUE[piece_abs(target)] - PIECE_VALUE[piece_abs(attacker)] / 8;
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
    uint64_t key = engine_state_key_internal(state);
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
    EvalAccumulator acc = {0, 0, 0};

    accumulate_material_and_tables(state, &acc);
    accumulate_piece_coordination_terms(state, &acc);
    accumulate_pawn_terms(state, &acc);
    accumulate_mobility_term(state, &acc);
    accumulate_king_safety_term(state, &acc);
    accumulate_king_activity_term(state, &acc);

    return finalize_score(state, &acc);
}

int engine_score_capture_internal(const EngineState *state, const EngineMove *move) {
    int victim = state->board[move->to];
    int attacker = state->board[move->from];
    int score = 0;

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
