#ifndef C_ENGINE_PL_ENGINE_EVAL_INTERNAL_H
#define C_ENGINE_PL_ENGINE_EVAL_INTERNAL_H

#include <stdbool.h>
#include <stdint.h>

#include "engine.h"

typedef struct EngineInstrumentation {
    uint64_t tt_probes;
    uint64_t tt_hits;
    uint64_t tt_cutoff_hits;
    uint64_t tt_stores;
    uint64_t eval_calls;
    uint64_t eval_cache_hits;
    uint64_t movegen_calls;
    uint64_t attack_calls;
    uint64_t beta_cutoffs;
} EngineInstrumentation;

int engine_evaluate_position_internal(EngineState *state);
int engine_score_capture_internal(const EngineState *state, const EngineMove *move);
void engine_reset_evaluation_tables(void);
const char *engine_eval_profile_name(void);

uint64_t engine_state_key_internal(const EngineState *state);
uint64_t engine_pawn_key_internal(const EngineState *state);
int engine_find_king_square_internal(const EngineState *state, int side);
bool engine_is_square_attacked_internal(const EngineState *state, int sq, int attacker_side);
void engine_generate_pseudo_moves_internal(const EngineState *state, EngineMoveList *list, bool captures_only);
void engine_reset_instrumentation_internal(void);
EngineInstrumentation engine_get_instrumentation_internal(void);
void engine_note_eval_call_internal(void);
void engine_note_eval_cache_hit_internal(void);
void engine_note_movegen_call_internal(void);
void engine_note_attack_call_internal(void);
void engine_note_tt_probe_internal(bool hit, bool cutoff_hit);
void engine_note_tt_store_internal(void);
void engine_note_beta_cutoff_internal(void);

#endif
