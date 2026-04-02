#ifndef C_ENGINE_PL_ENGINE_BACKEND_INTERNAL_H
#define C_ENGINE_PL_ENGINE_BACKEND_INTERNAL_H

#include <stdbool.h>

#include "engine.h"

void engine_sync_backend_state(EngineState *state);
int engine_backend_find_king_square(const EngineState *state, int side);
bool engine_backend_is_square_attacked(const EngineState *state, int sq, int attacker_side);
void engine_backend_generate_pseudo_moves(const EngineState *state, EngineMoveList *list, bool captures_only);
const char *engine_board_backend_name(void);

#endif
