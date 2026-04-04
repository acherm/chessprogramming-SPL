#ifndef C_ENGINE_PL_ENGINE_H
#define C_ENGINE_PL_ENGINE_H

#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>

#define ENGINE_MAX_MOVES 256
#define ENGINE_MAX_PLY 128
#define ENGINE_MAX_FEN 128
#define ENGINE_MAX_HISTORY 512
#define ENGINE_MAX_PIECES_PER_TYPE 16
#define ENGINE_MAX_BOOK_PATH 512

typedef struct EngineMove {
    uint8_t from;
    uint8_t to;
    uint8_t promotion; /* 0 none, 1 knight, 2 bishop, 3 rook, 4 queen */
    uint8_t flags;
    int score;
} EngineMove;

typedef struct EngineMoveList {
    EngineMove moves[ENGINE_MAX_MOVES];
    int count;
} EngineMoveList;

typedef struct EngineSearchResult {
    EngineMove best_move;
    int score_cp;
    int depth;
    uint64_t nodes;
    bool has_move;
} EngineSearchResult;

typedef struct EngineState {
    int board[64];
    int board_0x88[128];
    int board_120[120];
    uint64_t bb_pieces[12];
    uint64_t bb_white_occ;
    uint64_t bb_black_occ;
    int piece_list_squares[2][6][ENGINE_MAX_PIECES_PER_TYPE];
    uint8_t piece_list_counts[2][6];
    int side_to_move; /* 0 white, 1 black */
    int castling_rights; /* bitmask: 1 WK, 2 WQ, 4 BK, 8 BQ */
    int en_passant_square; /* -1 if none, otherwise 0..63 */
    int halfmove_clock;
    int fullmove_number;
    int plies_from_start;
    uint64_t position_history[ENGINE_MAX_HISTORY];
    int history_count;

    bool pondering_enabled;
    bool opening_book_enabled;
    int max_depth_hint;
    int movetime_ms;

    uint64_t nodes;
    bool stop;
    bool exact_movetime;
    int64_t soft_deadline_ms;
    int64_t deadline_ms;

    char last_fen[ENGINE_MAX_FEN];
    char opening_book_path[ENGINE_MAX_BOOK_PATH];
} EngineState;

void engine_init(EngineState *state);
int engine_set_startpos(EngineState *state);
int engine_set_fen(EngineState *state, const char *fen);
int engine_apply_move_uci(EngineState *state, const char *move_uci);
int engine_generate_legal_moves(EngineState *state, EngineMoveList *list);
uint64_t engine_perft(EngineState *state, int depth);
int engine_static_eval(EngineState *state);
EngineSearchResult engine_search(EngineState *state, int max_depth, int movetime_ms);
void engine_move_to_uci(const EngineMove *move, char out[6]);
void engine_variant_summary(char *out, size_t out_size);
void engine_print_compiled_features(FILE *out);

#endif
