#include "engine_search_internal.h"
#include "engine_backend_internal.h"
#include "engine_eval_internal.h"

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

#define TT_BUCKET_SIZE 4u
#define TT_SET_COUNT (1u << 16)
#define TT_SET_MASK (TT_SET_COUNT - 1u)

#define QUIESCENCE_MAX_DEPTH 8

#define STARTPOS_FEN "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"

#if defined(__clang__) || defined(__GNUC__)
#define ENGINE_MAYBE_UNUSED __attribute__((unused))
#else
#define ENGINE_MAYBE_UNUSED
#endif

static const int KNIGHT_OFFSETS[8] = {17, 15, 10, 6, -17, -15, -10, -6};
static const int BISHOP_OFFSETS[4] = {9, 7, -9, -7};
static const int ROOK_OFFSETS[4] = {8, -8, 1, -1};
static const int KING_OFFSETS[8] = {8, -8, 1, -1, 9, 7, -9, -7};

typedef struct TTEntry {
    uint64_t key;
    int score;
    int depth;
    int flag; /* 0 exact, -1 alpha, 1 beta */
    uint16_t move16;
    uint8_t generation;
    uint8_t reserved;
} TTEntry;

static TTEntry g_tt[TT_SET_COUNT][TT_BUCKET_SIZE];
static uint8_t g_tt_generation = 1;

static uint64_t g_zobrist_piece[12][64];
static uint64_t g_zobrist_side;
static uint64_t g_zobrist_castling[16];
static uint64_t g_zobrist_ep_file[8];
static bool g_zobrist_ready = false;

static int g_killers[ENGINE_MAX_PLY][2];
static int g_history[2][64][64];
static EngineInstrumentation g_instrumentation;

typedef struct ThreatInfo {
    int king_sq;
    int checker_count;
    uint64_t checkers_mask;
    uint64_t evasion_mask;
    uint64_t pinned_mask;
    uint64_t pin_allowed[64];
} ThreatInfo;

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

static inline int step_delta_between(int from, int to) {
    int dr = rank_of(to) - rank_of(from);
    int df = file_of(to) - file_of(from);

    if (df == 0 && dr != 0) {
        return dr > 0 ? 8 : -8;
    }
    if (dr == 0 && df != 0) {
        return df > 0 ? 1 : -1;
    }
    if (abs(dr) == abs(df) && dr != 0) {
        if (dr > 0 && df > 0) {
            return 9;
        }
        if (dr > 0 && df < 0) {
            return 7;
        }
        if (dr < 0 && df > 0) {
            return -7;
        }
        return -9;
    }
    return 0;
}

static inline bool step_preserves_geometry_local(int from, int to, int delta) {
    if (from < 0 || from >= 64 || to < 0 || to >= 64 || to != from + delta) {
        return false;
    }
    switch (delta) {
        case 1:
        case -1:
            return rank_of(from) == rank_of(to);
        case 8:
        case -8:
            return file_of(from) == file_of(to);
        case 9:
        case -9:
        case 7:
        case -7:
            return abs(file_of(to) - file_of(from)) == 1 && abs(rank_of(to) - rank_of(from)) == 1;
        default:
            return false;
    }
}

static inline uint64_t square_bb_local(int sq) {
    return 1ULL << sq;
}

static inline int square_to_0x88(int sq) {
    return (rank_of(sq) << 4) + file_of(sq);
}

static inline int square_to_120(int sq) {
    return (rank_of(sq) + 2) * 10 + (file_of(sq) + 1);
}

void engine_reset_instrumentation_internal(void) {
    memset(&g_instrumentation, 0, sizeof(g_instrumentation));
}

EngineInstrumentation engine_get_instrumentation_internal(void) {
    return g_instrumentation;
}

void engine_note_eval_call_internal(void) {
    g_instrumentation.eval_calls += 1;
}

void engine_note_eval_cache_hit_internal(void) {
    g_instrumentation.eval_cache_hits += 1;
}

void engine_note_movegen_call_internal(void) {
    g_instrumentation.movegen_calls += 1;
}

void engine_note_attack_call_internal(void) {
    g_instrumentation.attack_calls += 1;
}

void engine_note_tt_probe_internal(bool hit, bool cutoff_hit) {
    g_instrumentation.tt_probes += 1;
    if (hit) {
        g_instrumentation.tt_hits += 1;
    }
    if (cutoff_hit) {
        g_instrumentation.tt_cutoff_hits += 1;
    }
}

void engine_note_tt_store_internal(void) {
    g_instrumentation.tt_stores += 1;
}

void engine_note_beta_cutoff_internal(void) {
    g_instrumentation.beta_cutoffs += 1;
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

static ENGINE_MAYBE_UNUSED uint64_t compute_zobrist(const EngineState *state) {
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

static uint64_t compute_pawn_key(const EngineState *state) {
    uint64_t key = 0ULL;
    int sq;

    init_zobrist();
    for (sq = 0; sq < 64; ++sq) {
        int piece = state->board[sq];
        if (piece == WP) {
            key ^= g_zobrist_piece[0][sq];
        } else if (piece == BP) {
            key ^= g_zobrist_piece[6][sq];
        }
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

uint64_t engine_state_key_internal(const EngineState *state) {
#if CFG_ZOBRIST_HASHING
    return state->zobrist_key;
#else
    return compute_fallback_hash(state);
#endif
}

uint64_t engine_pawn_key_internal(const EngineState *state) {
#if CFG_ZOBRIST_HASHING
    return state->pawn_key;
#else
    return compute_pawn_key(state);
#endif
}

static void refresh_cached_keys(EngineState *state) {
    if (state == NULL) {
        return;
    }
#if CFG_ZOBRIST_HASHING
    state->zobrist_key = compute_zobrist(state);
    state->pawn_key = compute_pawn_key(state);
#else
    state->zobrist_key = compute_fallback_hash(state);
    state->pawn_key = compute_pawn_key(state);
#endif
}

static inline int piece_type_index_local(int piece) {
    int abs_piece = piece_abs(piece);
    return abs_piece >= WP && abs_piece <= WK ? abs_piece - 1 : -1;
}

static void piece_list_add(EngineState *state, int piece, int sq) {
#if CFG_PIECE_LISTS
    int side = piece_side(piece);
    int type = piece_type_index_local(piece);
    if (side >= WHITE && side <= BLACK && type >= 0) {
        int count = state->piece_list_counts[side][type];
        if (count < ENGINE_MAX_PIECES_PER_TYPE) {
            state->piece_list_squares[side][type][count] = sq;
            state->piece_list_counts[side][type] = (uint8_t)(count + 1);
        }
    }
#else
    (void)state;
    (void)piece;
    (void)sq;
#endif
}

static void piece_list_remove(EngineState *state, int piece, int sq) {
#if CFG_PIECE_LISTS
    int side = piece_side(piece);
    int type = piece_type_index_local(piece);
    if (side >= WHITE && side <= BLACK && type >= 0) {
        int count = state->piece_list_counts[side][type];
        int i;
        for (i = 0; i < count; ++i) {
            if (state->piece_list_squares[side][type][i] == sq) {
                int last = count - 1;
                state->piece_list_squares[side][type][i] = state->piece_list_squares[side][type][last];
                state->piece_list_squares[side][type][last] = 0;
                state->piece_list_counts[side][type] = (uint8_t)last;
                break;
            }
        }
    }
#else
    (void)state;
    (void)piece;
    (void)sq;
#endif
}

static void backend_add_piece(EngineState *state, int piece, int sq) {
    if (state == NULL || piece == EMPTY || sq < 0 || sq >= 64) {
        return;
    }
    if (piece == WK) {
        state->king_square[WHITE] = sq;
    } else if (piece == BK) {
        state->king_square[BLACK] = sq;
    }
#if CFG_0X88
    state->board_0x88[square_to_0x88(sq)] = piece;
#endif
#if CFG_10X12_BOARD
    state->board_120[square_to_120(sq)] = piece;
#endif
#if CFG_BITBOARDS
    {
        int idx = piece_to_zobrist_index(piece);
        uint64_t bit = square_bb_local(sq);
        if (idx >= 0) {
            state->bb_pieces[idx] |= bit;
        }
        if (piece_side(piece) == WHITE) {
            state->bb_white_occ |= bit;
        } else {
            state->bb_black_occ |= bit;
        }
    }
#endif
    piece_list_add(state, piece, sq);
}

static void backend_remove_piece(EngineState *state, int piece, int sq) {
    if (state == NULL || piece == EMPTY || sq < 0 || sq >= 64) {
        return;
    }
    if (piece == WK && state->king_square[WHITE] == sq) {
        state->king_square[WHITE] = -1;
    } else if (piece == BK && state->king_square[BLACK] == sq) {
        state->king_square[BLACK] = -1;
    }
#if CFG_0X88
    state->board_0x88[square_to_0x88(sq)] = EMPTY;
#endif
#if CFG_10X12_BOARD
    state->board_120[square_to_120(sq)] = EMPTY;
#endif
#if CFG_BITBOARDS
    {
        int idx = piece_to_zobrist_index(piece);
        uint64_t bit = square_bb_local(sq);
        if (idx >= 0) {
            state->bb_pieces[idx] &= ~bit;
        }
        if (piece_side(piece) == WHITE) {
            state->bb_white_occ &= ~bit;
        } else {
            state->bb_black_occ &= ~bit;
        }
    }
#endif
    piece_list_remove(state, piece, sq);
}

static inline void cached_key_toggle_piece(EngineState *state, int piece, int sq) {
#if CFG_ZOBRIST_HASHING
    int idx = piece_to_zobrist_index(piece);
    if (idx >= 0) {
        state->zobrist_key ^= g_zobrist_piece[idx][sq];
        if (piece == WP || piece == BP) {
            state->pawn_key ^= g_zobrist_piece[idx][sq];
        }
    }
#else
    (void)state;
    (void)piece;
    (void)sq;
#endif
}

static inline void cached_key_toggle_side(EngineState *state) {
#if CFG_ZOBRIST_HASHING
    state->zobrist_key ^= g_zobrist_side;
#else
    (void)state;
#endif
}

static inline void cached_key_toggle_castling(EngineState *state, int rights) {
#if CFG_ZOBRIST_HASHING
    state->zobrist_key ^= g_zobrist_castling[rights & 0x0f];
#else
    (void)state;
    (void)rights;
#endif
}

static inline void cached_key_toggle_ep(EngineState *state, int ep_sq) {
#if CFG_ZOBRIST_HASHING
    if (ep_sq >= 0 && ep_sq < 64) {
        state->zobrist_key ^= g_zobrist_ep_file[file_of(ep_sq)];
    }
#else
    (void)state;
    (void)ep_sq;
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
    memset(state->piece_list_squares, 0, sizeof(state->piece_list_squares));
    memset(state->piece_list_counts, 0, sizeof(state->piece_list_counts));
    state->bb_white_occ = 0ULL;
    state->bb_black_occ = 0ULL;
    state->king_square[WHITE] = -1;
    state->king_square[BLACK] = -1;
    state->side_to_move = WHITE;
    state->castling_rights = 0;
    state->en_passant_square = -1;
    state->halfmove_clock = 0;
    state->fullmove_number = 1;
    state->plies_from_start = 0;
    state->zobrist_key = 0ULL;
    state->pawn_key = 0ULL;
    state->history_count = 0;
    for (i = 0; i < ENGINE_MAX_HISTORY; ++i) {
        state->position_history[i] = 0ULL;
    }
    state->nodes = 0;
    state->stop = false;
    state->exact_movetime = false;
    state->soft_deadline_ms = 0;
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
    refresh_cached_keys(state);
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

static ENGINE_MAYBE_UNUSED EngineMove decode_move16(uint16_t code) {
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

int engine_find_king_square_internal(const EngineState *state, int side) {
    if (state != NULL && side >= WHITE && side <= BLACK && state->king_square[side] >= 0) {
        return state->king_square[side];
    }
    return engine_backend_find_king_square(state, side);
}

bool engine_is_square_attacked_internal(const EngineState *state, int sq, int attacker_side) {
    engine_note_attack_call_internal();
    return engine_backend_is_square_attacked(state, sq, attacker_side);
}

static bool in_check(const EngineState *state, int side) {
    int king_sq = engine_find_king_square_internal(state, side);
    if (king_sq < 0) {
        return false;
    }
    return engine_is_square_attacked_internal(state, king_sq, side ^ 1);
}

static uint64_t line_mask_from_to(int from, int to) {
    uint64_t mask = 0ULL;
    int step = step_delta_between(from, to);
    int sq;

    if (step == 0) {
        return 0ULL;
    }

    for (sq = from + step; sq != to; sq += step) {
        if (!step_preserves_geometry_local(sq - step, sq, step)) {
            return 0ULL;
        }
        mask |= square_bb_local(sq);
    }
    mask |= square_bb_local(to);
    return mask;
}

static void threat_info_add_checker(ThreatInfo *info, int checker_sq, uint64_t evasion_mask) {
    if (info == NULL || checker_sq < 0 || checker_sq >= 64) {
        return;
    }
    info->checker_count += 1;
    info->checkers_mask |= square_bb_local(checker_sq);
    if (info->checker_count == 1) {
        info->evasion_mask = evasion_mask;
    } else {
        info->evasion_mask = 0ULL;
    }
}

static void analyze_king_threats(const EngineState *state, int side, ThreatInfo *info) {
    static const int rook_dirs[4] = {8, -8, 1, -1};
    static const int bishop_dirs[4] = {9, 7, -9, -7};
    int enemy = side ^ 1;
    int king_sq;
    int i;

    memset(info, 0, sizeof(*info));
    for (i = 0; i < 64; ++i) {
        info->pin_allowed[i] = 0ULL;
    }

    king_sq = engine_find_king_square_internal(state, side);
    info->king_sq = king_sq;
    info->evasion_mask = ~0ULL;
    if (king_sq < 0) {
        return;
    }

    if (side == WHITE) {
        int sq = king_sq + 7;
        if (on_board64(sq) && abs(file_of(sq) - file_of(king_sq)) == 1 && state->board[sq] == BP) {
            threat_info_add_checker(info, sq, square_bb_local(sq));
        }
        sq = king_sq + 9;
        if (on_board64(sq) && abs(file_of(sq) - file_of(king_sq)) == 1 && state->board[sq] == BP) {
            threat_info_add_checker(info, sq, square_bb_local(sq));
        }
    } else {
        int sq = king_sq - 7;
        if (on_board64(sq) && abs(file_of(sq) - file_of(king_sq)) == 1 && state->board[sq] == WP) {
            threat_info_add_checker(info, sq, square_bb_local(sq));
        }
        sq = king_sq - 9;
        if (on_board64(sq) && abs(file_of(sq) - file_of(king_sq)) == 1 && state->board[sq] == WP) {
            threat_info_add_checker(info, sq, square_bb_local(sq));
        }
    }

    for (i = 0; i < 8; ++i) {
        int sq = king_sq + KNIGHT_OFFSETS[i];
        if (!on_board64(sq) || abs(file_of(sq) - file_of(king_sq)) > 2) {
            continue;
        }
        if (state->board[sq] == (enemy == WHITE ? WN : BN)) {
            threat_info_add_checker(info, sq, square_bb_local(sq));
        }
    }

    for (i = 0; i < 8; ++i) {
        int sq = king_sq + KING_OFFSETS[i];
        if (!on_board64(sq) || abs(file_of(sq) - file_of(king_sq)) > 1) {
            continue;
        }
        if (state->board[sq] == (enemy == WHITE ? WK : BK)) {
            threat_info_add_checker(info, sq, square_bb_local(sq));
        }
    }

    for (i = 0; i < 4; ++i) {
        int delta = rook_dirs[i];
        int sq = king_sq + delta;
        int first_own = -1;
        while (step_preserves_geometry_local(sq - delta, sq, delta)) {
            int piece = state->board[sq];
            if (piece == EMPTY) {
                sq += delta;
                continue;
            }
            if (piece_side(piece) == side) {
                if (first_own == -1) {
                    first_own = sq;
                    sq += delta;
                    continue;
                }
                break;
            }
            if (piece == (enemy == WHITE ? WR : BR) || piece == (enemy == WHITE ? WQ : BQ)) {
                if (first_own == -1) {
                    threat_info_add_checker(info, sq, line_mask_from_to(king_sq, sq));
                } else {
                    info->pinned_mask |= square_bb_local(first_own);
                    info->pin_allowed[first_own] = line_mask_from_to(king_sq, sq);
                }
            }
            break;
        }
    }

    for (i = 0; i < 4; ++i) {
        int delta = bishop_dirs[i];
        int sq = king_sq + delta;
        int first_own = -1;
        while (step_preserves_geometry_local(sq - delta, sq, delta)) {
            int piece = state->board[sq];
            if (piece == EMPTY) {
                sq += delta;
                continue;
            }
            if (piece_side(piece) == side) {
                if (first_own == -1) {
                    first_own = sq;
                    sq += delta;
                    continue;
                }
                break;
            }
            if (piece == (enemy == WHITE ? WB : BB) || piece == (enemy == WHITE ? WQ : BQ)) {
                if (first_own == -1) {
                    threat_info_add_checker(info, sq, line_mask_from_to(king_sq, sq));
                } else {
                    info->pinned_mask |= square_bb_local(first_own);
                    info->pin_allowed[first_own] = line_mask_from_to(king_sq, sq);
                }
            }
            break;
        }
    }
}

static int repetition_count(const EngineState *state) {
    int i;
    int count = 0;
    uint64_t key = engine_state_key_internal(state);
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
    int placed_piece;
    int rook_piece = EMPTY;

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
    undo->zobrist_key = state->zobrist_key;
    undo->pawn_key = state->pawn_key;
    undo->history_count = state->history_count;

    cached_key_toggle_castling(state, state->castling_rights);
    cached_key_toggle_ep(state, state->en_passant_square);
    cached_key_toggle_piece(state, piece, move->from);

    backend_remove_piece(state, piece, move->from);
    state->board[move->from] = EMPTY;

    if (captured != EMPTY) {
        cached_key_toggle_piece(state, captured, captured_sq);
        backend_remove_piece(state, captured, captured_sq);
        state->board[captured_sq] = EMPTY;
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
            rook_piece = state->board[rook_from];
            cached_key_toggle_piece(state, rook_piece, rook_from);
            backend_remove_piece(state, rook_piece, rook_from);
            state->board[rook_from] = EMPTY;
            state->board[rook_to] = rook_piece;
            backend_add_piece(state, rook_piece, rook_to);
            cached_key_toggle_piece(state, rook_piece, rook_to);
        }
    }

    placed_piece = move->promotion != 0 ? promotion_piece(side, move->promotion) : piece;
    state->board[move->to] = placed_piece;
    backend_add_piece(state, placed_piece, move->to);
    cached_key_toggle_piece(state, placed_piece, move->to);

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
    cached_key_toggle_castling(state, state->castling_rights);
    cached_key_toggle_ep(state, state->en_passant_square);
    cached_key_toggle_side(state);
    state->plies_from_start += 1;
    if (state->history_count < ENGINE_MAX_HISTORY) {
        state->position_history[state->history_count] = engine_state_key_internal(state);
        state->history_count += 1;
    } else {
        int i;
        for (i = 1; i < ENGINE_MAX_HISTORY; ++i) {
            state->position_history[i - 1] = state->position_history[i];
        }
        state->position_history[ENGINE_MAX_HISTORY - 1] = engine_state_key_internal(state);
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
    int piece_on_to;

    state->side_to_move ^= 1;
    mover_side = state->side_to_move;
    state->plies_from_start -= 1;
    state->castling_rights = undo->castling_rights;
    state->en_passant_square = undo->en_passant_square;
    state->halfmove_clock = undo->halfmove_clock;
    state->fullmove_number = undo->fullmove_number;
    state->zobrist_key = undo->zobrist_key;
    state->pawn_key = undo->pawn_key;
    state->history_count = undo->history_count;

    piece_on_to = state->board[move->to];
    if (piece_on_to != EMPTY) {
        backend_remove_piece(state, piece_on_to, move->to);
    }
    state->board[move->to] = EMPTY;
    state->board[move->from] = undo->moved_piece;
    backend_add_piece(state, undo->moved_piece, move->from);

    if ((move->flags & FLAG_CASTLING) != 0) {
        if (mover_side == WHITE && move->from == 4 && move->to == 6) {
            backend_remove_piece(state, WR, 5);
            state->board[7] = WR;
            state->board[5] = EMPTY;
            backend_add_piece(state, WR, 7);
        } else if (mover_side == WHITE && move->from == 4 && move->to == 2) {
            backend_remove_piece(state, WR, 3);
            state->board[0] = WR;
            state->board[3] = EMPTY;
            backend_add_piece(state, WR, 0);
        } else if (mover_side == BLACK && move->from == 60 && move->to == 62) {
            backend_remove_piece(state, BR, 61);
            state->board[63] = BR;
            state->board[61] = EMPTY;
            backend_add_piece(state, BR, 63);
        } else if (mover_side == BLACK && move->from == 60 && move->to == 58) {
            backend_remove_piece(state, BR, 59);
            state->board[56] = BR;
            state->board[59] = EMPTY;
            backend_add_piece(state, BR, 56);
        }
    }

    if ((move->flags & FLAG_EN_PASSANT) != 0) {
        state->board[undo->captured_square] = undo->captured;
        if (undo->captured != EMPTY) {
            backend_add_piece(state, undo->captured, undo->captured_square);
        }
    } else {
        state->board[move->to] = undo->captured;
        if (undo->captured != EMPTY) {
            backend_add_piece(state, undo->captured, move->to);
        }
    }
#endif
}

static ENGINE_MAYBE_UNUSED void generate_moves_scan(const EngineState *state, EngineMoveList *list, bool captures_only) {
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
                        !engine_is_square_attacked_internal(state, 5, BLACK) &&
                        !engine_is_square_attacked_internal(state, 6, BLACK)) {
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
                        !engine_is_square_attacked_internal(state, 3, BLACK) &&
                        !engine_is_square_attacked_internal(state, 2, BLACK)) {
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
                        !engine_is_square_attacked_internal(state, 61, WHITE) &&
                        !engine_is_square_attacked_internal(state, 62, WHITE)) {
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
                        !engine_is_square_attacked_internal(state, 59, WHITE) &&
                        !engine_is_square_attacked_internal(state, 58, WHITE)) {
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

void engine_generate_pseudo_moves_internal(const EngineState *state, EngineMoveList *list, bool captures_only) {
    engine_note_movegen_call_internal();
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
    ThreatInfo threats;
    bool tmp_initialized = false;
    int i;

    list->count = 0;
    engine_generate_pseudo_moves_internal(state, &pseudo, captures_only);
    analyze_king_threats(state, state->side_to_move, &threats);

    for (i = 0; i < pseudo.count; ++i) {
        const EngineMove *move = &pseudo.moves[i];
        int piece = state->board[move->from];
        bool needs_fallback = true;

        if (piece != EMPTY && piece_abs(piece) != WK && (move->flags & FLAG_EN_PASSANT) == 0) {
            uint64_t from_mask = square_bb_local(move->from);
            uint64_t to_mask = square_bb_local(move->to);

            if (threats.checker_count > 1) {
                needs_fallback = false;
            } else {
                if ((threats.pinned_mask & from_mask) != 0ULL &&
                    (threats.pin_allowed[move->from] & to_mask) == 0ULL) {
                    needs_fallback = false;
                } else if (threats.checker_count == 1 &&
                           (threats.evasion_mask & to_mask) == 0ULL) {
                    needs_fallback = false;
                } else {
                    needs_fallback = false;
                    move_list_push(list, *move);
                }
            }
        }

        if (!needs_fallback) {
            continue;
        }

        if (!tmp_initialized) {
            tmp = *state;
            tmp_initialized = true;
        }

        {
            Undo undo;
            if (!make_move(&tmp, move, &undo)) {
                continue;
            }
            if (!in_check(&tmp, state->side_to_move)) {
                move_list_push(list, *move);
            }
            unmake_move(&tmp, move, &undo);
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
    engine_generate_pseudo_moves_internal(state, list, captures_only);
#else
    generate_legal_moves(state, list, captures_only);
#endif
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
#if !CFG_HASH_MOVE
    (void)hash_move;
#endif

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
            score += 200000 + engine_score_capture_internal(state, m);
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

static int tt_store_score(int score, int ply) {
    if (score >= ENGINE_MATE - ENGINE_MAX_PLY) {
        return score + ply;
    }
    if (score <= -ENGINE_MATE + ENGINE_MAX_PLY) {
        return score - ply;
    }
    return score;
}

static int tt_load_score(int score, int ply) {
    if (score >= ENGINE_MATE - ENGINE_MAX_PLY) {
        return score - ply;
    }
    if (score <= -ENGINE_MATE + ENGINE_MAX_PLY) {
        return score + ply;
    }
    return score;
}

static int tt_entry_priority(const TTEntry *entry) {
    int age;
    int priority;

    if (entry == NULL || entry->generation == 0) {
        return INT_MIN;
    }

    age = (int)((uint8_t)(g_tt_generation - entry->generation));
    priority = entry->depth - age * 4;
    if (entry->flag != 0) {
        priority -= 1;
    }
    return priority;
}

static void tt_new_search(void) {
#if CFG_TRANSPOSITION_TABLE
    g_tt_generation += 1;
    if (g_tt_generation == 0) {
        g_tt_generation = 1;
    }
#endif
}

static int tt_probe(uint64_t key, int depth, int alpha, int beta, int ply, int *score, EngineMove *best_move) {
#if CFG_TRANSPOSITION_TABLE
    TTEntry *bucket = g_tt[key & TT_SET_MASK];
    const TTEntry *best_entry = NULL;
    unsigned i;
    bool probe_hit = false;
    bool cutoff_hit = false;

    for (i = 0; i < TT_BUCKET_SIZE; ++i) {
        TTEntry *entry = &bucket[i];
        int entry_score;

        if (entry->generation == 0 || entry->key != key) {
            continue;
        }
        probe_hit = true;
        entry->generation = g_tt_generation;
        if (best_entry == NULL || entry->depth > best_entry->depth) {
            best_entry = entry;
        }
        if (best_move != NULL && entry->move16 != 0) {
            *best_move = decode_move16(entry->move16);
        }
        if (entry->depth < depth) {
            continue;
        }
        entry_score = tt_load_score(entry->score, ply);
        if (depth <= 0) {
            if (score != NULL) {
                *score = entry_score;
            }
            cutoff_hit = true;
            engine_note_tt_probe_internal(probe_hit, cutoff_hit);
            return 1;
        }
        if (entry->flag == 0) {
            *score = entry_score;
            cutoff_hit = true;
            engine_note_tt_probe_internal(probe_hit, cutoff_hit);
            return 1;
        }
        if (entry->flag < 0 && entry_score <= alpha) {
            *score = entry_score;
            cutoff_hit = true;
            engine_note_tt_probe_internal(probe_hit, cutoff_hit);
            return 1;
        }
        if (entry->flag > 0 && entry_score >= beta) {
            *score = entry_score;
            cutoff_hit = true;
            engine_note_tt_probe_internal(probe_hit, cutoff_hit);
            return 1;
        }
    }

    if (best_move != NULL && best_entry != NULL && best_entry->move16 != 0) {
        *best_move = decode_move16(best_entry->move16);
    }
    engine_note_tt_probe_internal(probe_hit, cutoff_hit);
#else
    (void)key;
    (void)depth;
    (void)alpha;
    (void)beta;
    (void)ply;
    (void)score;
    (void)best_move;
#endif
    return 0;
}

static void tt_store(uint64_t key, int depth, int score, int flag, int ply, const EngineMove *best_move) {
#if CFG_TRANSPOSITION_TABLE
    TTEntry *bucket = g_tt[key & TT_SET_MASK];
    TTEntry *target = NULL;
    int target_priority = INT_MAX;
    unsigned i;

    for (i = 0; i < TT_BUCKET_SIZE; ++i) {
        TTEntry *entry = &bucket[i];
        int priority;

        if (entry->generation == 0) {
            target = entry;
            break;
        }
        if (entry->key == key) {
            target = entry;
            break;
        }
        priority = tt_entry_priority(entry);
        if (priority < target_priority) {
            target = entry;
            target_priority = priority;
        }
    }

    if (target == NULL) {
        target = &bucket[0];
    }

#if CFG_REPLACEMENT_SCHEMES
    if (
        target->generation != 0 &&
        target->key == key &&
        target->depth > depth &&
        target->flag == 0 &&
        flag != 0
    ) {
        return;
    }
#endif
    target->key = key;
    target->depth = depth;
    target->score = tt_store_score(score, ply);
    target->flag = flag;
    target->move16 = best_move != NULL ? encode_move16(best_move) : 0;
    target->generation = g_tt_generation;
    engine_note_tt_store_internal();
#else
    (void)key;
    (void)depth;
    (void)score;
    (void)flag;
    (void)ply;
    (void)best_move;
#endif
}

static bool parse_move_uci(const char *text, EngineMove *out);
static bool find_move_in_list(const EngineMoveList *list, const EngineMove *needle, EngineMove *matched);

static void record_beta_cutoff(EngineState *state, int ply, int depth, const EngineMove *move) {
    if (state == NULL || move == NULL) {
        return;
    }
    engine_note_beta_cutoff_internal();
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
    .evaluate_position = engine_evaluate_position_internal,
    .in_check = in_check,
    .repetition_count = repetition_count,
    .now_ms = now_ms,
    .generate_moves = generate_moves,
    .make_move = make_move,
    .unmake_move = unmake_move,
    .state_key = engine_state_key_internal,
    .order_moves = order_moves,
    .tt_probe = tt_probe,
    .tt_store = tt_store,
    .tt_new_search = tt_new_search,
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
    init_zobrist();
    memset(g_tt, 0, sizeof(g_tt));
    g_tt_generation = 1;
    engine_reset_evaluation_tables();
    memset(g_killers, 0, sizeof(g_killers));
    memset(g_history, 0, sizeof(g_history));
    state->pondering_enabled = false;
    state->opening_book_enabled = true;
    state->max_depth_hint = 5;
    state->movetime_ms = 150;
    snprintf(state->opening_book_path, sizeof(state->opening_book_path), "%s", "c_engine_pl/books/default_openings.txt");
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
    state->position_history[0] = engine_state_key_internal(state);
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
    state->position_history[0] = engine_state_key_internal(state);
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

int engine_static_eval(EngineState *state) {
    if (state == NULL) {
        return 0;
    }
    return engine_evaluate_position_internal(state);
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

    snprintf(
        out,
        out_size,
        "variant=%s board=%s search=%s eval=%s",
        PL_VARIANT_NAME,
        engine_board_backend_name(),
        engine_search_core_name(),
        engine_eval_profile_name()
    );
}

void engine_print_compiled_features(FILE *out) {
    int i;
    if (out == NULL) {
        return;
    }

    fprintf(out, "id name CPW-PL-Engine (%s)\n", PL_VARIANT_NAME);
    fprintf(out, "id author Codex\n");
#if CFG_OPENING_BOOK
    fprintf(out, "option name OwnBook type check default true\n");
    fprintf(out, "option name BookFile type string default %s\n", "c_engine_pl/books/default_openings.txt");
#endif
#if CFG_PONDERING
    fprintf(out, "option name Ponder type check default false\n");
#endif

    for (i = 0; i < PL_SELECTED_OPTION_COUNT; ++i) {
        fprintf(out, "info string feature[%d]=%s\n", i + 1, PL_SELECTED_OPTION_NAMES[i]);
    }

    fprintf(out, "info string repr=real_movegen_search_eval\n");
}
