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
static uint64_t g_knight_attack_masks[64];
static uint64_t g_king_attack_masks[64];
static bool g_backend_maps_ready = false;
static int pop_lsb(uint64_t *bits);

#if CFG_MAGIC_BITBOARDS
#define MAGIC_ROOK_TABLE_SIZE 4096
#define MAGIC_BISHOP_TABLE_SIZE 512

static const int MAGIC_ROOK_BITS[64] = {
    12, 11, 11, 11, 11, 11, 11, 12, 11, 10, 10, 10, 10, 10, 10, 11,
    11, 10, 10, 10, 10, 10, 10, 11, 11, 10, 10, 10, 10, 10, 10, 11,
    11, 10, 10, 10, 10, 10, 10, 11, 11, 10, 10, 10, 10, 10, 10, 11,
    11, 10, 10, 10, 10, 10, 10, 11, 12, 11, 11, 11, 11, 11, 11, 12
};

static const int MAGIC_BISHOP_BITS[64] = {
    6, 5, 5, 5, 5, 5, 5, 6, 5, 5, 5, 5, 5, 5, 5, 5,
    5, 5, 7, 7, 7, 7, 5, 5, 5, 5, 7, 9, 9, 7, 5, 5,
    5, 5, 7, 9, 9, 7, 5, 5, 5, 5, 7, 7, 7, 7, 5, 5,
    5, 5, 5, 5, 5, 5, 5, 5, 6, 5, 5, 5, 5, 5, 5, 6
};

static const uint64_t MAGIC_ROOK_MAGICS[64] = {
    0x2080021440002084ULL, 0x8140100040002000ULL, 0x0200082080120040ULL, 0x0200041040200a00ULL,
    0x828018001400800aULL, 0x1180040002000b80ULL, 0x0200440200010088ULL, 0x0200088044090026ULL,
    0x0100802080004004ULL, 0x2408c00140201001ULL, 0x0030801000802000ULL, 0x8080801000800800ULL,
    0x0002800800040080ULL, 0x0100800400800200ULL, 0x1001800100800a00ULL, 0x2002000049008224ULL,
    0x0080004000200044ULL, 0x0110014000c02000ULL, 0x0210010100200040ULL, 0x10001200400a0020ULL,
    0x0004008006800800ULL, 0x0148808002000400ULL, 0x8004808002000100ULL, 0x0808820004912344ULL,
    0x0000400080208000ULL, 0xc040030500458020ULL, 0x0002100480200080ULL, 0x0012200900100102ULL,
    0x0000080080800400ULL, 0x0182000280040080ULL, 0x009c484400621110ULL, 0x00a0090200048064ULL,
    0x0000844004800020ULL, 0x0002201001400044ULL, 0x0000100080802000ULL, 0x0028080080801006ULL,
    0x0001b100c5002800ULL, 0x002a001002000408ULL, 0x808a000102000804ULL, 0x8004210042000084ULL,
    0x0400208040008012ULL, 0x1200201000404000ULL, 0x0010008020068013ULL, 0x8203001000210009ULL,
    0x0042080100110005ULL, 0x482c008002008004ULL, 0x0040022891040030ULL, 0x0101008044020001ULL,
    0x0000801040290100ULL, 0x6010004000200040ULL, 0x2001012002411900ULL, 0x0001002008100100ULL,
    0x8e08040082080080ULL, 0x0014008022000480ULL, 0x8880410208100400ULL, 0x9000090c04894200ULL,
    0x448a408101201602ULL, 0x804220520084c102ULL, 0x8812002080081042ULL, 0x0c060020041040caULL,
    0x80820060980450b2ULL, 0x0009000400080201ULL, 0x0002215210088804ULL, 0x100c040080210042ULL
};

static const uint64_t MAGIC_BISHOP_MAGICS[64] = {
    0x3010101081040420ULL, 0x00a0188105002400ULL, 0x2404082081080800ULL, 0x8504042680040480ULL,
    0x00011040c0000004ULL, 0x02648a10c0000802ULL, 0x000a008420080580ULL, 0x4142010101012000ULL,
    0x4000302052040062ULL, 0x0000101009211022ULL, 0x0860500502012800ULL, 0x0104022082004400ULL,
    0x000011114000c002ULL, 0x1000808804400030ULL, 0x1010020701284000ULL, 0x0000061100921004ULL,
    0x0020444005040090ULL, 0xc06005440c8c2040ULL, 0x0028021000284014ULL, 0x6004000824001080ULL,
    0x2001002820085290ULL, 0x208603a888040200ULL, 0x0404000061041022ULL, 0x000200404a640400ULL,
    0x0020480104282801ULL, 0x82410801a0888108ULL, 0x0400904042040400ULL, 0x0008080010202020ULL,
    0x0001010000104000ULL, 0x0804044108080a00ULL, 0x0820808984122800ULL, 0x0200410062150100ULL,
    0x2024024000210480ULL, 0x4101412841200810ULL, 0x6021004100081802ULL, 0x1002020080080080ULL,
    0x00400080211a0020ULL, 0x12040800200a00a0ULL, 0x081000b200008220ULL, 0x0068008081422222ULL,
    0x0858080404121080ULL, 0x04014110a8291000ULL, 0x0060210040408802ULL, 0x2c00022214000800ULL,
    0x8140400812010040ULL, 0x04040c8801100200ULL, 0x090830010a083069ULL, 0x1008010408280891ULL,
    0x21240a0230041024ULL, 0x0141410401e00010ULL, 0x00002200a4042000ULL, 0x800001108404000aULL,
    0x010a081082022210ULL, 0x0100202012908804ULL, 0x0004082208120040ULL, 0x4008020c004a1100ULL,
    0x2024420804020202ULL, 0x8004204110901000ULL, 0x0048000180482800ULL, 0x8010800c10420200ULL,
    0x0008802011820204ULL, 0x0800003012100442ULL, 0x0a4024600a440100ULL, 0x4810690125120200ULL
};

static uint64_t g_magic_rook_masks[64];
static uint64_t g_magic_bishop_masks[64];
static uint64_t g_magic_rook_attacks[64][MAGIC_ROOK_TABLE_SIZE];
static uint64_t g_magic_bishop_attacks[64][MAGIC_BISHOP_TABLE_SIZE];
static bool g_magic_tables_ready = false;
#endif

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

static inline int piece_type_index(int piece) {
    int abs_piece = piece_abs(piece);
    return abs_piece >= WP && abs_piece <= WK ? abs_piece - 1 : -1;
}

static uint64_t attack_mask_from_offsets(int sq, const int *offsets, int count, int max_file_delta) {
    uint64_t mask = 0ULL;
    int from_file = file_of(sq);
    int i;

    for (i = 0; i < count; ++i) {
        int to = sq + offsets[i];
        if (!on_board64(to)) {
            continue;
        }
        if (abs(file_of(to) - from_file) > max_file_delta) {
            continue;
        }
        mask |= square_bb(to);
    }

    return mask;
}

#if CFG_PIECE_LISTS
static int king_square_from_piece_lists(const EngineState *state, int side) {
    int count;

    if (state == NULL || side < WHITE || side > BLACK) {
        return -1;
    }

    count = state->piece_list_counts[side][5];
    if (count <= 0) {
        return -1;
    }
    return state->piece_list_squares[side][5][0];
}

static int collect_piece_list_squares(const EngineState *state, int side, int squares[32]) {
    int total = 0;
    int piece_index;
    int i;

    if (state == NULL || squares == NULL || side < WHITE || side > BLACK) {
        return 0;
    }

    for (piece_index = 0; piece_index < 6; ++piece_index) {
        int count = state->piece_list_counts[side][piece_index];
        for (i = 0; i < count && total < 32; ++i) {
            squares[total++] = state->piece_list_squares[side][piece_index][i];
        }
    }

    return total;
}
#endif

#if CFG_MAGIC_BITBOARDS
static uint64_t rook_mask_magic(int sq) {
    uint64_t result = 0ULL;
    int rank = rank_of(sq);
    int file = file_of(sq);
    int r;
    int f;

    for (r = rank + 1; r <= 6; ++r) {
        result |= square_bb(file + r * 8);
    }
    for (r = rank - 1; r >= 1; --r) {
        result |= square_bb(file + r * 8);
    }
    for (f = file + 1; f <= 6; ++f) {
        result |= square_bb(f + rank * 8);
    }
    for (f = file - 1; f >= 1; --f) {
        result |= square_bb(f + rank * 8);
    }
    return result;
}

static uint64_t bishop_mask_magic(int sq) {
    uint64_t result = 0ULL;
    int rank = rank_of(sq);
    int file = file_of(sq);
    int r;
    int f;

    for (r = rank + 1, f = file + 1; r <= 6 && f <= 6; ++r, ++f) {
        result |= square_bb(f + r * 8);
    }
    for (r = rank + 1, f = file - 1; r <= 6 && f >= 1; ++r, --f) {
        result |= square_bb(f + r * 8);
    }
    for (r = rank - 1, f = file + 1; r >= 1 && f <= 6; --r, ++f) {
        result |= square_bb(f + r * 8);
    }
    for (r = rank - 1, f = file - 1; r >= 1 && f >= 1; --r, --f) {
        result |= square_bb(f + r * 8);
    }
    return result;
}

static uint64_t rook_attacks_on_the_fly(int sq, uint64_t blockers) {
    uint64_t result = 0ULL;
    int rank = rank_of(sq);
    int file = file_of(sq);
    int r;
    int f;

    for (r = rank + 1; r <= 7; ++r) {
        int to = file + r * 8;
        result |= square_bb(to);
        if ((blockers & square_bb(to)) != 0ULL) {
            break;
        }
    }
    for (r = rank - 1; r >= 0; --r) {
        int to = file + r * 8;
        result |= square_bb(to);
        if ((blockers & square_bb(to)) != 0ULL) {
            break;
        }
    }
    for (f = file + 1; f <= 7; ++f) {
        int to = f + rank * 8;
        result |= square_bb(to);
        if ((blockers & square_bb(to)) != 0ULL) {
            break;
        }
    }
    for (f = file - 1; f >= 0; --f) {
        int to = f + rank * 8;
        result |= square_bb(to);
        if ((blockers & square_bb(to)) != 0ULL) {
            break;
        }
    }

    return result;
}

static uint64_t bishop_attacks_on_the_fly(int sq, uint64_t blockers) {
    uint64_t result = 0ULL;
    int rank = rank_of(sq);
    int file = file_of(sq);
    int r;
    int f;

    for (r = rank + 1, f = file + 1; r <= 7 && f <= 7; ++r, ++f) {
        int to = f + r * 8;
        result |= square_bb(to);
        if ((blockers & square_bb(to)) != 0ULL) {
            break;
        }
    }
    for (r = rank + 1, f = file - 1; r <= 7 && f >= 0; ++r, --f) {
        int to = f + r * 8;
        result |= square_bb(to);
        if ((blockers & square_bb(to)) != 0ULL) {
            break;
        }
    }
    for (r = rank - 1, f = file + 1; r >= 0 && f <= 7; --r, ++f) {
        int to = f + r * 8;
        result |= square_bb(to);
        if ((blockers & square_bb(to)) != 0ULL) {
            break;
        }
    }
    for (r = rank - 1, f = file - 1; r >= 0 && f >= 0; --r, --f) {
        int to = f + r * 8;
        result |= square_bb(to);
        if ((blockers & square_bb(to)) != 0ULL) {
            break;
        }
    }

    return result;
}

static void init_magic_tables(void) {
    int sq;

    if (g_magic_tables_ready) {
        return;
    }

    for (sq = 0; sq < 64; ++sq) {
        int rook_variations = 1 << MAGIC_ROOK_BITS[sq];
        int bishop_variations = 1 << MAGIC_BISHOP_BITS[sq];
        int i;

        g_magic_rook_masks[sq] = rook_mask_magic(sq);
        g_magic_bishop_masks[sq] = bishop_mask_magic(sq);

        for (i = 0; i < rook_variations; ++i) {
            uint64_t blockers = 0ULL;
            uint64_t mask = g_magic_rook_masks[sq];
            int bit = 0;
            while (mask != 0ULL) {
                int blocker_sq = pop_lsb(&mask);
                if ((i & (1 << bit)) != 0) {
                    blockers |= square_bb(blocker_sq);
                }
                bit += 1;
            }
            g_magic_rook_attacks[sq][(int)(((blockers & g_magic_rook_masks[sq]) * MAGIC_ROOK_MAGICS[sq]) >> (64 - MAGIC_ROOK_BITS[sq]))] =
                rook_attacks_on_the_fly(sq, blockers);
        }

        for (i = 0; i < bishop_variations; ++i) {
            uint64_t blockers = 0ULL;
            uint64_t mask = g_magic_bishop_masks[sq];
            int bit = 0;
            while (mask != 0ULL) {
                int blocker_sq = pop_lsb(&mask);
                if ((i & (1 << bit)) != 0) {
                    blockers |= square_bb(blocker_sq);
                }
                bit += 1;
            }
            g_magic_bishop_attacks[sq][(int)(((blockers & g_magic_bishop_masks[sq]) * MAGIC_BISHOP_MAGICS[sq]) >> (64 - MAGIC_BISHOP_BITS[sq]))] =
                bishop_attacks_on_the_fly(sq, blockers);
        }
    }

    g_magic_tables_ready = true;
}

static inline uint64_t rook_attacks_magic(int sq, uint64_t occupancy) {
    uint64_t blockers = occupancy & g_magic_rook_masks[sq];
    return g_magic_rook_attacks[sq][(int)((blockers * MAGIC_ROOK_MAGICS[sq]) >> (64 - MAGIC_ROOK_BITS[sq]))];
}

static inline uint64_t bishop_attacks_magic(int sq, uint64_t occupancy) {
    uint64_t blockers = occupancy & g_magic_bishop_masks[sq];
    return g_magic_bishop_attacks[sq][(int)((blockers * MAGIC_BISHOP_MAGICS[sq]) >> (64 - MAGIC_BISHOP_BITS[sq]))];
}
#endif

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
        g_knight_attack_masks[sq] = attack_mask_from_offsets(sq, KNIGHT_OFFSETS_64, 8, 2);
        g_king_attack_masks[sq] = attack_mask_from_offsets(sq, KING_OFFSETS_64, 8, 1);
    }

#if CFG_MAGIC_BITBOARDS
    init_magic_tables();
#endif
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
#if CFG_PIECE_LISTS
    int king_sq = king_square_from_piece_lists(state, side);
    if (king_sq >= 0) {
        return king_sq;
    }
#endif
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
#if CFG_PIECE_LISTS
    int king_sq = king_square_from_piece_lists(state, side);
    if (king_sq >= 0) {
        return king_sq;
    }
#endif
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
#if CFG_PIECE_LISTS
    int king_sq = king_square_from_piece_lists(state, side);
    if (king_sq >= 0) {
        return king_sq;
    }
#endif
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
    uint64_t occ;
    uint64_t target;
    uint64_t knights;
    uint64_t kings;
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

    knights = state->bb_pieces[attacker_side == WHITE ? 1 : 7];
    if ((g_knight_attack_masks[sq] & knights) != 0ULL) {
        return true;
    }

#if CFG_MAGIC_BITBOARDS
    {
        uint64_t bishop_like = state->bb_pieces[attacker_side == WHITE ? 2 : 8] | state->bb_pieces[attacker_side == WHITE ? 4 : 10];
        if ((bishop_attacks_magic(sq, occ) & bishop_like) != 0ULL) {
            return true;
        }
    }
    {
        uint64_t rook_like = state->bb_pieces[attacker_side == WHITE ? 3 : 9] | state->bb_pieces[attacker_side == WHITE ? 4 : 10];
        if ((rook_attacks_magic(sq, occ) & rook_like) != 0ULL) {
            return true;
        }
    }
#else
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
#endif

    kings = state->bb_pieces[attacker_side == WHITE ? 5 : 11];
    if ((g_king_attack_masks[sq] & kings) != 0ULL) {
        return true;
    }

    return false;
}

static ENGINE_MAYBE_UNUSED void generate_moves_mailbox(const EngineState *state, EngineMoveList *list, bool captures_only) {
    int side = state->side_to_move;
    int idx;
#if CFG_PIECE_LISTS
    int squares[32];
    int square_count = collect_piece_list_squares(state, side, squares);
#else
    int squares[64];
    int square_count = 64;
    for (idx = 0; idx < 64; ++idx) {
        squares[idx] = idx;
    }
#endif

    list->count = 0;

    for (idx = 0; idx < square_count; ++idx) {
        int sq = squares[idx];
        int piece = state->board[sq];
        int abs_piece;
        int i;

        if (piece == EMPTY || piece_side(piece) != side) {
            continue;
        }

        abs_piece = piece_abs(piece);
        if (abs_piece == WP) {
            int forward = side == WHITE ? 8 : -8;
            int start_rank = side == WHITE ? 1 : 6;
            int promote_rank = side == WHITE ? 6 : 1;
            int to = sq + forward;

            if (!captures_only && on_board64(to) && state->board[to] == EMPTY) {
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

            for (i = 0; i < 2; ++i) {
                int delta = side == WHITE ? (i == 0 ? 7 : 9) : (i == 0 ? -9 : -7);
                int capture_sq = sq + delta;
                if (!on_board64(capture_sq) || abs(file_of(capture_sq) - file_of(sq)) != 1) {
                    continue;
                }
                if (state->board[capture_sq] != EMPTY && piece_side(state->board[capture_sq]) != side) {
                    EngineMove mv;
                    memset(&mv, 0, sizeof(mv));
                    mv.from = (uint8_t)sq;
                    mv.to = (uint8_t)capture_sq;
                    mv.flags = FLAG_CAPTURE;
                    if (rank_of(sq) == promote_rank) {
                        mv.promotion = 4;
                        mv.flags |= FLAG_PROMOTION;
                    }
                    move_list_push(list, mv);
                }
            }
            continue;
        }

        if (abs_piece == WN || abs_piece == WK) {
            const int *deltas = abs_piece == WN ? KNIGHT_OFFSETS_64 : KING_OFFSETS_64;
            for (i = 0; i < 8; ++i) {
                int to = sq + deltas[i];
                int target;
                if (!on_board64(to)) {
                    continue;
                }
                if ((abs_piece == WN && abs(file_of(to) - file_of(sq)) > 2) ||
                    (abs_piece == WK && abs(file_of(to) - file_of(sq)) > 1)) {
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
                        mv.flags = FLAG_CAPTURE;
                    }
                    move_list_push(list, mv);
                }
            }
            continue;
        }

        {
            const int *deltas = NULL;
            int delta_count = 0;
            if (abs_piece == WB) {
                deltas = BISHOP_OFFSETS_64;
                delta_count = 4;
            } else if (abs_piece == WR) {
                deltas = ROOK_OFFSETS_64;
                delta_count = 4;
            } else if (abs_piece == WQ) {
                static const int queen_offsets[8] = {9, 7, -9, -7, 8, -8, 1, -1};
                deltas = queen_offsets;
                delta_count = 8;
            }
            if (deltas == NULL) {
                continue;
            }

            for (i = 0; i < delta_count; ++i) {
                int delta = deltas[i];
                int to = sq + delta;
                while (step_preserves_geometry(to - delta, to, delta)) {
                    int target = state->board[to];
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
        }
    }

    add_special_moves(state, list, captures_only);
}

static ENGINE_MAYBE_UNUSED void generate_moves_0x88(const EngineState *state, EngineMoveList *list, bool captures_only) {
    int idx;
#if CFG_PIECE_LISTS
    int squares[32];
    int square_count = collect_piece_list_squares(state, state->side_to_move, squares);
#else
    int squares[128];
    int square_count = 0;
    int sq;
    for (sq = 0; sq < 128; ++sq) {
        if ((sq & 0x88) == 0) {
            squares[square_count++] = sq;
        }
    }
#endif

    list->count = 0;
    for (idx = 0; idx < square_count; ++idx) {
        int piece;
#if CFG_PIECE_LISTS
        int sq = g_sq64_to_0x88[squares[idx]];
#else
        int sq = squares[idx];
#endif
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
    int idx;
#if CFG_PIECE_LISTS
    int squares[32];
    int square_count = collect_piece_list_squares(state, state->side_to_move, squares);
#else
    int squares[120];
    int square_count = 0;
    int sq;
    for (sq = 0; sq < 120; ++sq) {
        if (state->board_120[sq] != OFFBOARD_120) {
            squares[square_count++] = sq;
        }
    }
#endif

    list->count = 0;
    for (idx = 0; idx < square_count; ++idx) {
#if CFG_PIECE_LISTS
        int sq = g_sq64_to_120[squares[idx]];
#else
        int sq = squares[idx];
#endif
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
        uint64_t targets = g_knight_attack_masks[from] & ~own_occ;
        if (captures_only) {
            targets &= opp_occ;
        }
        while (targets != 0ULL) {
            int to = pop_lsb(&targets);
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

    pieces = state->bb_pieces[side == WHITE ? 2 : 8];
    while (pieces != 0ULL) {
        int from = pop_lsb(&pieces);
#if CFG_MAGIC_BITBOARDS
        uint64_t targets;
        targets = bishop_attacks_magic(from, all_occ) & ~own_occ;
        if (captures_only) {
            targets &= opp_occ;
        }
        while (targets != 0ULL) {
            int to = pop_lsb(&targets);
            EngineMove mv;
            memset(&mv, 0, sizeof(mv));
            mv.from = (uint8_t)from;
            mv.to = (uint8_t)to;
            if ((opp_occ & square_bb(to)) != 0ULL) {
                mv.flags = FLAG_CAPTURE;
            }
            move_list_push(list, mv);
        }
#else
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
#endif
    }

    pieces = state->bb_pieces[side == WHITE ? 3 : 9];
    while (pieces != 0ULL) {
        int from = pop_lsb(&pieces);
#if CFG_MAGIC_BITBOARDS
        uint64_t targets;
        targets = rook_attacks_magic(from, all_occ) & ~own_occ;
        if (captures_only) {
            targets &= opp_occ;
        }
        while (targets != 0ULL) {
            int to = pop_lsb(&targets);
            EngineMove mv;
            memset(&mv, 0, sizeof(mv));
            mv.from = (uint8_t)from;
            mv.to = (uint8_t)to;
            if ((opp_occ & square_bb(to)) != 0ULL) {
                mv.flags = FLAG_CAPTURE;
            }
            move_list_push(list, mv);
        }
#else
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
#endif
    }

    pieces = state->bb_pieces[side == WHITE ? 4 : 10];
    while (pieces != 0ULL) {
        int from = pop_lsb(&pieces);
#if CFG_MAGIC_BITBOARDS
        uint64_t targets;
        targets = (rook_attacks_magic(from, all_occ) | bishop_attacks_magic(from, all_occ)) & ~own_occ;
        if (captures_only) {
            targets &= opp_occ;
        }
        while (targets != 0ULL) {
            int to = pop_lsb(&targets);
            EngineMove mv;
            memset(&mv, 0, sizeof(mv));
            mv.from = (uint8_t)from;
            mv.to = (uint8_t)to;
            if ((opp_occ & square_bb(to)) != 0ULL) {
                mv.flags = FLAG_CAPTURE;
            }
            move_list_push(list, mv);
        }
#else
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
#endif
    }

    pieces = state->bb_pieces[side == WHITE ? 5 : 11];
    while (pieces != 0ULL) {
        int from = pop_lsb(&pieces);
        uint64_t targets = g_king_attack_masks[from] & ~own_occ;
        if (captures_only) {
            targets &= opp_occ;
        }
        while (targets != 0ULL) {
            int to = pop_lsb(&targets);
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

    add_special_moves(state, list, captures_only);
}

void engine_sync_backend_state(EngineState *state) {
    int sq;

    if (state == NULL) {
        return;
    }

    init_backend_maps();
#if CFG_0X88
    memset(state->board_0x88, 0, sizeof(state->board_0x88));
#endif
#if CFG_BITBOARDS
    memset(state->bb_pieces, 0, sizeof(state->bb_pieces));
    state->bb_white_occ = 0ULL;
    state->bb_black_occ = 0ULL;
#endif
    state->king_square[WHITE] = -1;
    state->king_square[BLACK] = -1;
#if CFG_PIECE_LISTS
    memset(state->piece_list_squares, 0, sizeof(state->piece_list_squares));
    memset(state->piece_list_counts, 0, sizeof(state->piece_list_counts));
#endif
#if CFG_10X12_BOARD
    for (sq = 0; sq < 120; ++sq) {
        state->board_120[sq] = OFFBOARD_120;
    }
#endif

    for (sq = 0; sq < 64; ++sq) {
        int piece = state->board[sq];
        
#if CFG_0X88
        state->board_0x88[g_sq64_to_0x88[sq]] = piece;
#endif
#if CFG_10X12_BOARD
        state->board_120[g_sq64_to_120[sq]] = piece;
#endif

        if (piece == EMPTY) {
            continue;
        }

#if CFG_BITBOARDS
        {
            int idx;
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
#endif

#if CFG_PIECE_LISTS
        {
            int side = piece_side(piece);
            int type = piece_type_index(piece);
            if (side >= WHITE && side <= BLACK && type >= 0) {
                int count = state->piece_list_counts[side][type];
                if (count < ENGINE_MAX_PIECES_PER_TYPE) {
                    state->piece_list_squares[side][type][count] = sq;
                    state->piece_list_counts[side][type] = (uint8_t)(count + 1);
                }
            }
        }
#endif
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
#elif CFG_10X12_BOARD
    return find_king_square_120(state, side);
#elif CFG_MAILBOX
    return find_king_square_default(state, side);
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
#elif CFG_10X12_BOARD
    return is_square_attacked_120(state, sq, attacker_side);
#elif CFG_MAILBOX
    return is_square_attacked_default(state, sq, attacker_side);
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
#elif CFG_10X12_BOARD
    generate_moves_120(state, list, captures_only);
#elif CFG_MAILBOX
    generate_moves_mailbox(state, list, captures_only);
#else
    (void)captures_only;
#endif
}

const char *engine_board_backend_name(void) {
#if CFG_BITBOARDS
#if CFG_MAGIC_BITBOARDS
    return "MagicBitboards";
#else
    return "Bitboards";
#endif
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
