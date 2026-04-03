#ifndef C_ENGINE_PL_ENGINE_EVAL_INTERNAL_H
#define C_ENGINE_PL_ENGINE_EVAL_INTERNAL_H

#include <stdbool.h>
#include <stdint.h>

#include "engine.h"

int engine_evaluate_position_internal(EngineState *state);
int engine_score_capture_internal(const EngineState *state, const EngineMove *move);
void engine_reset_evaluation_tables(void);
const char *engine_eval_profile_name(void);

uint64_t engine_state_key_internal(const EngineState *state);
int engine_find_king_square_internal(const EngineState *state, int side);
bool engine_is_square_attacked_internal(const EngineState *state, int sq, int attacker_side);
void engine_generate_pseudo_moves_internal(const EngineState *state, EngineMoveList *list, bool captures_only);

#endif
