#ifndef C_ENGINE_PL_ENGINE_SEARCH_INTERNAL_H
#define C_ENGINE_PL_ENGINE_SEARCH_INTERNAL_H

#include <stdbool.h>
#include <stdint.h>

#include "engine.h"

#define ENGINE_WHITE 0
#define ENGINE_BLACK 1

#define ENGINE_INF 30000
#define ENGINE_MATE 29000

typedef struct Undo {
    int captured;
    int captured_square;
    int moved_piece;
    int castling_rights;
    int en_passant_square;
    int halfmove_clock;
    int fullmove_number;
    int history_count;
} Undo;

typedef struct EngineSearchOps {
    int (*evaluate_position)(EngineState *state);
    bool (*in_check)(const EngineState *state, int side);
    int (*repetition_count)(const EngineState *state);
    int64_t (*now_ms)(void);
    void (*generate_moves)(const EngineState *state, EngineMoveList *list, bool captures_only);
    bool (*make_move)(EngineState *state, const EngineMove *move, Undo *undo);
    void (*unmake_move)(EngineState *state, const EngineMove *move, const Undo *undo);
    uint64_t (*state_key)(const EngineState *state);
    void (*order_moves)(EngineState *state, EngineMoveList *list, int ply, const EngineMove *hash_move);
    int (*tt_probe)(uint64_t key, int depth, int alpha, int beta, int *score, EngineMove *best_move);
    void (*tt_store)(uint64_t key, int depth, int score, int flag, const EngineMove *best_move);
    bool (*parse_move_uci)(const char *text, EngineMove *out);
    bool (*find_move_in_list)(const EngineMoveList *list, const EngineMove *needle, EngineMove *matched);
    void (*move_to_front)(EngineMoveList *list, const EngineMove *move);
    void (*record_beta_cutoff)(EngineState *state, int ply, int depth, const EngineMove *move);
} EngineSearchOps;

const EngineSearchOps *engine_get_search_ops(void);
const char *engine_search_core_name(void);

#endif
