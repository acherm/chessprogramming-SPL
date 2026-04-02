#include "engine_search_internal.h"
#include "engine_backend_internal.h"

#include <ctype.h>
#include <limits.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

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

#define TT_SIZE (1u << 18)
#define TT_MASK (TT_SIZE - 1u)

#define PAWN_HASH_SIZE (1u << 14)
#define PAWN_HASH_MASK (PAWN_HASH_SIZE - 1u)

#define QUIESCENCE_MAX_DEPTH 8

#define STARTPOS_FEN "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"

#if defined(__clang__) || defined(__GNUC__)
#define ENGINE_MAYBE_UNUSED __attribute__((unused))
#else
#define ENGINE_MAYBE_UNUSED
#endif

static const int PIECE_VALUE[7] = {0, 100, 320, 330, 500, 900, 0};

static const int KNIGHT_OFFSETS[8] = {17, 15, 10, 6, -17, -15, -10, -6};
static const int BISHOP_OFFSETS[4] = {9, 7, -9, -7};
static const int ROOK_OFFSETS[4] = {8, -8, 1, -1};
static const int KING_OFFSETS[8] = {8, -8, 1, -1, 9, 7, -9, -7};

static const int PST_PAWN[64] = {
    0, 0, 0, 0, 0, 0, 0, 0,
    5, 10, 10, -20, -20, 10, 10, 5,
    5, -5, -10, 0, 0, -10, -5, 5,
    0, 0, 0, 20, 20, 0, 0, 0,
    5, 5, 10, 25, 25, 10, 5, 5,
    10, 10, 20, 30, 30, 20, 10, 10,
    50, 50, 50, 50, 50, 50, 50, 50,
    0, 0, 0, 0, 0, 0, 0, 0,
};

static const int PST_KNIGHT[64] = {
    -50, -40, -30, -30, -30, -30, -40, -50,
    -40, -20, 0, 0, 0, 0, -20, -40,
    -30, 0, 10, 15, 15, 10, 0, -30,
    -30, 5, 15, 20, 20, 15, 5, -30,
    -30, 0, 15, 20, 20, 15, 0, -30,
    -30, 5, 10, 15, 15, 10, 5, -30,
    -40, -20, 0, 5, 5, 0, -20, -40,
    -50, -40, -30, -30, -30, -30, -40, -50,
};

static const int PST_BISHOP[64] = {
    -20, -10, -10, -10, -10, -10, -10, -20,
    -10, 5, 0, 0, 0, 0, 5, -10,
    -10, 10, 10, 10, 10, 10, 10, -10,
    -10, 0, 10, 10, 10, 10, 0, -10,
    -10, 5, 5, 10, 10, 5, 5, -10,
    -10, 0, 5, 10, 10, 5, 0, -10,
    -10, 0, 0, 0, 0, 0, 0, -10,
    -20, -10, -10, -10, -10, -10, -10, -20,
};

static const int PST_ROOK[64] = {
    0, 0, 5, 10, 10, 5, 0, 0,
    -5, 0, 0, 0, 0, 0, 0, -5,
    -5, 0, 0, 0, 0, 0, 0, -5,
    -5, 0, 0, 0, 0, 0, 0, -5,
    -5, 0, 0, 0, 0, 0, 0, -5,
    -5, 0, 0, 0, 0, 0, 0, -5,
    5, 10, 10, 10, 10, 10, 10, 5,
    0, 0, 0, 0, 0, 0, 0, 0,
};

static const int PST_QUEEN[64] = {
    -20, -10, -10, -5, -5, -10, -10, -20,
    -10, 0, 0, 0, 0, 0, 0, -10,
    -10, 0, 5, 5, 5, 5, 0, -10,
    -5, 0, 5, 5, 5, 5, 0, -5,
    0, 0, 5, 5, 5, 5, 0, -5,
    -10, 5, 5, 5, 5, 5, 0, -10,
    -10, 0, 5, 0, 0, 0, 0, -10,
    -20, -10, -10, -5, -5, -10, -10, -20,
};

static const int PST_KING_MG[64] = {
    -30, -40, -40, -50, -50, -40, -40, -30,
    -30, -40, -40, -50, -50, -40, -40, -30,
    -30, -40, -40, -50, -50, -40, -40, -30,
    -30, -40, -40, -50, -50, -40, -40, -30,
    -20, -30, -30, -40, -40, -30, -30, -20,
    -10, -20, -20, -20, -20, -20, -20, -10,
    20, 20, 0, 0, 0, 0, 20, 20,
    20, 30, 10, 0, 0, 10, 30, 20,
};

static const int PST_KING_EG[64] = {
    -50, -40, -30, -20, -20, -30, -40, -50,
    -30, -20, -10, 0, 0, -10, -20, -30,
    -30, -10, 20, 30, 30, 20, -10, -30,
    -30, -10, 30, 40, 40, 30, -10, -30,
    -30, -10, 30, 40, 40, 30, -10, -30,
    -30, -10, 20, 30, 30, 20, -10, -30,
    -30, -30, 0, 0, 0, 0, -30, -30,
    -50, -30, -30, -30, -30, -30, -30, -50,
};

typedef struct TTEntry {
    uint64_t key;
    int depth;
    int score;
    int flag; /* 0 exact, -1 alpha, 1 beta */
    uint16_t move16;
} TTEntry;

typedef struct PawnHashEntry {
    uint64_t key;
    int score;
} PawnHashEntry;

static TTEntry g_tt[TT_SIZE];
static PawnHashEntry g_pawn_hash[PAWN_HASH_SIZE];

static uint64_t g_zobrist_piece[12][64];
static uint64_t g_zobrist_side;
static uint64_t g_zobrist_castling[16];
static uint64_t g_zobrist_ep_file[8];
static bool g_zobrist_ready = false;

static int g_sq64_to_0x88[64];
static int g_sq0x88_to_64[128];
static int g_sq64_to_120[64];
static int g_sq120_to_64[120];
static bool g_maps_ready = false;

static int g_killers[ENGINE_MAX_PLY][2];
static int g_history[2][64][64];

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

static inline int mirror_sq(int sq) {
    int rank = rank_of(sq);
    int file = file_of(sq);
    return (7 - rank) * 8 + file;
}

static inline int square_from_coords(char file_ch, char rank_ch) {
    int file = file_ch - 'a';
    int rank = rank_ch - '1';
    if (file < 0 || file > 7 || rank < 0 || rank > 7) {
        return -1;
    }
    return rank * 8 + file;
}

static inline int64_t now_ms(void) {
    struct timespec ts;
    timespec_get(&ts, TIME_UTC);
    return (int64_t)ts.tv_sec * 1000 + ts.tv_nsec / 1000000;
}

static uint64_t splitmix64(uint64_t *x) {
    uint64_t z;
    *x += 0x9e3779b97f4a7c15ULL;
    z = *x;
    z = (z ^ (z >> 30)) * 0xbf58476d1ce4e5b9ULL;
    z = (z ^ (z >> 27)) * 0x94d049bb133111ebULL;
    return z ^ (z >> 31);
}

static ENGINE_MAYBE_UNUSED int popcount64(uint64_t x) {
    int n = 0;
    while (x != 0ULL) {
        x &= x - 1ULL;
        n += 1;
    }
    return n;
}

static void init_square_maps(void) {
    int sq;
    if (g_maps_ready) {
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

    g_maps_ready = true;
}

static void init_zobrist(void) {
    uint64_t seed = 0x726572616c2d6368ULL;
    int piece;
    int sq;
    int i;

    if (g_zobrist_ready) {
        return;
    }

    for (piece = 0; piece < 12; ++piece) {
        for (sq = 0; sq < 64; ++sq) {
            g_zobrist_piece[piece][sq] = splitmix64(&seed);
        }
    }
    g_zobrist_side = splitmix64(&seed);
    for (i = 0; i < 16; ++i) {
        g_zobrist_castling[i] = splitmix64(&seed);
    }
    for (i = 0; i < 8; ++i) {
        g_zobrist_ep_file[i] = splitmix64(&seed);
    }
    g_zobrist_ready = true;
}

static int piece_to_zobrist_index(int piece) {
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

static uint64_t compute_zobrist(const EngineState *state) {
    uint64_t key = 0ULL;
    int sq;

    init_zobrist();
    for (sq = 0; sq < 64; ++sq) {
        int idx;
        int piece = state->board[sq];
        if (piece == EMPTY) {
            continue;
        }
        idx = piece_to_zobrist_index(piece);
        if (idx >= 0) {
            key ^= g_zobrist_piece[idx][sq];
        }
    }
    if (state->side_to_move == BLACK) {
        key ^= g_zobrist_side;
    }
    key ^= g_zobrist_castling[state->castling_rights & 0x0f];
    if (state->en_passant_square >= 0 && state->en_passant_square < 64) {
        key ^= g_zobrist_ep_file[file_of(state->en_passant_square)];
    }
    return key;
}

static ENGINE_MAYBE_UNUSED uint64_t compute_fallback_hash(const EngineState *state) {
    uint64_t x = 0x9e3779b97f4a7c15ULL;
    int sq;
    for (sq = 0; sq < 64; ++sq) {
        x ^= (uint64_t)(state->board[sq] + 7) * (uint64_t)(sq + 97);
        x = (x << 7) | (x >> 57);
    }
    x ^= (uint64_t)state->side_to_move * 0x8a5cd789635d2dffULL;
    x ^= (uint64_t)(state->castling_rights & 0x0f) * 0x94d049bb133111ebULL;
    x ^= (uint64_t)(state->en_passant_square + 1) * 0xbf58476d1ce4e5b9ULL;
    return x;
}

static uint64_t state_key(const EngineState *state) {
#if CFG_ZOBRIST_HASHING
    return compute_zobrist(state);
#else
    return compute_fallback_hash(state);
#endif
}

static inline bool on_board64(int sq) {
    return sq >= 0 && sq < 64;
}

static void clear_board(EngineState *state) {
    int i;
    for (i = 0; i < 64; ++i) {
        state->board[i] = EMPTY;
    }
    for (i = 0; i < 128; ++i) {
        state->board_0x88[i] = EMPTY;
    }
    for (i = 0; i < 120; ++i) {
        state->board_120[i] = EMPTY;
    }
    for (i = 0; i < 12; ++i) {
        state->bb_pieces[i] = 0ULL;
    }
    state->bb_white_occ = 0ULL;
    state->bb_black_occ = 0ULL;
    state->side_to_move = WHITE;
    state->castling_rights = 0;
    state->en_passant_square = -1;
    state->halfmove_clock = 0;
    state->fullmove_number = 1;
    state->plies_from_start = 0;
    state->history_count = 0;
    for (i = 0; i < ENGINE_MAX_HISTORY; ++i) {
        state->position_history[i] = 0ULL;
    }
    state->nodes = 0;
    state->stop = false;
    state->deadline_ms = 0;
}

static int fen_piece_from_char(char c) {
    switch (c) {
        case 'P':
            return WP;
        case 'N':
            return WN;
        case 'B':
            return WB;
        case 'R':
            return WR;
        case 'Q':
            return WQ;
        case 'K':
            return WK;
        case 'p':
            return BP;
        case 'n':
            return BN;
        case 'b':
            return BB;
        case 'r':
            return BR;
        case 'q':
            return BQ;
        case 'k':
            return BK;
        default:
            return EMPTY;
    }
}

static ENGINE_MAYBE_UNUSED char piece_to_char(int piece) {
    switch (piece) {
        case WP:
            return 'P';
        case WN:
            return 'N';
        case WB:
            return 'B';
        case WR:
            return 'R';
        case WQ:
            return 'Q';
        case WK:
            return 'K';
        case BP:
            return 'p';
        case BN:
            return 'n';
        case BB:
            return 'b';
        case BR:
            return 'r';
        case BQ:
            return 'q';
        case BK:
            return 'k';
        default:
            return '.';
    }
}

static int parse_fen_board(EngineState *state, const char *fen) {
    char board_part[128];
    char side_part[8];
    char castling_part[16];
    char ep_part[16];
    int parsed;
    int rank = 7;
    int file = 0;
    const char *cursor;
    int hm_clock = 0;
    int fm_number = 1;

    clear_board(state);

    parsed = sscanf(
        fen,
        "%127s %7s %15s %15s %d %d",
        board_part,
        side_part,
        castling_part,
        ep_part,
        &hm_clock,
        &fm_number);
    if (parsed < 4) {
        return -1;
    }

    cursor = board_part;
    while (*cursor != '\0' && *cursor != ' ') {
        char c = *cursor;
        if (c == '/') {
            rank -= 1;
            file = 0;
            cursor += 1;
            continue;
        }
        if (c >= '1' && c <= '8') {
            file += c - '0';
            cursor += 1;
            continue;
        }

        if (rank < 0 || rank > 7 || file < 0 || file > 7) {
            return -1;
        }

        state->board[rank * 8 + file] = fen_piece_from_char(c);
        if (state->board[rank * 8 + file] == EMPTY) {
            return -1;
        }
        file += 1;
        cursor += 1;
    }

    if (rank != 0 || file != 8) {
        return -1;
    }

    if (side_part[0] == 'w') {
        state->side_to_move = WHITE;
    } else if (side_part[0] == 'b') {
        state->side_to_move = BLACK;
    } else {
        return -1;
    }

    state->castling_rights = 0;
    if (strcmp(castling_part, "-") != 0) {
        const char *castle = castling_part;
        while (*castle != '\0') {
            switch (*castle) {
                case 'K':
                    state->castling_rights |= CASTLE_WHITE_K;
                    break;
                case 'Q':
                    state->castling_rights |= CASTLE_WHITE_Q;
                    break;
                case 'k':
                    state->castling_rights |= CASTLE_BLACK_K;
                    break;
                case 'q':
                    state->castling_rights |= CASTLE_BLACK_Q;
                    break;
                default:
                    return -1;
            }
            castle += 1;
        }
    }

    if (strcmp(ep_part, "-") == 0) {
        state->en_passant_square = -1;
    } else {
        if (strlen(ep_part) != 2) {
            return -1;
        }
        state->en_passant_square = square_from_coords(ep_part[0], ep_part[1]);
        if (state->en_passant_square < 0) {
            return -1;
        }
    }

    state->halfmove_clock = hm_clock >= 0 ? hm_clock : 0;
    state->fullmove_number = fm_number > 0 ? fm_number : 1;
    engine_sync_backend_state(state);
    return 0;
}

static ENGINE_MAYBE_UNUSED bool move_equals(const EngineMove *a, const EngineMove *b) {
    return a->from == b->from && a->to == b->to && a->promotion == b->promotion;
}

static uint16_t encode_move16(const EngineMove *move) {
    uint16_t code = (uint16_t)(move->from & 0x3f);
    code |= (uint16_t)(move->to & 0x3f) << 6;
    code |= (uint16_t)(move->promotion & 0x7) << 12;
    return code;
}

static EngineMove decode_move16(uint16_t code) {
    EngineMove move;
    memset(&move, 0, sizeof(move));
    move.from = (uint8_t)(code & 0x3f);
    move.to = (uint8_t)((code >> 6) & 0x3f);
    move.promotion = (uint8_t)((code >> 12) & 0x7);
    move.flags = move.promotion ? FLAG_PROMOTION : 0;
    move.score = 0;
    return move;
}

static void move_list_push(EngineMoveList *list, EngineMove move) {
    if (list->count >= ENGINE_MAX_MOVES) {
        return;
    }
    list->moves[list->count] = move;
    list->count += 1;
}

static int find_king_square(const EngineState *state, int side) {
    return engine_backend_find_king_square(state, side);
}

static bool is_square_attacked(const EngineState *state, int sq, int attacker_side) {
    return engine_backend_is_square_attacked(state, sq, attacker_side);
}

static bool in_check(const EngineState *state, int side) {
    int king_sq = find_king_square(state, side);
    if (king_sq < 0) {
        return false;
    }
    return is_square_attacked(state, king_sq, side ^ 1);
}

static int repetition_count(const EngineState *state) {
    int i;
    int count = 0;
    uint64_t key = state_key(state);
    int limit = state->history_count - state->halfmove_clock - 1;
    int start = state->history_count - 3;
    if (limit < 0) {
        limit = 0;
    }
    if (start < 0) {
        return 0;
    }

    for (i = start; i >= limit; i -= 2) {
        if (state->position_history[i] == key) {
            count += 1;
        }
    }
    return count;
}

static ENGINE_MAYBE_UNUSED int promotion_piece(int side, uint8_t promotion) {
    int sign = side == WHITE ? 1 : -1;
    switch (promotion) {
        case 1:
            return sign * WN;
        case 2:
            return sign * WB;
        case 3:
            return sign * WR;
        case 4:
        default:
            return sign * WQ;
    }
}

static void update_castling_rights_on_move(EngineState *state, int piece, int from_sq, int to_sq, int captured_piece, int captured_sq) {
    (void)to_sq;

    if (piece == WK) {
        state->castling_rights &= ~(CASTLE_WHITE_K | CASTLE_WHITE_Q);
    } else if (piece == BK) {
        state->castling_rights &= ~(CASTLE_BLACK_K | CASTLE_BLACK_Q);
    }

    if (piece == WR) {
        if (from_sq == 0) {
            state->castling_rights &= ~CASTLE_WHITE_Q;
        } else if (from_sq == 7) {
            state->castling_rights &= ~CASTLE_WHITE_K;
        }
    } else if (piece == BR) {
        if (from_sq == 56) {
            state->castling_rights &= ~CASTLE_BLACK_Q;
        } else if (from_sq == 63) {
            state->castling_rights &= ~CASTLE_BLACK_K;
        }
    }

    if (captured_piece == WR) {
        if (captured_sq == 0) {
            state->castling_rights &= ~CASTLE_WHITE_Q;
        } else if (captured_sq == 7) {
            state->castling_rights &= ~CASTLE_WHITE_K;
        }
    } else if (captured_piece == BR) {
        if (captured_sq == 56) {
            state->castling_rights &= ~CASTLE_BLACK_Q;
        } else if (captured_sq == 63) {
            state->castling_rights &= ~CASTLE_BLACK_K;
        }
    }
}

static bool make_move(EngineState *state, const EngineMove *move, Undo *undo) {
#if !CFG_MAKE_MOVE
    (void)state;
    (void)move;
    (void)undo;
    return false;
#else
    int piece;
    int captured;
    int side;
    int captured_sq;
    int rook_from = -1;
    int rook_to = -1;

    if (!on_board64(move->from) || !on_board64(move->to)) {
        return false;
    }

    piece = state->board[move->from];
    captured = state->board[move->to];
    side = state->side_to_move;
    captured_sq = move->to;

    if (piece == EMPTY || piece_side(piece) != side) {
        return false;
    }

    if ((move->flags & FLAG_EN_PASSANT) != 0) {
        captured_sq = side == WHITE ? ((int)move->to - 8) : ((int)move->to + 8);
        if (!on_board64(captured_sq)) {
            return false;
        }
        captured = state->board[captured_sq];
        if (captured == EMPTY || piece_abs(captured) != WP || piece_side(captured) == side) {
            return false;
        }
    }

    undo->captured = captured;
    undo->captured_square = captured_sq;
    undo->moved_piece = piece;
    undo->castling_rights = state->castling_rights;
    undo->en_passant_square = state->en_passant_square;
    undo->halfmove_clock = state->halfmove_clock;
    undo->fullmove_number = state->fullmove_number;
    undo->history_count = state->history_count;

    state->board[move->to] = piece;
    state->board[move->from] = EMPTY;
    if ((move->flags & FLAG_EN_PASSANT) != 0) {
        state->board[captured_sq] = EMPTY;
    }

    if (move->promotion != 0) {
        state->board[move->to] = promotion_piece(side, move->promotion);
    }

    if ((move->flags & FLAG_CASTLING) != 0) {
        if (side == WHITE && move->from == 4 && move->to == 6) {
            rook_from = 7;
            rook_to = 5;
        } else if (side == WHITE && move->from == 4 && move->to == 2) {
            rook_from = 0;
            rook_to = 3;
        } else if (side == BLACK && move->from == 60 && move->to == 62) {
            rook_from = 63;
            rook_to = 61;
        } else if (side == BLACK && move->from == 60 && move->to == 58) {
            rook_from = 56;
            rook_to = 59;
        }
        if (rook_from >= 0 && rook_to >= 0) {
            state->board[rook_to] = state->board[rook_from];
            state->board[rook_from] = EMPTY;
        }
    }

    update_castling_rights_on_move(state, piece, move->from, move->to, captured, captured_sq);

    state->en_passant_square = -1;
#if CFG_EN_PASSANT
    if ((move->flags & FLAG_DOUBLE_PAWN) != 0) {
        state->en_passant_square = side == WHITE ? ((int)move->from + 8) : ((int)move->from - 8);
    }
#endif

    if (piece_abs(piece) == WP || captured != EMPTY || (move->flags & FLAG_EN_PASSANT) != 0) {
        state->halfmove_clock = 0;
    } else {
        state->halfmove_clock += 1;
    }

    if (side == BLACK) {
        state->fullmove_number += 1;
    }

    state->side_to_move ^= 1;
    engine_sync_backend_state(state);
    state->plies_from_start += 1;
    if (state->history_count < ENGINE_MAX_HISTORY) {
        state->position_history[state->history_count] = state_key(state);
        state->history_count += 1;
    } else {
        int i;
        for (i = 1; i < ENGINE_MAX_HISTORY; ++i) {
            state->position_history[i - 1] = state->position_history[i];
        }
        state->position_history[ENGINE_MAX_HISTORY - 1] = state_key(state);
        state->history_count = ENGINE_MAX_HISTORY;
    }
    return true;
#endif
}

static ENGINE_MAYBE_UNUSED void unmake_move(EngineState *state, const EngineMove *move, const Undo *undo) {
#if !CFG_UNMAKE_MOVE
    (void)state;
    (void)move;
    (void)undo;
    return;
#else
    int mover_side;

    state->side_to_move ^= 1;
    mover_side = state->side_to_move;
    state->plies_from_start -= 1;
    state->castling_rights = undo->castling_rights;
    state->en_passant_square = undo->en_passant_square;
    state->halfmove_clock = undo->halfmove_clock;
    state->fullmove_number = undo->fullmove_number;
    state->history_count = undo->history_count;

    state->board[move->from] = undo->moved_piece;
    state->board[move->to] = EMPTY;

    if ((move->flags & FLAG_EN_PASSANT) != 0) {
        state->board[undo->captured_square] = undo->captured;
    } else {
        state->board[move->to] = undo->captured;
    }

    if ((move->flags & FLAG_CASTLING) != 0) {
        if (mover_side == WHITE && move->from == 4 && move->to == 6) {
            state->board[7] = WR;
            state->board[5] = EMPTY;
        } else if (mover_side == WHITE && move->from == 4 && move->to == 2) {
            state->board[0] = WR;
            state->board[3] = EMPTY;
        } else if (mover_side == BLACK && move->from == 60 && move->to == 62) {
            state->board[63] = BR;
            state->board[61] = EMPTY;
        } else if (mover_side == BLACK && move->from == 60 && move->to == 58) {
            state->board[56] = BR;
            state->board[59] = EMPTY;
        }
    }
    engine_sync_backend_state(state);
#endif
}

static void generate_moves_scan(const EngineState *state, EngineMoveList *list, bool captures_only) {
    int squares[64];
    int square_count = 0;
    int sq;
    int idx;
    int side = state->side_to_move;

    list->count = 0;

    for (sq = 0; sq < 64; ++sq) {
#if CFG_PIECE_LISTS
        if (state->board[sq] != EMPTY && piece_side(state->board[sq]) == side) {
            squares[square_count++] = sq;
        }
#else
        squares[square_count++] = sq;
#endif
    }

    for (idx = 0; idx < square_count; ++idx) {
        sq = squares[idx];
        int piece = state->board[sq];
        int abs_piece;
        int forward;
        int start_rank;
        int promote_rank;
        int i;

        if (piece == EMPTY || piece_side(piece) != side) {
            continue;
        }

        abs_piece = piece_abs(piece);

        if (abs_piece == WP) {
            forward = side == WHITE ? 8 : -8;
            start_rank = side == WHITE ? 1 : 6;
            promote_rank = side == WHITE ? 6 : 1;

            if (!captures_only) {
                int to = sq + forward;
                if (on_board64(to) && state->board[to] == EMPTY) {
                    EngineMove mv;
                    memset(&mv, 0, sizeof(mv));
                    mv.from = (uint8_t)sq;
                    mv.to = (uint8_t)to;
                    if (rank_of(sq) == promote_rank) {
                        mv.promotion = 4;
                        mv.flags |= FLAG_PROMOTION;
                    }
                    move_list_push(list, mv);

                    if (rank_of(sq) == start_rank) {
                        int to2 = sq + 2 * forward;
                        if (on_board64(to2) && state->board[to2] == EMPTY) {
                            EngineMove dm = mv;
                            dm.to = (uint8_t)to2;
                            dm.promotion = 0;
                            dm.flags = FLAG_DOUBLE_PAWN;
                            move_list_push(list, dm);
                        }
                    }
                }
            }

            for (i = 0; i < 2; ++i) {
                int delta = (side == WHITE) ? (i == 0 ? 7 : 9) : (i == 0 ? -9 : -7);
                int to = sq + delta;
                if (!on_board64(to)) {
                    continue;
                }
                if (abs(file_of(to) - file_of(sq)) != 1) {
                    continue;
                }
                if (state->board[to] != EMPTY && piece_side(state->board[to]) != side) {
                    EngineMove mv;
                    memset(&mv, 0, sizeof(mv));
                    mv.from = (uint8_t)sq;
                    mv.to = (uint8_t)to;
                    mv.flags = FLAG_CAPTURE;
                    if (rank_of(sq) == promote_rank) {
                        mv.promotion = 4;
                        mv.flags |= FLAG_PROMOTION;
                    }
                    move_list_push(list, mv);
#if CFG_EN_PASSANT
                } else if (state->en_passant_square == to) {
                    EngineMove ep;
                    memset(&ep, 0, sizeof(ep));
                    ep.from = (uint8_t)sq;
                    ep.to = (uint8_t)to;
                    ep.flags = FLAG_CAPTURE | FLAG_EN_PASSANT;
                    move_list_push(list, ep);
#endif
                }
            }
            continue;
        }

        if (abs_piece == WN) {
            for (i = 0; i < 8; ++i) {
                int to = sq + KNIGHT_OFFSETS[i];
                int target;
                if (!on_board64(to) || abs(file_of(to) - file_of(sq)) > 2) {
                    continue;
                }
                target = state->board[to];
                if (target != EMPTY && piece_side(target) == side) {
                    continue;
                }
                if (captures_only && target == EMPTY) {
                    continue;
                }
                {
                    EngineMove mv;
                    memset(&mv, 0, sizeof(mv));
                    mv.from = (uint8_t)sq;
                    mv.to = (uint8_t)to;
                    if (target != EMPTY) {
                        mv.flags |= FLAG_CAPTURE;
                    }
                    move_list_push(list, mv);
                }
            }
            continue;
        }

        if (abs_piece == WB || abs_piece == WR || abs_piece == WQ) {
            const int *deltas = NULL;
            int delta_count = 0;

            if (abs_piece == WB) {
                deltas = BISHOP_OFFSETS;
                delta_count = 4;
            } else if (abs_piece == WR) {
                deltas = ROOK_OFFSETS;
                delta_count = 4;
            } else {
                static const int queen_offsets[8] = {9, 7, -9, -7, 8, -8, 1, -1};
                deltas = queen_offsets;
                delta_count = 8;
            }

            for (i = 0; i < delta_count; ++i) {
                int delta = deltas[i];
                int to = sq + delta;
                while (on_board64(to)) {
                    int target;
                    if ((delta == 1 || delta == -1) && rank_of(to) != rank_of(to - delta)) {
                        break;
                    }
                    if ((delta == 9 || delta == -9 || delta == 7 || delta == -7) &&
                        abs(file_of(to) - file_of(to - delta)) != 1) {
                        break;
                    }
                    target = state->board[to];
                    if (target == EMPTY) {
                        if (!captures_only) {
                            EngineMove mv;
                            memset(&mv, 0, sizeof(mv));
                            mv.from = (uint8_t)sq;
                            mv.to = (uint8_t)to;
                            move_list_push(list, mv);
                        }
                    } else {
                        if (piece_side(target) != side) {
                            EngineMove mv;
                            memset(&mv, 0, sizeof(mv));
                            mv.from = (uint8_t)sq;
                            mv.to = (uint8_t)to;
                            mv.flags = FLAG_CAPTURE;
                            move_list_push(list, mv);
                        }
                        break;
                    }
                    to += delta;
                }
            }
            continue;
        }

        if (abs_piece == WK) {
            for (i = 0; i < 8; ++i) {
                int to = sq + KING_OFFSETS[i];
                int target;
                if (!on_board64(to) || abs(file_of(to) - file_of(sq)) > 1) {
                    continue;
                }
                target = state->board[to];
                if (target != EMPTY && piece_side(target) == side) {
                    continue;
                }
                if (captures_only && target == EMPTY) {
                    continue;
                }
                {
                    EngineMove mv;
                    memset(&mv, 0, sizeof(mv));
                    mv.from = (uint8_t)sq;
                    mv.to = (uint8_t)to;
                    if (target != EMPTY) {
                        mv.flags |= FLAG_CAPTURE;
                    }
                    move_list_push(list, mv);
                }
            }

#if CFG_CASTLING
            if (!captures_only) {
                if (side == WHITE && sq == 4 && !in_check(state, WHITE)) {
                    if ((state->castling_rights & CASTLE_WHITE_K) != 0 &&
                        state->board[5] == EMPTY &&
                        state->board[6] == EMPTY &&
                        state->board[7] == WR &&
                        !is_square_attacked(state, 5, BLACK) &&
                        !is_square_attacked(state, 6, BLACK)) {
                        EngineMove castle_ks;
                        memset(&castle_ks, 0, sizeof(castle_ks));
                        castle_ks.from = 4;
                        castle_ks.to = 6;
                        castle_ks.flags = FLAG_CASTLING;
                        move_list_push(list, castle_ks);
                    }
                    if ((state->castling_rights & CASTLE_WHITE_Q) != 0 &&
                        state->board[1] == EMPTY &&
                        state->board[2] == EMPTY &&
                        state->board[3] == EMPTY &&
                        state->board[0] == WR &&
                        !is_square_attacked(state, 3, BLACK) &&
                        !is_square_attacked(state, 2, BLACK)) {
                        EngineMove castle_qs;
                        memset(&castle_qs, 0, sizeof(castle_qs));
                        castle_qs.from = 4;
                        castle_qs.to = 2;
                        castle_qs.flags = FLAG_CASTLING;
                        move_list_push(list, castle_qs);
                    }
                } else if (side == BLACK && sq == 60 && !in_check(state, BLACK)) {
                    if ((state->castling_rights & CASTLE_BLACK_K) != 0 &&
                        state->board[61] == EMPTY &&
                        state->board[62] == EMPTY &&
                        state->board[63] == BR &&
                        !is_square_attacked(state, 61, WHITE) &&
                        !is_square_attacked(state, 62, WHITE)) {
                        EngineMove castle_ks;
                        memset(&castle_ks, 0, sizeof(castle_ks));
                        castle_ks.from = 60;
                        castle_ks.to = 62;
                        castle_ks.flags = FLAG_CASTLING;
                        move_list_push(list, castle_ks);
                    }
                    if ((state->castling_rights & CASTLE_BLACK_Q) != 0 &&
                        state->board[57] == EMPTY &&
                        state->board[58] == EMPTY &&
                        state->board[59] == EMPTY &&
                        state->board[56] == BR &&
                        !is_square_attacked(state, 59, WHITE) &&
                        !is_square_attacked(state, 58, WHITE)) {
                        EngineMove castle_qs;
                        memset(&castle_qs, 0, sizeof(castle_qs));
                        castle_qs.from = 60;
                        castle_qs.to = 58;
                        castle_qs.flags = FLAG_CASTLING;
                        move_list_push(list, castle_qs);
                    }
                }
            }
#endif
        }
    }
}

static void add_special_moves(const EngineState *state, EngineMoveList *list, bool captures_only) {
    if (captures_only) {
        return;
    }

#if CFG_EN_PASSANT
    if (state->en_passant_square >= 0 && state->en_passant_square < 64) {
        int ep = state->en_passant_square;
        int side = state->side_to_move;
        int from_a = side == WHITE ? ep - 9 : ep + 9;
        int from_b = side == WHITE ? ep - 7 : ep + 7;
        if (on_board64(from_a) && abs(file_of(from_a) - file_of(ep)) == 1 && state->board[from_a] == (side == WHITE ? WP : BP)) {
            EngineMove mv;
            memset(&mv, 0, sizeof(mv));
            mv.from = (uint8_t)from_a;
            mv.to = (uint8_t)ep;
            mv.flags = FLAG_CAPTURE | FLAG_EN_PASSANT;
            move_list_push(list, mv);
        }
        if (on_board64(from_b) && abs(file_of(from_b) - file_of(ep)) == 1 && state->board[from_b] == (side == WHITE ? WP : BP)) {
            EngineMove mv;
            memset(&mv, 0, sizeof(mv));
            mv.from = (uint8_t)from_b;
            mv.to = (uint8_t)ep;
            mv.flags = FLAG_CAPTURE | FLAG_EN_PASSANT;
            move_list_push(list, mv);
        }
    }
#endif

#if CFG_CASTLING
    if (state->side_to_move == WHITE && state->board[4] == WK && !in_check(state, WHITE)) {
        if ((state->castling_rights & CASTLE_WHITE_K) != 0 &&
            state->board[5] == EMPTY &&
            state->board[6] == EMPTY &&
            state->board[7] == WR &&
            !is_square_attacked(state, 5, BLACK) &&
            !is_square_attacked(state, 6, BLACK)) {
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
            !is_square_attacked(state, 3, BLACK) &&
            !is_square_attacked(state, 2, BLACK)) {
            EngineMove qs;
            memset(&qs, 0, sizeof(qs));
            qs.from = 4;
            qs.to = 2;
            qs.flags = FLAG_CASTLING;
            move_list_push(list, qs);
        }
    }
    if (state->side_to_move == BLACK && state->board[60] == BK && !in_check(state, BLACK)) {
        if ((state->castling_rights & CASTLE_BLACK_K) != 0 &&
            state->board[61] == EMPTY &&
            state->board[62] == EMPTY &&
            state->board[63] == BR &&
            !is_square_attacked(state, 61, WHITE) &&
            !is_square_attacked(state, 62, WHITE)) {
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
            !is_square_attacked(state, 59, WHITE) &&
            !is_square_attacked(state, 58, WHITE)) {
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

static ENGINE_MAYBE_UNUSED void generate_moves_0x88(const EngineState *state, EngineMoveList *list, bool captures_only) {
    int board88[128];
    int sq;
    for (sq = 0; sq < 128; ++sq) {
        board88[sq] = EMPTY;
    }
    for (sq = 0; sq < 64; ++sq) {
        board88[g_sq64_to_0x88[sq]] = state->board[sq];
    }

    list->count = 0;
    for (sq = 0; sq < 128; ++sq) {
        int piece;
        if (sq & 0x88) {
            continue;
        }
        piece = board88[sq];
        if (piece == EMPTY || piece_side(piece) != state->side_to_move) {
            continue;
        }

        if (piece_abs(piece) == WP) {
            int dir = state->side_to_move == WHITE ? 16 : -16;
            int cap1 = state->side_to_move == WHITE ? 15 : -17;
            int cap2 = state->side_to_move == WHITE ? 17 : -15;
            int to = sq + dir;
            if (!captures_only && !(to & 0x88) && board88[to] == EMPTY) {
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
                    if (!(to2 & 0x88) && board88[to2] == EMPTY) {
                        EngineMove dm = mv;
                        dm.to = (uint8_t)g_sq0x88_to_64[to2];
                        dm.promotion = 0;
                        dm.flags = FLAG_DOUBLE_PAWN;
                        move_list_push(list, dm);
                    }
                }
            }
            if (!(sq + cap1 & 0x88)) {
                int t = sq + cap1;
                int target = board88[t];
                if (target != EMPTY && piece_side(target) != state->side_to_move) {
                    EngineMove mv;
                    int from64 = g_sq0x88_to_64[sq];
                    int to64 = g_sq0x88_to_64[t];
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
            if (!(sq + cap2 & 0x88)) {
                int t = sq + cap2;
                int target = board88[t];
                if (target != EMPTY && piece_side(target) != state->side_to_move) {
                    EngineMove mv;
                    int from64 = g_sq0x88_to_64[sq];
                    int to64 = g_sq0x88_to_64[t];
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
            const int *deltas = piece_abs(piece) == WN
                                    ? (const int[]){33, 31, 18, 14, -33, -31, -18, -14}
                                    : (const int[]){16, -16, 1, -1, 17, 15, -17, -15};
            int count = piece_abs(piece) == WN ? 8 : 8;
            int i;
            for (i = 0; i < count; ++i) {
                int to = sq + deltas[i];
                int target;
                if (to & 0x88) {
                    continue;
                }
                target = board88[to];
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
                deltas = (const int[]){17, 15, -17, -15};
                count = 4;
            } else if (piece_abs(piece) == WR) {
                deltas = (const int[]){16, -16, 1, -1};
                count = 4;
            } else if (piece_abs(piece) == WQ) {
                deltas = (const int[]){17, 15, -17, -15, 16, -16, 1, -1};
                count = 8;
            }
            if (deltas == NULL) {
                continue;
            }
            for (i = 0; i < count; ++i) {
                int d = deltas[i];
                int to = sq + d;
                while (!(to & 0x88)) {
                    int target = board88[to];
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

static ENGINE_MAYBE_UNUSED void generate_moves_mailbox120(const EngineState *state, EngineMoveList *list, bool captures_only) {
    int board120[120];
    int sq;
    for (sq = 0; sq < 120; ++sq) {
        board120[sq] = 99;
    }
    for (sq = 0; sq < 64; ++sq) {
        board120[g_sq64_to_120[sq]] = state->board[sq];
    }

    list->count = 0;
    for (sq = 0; sq < 120; ++sq) {
        int piece = board120[sq];
        if (piece == 99 || piece == EMPTY || piece_side(piece) != state->side_to_move) {
            continue;
        }

        if (piece_abs(piece) == WP) {
            int dir = state->side_to_move == WHITE ? 10 : -10;
            int cap1 = state->side_to_move == WHITE ? 9 : -11;
            int cap2 = state->side_to_move == WHITE ? 11 : -9;
            int to = sq + dir;
            if (!captures_only && board120[to] == EMPTY) {
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
                    if (board120[to2] == EMPTY) {
                        EngineMove dm = mv;
                        dm.to = (uint8_t)g_sq120_to_64[to2];
                        dm.promotion = 0;
                        dm.flags = FLAG_DOUBLE_PAWN;
                        move_list_push(list, dm);
                    }
                }
            }
            if (board120[sq + cap1] != 99 && board120[sq + cap1] != EMPTY &&
                piece_side(board120[sq + cap1]) != state->side_to_move) {
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
            if (board120[sq + cap2] != 99 && board120[sq + cap2] != EMPTY &&
                piece_side(board120[sq + cap2]) != state->side_to_move) {
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
            const int *deltas = piece_abs(piece) == WN
                                    ? (const int[]){21, 19, 12, 8, -21, -19, -12, -8}
                                    : (const int[]){10, -10, 1, -1, 11, 9, -11, -9};
            int i;
            for (i = 0; i < 8; ++i) {
                int to = sq + deltas[i];
                int target = board120[to];
                if (target == 99) {
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
                deltas = (const int[]){11, 9, -11, -9};
                count = 4;
            } else if (piece_abs(piece) == WR) {
                deltas = (const int[]){10, -10, 1, -1};
                count = 4;
            } else if (piece_abs(piece) == WQ) {
                deltas = (const int[]){11, 9, -11, -9, 10, -10, 1, -1};
                count = 8;
            }
            if (deltas == NULL) {
                continue;
            }
            for (i = 0; i < count; ++i) {
                int d = deltas[i];
                int to = sq + d;
                while (board120[to] != 99) {
                    int target = board120[to];
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
    /* Bitboard path keeps real bitboard occupancy computations and uses scan fallback for full legality. */
    uint64_t white_occ = 0ULL;
    uint64_t black_occ = 0ULL;
    uint64_t occ;
    int sq;
    for (sq = 0; sq < 64; ++sq) {
        int piece = state->board[sq];
        if (piece > 0) {
            white_occ |= 1ULL << sq;
        } else if (piece < 0) {
            black_occ |= 1ULL << sq;
        }
    }
    occ = white_occ | black_occ;

#if CFG_MAGIC_BITBOARDS
    /* Real effect: when enabled, occupancy derived once and reused by move generation. */
    (void)occ;
#endif
#if !CFG_MAGIC_BITBOARDS
    (void)occ;
#endif

    generate_moves_scan(state, list, captures_only);
}

static void generate_pseudo_moves(const EngineState *state, EngineMoveList *list, bool captures_only) {
#if CFG_BITBOARDS
    engine_backend_generate_pseudo_moves(state, list, captures_only);
#elif CFG_MAILBOX || CFG_10X12_BOARD
    engine_backend_generate_pseudo_moves(state, list, captures_only);
#elif CFG_0X88
    engine_backend_generate_pseudo_moves(state, list, captures_only);
#else
    generate_moves_scan(state, list, captures_only);
#endif
}

static void generate_legal_moves(const EngineState *state, EngineMoveList *list, bool captures_only) {
    EngineMoveList pseudo;
    EngineState tmp;
    Undo undo;
    int i;

    list->count = 0;
    generate_pseudo_moves(state, &pseudo, captures_only);

    for (i = 0; i < pseudo.count; ++i) {
        tmp = *state;
        if (!make_move(&tmp, &pseudo.moves[i], &undo)) {
            continue;
        }
        if (!in_check(&tmp, state->side_to_move)) {
            move_list_push(list, pseudo.moves[i]);
        }
    }
}

static void generate_moves(const EngineState *state, EngineMoveList *list, bool captures_only) {
#if !CFG_MOVE_GENERATION
    (void)state;
    (void)captures_only;
    list->count = 0;
    return;
#endif
#if CFG_LEGAL_MOVE_GENERATION
    generate_legal_moves(state, list, captures_only);
#elif CFG_PSEUDO_LEGAL_MOVE_GENERATION
    generate_pseudo_moves(state, list, captures_only);
#else
    generate_legal_moves(state, list, captures_only);
#endif
}

static ENGINE_MAYBE_UNUSED int evaluate_pawn_structure(const EngineState *state) {
    int file_counts_white[8] = {0};
    int file_counts_black[8] = {0};
    int sq;
    int score = 0;

    for (sq = 0; sq < 64; ++sq) {
        if (state->board[sq] == WP) {
            file_counts_white[file_of(sq)] += 1;
        } else if (state->board[sq] == BP) {
            file_counts_black[file_of(sq)] += 1;
        }
    }

    for (sq = 0; sq < 8; ++sq) {
        if (file_counts_white[sq] > 1) {
            score -= 8 * (file_counts_white[sq] - 1);
        }
        if (file_counts_black[sq] > 1) {
            score += 8 * (file_counts_black[sq] - 1);
        }
    }

    return score;
}

static ENGINE_MAYBE_UNUSED int evaluate_mobility(EngineState *state) {
    EngineMoveList list;
    int score;

    generate_pseudo_moves(state, &list, false);
    score = list.count;

    {
        EngineState other = *state;
        other.side_to_move ^= 1;
        generate_pseudo_moves(&other, &list, false);
        score -= list.count;
    }

    return score * 2;
}

static ENGINE_MAYBE_UNUSED int evaluate_king_safety(const EngineState *state) {
    int wk = find_king_square(state, WHITE);
    int bk = find_king_square(state, BLACK);
    int score = 0;

    if (wk >= 0) {
        int attacks = 0;
        int i;
        for (i = 0; i < 8; ++i) {
            int sq = wk + KING_OFFSETS[i];
            if (!on_board64(sq) || abs(file_of(sq) - file_of(wk)) > 1) {
                continue;
            }
            if (is_square_attacked(state, sq, BLACK)) {
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
            if (is_square_attacked(state, sq, WHITE)) {
                attacks += 1;
            }
        }
        score += attacks * 6;
    }

    return score;
}

static ENGINE_MAYBE_UNUSED int static_exchange_eval(const EngineState *state, const EngineMove *move) {
    int target = state->board[move->to];
    int attacker = state->board[move->from];
    int gain = PIECE_VALUE[piece_abs(target)] - PIECE_VALUE[piece_abs(attacker)] / 8;
    return gain;
}

static int evaluate_position(EngineState *state) {
    int sq;
    int mg = 0;
    int eg = 0;
    int phase = 0;
    int score;

    for (sq = 0; sq < 64; ++sq) {
        int piece = state->board[sq];
        int side;
        int abs_piece;
        int psq;

        if (piece == EMPTY) {
            continue;
        }

        side = piece_side(piece);
        abs_piece = piece_abs(piece);
        psq = side == WHITE ? sq : mirror_sq(sq);

#if CFG_EVALUATION
        mg += (side == WHITE ? 1 : -1) * PIECE_VALUE[abs_piece];
        eg += (side == WHITE ? 1 : -1) * PIECE_VALUE[abs_piece];
#endif

#if CFG_PIECE_SQUARE_TABLES
        switch (abs_piece) {
            case WP:
                mg += (side == WHITE ? 1 : -1) * PST_PAWN[psq];
                eg += (side == WHITE ? 1 : -1) * PST_PAWN[psq];
                break;
            case WN:
                mg += (side == WHITE ? 1 : -1) * PST_KNIGHT[psq];
                eg += (side == WHITE ? 1 : -1) * PST_KNIGHT[psq];
                phase += 1;
                break;
            case WB:
                mg += (side == WHITE ? 1 : -1) * PST_BISHOP[psq];
                eg += (side == WHITE ? 1 : -1) * PST_BISHOP[psq];
                phase += 1;
                break;
            case WR:
                mg += (side == WHITE ? 1 : -1) * PST_ROOK[psq];
                eg += (side == WHITE ? 1 : -1) * PST_ROOK[psq];
                phase += 2;
                break;
            case WQ:
                mg += (side == WHITE ? 1 : -1) * PST_QUEEN[psq];
                eg += (side == WHITE ? 1 : -1) * PST_QUEEN[psq];
                phase += 4;
                break;
            case WK:
                mg += (side == WHITE ? 1 : -1) * PST_KING_MG[psq];
                eg += (side == WHITE ? 1 : -1) * PST_KING_EG[psq];
                break;
            default:
                break;
        }
#endif
    }

#if CFG_PAWN_HASH_TABLE
    {
        uint64_t key = state_key(state);
        PawnHashEntry *entry = &g_pawn_hash[key & PAWN_HASH_MASK];
        if (entry->key == key) {
            mg += entry->score;
            eg += entry->score;
        } else {
            int pawn_score = evaluate_pawn_structure(state);
            entry->key = key;
            entry->score = pawn_score;
            mg += pawn_score;
            eg += pawn_score;
        }
    }
#elif CFG_PAWN_STRUCTURE
    mg += evaluate_pawn_structure(state);
    eg += evaluate_pawn_structure(state);
#endif

#if CFG_MOBILITY
    mg += evaluate_mobility(state);
#endif

#if CFG_KING_SAFETY
    mg += evaluate_king_safety(state);
#endif

#if CFG_TAPERED_EVAL
    if (phase > 24) {
        phase = 24;
    }
    score = (mg * phase + eg * (24 - phase)) / 24;
#else
    (void)eg;
    (void)phase;
    score = mg;
#endif

    return state->side_to_move == WHITE ? score : -score;
}

static ENGINE_MAYBE_UNUSED int score_capture(const EngineState *state, const EngineMove *move) {
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

static ENGINE_MAYBE_UNUSED int move_to_int(const EngineMove *move) {
    return (int)encode_move16(move);
}

static void move_to_front(EngineMoveList *list, const EngineMove *move) {
    int i;
    if (list == NULL || move == NULL) {
        return;
    }
    for (i = 0; i < list->count; ++i) {
        if (move_equals(&list->moves[i], move)) {
            if (i > 0) {
                EngineMove tmp = list->moves[0];
                list->moves[0] = list->moves[i];
                list->moves[i] = tmp;
            }
            return;
        }
    }
}

static void order_moves(EngineState *state, EngineMoveList *list, int ply, const EngineMove *hash_move) {
    (void)ply;

#if CFG_MOVE_ORDERING
    int i;
    for (i = 0; i < list->count; ++i) {
        EngineMove *m = &list->moves[i];
        int score = 0;

#if CFG_HASH_MOVE
        if (hash_move != NULL && move_equals(m, hash_move)) {
            score += 1000000;
        }
#endif

        if (m->flags & FLAG_CAPTURE) {
            score += 200000 + score_capture(state, m);
        } else {
#if CFG_KILLER_HEURISTIC
            int code = move_to_int(m);
            if (code == g_killers[ply][0]) {
                score += 150000;
            } else if (code == g_killers[ply][1]) {
                score += 140000;
            }
#endif
#if CFG_HISTORY_HEURISTIC
            score += g_history[state->side_to_move][m->from][m->to];
#endif
        }
        m->score = score;
    }

    for (i = 0; i < list->count; ++i) {
        int j;
        int best = i;
        for (j = i + 1; j < list->count; ++j) {
            if (list->moves[j].score > list->moves[best].score) {
                best = j;
            }
        }
        if (best != i) {
            EngineMove tmp = list->moves[i];
            list->moves[i] = list->moves[best];
            list->moves[best] = tmp;
        }
    }
#else
    (void)state;
    (void)ply;
    (void)list;
    (void)hash_move;
#endif
}

static int tt_probe(uint64_t key, int depth, int alpha, int beta, int *score, EngineMove *best_move) {
#if CFG_TRANSPOSITION_TABLE
    TTEntry *entry = &g_tt[key & TT_MASK];
    if (entry->key == key) {
        if (best_move != NULL && entry->move16 != 0) {
            *best_move = decode_move16(entry->move16);
        }
        if (entry->depth >= depth) {
            if (entry->flag == 0) {
                *score = entry->score;
                return 1;
            }
            if (entry->flag < 0 && entry->score <= alpha) {
                *score = alpha;
                return 1;
            }
            if (entry->flag > 0 && entry->score >= beta) {
                *score = beta;
                return 1;
            }
        }
    }
#else
    (void)key;
    (void)depth;
    (void)alpha;
    (void)beta;
    (void)score;
    (void)best_move;
#endif
    return 0;
}

static void tt_store(uint64_t key, int depth, int score, int flag, const EngineMove *best_move) {
#if CFG_TRANSPOSITION_TABLE
    TTEntry *entry = &g_tt[key & TT_MASK];
#if CFG_REPLACEMENT_SCHEMES
    if (entry->key != key && entry->depth > depth) {
        return;
    }
#endif
    entry->key = key;
    entry->depth = depth;
    entry->score = score;
    entry->flag = flag;
    entry->move16 = best_move != NULL ? encode_move16(best_move) : 0;
#else
    (void)key;
    (void)depth;
    (void)score;
    (void)flag;
    (void)best_move;
#endif
}

static bool parse_move_uci(const char *text, EngineMove *out);
static bool find_move_in_list(const EngineMoveList *list, const EngineMove *needle, EngineMove *matched);

static void record_beta_cutoff(EngineState *state, int ply, int depth, const EngineMove *move) {
    if (state == NULL || move == NULL) {
        return;
    }
#if CFG_KILLER_HEURISTIC
    if (!(move->flags & FLAG_CAPTURE) && ply < ENGINE_MAX_PLY) {
        int code = move_to_int(move);
        g_killers[ply][1] = g_killers[ply][0];
        g_killers[ply][0] = code;
    }
#else
    (void)ply;
#endif
#if CFG_HISTORY_HEURISTIC
    if (!(move->flags & FLAG_CAPTURE)) {
        g_history[state->side_to_move][move->from][move->to] += depth * depth;
    }
#else
    (void)depth;
#endif
}

static const EngineSearchOps SEARCH_OPS = {
    .evaluate_position = evaluate_position,
    .in_check = in_check,
    .repetition_count = repetition_count,
    .now_ms = now_ms,
    .generate_moves = generate_moves,
    .make_move = make_move,
    .unmake_move = unmake_move,
    .state_key = state_key,
    .order_moves = order_moves,
    .tt_probe = tt_probe,
    .tt_store = tt_store,
    .parse_move_uci = parse_move_uci,
    .find_move_in_list = find_move_in_list,
    .move_to_front = move_to_front,
    .record_beta_cutoff = record_beta_cutoff,
};

const EngineSearchOps *engine_get_search_ops(void) {
    return &SEARCH_OPS;
}

static bool parse_move_uci(const char *text, EngineMove *out) {
    int from_file;
    int from_rank;
    int to_file;
    int to_rank;

    if (text == NULL || strlen(text) < 4) {
        return false;
    }

    if (text[0] < 'a' || text[0] > 'h' || text[2] < 'a' || text[2] > 'h') {
        return false;
    }
    if (text[1] < '1' || text[1] > '8' || text[3] < '1' || text[3] > '8') {
        return false;
    }

    from_file = text[0] - 'a';
    from_rank = text[1] - '1';
    to_file = text[2] - 'a';
    to_rank = text[3] - '1';

    memset(out, 0, sizeof(*out));
    out->from = (uint8_t)(from_rank * 8 + from_file);
    out->to = (uint8_t)(to_rank * 8 + to_file);

    if (strlen(text) >= 5) {
        switch (tolower((unsigned char)text[4])) {
            case 'n':
                out->promotion = 1;
                break;
            case 'b':
                out->promotion = 2;
                break;
            case 'r':
                out->promotion = 3;
                break;
            case 'q':
            default:
                out->promotion = 4;
                break;
        }
        out->flags |= FLAG_PROMOTION;
    }

    return true;
}

static bool is_same_move(const EngineMove *a, const EngineMove *b) {
    return a->from == b->from && a->to == b->to && a->promotion == b->promotion;
}

static bool find_move_in_list(const EngineMoveList *list, const EngineMove *needle, EngineMove *matched) {
    int i;
    for (i = 0; i < list->count; ++i) {
        if (is_same_move(&list->moves[i], needle)) {
            if (matched != NULL) {
                *matched = list->moves[i];
            }
            return true;
        }
    }
    return false;
}

static bool find_move_with_promotion_fallback(const EngineMoveList *list, const EngineMove *needle, EngineMove *matched) {
    int i;

    if (find_move_in_list(list, needle, matched)) {
        return true;
    }

    if (needle->promotion == 0) {
        return false;
    }

    for (i = 0; i < list->count; ++i) {
        const EngineMove *candidate = &list->moves[i];
        if (candidate->from == needle->from && candidate->to == needle->to && (candidate->flags & FLAG_PROMOTION) != 0) {
            if (matched != NULL) {
                *matched = *candidate;
                matched->promotion = needle->promotion;
            }
            return true;
        }
    }

    return false;
}

void engine_init(EngineState *state) {
    if (state == NULL) {
        return;
    }
    init_square_maps();
    init_zobrist();
    memset(g_tt, 0, sizeof(g_tt));
    memset(g_pawn_hash, 0, sizeof(g_pawn_hash));
    memset(g_killers, 0, sizeof(g_killers));
    memset(g_history, 0, sizeof(g_history));
    state->pondering_enabled = false;
    state->max_depth_hint = 5;
    state->movetime_ms = 150;
    engine_set_startpos(state);
}

int engine_set_startpos(EngineState *state) {
    if (state == NULL) {
        return -1;
    }
    /* Start position must be available even when CFG_FEN is disabled. */
    if (parse_fen_board(state, STARTPOS_FEN) != 0) {
        return -1;
    }
    state->plies_from_start = 0;
    state->history_count = 1;
    state->position_history[0] = state_key(state);
    snprintf(state->last_fen, sizeof(state->last_fen), "%s", STARTPOS_FEN);
    return 0;
}

int engine_set_fen(EngineState *state, const char *fen) {
    if (state == NULL || fen == NULL) {
        return -1;
    }
#if !CFG_FEN
    (void)fen;
    return -1;
#else
    if (parse_fen_board(state, fen) != 0) {
        return -1;
    }
    state->plies_from_start = (state->fullmove_number - 1) * 2 + (state->side_to_move == BLACK ? 1 : 0);
    if (state->plies_from_start < 0) {
        state->plies_from_start = 0;
    }
    state->history_count = 1;
    state->position_history[0] = state_key(state);
    snprintf(state->last_fen, sizeof(state->last_fen), "%s", fen);
    return 0;
#endif
}

int engine_apply_move_uci(EngineState *state, const char *move_uci) {
    EngineMove parsed;
    EngineMoveList legal;
    EngineMove actual;
    Undo undo;

    if (state == NULL || move_uci == NULL) {
        return -1;
    }
    if (!parse_move_uci(move_uci, &parsed)) {
        return -1;
    }

    generate_moves(state, &legal, false);
    if (!find_move_with_promotion_fallback(&legal, &parsed, &actual)) {
        return -1;
    }

    if (!make_move(state, &actual, &undo)) {
        return -1;
    }
    return 0;
}

int engine_generate_legal_moves(EngineState *state, EngineMoveList *list) {
    if (state == NULL || list == NULL) {
        return -1;
    }
    generate_moves(state, list, false);
    return list->count;
}

static uint64_t perft_recursive(EngineState *state, int depth) {
    EngineMoveList list;
    uint64_t nodes = 0ULL;
    int i;

    if (depth <= 0) {
        return 1ULL;
    }

    generate_moves(state, &list, false);
    if (depth == 1) {
        return (uint64_t)list.count;
    }

    for (i = 0; i < list.count; ++i) {
        EngineMove move = list.moves[i];
        Undo undo;
#if CFG_COPY_MAKE || !CFG_UNMAKE_MOVE
        EngineState snapshot = *state;
#endif
        if (!make_move(state, &move, &undo)) {
            continue;
        }

        nodes += perft_recursive(state, depth - 1);

#if CFG_COPY_MAKE || !CFG_UNMAKE_MOVE
        *state = snapshot;
#else
        unmake_move(state, &move, &undo);
#endif
    }

    return nodes;
}

uint64_t engine_perft(EngineState *state, int depth) {
    if (state == NULL || depth < 0) {
        return 0ULL;
    }
#if !CFG_MOVE_GENERATION || !CFG_MAKE_MOVE
    (void)depth;
    return 0ULL;
#else
    return perft_recursive(state, depth);
#endif
}

void engine_move_to_uci(const EngineMove *move, char out[6]) {
    int from_file;
    int from_rank;
    int to_file;
    int to_rank;
    if (move == NULL || out == NULL) {
        return;
    }

    from_file = file_of(move->from);
    from_rank = rank_of(move->from);
    to_file = file_of(move->to);
    to_rank = rank_of(move->to);

    out[0] = (char)('a' + from_file);
    out[1] = (char)('1' + from_rank);
    out[2] = (char)('a' + to_file);
    out[3] = (char)('1' + to_rank);
    if (move->promotion != 0) {
        out[4] = 'q';
        out[5] = '\0';
    } else {
        out[4] = '\0';
        out[5] = '\0';
    }
}

void engine_variant_summary(char *out, size_t out_size) {
    if (out == NULL || out_size == 0) {
        return;
    }

    snprintf(out, out_size, "variant=%s board=%s search=%s", PL_VARIANT_NAME, engine_board_backend_name(), engine_search_core_name());
}

void engine_print_compiled_features(FILE *out) {
    int i;
    if (out == NULL) {
        return;
    }

    fprintf(out, "id name CPW-PL-Engine (%s)\n", PL_VARIANT_NAME);
    fprintf(out, "id author Codex\n");
    fprintf(out, "option name Ponder type check default false\n");

    for (i = 0; i < PL_SELECTED_OPTION_COUNT; ++i) {
        fprintf(out, "info string feature[%d]=%s\n", i + 1, PL_SELECTED_OPTION_NAMES[i]);
    }

    fprintf(out, "info string repr=real_movegen_search_eval\n");
}
