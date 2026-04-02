#include "engine_backend_internal.h"

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

#define FLAG_CAPTURE 1
#define FLAG_PROMOTION 2
#define FLAG_EN_PASSANT 4
#define FLAG_CASTLING 8
#define FLAG_DOUBLE_PAWN 16

#define CASTLE_WHITE_K 1
#define CASTLE_WHITE_Q 2
#define CASTLE_BLACK_K 4
#define CASTLE_BLACK_Q 8

#define OFFBOARD_120 99

#if defined(__clang__) || defined(__GNUC__)
#define ENGINE_MAYBE_UNUSED __attribute__((unused))
#else
#define ENGINE_MAYBE_UNUSED
#endif

static const int KNIGHT_OFFSETS_64[8] = {17, 15, 10, 6, -17, -15, -10, -6};
static const int BISHOP_OFFSETS_64[4] = {9, 7, -9, -7};
static const int ROOK_OFFSETS_64[4] = {8, -8, 1, -1};
static const int KING_OFFSETS_64[8] = {8, -8, 1, -1, 9, 7, -9, -7};

static const int KNIGHT_OFFSETS_0X88[8] = {33, 31, 18, 14, -33, -31, -18, -14};
static const int BISHOP_OFFSETS_0X88[4] = {17, 15, -17, -15};
static const int ROOK_OFFSETS_0X88[4] = {16, -16, 1, -1};
static const int KING_OFFSETS_0X88[8] = {16, -16, 1, -1, 17, 15, -17, -15};

static const int KNIGHT_OFFSETS_120[8] = {21, 19, 12, 8, -21, -19, -12, -8};
static const int BISHOP_OFFSETS_120[4] = {11, 9, -11, -9};
static const int ROOK_OFFSETS_120[4] = {10, -10, 1, -1};
static const int KING_OFFSETS_120[8] = {10, -10, 1, -1, 11, 9, -11, -9};

static const uint64_t FILE_A_MASK = 0x0101010101010101ULL;
static const uint64_t FILE_H_MASK = 0x8080808080808080ULL;

static int g_sq64_to_0x88[64];
static int g_sq0x88_to_64[128];
static int g_sq64_to_120[64];
static int g_sq120_to_64[120];
static bool g_backend_maps_ready = false;

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

static inline bool on_board64(int sq) {
    return sq >= 0 && sq < 64;
}

static inline bool same_rank(int a, int b) {
    return rank_of(a) == rank_of(b);
}

static inline uint64_t square_bb(int sq) {
    return 1ULL << sq;
}

static void move_list_push(EngineMoveList *list, EngineMove move) {
    if (list->count >= ENGINE_MAX_MOVES) {
        return;
    }
    list->moves[list->count] = move;
    list->count += 1;
}

static void init_backend_maps(void) {
    int sq;

    if (g_backend_maps_ready) {
        return;
    }

    for (sq = 0; sq < 128; ++sq) {
        g_sq0x88_to_64[sq] = -1;
    }
    for (sq = 0; sq < 120; ++sq) {
        g_sq120_to_64[sq] = -1;
    }

    for (sq = 0; sq < 64; ++sq) {
        int rank = rank_of(sq);
        int file = file_of(sq);
        int sq0x88 = (rank << 4) + file;
        int sq120 = (rank + 2) * 10 + (file + 1);
        g_sq64_to_0x88[sq] = sq0x88;
        g_sq0x88_to_64[sq0x88] = sq;
        g_sq64_to_120[sq] = sq120;
        g_sq120_to_64[sq120] = sq;
    }

    g_backend_maps_ready = true;
}

static int piece_to_bb_index(int piece) {
    switch (piece) {
        case WP:
            return 0;
        case WN:
            return 1;
        case WB:
            return 2;
        case WR:
            return 3;
        case WQ:
            return 4;
        case WK:
            return 5;
        case BP:
            return 6;
        case BN:
            return 7;
        case BB:
            return 8;
        case BR:
            return 9;
        case BQ:
            return 10;
        case BK:
            return 11;
        default:
            return -1;
    }
}

static int bit_scan_forward(uint64_t bits) {
    int sq = 0;
    while ((bits & 1ULL) == 0ULL) {
        bits >>= 1;
        sq += 1;
    }
    return sq;
}

static int pop_lsb(uint64_t *bits) {
    uint64_t lsb = *bits & (~(*bits) + 1ULL);
    int sq = bit_scan_forward(lsb);
    *bits &= *bits - 1ULL;
    return sq;
}

static bool step_preserves_geometry(int from_sq, int to_sq, int delta) {
    if (!on_board64(to_sq)) {
        return false;
    }
    if (delta == 1 || delta == -1) {
        return same_rank(from_sq, to_sq);
    }
    if (delta == 9 || delta == -9 || delta == 7 || delta == -7) {
        return abs(file_of(to_sq) - file_of(from_sq)) == 1;
    }
    return true;
}

static bool ray_attacks_square(int from_sq, int target_sq, int delta, uint64_t occ) {
    int sq = from_sq + delta;

    while (step_preserves_geometry(sq - delta, sq, delta)) {
        if (sq == target_sq) {
            return true;
        }
        if ((occ & square_bb(sq)) != 0ULL) {
            return false;
        }
        sq += delta;
    }

    return false;
}

static bool square_attacked_by_knight_64(int from_sq, int target_sq) {
    int i;

    for (i = 0; i < 8; ++i) {
        int to = from_sq + KNIGHT_OFFSETS_64[i];
        if (!on_board64(to)) {
            continue;
        }
        if (abs(file_of(to) - file_of(from_sq)) > 2) {
            continue;
        }
        if (to == target_sq) {
            return true;
        }
    }

    return false;
}

static bool square_attacked_by_king_64(int from_sq, int target_sq) {
    int i;

    for (i = 0; i < 8; ++i) {
        int to = from_sq + KING_OFFSETS_64[i];
        if (!on_board64(to)) {
            continue;
        }
        if (abs(file_of(to) - file_of(from_sq)) > 1) {
            continue;
        }
        if (to == target_sq) {
            return true;
        }
    }

    return false;
}

static void add_special_moves(const EngineState *state, EngineMoveList *list, bool captures_only) {
#if CFG_EN_PASSANT
    if (state->en_passant_square >= 0 && state->en_passant_square < 64) {
        int ep = state->en_passant_square;
        int side = state->side_to_move;
        int from_a = side == WHITE ? ep - 9 : ep + 9;
        int from_b = side == WHITE ? ep - 7 : ep + 7;

        if (on_board64(from_a) &&
            abs(file_of(from_a) - file_of(ep)) == 1 &&
            state->board[from_a] == (side == WHITE ? WP : BP)) {
            EngineMove mv;
            memset(&mv, 0, sizeof(mv));
            mv.from = (uint8_t)from_a;
            mv.to = (uint8_t)ep;
            mv.flags = FLAG_CAPTURE | FLAG_EN_PASSANT;
            move_list_push(list, mv);
        }
        if (on_board64(from_b) &&
            abs(file_of(from_b) - file_of(ep)) == 1 &&
            state->board[from_b] == (side == WHITE ? WP : BP)) {
            EngineMove mv;
            memset(&mv, 0, sizeof(mv));
            mv.from = (uint8_t)from_b;
            mv.to = (uint8_t)ep;
            mv.flags = FLAG_CAPTURE | FLAG_EN_PASSANT;
            move_list_push(list, mv);
        }
    }
#endif

    if (captures_only) {
        return;
    }

#if CFG_CASTLING
    if (state->side_to_move == WHITE &&
        state->board[4] == WK &&
        !engine_backend_is_square_attacked(state, 4, BLACK)) {
        if ((state->castling_rights & CASTLE_WHITE_K) != 0 &&
            state->board[5] == EMPTY &&
            state->board[6] == EMPTY &&
            state->board[7] == WR &&
            !engine_backend_is_square_attacked(state, 5, BLACK) &&
            !engine_backend_is_square_attacked(state, 6, BLACK)) {
            EngineMove ks;
            memset(&ks, 0, sizeof(ks));
            ks.from = 4;
            ks.to = 6;
            ks.flags = FLAG_CASTLING;
            move_list_push(list, ks);
        }
        if ((state->castling_rights & CASTLE_WHITE_Q) != 0 &&
            state->board[1] == EMPTY &&
            state->board[2] == EMPTY &&
            state->board[3] == EMPTY &&
            state->board[0] == WR &&
            !engine_backend_is_square_attacked(state, 3, BLACK) &&
            !engine_backend_is_square_attacked(state, 2, BLACK)) {
            EngineMove qs;
            memset(&qs, 0, sizeof(qs));
            qs.from = 4;
            qs.to = 2;
            qs.flags = FLAG_CASTLING;
            move_list_push(list, qs);
        }
    } else if (state->side_to_move == BLACK &&
               state->board[60] == BK &&
               !engine_backend_is_square_attacked(state, 60, WHITE)) {
        if ((state->castling_rights & CASTLE_BLACK_K) != 0 &&
            state->board[61] == EMPTY &&
            state->board[62] == EMPTY &&
            state->board[63] == BR &&
            !engine_backend_is_square_attacked(state, 61, WHITE) &&
            !engine_backend_is_square_attacked(state, 62, WHITE)) {
            EngineMove ks;
            memset(&ks, 0, sizeof(ks));
            ks.from = 60;
            ks.to = 62;
            ks.flags = FLAG_CASTLING;
            move_list_push(list, ks);
        }
        if ((state->castling_rights & CASTLE_BLACK_Q) != 0 &&
            state->board[57] == EMPTY &&
            state->board[58] == EMPTY &&
            state->board[59] == EMPTY &&
            state->board[56] == BR &&
            !engine_backend_is_square_attacked(state, 59, WHITE) &&
            !engine_backend_is_square_attacked(state, 58, WHITE)) {
            EngineMove qs;
            memset(&qs, 0, sizeof(qs));
            qs.from = 60;
            qs.to = 58;
            qs.flags = FLAG_CASTLING;
            move_list_push(list, qs);
        }
    }
#endif
}

static ENGINE_MAYBE_UNUSED int find_king_square_default(const EngineState *state, int side) {
    int sq;
    int king = side == WHITE ? WK : BK;

    for (sq = 0; sq < 64; ++sq) {
        if (state->board[sq] == king) {
            return sq;
        }
    }

    return -1;
}

static ENGINE_MAYBE_UNUSED bool is_square_attacked_default(const EngineState *state, int sq, int attacker_side) {
    int i;

    if (!on_board64(sq)) {
        return false;
    }

    if (attacker_side == WHITE) {
        int p1 = sq - 9;
        int p2 = sq - 7;
        if (on_board64(p1) && file_of(p1) == file_of(sq) - 1 && state->board[p1] == WP) {
            return true;
        }
        if (on_board64(p2) && file_of(p2) == file_of(sq) + 1 && state->board[p2] == WP) {
            return true;
        }
    } else {
        int p1 = sq + 9;
        int p2 = sq + 7;
        if (on_board64(p1) && file_of(p1) == file_of(sq) + 1 && state->board[p1] == BP) {
            return true;
        }
        if (on_board64(p2) && file_of(p2) == file_of(sq) - 1 && state->board[p2] == BP) {
            return true;
        }
    }

    for (i = 0; i < 8; ++i) {
        int nsq = sq + KNIGHT_OFFSETS_64[i];
        if (!on_board64(nsq)) {
            continue;
        }
        if (abs(file_of(nsq) - file_of(sq)) > 2) {
            continue;
        }
        if (attacker_side == WHITE && state->board[nsq] == WN) {
            return true;
        }
        if (attacker_side == BLACK && state->board[nsq] == BN) {
            return true;
        }
    }

    for (i = 0; i < 4; ++i) {
        int delta = BISHOP_OFFSETS_64[i];
        int nsq = sq + delta;
        while (step_preserves_geometry(nsq - delta, nsq, delta)) {
            int piece = state->board[nsq];
            if (piece != EMPTY) {
                if (attacker_side == WHITE && (piece == WB || piece == WQ)) {
                    return true;
                }
                if (attacker_side == BLACK && (piece == BB || piece == BQ)) {
                    return true;
                }
                break;
            }
            nsq += delta;
        }
    }

    for (i = 0; i < 4; ++i) {
        int delta = ROOK_OFFSETS_64[i];
        int nsq = sq + delta;
        while (step_preserves_geometry(nsq - delta, nsq, delta)) {
            int piece = state->board[nsq];
            if (piece != EMPTY) {
                if (attacker_side == WHITE && (piece == WR || piece == WQ)) {
                    return true;
                }
                if (attacker_side == BLACK && (piece == BR || piece == BQ)) {
                    return true;
                }
                break;
            }
            nsq += delta;
        }
    }

    for (i = 0; i < 8; ++i) {
        int nsq = sq + KING_OFFSETS_64[i];
        if (!on_board64(nsq)) {
            continue;
        }
        if (abs(file_of(nsq) - file_of(sq)) > 1) {
            continue;
        }
        if (attacker_side == WHITE && state->board[nsq] == WK) {
            return true;
        }
        if (attacker_side == BLACK && state->board[nsq] == BK) {
            return true;
        }
    }

    return false;
}

static ENGINE_MAYBE_UNUSED int find_king_square_0x88(const EngineState *state, int side) {
    int sq;
    int king = side == WHITE ? WK : BK;

    for (sq = 0; sq < 128; ++sq) {
        if ((sq & 0x88) != 0) {
            continue;
        }
        if (state->board_0x88[sq] == king) {
            return g_sq0x88_to_64[sq];
        }
    }

    return -1;
}

static ENGINE_MAYBE_UNUSED bool is_square_attacked_0x88(const EngineState *state, int sq64, int attacker_side) {
    int sq;
    int i;

    if (!on_board64(sq64)) {
        return false;
    }

    sq = g_sq64_to_0x88[sq64];
    if (attacker_side == WHITE) {
        int p1 = sq - 15;
        int p2 = sq - 17;
        if ((p1 & 0x88) == 0 && state->board_0x88[p1] == WP) {
            return true;
        }
        if ((p2 & 0x88) == 0 && state->board_0x88[p2] == WP) {
            return true;
        }
    } else {
        int p1 = sq + 15;
        int p2 = sq + 17;
        if ((p1 & 0x88) == 0 && state->board_0x88[p1] == BP) {
            return true;
        }
        if ((p2 & 0x88) == 0 && state->board_0x88[p2] == BP) {
            return true;
        }
    }

    for (i = 0; i < 8; ++i) {
        int to = sq + KNIGHT_OFFSETS_0X88[i];
        if ((to & 0x88) != 0) {
            continue;
        }
        if (attacker_side == WHITE && state->board_0x88[to] == WN) {
            return true;
        }
        if (attacker_side == BLACK && state->board_0x88[to] == BN) {
            return true;
        }
    }

    for (i = 0; i < 4; ++i) {
        int delta = BISHOP_OFFSETS_0X88[i];
        int to = sq + delta;
        while ((to & 0x88) == 0) {
            int piece = state->board_0x88[to];
            if (piece != EMPTY) {
                if (attacker_side == WHITE && (piece == WB || piece == WQ)) {
                    return true;
                }
                if (attacker_side == BLACK && (piece == BB || piece == BQ)) {
                    return true;
                }
                break;
            }
            to += delta;
        }
    }

    for (i = 0; i < 4; ++i) {
        int delta = ROOK_OFFSETS_0X88[i];
        int to = sq + delta;
        while ((to & 0x88) == 0) {
            int piece = state->board_0x88[to];
            if (piece != EMPTY) {
                if (attacker_side == WHITE && (piece == WR || piece == WQ)) {
                    return true;
                }
                if (attacker_side == BLACK && (piece == BR || piece == BQ)) {
                    return true;
                }
                break;
            }
            to += delta;
        }
    }

    for (i = 0; i < 8; ++i) {
        int to = sq + KING_OFFSETS_0X88[i];
        if ((to & 0x88) != 0) {
            continue;
        }
        if (attacker_side == WHITE && state->board_0x88[to] == WK) {
            return true;
        }
        if (attacker_side == BLACK && state->board_0x88[to] == BK) {
            return true;
        }
    }

    return false;
}

static ENGINE_MAYBE_UNUSED int find_king_square_120(const EngineState *state, int side) {
    int sq;
    int king = side == WHITE ? WK : BK;

    for (sq = 0; sq < 120; ++sq) {
        if (state->board_120[sq] == king) {
            return g_sq120_to_64[sq];
        }
    }

    return -1;
}

static ENGINE_MAYBE_UNUSED bool is_square_attacked_120(const EngineState *state, int sq64, int attacker_side) {
    int sq;
    int i;

    if (!on_board64(sq64)) {
        return false;
    }

    sq = g_sq64_to_120[sq64];
    if (attacker_side == WHITE) {
        int p1 = sq - 9;
        int p2 = sq - 11;
        if (state->board_120[p1] == WP || state->board_120[p2] == WP) {
            return true;
        }
    } else {
        int p1 = sq + 9;
        int p2 = sq + 11;
        if (state->board_120[p1] == BP || state->board_120[p2] == BP) {
            return true;
        }
    }

    for (i = 0; i < 8; ++i) {
        int to = sq + KNIGHT_OFFSETS_120[i];
        if (state->board_120[to] == OFFBOARD_120) {
            continue;
        }
        if (attacker_side == WHITE && state->board_120[to] == WN) {
            return true;
        }
        if (attacker_side == BLACK && state->board_120[to] == BN) {
            return true;
        }
    }

    for (i = 0; i < 4; ++i) {
        int delta = BISHOP_OFFSETS_120[i];
        int to = sq + delta;
        while (state->board_120[to] != OFFBOARD_120) {
            int piece = state->board_120[to];
            if (piece != EMPTY) {
                if (attacker_side == WHITE && (piece == WB || piece == WQ)) {
                    return true;
                }
                if (attacker_side == BLACK && (piece == BB || piece == BQ)) {
                    return true;
                }
                break;
            }
            to += delta;
        }
    }

    for (i = 0; i < 4; ++i) {
        int delta = ROOK_OFFSETS_120[i];
        int to = sq + delta;
        while (state->board_120[to] != OFFBOARD_120) {
            int piece = state->board_120[to];
            if (piece != EMPTY) {
                if (attacker_side == WHITE && (piece == WR || piece == WQ)) {
                    return true;
                }
                if (attacker_side == BLACK && (piece == BR || piece == BQ)) {
                    return true;
                }
                break;
            }
            to += delta;
        }
    }

    for (i = 0; i < 8; ++i) {
        int to = sq + KING_OFFSETS_120[i];
        if (state->board_120[to] == OFFBOARD_120) {
            continue;
        }
        if (attacker_side == WHITE && state->board_120[to] == WK) {
            return true;
        }
        if (attacker_side == BLACK && state->board_120[to] == BK) {
            return true;
        }
    }

    return false;
}

static ENGINE_MAYBE_UNUSED int find_king_square_bitboards(const EngineState *state, int side) {
    uint64_t kings = state->bb_pieces[side == WHITE ? 5 : 11];
    if (kings == 0ULL) {
        return -1;
    }
    return bit_scan_forward(kings);
}

static ENGINE_MAYBE_UNUSED bool is_square_attacked_bitboards(const EngineState *state, int sq, int attacker_side) {
    uint64_t target;
    uint64_t occ;
    uint64_t pieces;

    if (!on_board64(sq)) {
        return false;
    }

    target = square_bb(sq);
    occ = state->bb_white_occ | state->bb_black_occ;

    if (attacker_side == WHITE) {
        uint64_t pawns = state->bb_pieces[0];
        uint64_t attacks = ((pawns & ~FILE_A_MASK) << 7) | ((pawns & ~FILE_H_MASK) << 9);
        if ((attacks & target) != 0ULL) {
            return true;
        }
    } else {
        uint64_t pawns = state->bb_pieces[6];
        uint64_t attacks = ((pawns & ~FILE_H_MASK) >> 7) | ((pawns & ~FILE_A_MASK) >> 9);
        if ((attacks & target) != 0ULL) {
            return true;
        }
    }

    pieces = state->bb_pieces[attacker_side == WHITE ? 1 : 7];
    while (pieces != 0ULL) {
        int from = pop_lsb(&pieces);
        if (square_attacked_by_knight_64(from, sq)) {
            return true;
        }
    }

    pieces = state->bb_pieces[attacker_side == WHITE ? 2 : 8] | state->bb_pieces[attacker_side == WHITE ? 4 : 10];
    while (pieces != 0ULL) {
        int from = pop_lsb(&pieces);
        int i;
        for (i = 0; i < 4; ++i) {
            if (ray_attacks_square(from, sq, BISHOP_OFFSETS_64[i], occ)) {
                return true;
            }
        }
    }

    pieces = state->bb_pieces[attacker_side == WHITE ? 3 : 9] | state->bb_pieces[attacker_side == WHITE ? 4 : 10];
    while (pieces != 0ULL) {
        int from = pop_lsb(&pieces);
        int i;
        for (i = 0; i < 4; ++i) {
            if (ray_attacks_square(from, sq, ROOK_OFFSETS_64[i], occ)) {
                return true;
            }
        }
    }

    pieces = state->bb_pieces[attacker_side == WHITE ? 5 : 11];
    while (pieces != 0ULL) {
        int from = pop_lsb(&pieces);
        if (square_attacked_by_king_64(from, sq)) {
            return true;
        }
    }

    return false;
}

static ENGINE_MAYBE_UNUSED void generate_moves_0x88(const EngineState *state, EngineMoveList *list, bool captures_only) {
    int sq;

    list->count = 0;
    for (sq = 0; sq < 128; ++sq) {
        int piece;
        if ((sq & 0x88) != 0) {
            continue;
        }
        piece = state->board_0x88[sq];
        if (piece == EMPTY || piece_side(piece) != state->side_to_move) {
            continue;
        }

        if (piece_abs(piece) == WP) {
            int dir = state->side_to_move == WHITE ? 16 : -16;
            int cap1 = state->side_to_move == WHITE ? 15 : -17;
            int cap2 = state->side_to_move == WHITE ? 17 : -15;
            int to = sq + dir;
            if (!captures_only && (to & 0x88) == 0 && state->board_0x88[to] == EMPTY) {
                EngineMove mv;
                int from64 = g_sq0x88_to_64[sq];
                int to64 = g_sq0x88_to_64[to];
                memset(&mv, 0, sizeof(mv));
                mv.from = (uint8_t)from64;
                mv.to = (uint8_t)to64;
                if ((state->side_to_move == WHITE && rank_of(from64) == 6) ||
                    (state->side_to_move == BLACK && rank_of(from64) == 1)) {
                    mv.promotion = 4;
                    mv.flags |= FLAG_PROMOTION;
                }
                move_list_push(list, mv);
                if ((state->side_to_move == WHITE && rank_of(from64) == 1) ||
                    (state->side_to_move == BLACK && rank_of(from64) == 6)) {
                    int to2 = sq + dir + dir;
                    if ((to2 & 0x88) == 0 && state->board_0x88[to2] == EMPTY) {
                        EngineMove dm = mv;
                        dm.to = (uint8_t)g_sq0x88_to_64[to2];
                        dm.promotion = 0;
                        dm.flags = FLAG_DOUBLE_PAWN;
                        move_list_push(list, dm);
                    }
                }
            }
            if (((sq + cap1) & 0x88) == 0) {
                int target = state->board_0x88[sq + cap1];
                if (target != EMPTY && piece_side(target) != state->side_to_move) {
                    EngineMove mv;
                    int from64 = g_sq0x88_to_64[sq];
                    int to64 = g_sq0x88_to_64[sq + cap1];
                    memset(&mv, 0, sizeof(mv));
                    mv.from = (uint8_t)from64;
                    mv.to = (uint8_t)to64;
                    mv.flags = FLAG_CAPTURE;
                    if ((state->side_to_move == WHITE && rank_of(from64) == 6) ||
                        (state->side_to_move == BLACK && rank_of(from64) == 1)) {
                        mv.promotion = 4;
                        mv.flags |= FLAG_PROMOTION;
                    }
                    move_list_push(list, mv);
                }
            }
            if (((sq + cap2) & 0x88) == 0) {
                int target = state->board_0x88[sq + cap2];
                if (target != EMPTY && piece_side(target) != state->side_to_move) {
                    EngineMove mv;
                    int from64 = g_sq0x88_to_64[sq];
                    int to64 = g_sq0x88_to_64[sq + cap2];
                    memset(&mv, 0, sizeof(mv));
                    mv.from = (uint8_t)from64;
                    mv.to = (uint8_t)to64;
                    mv.flags = FLAG_CAPTURE;
                    if ((state->side_to_move == WHITE && rank_of(from64) == 6) ||
                        (state->side_to_move == BLACK && rank_of(from64) == 1)) {
                        mv.promotion = 4;
                        mv.flags |= FLAG_PROMOTION;
                    }
                    move_list_push(list, mv);
                }
            }
            continue;
        }

        if (piece_abs(piece) == WN || piece_abs(piece) == WK) {
            const int *deltas = piece_abs(piece) == WN ? KNIGHT_OFFSETS_0X88 : KING_OFFSETS_0X88;
            int i;
            for (i = 0; i < 8; ++i) {
                int to = sq + deltas[i];
                int target;
                if ((to & 0x88) != 0) {
                    continue;
                }
                target = state->board_0x88[to];
                if (target != EMPTY && piece_side(target) == state->side_to_move) {
                    continue;
                }
                if (captures_only && target == EMPTY) {
                    continue;
                }
                {
                    EngineMove mv;
                    memset(&mv, 0, sizeof(mv));
                    mv.from = (uint8_t)g_sq0x88_to_64[sq];
                    mv.to = (uint8_t)g_sq0x88_to_64[to];
                    if (target != EMPTY) {
                        mv.flags = FLAG_CAPTURE;
                    }
                    move_list_push(list, mv);
                }
            }
            continue;
        }

        {
            const int *deltas = NULL;
            int count = 0;
            int i;
            if (piece_abs(piece) == WB) {
                deltas = BISHOP_OFFSETS_0X88;
                count = 4;
            } else if (piece_abs(piece) == WR) {
                deltas = ROOK_OFFSETS_0X88;
                count = 4;
            } else if (piece_abs(piece) == WQ) {
                static const int queen_offsets[8] = {17, 15, -17, -15, 16, -16, 1, -1};
                deltas = queen_offsets;
                count = 8;
            }
            if (deltas == NULL) {
                continue;
            }
            for (i = 0; i < count; ++i) {
                int d = deltas[i];
                int to = sq + d;
                while ((to & 0x88) == 0) {
                    int target = state->board_0x88[to];
                    if (target == EMPTY) {
                        if (!captures_only) {
                            EngineMove mv;
                            memset(&mv, 0, sizeof(mv));
                            mv.from = (uint8_t)g_sq0x88_to_64[sq];
                            mv.to = (uint8_t)g_sq0x88_to_64[to];
                            move_list_push(list, mv);
                        }
                    } else {
                        if (piece_side(target) != state->side_to_move) {
                            EngineMove mv;
                            memset(&mv, 0, sizeof(mv));
                            mv.from = (uint8_t)g_sq0x88_to_64[sq];
                            mv.to = (uint8_t)g_sq0x88_to_64[to];
                            mv.flags = FLAG_CAPTURE;
                            move_list_push(list, mv);
                        }
                        break;
                    }
                    to += d;
                }
            }
        }
    }

    add_special_moves(state, list, captures_only);
}

static ENGINE_MAYBE_UNUSED void generate_moves_120(const EngineState *state, EngineMoveList *list, bool captures_only) {
    int sq;

    list->count = 0;
    for (sq = 0; sq < 120; ++sq) {
        int piece = state->board_120[sq];
        if (piece == OFFBOARD_120 || piece == EMPTY || piece_side(piece) != state->side_to_move) {
            continue;
        }

        if (piece_abs(piece) == WP) {
            int dir = state->side_to_move == WHITE ? 10 : -10;
            int cap1 = state->side_to_move == WHITE ? 9 : -11;
            int cap2 = state->side_to_move == WHITE ? 11 : -9;
            int to = sq + dir;
            if (!captures_only && state->board_120[to] == EMPTY) {
                EngineMove mv;
                int from64 = g_sq120_to_64[sq];
                int to64 = g_sq120_to_64[to];
                memset(&mv, 0, sizeof(mv));
                mv.from = (uint8_t)from64;
                mv.to = (uint8_t)to64;
                if ((state->side_to_move == WHITE && rank_of(from64) == 6) ||
                    (state->side_to_move == BLACK && rank_of(from64) == 1)) {
                    mv.promotion = 4;
                    mv.flags |= FLAG_PROMOTION;
                }
                move_list_push(list, mv);
                if ((state->side_to_move == WHITE && rank_of(from64) == 1) ||
                    (state->side_to_move == BLACK && rank_of(from64) == 6)) {
                    int to2 = sq + dir + dir;
                    if (state->board_120[to2] == EMPTY) {
                        EngineMove dm = mv;
                        dm.to = (uint8_t)g_sq120_to_64[to2];
                        dm.promotion = 0;
                        dm.flags = FLAG_DOUBLE_PAWN;
                        move_list_push(list, dm);
                    }
                }
            }
            if (state->board_120[sq + cap1] != OFFBOARD_120 &&
                state->board_120[sq + cap1] != EMPTY &&
                piece_side(state->board_120[sq + cap1]) != state->side_to_move) {
                EngineMove mv;
                int from64 = g_sq120_to_64[sq];
                int to64 = g_sq120_to_64[sq + cap1];
                memset(&mv, 0, sizeof(mv));
                mv.from = (uint8_t)from64;
                mv.to = (uint8_t)to64;
                mv.flags = FLAG_CAPTURE;
                if ((state->side_to_move == WHITE && rank_of(from64) == 6) ||
                    (state->side_to_move == BLACK && rank_of(from64) == 1)) {
                    mv.promotion = 4;
                    mv.flags |= FLAG_PROMOTION;
                }
                move_list_push(list, mv);
            }
            if (state->board_120[sq + cap2] != OFFBOARD_120 &&
                state->board_120[sq + cap2] != EMPTY &&
                piece_side(state->board_120[sq + cap2]) != state->side_to_move) {
                EngineMove mv;
                int from64 = g_sq120_to_64[sq];
                int to64 = g_sq120_to_64[sq + cap2];
                memset(&mv, 0, sizeof(mv));
                mv.from = (uint8_t)from64;
                mv.to = (uint8_t)to64;
                mv.flags = FLAG_CAPTURE;
                if ((state->side_to_move == WHITE && rank_of(from64) == 6) ||
                    (state->side_to_move == BLACK && rank_of(from64) == 1)) {
                    mv.promotion = 4;
                    mv.flags |= FLAG_PROMOTION;
                }
                move_list_push(list, mv);
            }
            continue;
        }

        if (piece_abs(piece) == WN || piece_abs(piece) == WK) {
            const int *deltas = piece_abs(piece) == WN ? KNIGHT_OFFSETS_120 : KING_OFFSETS_120;
            int i;
            for (i = 0; i < 8; ++i) {
                int to = sq + deltas[i];
                int target = state->board_120[to];
                if (target == OFFBOARD_120) {
                    continue;
                }
                if (target != EMPTY && piece_side(target) == state->side_to_move) {
                    continue;
                }
                if (captures_only && target == EMPTY) {
                    continue;
                }
                {
                    EngineMove mv;
                    memset(&mv, 0, sizeof(mv));
                    mv.from = (uint8_t)g_sq120_to_64[sq];
                    mv.to = (uint8_t)g_sq120_to_64[to];
                    if (target != EMPTY) {
                        mv.flags = FLAG_CAPTURE;
                    }
                    move_list_push(list, mv);
                }
            }
            continue;
        }

        {
            const int *deltas = NULL;
            int count = 0;
            int i;
            if (piece_abs(piece) == WB) {
                deltas = BISHOP_OFFSETS_120;
                count = 4;
            } else if (piece_abs(piece) == WR) {
                deltas = ROOK_OFFSETS_120;
                count = 4;
            } else if (piece_abs(piece) == WQ) {
                static const int queen_offsets[8] = {11, 9, -11, -9, 10, -10, 1, -1};
                deltas = queen_offsets;
                count = 8;
            }
            if (deltas == NULL) {
                continue;
            }
            for (i = 0; i < count; ++i) {
                int d = deltas[i];
                int to = sq + d;
                while (state->board_120[to] != OFFBOARD_120) {
                    int target = state->board_120[to];
                    if (target == EMPTY) {
                        if (!captures_only) {
                            EngineMove mv;
                            memset(&mv, 0, sizeof(mv));
                            mv.from = (uint8_t)g_sq120_to_64[sq];
                            mv.to = (uint8_t)g_sq120_to_64[to];
                            move_list_push(list, mv);
                        }
                    } else {
                        if (piece_side(target) != state->side_to_move) {
                            EngineMove mv;
                            memset(&mv, 0, sizeof(mv));
                            mv.from = (uint8_t)g_sq120_to_64[sq];
                            mv.to = (uint8_t)g_sq120_to_64[to];
                            mv.flags = FLAG_CAPTURE;
                            move_list_push(list, mv);
                        }
                        break;
                    }
                    to += d;
                }
            }
        }
    }

    add_special_moves(state, list, captures_only);
}

static ENGINE_MAYBE_UNUSED void generate_moves_bitboards(const EngineState *state, EngineMoveList *list, bool captures_only) {
    int side = state->side_to_move;
    uint64_t own_occ = side == WHITE ? state->bb_white_occ : state->bb_black_occ;
    uint64_t opp_occ = side == WHITE ? state->bb_black_occ : state->bb_white_occ;
    uint64_t all_occ = own_occ | opp_occ;
    uint64_t pieces;

    list->count = 0;

    pieces = state->bb_pieces[side == WHITE ? 0 : 6];
    while (pieces != 0ULL) {
        int from = pop_lsb(&pieces);
        int forward = side == WHITE ? 8 : -8;
        int promote_rank = side == WHITE ? 6 : 1;
        int start_rank = side == WHITE ? 1 : 6;

        if (!captures_only) {
            int to = from + forward;
            if (on_board64(to) && (all_occ & square_bb(to)) == 0ULL) {
                EngineMove mv;
                memset(&mv, 0, sizeof(mv));
                mv.from = (uint8_t)from;
                mv.to = (uint8_t)to;
                if (rank_of(from) == promote_rank) {
                    mv.promotion = 4;
                    mv.flags |= FLAG_PROMOTION;
                }
                move_list_push(list, mv);

                if (rank_of(from) == start_rank) {
                    int to2 = from + 2 * forward;
                    if (on_board64(to2) && (all_occ & square_bb(to2)) == 0ULL) {
                        EngineMove dm = mv;
                        dm.to = (uint8_t)to2;
                        dm.promotion = 0;
                        dm.flags = FLAG_DOUBLE_PAWN;
                        move_list_push(list, dm);
                    }
                }
            }
        }

        {
            int deltas[2];
            int i;
            deltas[0] = side == WHITE ? 7 : -9;
            deltas[1] = side == WHITE ? 9 : -7;
            for (i = 0; i < 2; ++i) {
                int to = from + deltas[i];
                if (!on_board64(to)) {
                    continue;
                }
                if (abs(file_of(to) - file_of(from)) != 1) {
                    continue;
                }
                if ((opp_occ & square_bb(to)) != 0ULL) {
                    EngineMove mv;
                    memset(&mv, 0, sizeof(mv));
                    mv.from = (uint8_t)from;
                    mv.to = (uint8_t)to;
                    mv.flags = FLAG_CAPTURE;
                    if (rank_of(from) == promote_rank) {
                        mv.promotion = 4;
                        mv.flags |= FLAG_PROMOTION;
                    }
                    move_list_push(list, mv);
                }
            }
        }
    }

    pieces = state->bb_pieces[side == WHITE ? 1 : 7];
    while (pieces != 0ULL) {
        int from = pop_lsb(&pieces);
        int i;
        for (i = 0; i < 8; ++i) {
            int to = from + KNIGHT_OFFSETS_64[i];
            if (!on_board64(to) || abs(file_of(to) - file_of(from)) > 2) {
                continue;
            }
            if ((own_occ & square_bb(to)) != 0ULL) {
                continue;
            }
            if (captures_only && (opp_occ & square_bb(to)) == 0ULL) {
                continue;
            }
            {
                EngineMove mv;
                memset(&mv, 0, sizeof(mv));
                mv.from = (uint8_t)from;
                mv.to = (uint8_t)to;
                if ((opp_occ & square_bb(to)) != 0ULL) {
                    mv.flags = FLAG_CAPTURE;
                }
                move_list_push(list, mv);
            }
        }
    }

    pieces = state->bb_pieces[side == WHITE ? 2 : 8];
    while (pieces != 0ULL) {
        int from = pop_lsb(&pieces);
        int i;
        for (i = 0; i < 4; ++i) {
            int to = from + BISHOP_OFFSETS_64[i];
            while (step_preserves_geometry(to - BISHOP_OFFSETS_64[i], to, BISHOP_OFFSETS_64[i])) {
                if ((own_occ & square_bb(to)) != 0ULL) {
                    break;
                }
                if ((opp_occ & square_bb(to)) != 0ULL) {
                    EngineMove mv;
                    memset(&mv, 0, sizeof(mv));
                    mv.from = (uint8_t)from;
                    mv.to = (uint8_t)to;
                    mv.flags = FLAG_CAPTURE;
                    move_list_push(list, mv);
                    break;
                }
                if (!captures_only) {
                    EngineMove mv;
                    memset(&mv, 0, sizeof(mv));
                    mv.from = (uint8_t)from;
                    mv.to = (uint8_t)to;
                    move_list_push(list, mv);
                }
                to += BISHOP_OFFSETS_64[i];
            }
        }
    }

    pieces = state->bb_pieces[side == WHITE ? 3 : 9];
    while (pieces != 0ULL) {
        int from = pop_lsb(&pieces);
        int i;
        for (i = 0; i < 4; ++i) {
            int to = from + ROOK_OFFSETS_64[i];
            while (step_preserves_geometry(to - ROOK_OFFSETS_64[i], to, ROOK_OFFSETS_64[i])) {
                if ((own_occ & square_bb(to)) != 0ULL) {
                    break;
                }
                if ((opp_occ & square_bb(to)) != 0ULL) {
                    EngineMove mv;
                    memset(&mv, 0, sizeof(mv));
                    mv.from = (uint8_t)from;
                    mv.to = (uint8_t)to;
                    mv.flags = FLAG_CAPTURE;
                    move_list_push(list, mv);
                    break;
                }
                if (!captures_only) {
                    EngineMove mv;
                    memset(&mv, 0, sizeof(mv));
                    mv.from = (uint8_t)from;
                    mv.to = (uint8_t)to;
                    move_list_push(list, mv);
                }
                to += ROOK_OFFSETS_64[i];
            }
        }
    }

    pieces = state->bb_pieces[side == WHITE ? 4 : 10];
    while (pieces != 0ULL) {
        int from = pop_lsb(&pieces);
        int i;
        static const int queen_offsets[8] = {9, 7, -9, -7, 8, -8, 1, -1};
        for (i = 0; i < 8; ++i) {
            int delta = queen_offsets[i];
            int to = from + delta;
            while (step_preserves_geometry(to - delta, to, delta)) {
                if ((own_occ & square_bb(to)) != 0ULL) {
                    break;
                }
                if ((opp_occ & square_bb(to)) != 0ULL) {
                    EngineMove mv;
                    memset(&mv, 0, sizeof(mv));
                    mv.from = (uint8_t)from;
                    mv.to = (uint8_t)to;
                    mv.flags = FLAG_CAPTURE;
                    move_list_push(list, mv);
                    break;
                }
                if (!captures_only) {
                    EngineMove mv;
                    memset(&mv, 0, sizeof(mv));
                    mv.from = (uint8_t)from;
                    mv.to = (uint8_t)to;
                    move_list_push(list, mv);
                }
                to += delta;
            }
        }
    }

    pieces = state->bb_pieces[side == WHITE ? 5 : 11];
    while (pieces != 0ULL) {
        int from = pop_lsb(&pieces);
        int i;
        for (i = 0; i < 8; ++i) {
            int to = from + KING_OFFSETS_64[i];
            if (!on_board64(to) || abs(file_of(to) - file_of(from)) > 1) {
                continue;
            }
            if ((own_occ & square_bb(to)) != 0ULL) {
                continue;
            }
            if (captures_only && (opp_occ & square_bb(to)) == 0ULL) {
                continue;
            }
            {
                EngineMove mv;
                memset(&mv, 0, sizeof(mv));
                mv.from = (uint8_t)from;
                mv.to = (uint8_t)to;
                if ((opp_occ & square_bb(to)) != 0ULL) {
                    mv.flags = FLAG_CAPTURE;
                }
                move_list_push(list, mv);
            }
        }
    }

    add_special_moves(state, list, captures_only);
}

void engine_sync_backend_state(EngineState *state) {
    int sq;

    if (state == NULL) {
        return;
    }

    init_backend_maps();
    memset(state->board_0x88, 0, sizeof(state->board_0x88));
    memset(state->bb_pieces, 0, sizeof(state->bb_pieces));
    for (sq = 0; sq < 120; ++sq) {
        state->board_120[sq] = OFFBOARD_120;
    }
    state->bb_white_occ = 0ULL;
    state->bb_black_occ = 0ULL;

    for (sq = 0; sq < 64; ++sq) {
        int piece = state->board[sq];
        int idx;

        state->board_0x88[g_sq64_to_0x88[sq]] = piece;
        state->board_120[g_sq64_to_120[sq]] = piece;

        if (piece == EMPTY) {
            continue;
        }

        idx = piece_to_bb_index(piece);
        if (idx >= 0) {
            state->bb_pieces[idx] |= square_bb(sq);
        }
        if (piece_side(piece) == WHITE) {
            state->bb_white_occ |= square_bb(sq);
        } else {
            state->bb_black_occ |= square_bb(sq);
        }
    }
}

int engine_backend_find_king_square(const EngineState *state, int side) {
    if (state == NULL) {
        return -1;
    }

#if CFG_BITBOARDS
    return find_king_square_bitboards(state, side);
#elif CFG_0X88
    return find_king_square_0x88(state, side);
#elif CFG_10X12_BOARD || CFG_MAILBOX
    return find_king_square_120(state, side);
#else
    return find_king_square_default(state, side);
#endif
}

bool engine_backend_is_square_attacked(const EngineState *state, int sq, int attacker_side) {
    if (state == NULL) {
        return false;
    }

#if CFG_BITBOARDS
    return is_square_attacked_bitboards(state, sq, attacker_side);
#elif CFG_0X88
    return is_square_attacked_0x88(state, sq, attacker_side);
#elif CFG_10X12_BOARD || CFG_MAILBOX
    return is_square_attacked_120(state, sq, attacker_side);
#else
    return is_square_attacked_default(state, sq, attacker_side);
#endif
}

void engine_backend_generate_pseudo_moves(const EngineState *state, EngineMoveList *list, bool captures_only) {
    if (list == NULL) {
        return;
    }

    list->count = 0;
    if (state == NULL) {
        return;
    }

#if CFG_BITBOARDS
    generate_moves_bitboards(state, list, captures_only);
#elif CFG_0X88
    generate_moves_0x88(state, list, captures_only);
#elif CFG_10X12_BOARD || CFG_MAILBOX
    generate_moves_120(state, list, captures_only);
#else
    (void)captures_only;
#endif
}

const char *engine_board_backend_name(void) {
#if CFG_BITBOARDS
    return "Bitboards";
#elif CFG_0X88
    return "0x88";
#elif CFG_10X12_BOARD
    return "10x12";
#elif CFG_MAILBOX
    return "Mailbox";
#else
    return "Default";
#endif
}
