#include "engine_search_internal.h"

#include <stdio.h>
#include <string.h>

#include "generated/variant_config.h"

#define QUIESCENCE_MAX_DEPTH 8
#define SEARCH_FLAG_CAPTURE 1

typedef enum SearchWindowMode {
    SEARCH_WINDOW_NONE = 0,
    SEARCH_WINDOW_ALPHA_BETA = 1,
    SEARCH_WINDOW_PVS = 2,
} SearchWindowMode;

static const EngineSearchOps *search_ops(void) {
    return engine_get_search_ops();
}

#if CFG_DELTA_PRUNING
static const int SEARCH_PIECE_VALUE[7] = {0, 100, 320, 330, 500, 900, 0};

static int search_piece_abs(int piece) {
    return piece >= 0 ? piece : -piece;
}
#endif

static bool search_use_negamax(void) {
#if CFG_NEGAMAX
    return true;
#else
    return false;
#endif
}

static SearchWindowMode search_window_mode(void) {
#if CFG_PRINCIPAL_VARIATION_SEARCH && CFG_ALPHA_BETA
    return SEARCH_WINDOW_PVS;
#elif CFG_ALPHA_BETA
    return SEARCH_WINDOW_ALPHA_BETA;
#else
    return SEARCH_WINDOW_NONE;
#endif
}

static int evaluate_absolute(EngineState *state) {
    int relative = search_ops()->evaluate_position(state);
    return state->side_to_move == ENGINE_WHITE ? relative : -relative;
}

static int mate_score_relative(int ply) {
    return -ENGINE_MATE + ply;
}

static int mate_score_absolute(const EngineState *state, int ply) {
    return state->side_to_move == ENGINE_WHITE ? (-ENGINE_MATE + ply) : (ENGINE_MATE - ply);
}

static bool search_hit_deadline(EngineState *state) {
    if ((state->nodes & 1023ULL) == 0ULL && state->deadline_ms > 0 && search_ops()->now_ms() >= state->deadline_ms) {
        state->stop = true;
        return true;
    }
    return false;
}

static bool search_prepare_child(EngineState *state, const EngineMove *move, Undo *undo, EngineState *snapshot) {
#if CFG_COPY_MAKE || !CFG_UNMAKE_MOVE
    *snapshot = *state;
#else
    (void)snapshot;
#endif
    if (!search_ops()->make_move(state, move, undo)) {
        return false;
    }
    if (search_ops()->in_check(state, state->side_to_move ^ 1)) {
#if CFG_COPY_MAKE || !CFG_UNMAKE_MOVE
        *state = *snapshot;
#else
        search_ops()->unmake_move(state, move, undo);
#endif
        return false;
    }
    return true;
}

static void search_restore_child(EngineState *state, const EngineMove *move, const Undo *undo, const EngineState *snapshot, uint64_t nodes_after, bool stop_after) {
#if CFG_COPY_MAKE || !CFG_UNMAKE_MOVE
    *state = *snapshot;
    state->nodes = nodes_after;
    state->stop = stop_after;
#else
    search_ops()->unmake_move(state, move, undo);
    (void)nodes_after;
    (void)stop_after;
    (void)snapshot;
#endif
}

static int quiescence_negamax(EngineState *state, int alpha, int beta, int ply, int qdepth) {
    bool side_in_check;
    int stand_pat;
    EngineMoveList list;
    int legal_moves = 0;
    int i;

    if (state->stop) {
        return alpha;
    }

#if CFG_FIFTY_MOVE_RULE
    if (state->halfmove_clock >= 100) {
        return 0;
    }
#endif

#if CFG_THREEFOLD_REPETITION
    if (search_ops()->repetition_count(state) >= 2) {
        return 0;
    }
#endif

    side_in_check = search_ops()->in_check(state, state->side_to_move);
    if (side_in_check) {
        stand_pat = mate_score_relative(ply);
    } else {
        stand_pat = search_ops()->evaluate_position(state);
        if (stand_pat >= beta) {
            return beta;
        }
        if (stand_pat > alpha) {
            alpha = stand_pat;
        }
    }

    if (qdepth >= QUIESCENCE_MAX_DEPTH) {
        return alpha;
    }

    search_ops()->generate_moves(state, &list, side_in_check ? false : true);
    search_ops()->order_moves(state, &list, ply, NULL);

    for (i = 0; i < list.count; ++i) {
        EngineMove move = list.moves[i];
        Undo undo;
        EngineState snapshot;
        uint64_t nodes_after;
        bool stop_after;
        int score;

#if CFG_DELTA_PRUNING
        if (!side_in_check) {
            int target = state->board[move.to];
            int gain = target == 0 ? 0 : SEARCH_PIECE_VALUE[search_piece_abs(target)];
            if (stand_pat + gain + 80 < alpha) {
                continue;
            }
        }
#endif

        if (!search_prepare_child(state, &move, &undo, &snapshot)) {
            continue;
        }

        legal_moves += 1;
        state->nodes += 1;
        score = -quiescence_negamax(state, -beta, -alpha, ply + 1, qdepth + 1);

        nodes_after = state->nodes;
        stop_after = state->stop;
        search_restore_child(state, &move, &undo, &snapshot, nodes_after, stop_after);

        if (score >= beta) {
            return beta;
        }
        if (score > alpha) {
            alpha = score;
        }
    }

    if (side_in_check && legal_moves == 0) {
        return mate_score_relative(ply);
    }

    return alpha;
}

static int quiescence_minimax(EngineState *state, int alpha, int beta, int ply, int qdepth) {
    bool side_in_check;
    bool maximizing = state->side_to_move == ENGINE_WHITE;
    int stand_pat;
    EngineMoveList list;
    int legal_moves = 0;
    int i;

    if (state->stop) {
        return evaluate_absolute(state);
    }

#if CFG_FIFTY_MOVE_RULE
    if (state->halfmove_clock >= 100) {
        return 0;
    }
#endif

#if CFG_THREEFOLD_REPETITION
    if (search_ops()->repetition_count(state) >= 2) {
        return 0;
    }
#endif

    side_in_check = search_ops()->in_check(state, state->side_to_move);
    if (side_in_check) {
        stand_pat = mate_score_absolute(state, ply);
    } else {
        stand_pat = evaluate_absolute(state);
        if (maximizing) {
            if (stand_pat >= beta) {
                return beta;
            }
            if (stand_pat > alpha) {
                alpha = stand_pat;
            }
        } else {
            if (stand_pat <= alpha) {
                return alpha;
            }
            if (stand_pat < beta) {
                beta = stand_pat;
            }
        }
    }

    if (qdepth >= QUIESCENCE_MAX_DEPTH) {
        return stand_pat;
    }

    search_ops()->generate_moves(state, &list, side_in_check ? false : true);
    search_ops()->order_moves(state, &list, ply, NULL);

    for (i = 0; i < list.count; ++i) {
        EngineMove move = list.moves[i];
        Undo undo;
        EngineState snapshot;
        uint64_t nodes_after;
        bool stop_after;
        int score;

#if CFG_DELTA_PRUNING
        if (!side_in_check) {
            int target = state->board[move.to];
            int gain = target == 0 ? 0 : SEARCH_PIECE_VALUE[search_piece_abs(target)];
            if (maximizing) {
                if (stand_pat + gain + 80 < alpha) {
                    continue;
                }
            } else if (stand_pat - gain - 80 > beta) {
                continue;
            }
        }
#endif

        if (!search_prepare_child(state, &move, &undo, &snapshot)) {
            continue;
        }

        legal_moves += 1;
        state->nodes += 1;
        score = quiescence_minimax(state, alpha, beta, ply + 1, qdepth + 1);

        nodes_after = state->nodes;
        stop_after = state->stop;
        search_restore_child(state, &move, &undo, &snapshot, nodes_after, stop_after);

        if (maximizing) {
            if (score >= beta) {
                return beta;
            }
            if (score > alpha) {
                alpha = score;
            }
        } else {
            if (score <= alpha) {
                return alpha;
            }
            if (score < beta) {
                beta = score;
            }
        }
    }

    if (side_in_check && legal_moves == 0) {
        return mate_score_absolute(state, ply);
    }

    return maximizing ? alpha : beta;
}

static int search_negamax(EngineState *state, int depth, int alpha, int beta, int ply, bool allow_null, SearchWindowMode mode);
static int search_minimax(EngineState *state, int depth, int alpha, int beta, int ply, bool allow_null, SearchWindowMode mode);

static int search_negamax(EngineState *state, int depth, int alpha, int beta, int ply, bool allow_null, SearchWindowMode mode) {
    EngineMoveList list;
    EngineMove best_move;
    EngineMove hash_move;
    int best_score = -ENGINE_INF;
    int alpha_orig = alpha;
    int legal_moves = 0;
    int i;
    int tt_score = 0;
    uint64_t key;
    bool has_hash_move = false;

    if (state->stop) {
        return search_ops()->evaluate_position(state);
    }

#if !CFG_NULL_MOVE_PRUNING
    (void)allow_null;
#endif

#if CFG_FIFTY_MOVE_RULE
    if (state->halfmove_clock >= 100) {
        return 0;
    }
#endif

#if CFG_THREEFOLD_REPETITION
    if (search_ops()->repetition_count(state) >= 2) {
        return 0;
    }
#endif

    if (search_hit_deadline(state)) {
        return search_ops()->evaluate_position(state);
    }

#if CFG_QUIESCENCE_SEARCH
    if (depth <= 0) {
        return quiescence_negamax(state, alpha, beta, ply, 0);
    }
#else
    if (depth <= 0) {
        return search_ops()->evaluate_position(state);
    }
#endif

    key = search_ops()->state_key(state);
    if (mode == SEARCH_WINDOW_NONE) {
        if (search_ops()->tt_probe(key, depth, -ENGINE_INF, ENGINE_INF, &tt_score, &hash_move)) {
            return tt_score;
        }
    } else {
        if (search_ops()->tt_probe(key, depth, alpha, beta, &tt_score, &hash_move)) {
            return tt_score;
        }
#if CFG_HASH_MOVE
        if (search_ops()->tt_probe(key, 0, -ENGINE_INF, ENGINE_INF, &tt_score, &hash_move)) {
            has_hash_move = true;
        }
#endif
    }

#if CFG_RAZORING
    if (mode != SEARCH_WINDOW_NONE && depth == 1 && !search_ops()->in_check(state, state->side_to_move)) {
        int eval = search_ops()->evaluate_position(state);
        if (eval + 120 <= alpha) {
            return quiescence_negamax(state, alpha, beta, ply, 0);
        }
    }
#endif

#if CFG_NULL_MOVE_PRUNING
    if (mode != SEARCH_WINDOW_NONE && allow_null && depth >= 3 && !search_ops()->in_check(state, state->side_to_move)) {
        EngineState tmp = *state;
        int score;
        tmp.side_to_move ^= 1;
        tmp.plies_from_start += 1;
        score = -search_negamax(&tmp, depth - 3, -beta, -beta + 1, ply + 1, false, SEARCH_WINDOW_ALPHA_BETA);
        if (score >= beta) {
            return beta;
        }
    }
#endif

    search_ops()->generate_moves(state, &list, false);
    search_ops()->order_moves(state, &list, ply, has_hash_move ? &hash_move : NULL);
    memset(&best_move, 0, sizeof(best_move));

    for (i = 0; i < list.count; ++i) {
        EngineMove move = list.moves[i];
        Undo undo;
        EngineState snapshot;
        uint64_t nodes_after;
        bool stop_after;
        int score;
        int child_depth = depth - 1;

#if CFG_FUTILITY_PRUNING
        if (mode != SEARCH_WINDOW_NONE && depth == 1 && !(move.flags & SEARCH_FLAG_CAPTURE)) {
            int eval = search_ops()->evaluate_position(state);
            if (eval + 90 <= alpha) {
                continue;
            }
        }
#endif

#if CFG_LATE_MOVE_REDUCTIONS
        if (mode != SEARCH_WINDOW_NONE && depth >= 3 && i >= 4 && !(move.flags & SEARCH_FLAG_CAPTURE) && !search_ops()->in_check(state, state->side_to_move)) {
            child_depth -= 1;
        }
#endif

        if (!search_prepare_child(state, &move, &undo, &snapshot)) {
            continue;
        }

        legal_moves += 1;
        state->nodes += 1;

        if (mode == SEARCH_WINDOW_PVS) {
            if (legal_moves == 1) {
                score = -search_negamax(state, child_depth, -beta, -alpha, ply + 1, true, mode);
            } else {
                score = -search_negamax(state, child_depth, -alpha - 1, -alpha, ply + 1, true, SEARCH_WINDOW_ALPHA_BETA);
                if (score > alpha && score < beta) {
                    score = -search_negamax(state, child_depth, -beta, -alpha, ply + 1, true, mode);
                }
            }
        } else if (mode == SEARCH_WINDOW_ALPHA_BETA) {
            score = -search_negamax(state, child_depth, -beta, -alpha, ply + 1, true, mode);
        } else {
            score = -search_negamax(state, child_depth, -ENGINE_INF, ENGINE_INF, ply + 1, true, mode);
        }

        nodes_after = state->nodes;
        stop_after = state->stop;
        search_restore_child(state, &move, &undo, &snapshot, nodes_after, stop_after);

        if (state->stop) {
            return mode == SEARCH_WINDOW_NONE ? best_score : alpha;
        }

        if (score > best_score) {
            best_score = score;
            best_move = move;
        }

        if (mode != SEARCH_WINDOW_NONE) {
            if (score > alpha) {
                alpha = score;
            }
            if (alpha >= beta) {
                search_ops()->record_beta_cutoff(state, ply, depth, &move);
                break;
            }
        }
    }

    if (legal_moves == 0) {
        if (search_ops()->in_check(state, state->side_to_move)) {
            return mate_score_relative(ply);
        }
        return 0;
    }

    if (best_score == -ENGINE_INF) {
        best_score = 0;
    }

    {
        int flag = 0;
        if (mode != SEARCH_WINDOW_NONE) {
            if (best_score <= alpha_orig) {
                flag = -1;
            } else if (best_score >= beta) {
                flag = 1;
            }
        }
        search_ops()->tt_store(key, depth, best_score, flag, &best_move);
    }

    return best_score;
}

static int search_minimax(EngineState *state, int depth, int alpha, int beta, int ply, bool allow_null, SearchWindowMode mode) {
    EngineMoveList list;
    EngineMove best_move;
    EngineMove hash_move;
    bool maximizing = state->side_to_move == ENGINE_WHITE;
    int best_score = maximizing ? -ENGINE_INF : ENGINE_INF;
    int alpha_orig = alpha;
    int beta_orig = beta;
    int legal_moves = 0;
    int i;
    int tt_score = 0;
    uint64_t key;
    bool has_hash_move = false;

    if (state->stop) {
        return evaluate_absolute(state);
    }

#if !CFG_NULL_MOVE_PRUNING
    (void)allow_null;
#endif

#if CFG_FIFTY_MOVE_RULE
    if (state->halfmove_clock >= 100) {
        return 0;
    }
#endif

#if CFG_THREEFOLD_REPETITION
    if (search_ops()->repetition_count(state) >= 2) {
        return 0;
    }
#endif

    if (search_hit_deadline(state)) {
        return evaluate_absolute(state);
    }

#if CFG_QUIESCENCE_SEARCH
    if (depth <= 0) {
        return quiescence_minimax(state, alpha, beta, ply, 0);
    }
#else
    if (depth <= 0) {
        return evaluate_absolute(state);
    }
#endif

    key = search_ops()->state_key(state);
    if (mode == SEARCH_WINDOW_NONE) {
        if (search_ops()->tt_probe(key, depth, -ENGINE_INF, ENGINE_INF, &tt_score, &hash_move)) {
            return tt_score;
        }
    } else {
        if (search_ops()->tt_probe(key, depth, alpha, beta, &tt_score, &hash_move)) {
            return tt_score;
        }
#if CFG_HASH_MOVE
        if (search_ops()->tt_probe(key, 0, -ENGINE_INF, ENGINE_INF, &tt_score, &hash_move)) {
            has_hash_move = true;
        }
#endif
    }

#if CFG_RAZORING
    if (mode != SEARCH_WINDOW_NONE && depth == 1 && !search_ops()->in_check(state, state->side_to_move)) {
        int eval = evaluate_absolute(state);
        if (maximizing) {
            if (eval + 120 <= alpha) {
                return quiescence_minimax(state, alpha, beta, ply, 0);
            }
        } else if (eval - 120 >= beta) {
            return quiescence_minimax(state, alpha, beta, ply, 0);
        }
    }
#endif

#if CFG_NULL_MOVE_PRUNING
    if (mode != SEARCH_WINDOW_NONE && allow_null && depth >= 3 && !search_ops()->in_check(state, state->side_to_move)) {
        EngineState tmp = *state;
        int score;
        tmp.side_to_move ^= 1;
        tmp.plies_from_start += 1;
        if (maximizing) {
            score = search_minimax(&tmp, depth - 3, beta - 1, beta, ply + 1, false, SEARCH_WINDOW_ALPHA_BETA);
            if (score >= beta) {
                return beta;
            }
        } else {
            score = search_minimax(&tmp, depth - 3, alpha, alpha + 1, ply + 1, false, SEARCH_WINDOW_ALPHA_BETA);
            if (score <= alpha) {
                return alpha;
            }
        }
    }
#endif

    search_ops()->generate_moves(state, &list, false);
    search_ops()->order_moves(state, &list, ply, has_hash_move ? &hash_move : NULL);
    memset(&best_move, 0, sizeof(best_move));

    for (i = 0; i < list.count; ++i) {
        EngineMove move = list.moves[i];
        Undo undo;
        EngineState snapshot;
        uint64_t nodes_after;
        bool stop_after;
        int score;
        int child_depth = depth - 1;

#if CFG_FUTILITY_PRUNING
        if (mode != SEARCH_WINDOW_NONE && depth == 1 && !(move.flags & SEARCH_FLAG_CAPTURE)) {
            int eval = evaluate_absolute(state);
            if (maximizing) {
                if (eval + 90 <= alpha) {
                    continue;
                }
            } else if (eval - 90 >= beta) {
                continue;
            }
        }
#endif

#if CFG_LATE_MOVE_REDUCTIONS
        if (mode != SEARCH_WINDOW_NONE && depth >= 3 && i >= 4 && !(move.flags & SEARCH_FLAG_CAPTURE) && !search_ops()->in_check(state, state->side_to_move)) {
            child_depth -= 1;
        }
#endif

        if (!search_prepare_child(state, &move, &undo, &snapshot)) {
            continue;
        }

        legal_moves += 1;
        state->nodes += 1;

        if (mode == SEARCH_WINDOW_PVS) {
            if (legal_moves == 1) {
                score = search_minimax(state, child_depth, alpha, beta, ply + 1, true, mode);
            } else if (maximizing) {
                score = search_minimax(state, child_depth, alpha, alpha + 1, ply + 1, true, SEARCH_WINDOW_ALPHA_BETA);
                if (score > alpha && score < beta) {
                    score = search_minimax(state, child_depth, alpha, beta, ply + 1, true, mode);
                }
            } else {
                score = search_minimax(state, child_depth, beta - 1, beta, ply + 1, true, SEARCH_WINDOW_ALPHA_BETA);
                if (score > alpha && score < beta) {
                    score = search_minimax(state, child_depth, alpha, beta, ply + 1, true, mode);
                }
            }
        } else if (mode == SEARCH_WINDOW_ALPHA_BETA) {
            score = search_minimax(state, child_depth, alpha, beta, ply + 1, true, mode);
        } else {
            score = search_minimax(state, child_depth, -ENGINE_INF, ENGINE_INF, ply + 1, true, mode);
        }

        nodes_after = state->nodes;
        stop_after = state->stop;
        search_restore_child(state, &move, &undo, &snapshot, nodes_after, stop_after);

        if (state->stop) {
            return best_score;
        }

        if (maximizing) {
            if (score > best_score) {
                best_score = score;
                best_move = move;
            }
            if (mode != SEARCH_WINDOW_NONE) {
                if (score > alpha) {
                    alpha = score;
                }
                if (alpha >= beta) {
                    search_ops()->record_beta_cutoff(state, ply, depth, &move);
                    break;
                }
            }
        } else {
            if (score < best_score) {
                best_score = score;
                best_move = move;
            }
            if (mode != SEARCH_WINDOW_NONE) {
                if (score < beta) {
                    beta = score;
                }
                if (alpha >= beta) {
                    search_ops()->record_beta_cutoff(state, ply, depth, &move);
                    break;
                }
            }
        }
    }

    if (legal_moves == 0) {
        if (search_ops()->in_check(state, state->side_to_move)) {
            return mate_score_absolute(state, ply);
        }
        return 0;
    }

    {
        int flag = 0;
        if (mode != SEARCH_WINDOW_NONE) {
            if (best_score <= alpha_orig) {
                flag = -1;
            } else if (best_score >= beta_orig) {
                flag = 1;
            }
        }
        search_ops()->tt_store(key, depth, best_score, flag, &best_move);
    }

    return best_score;
}

static int root_score_to_cp(const EngineState *state, int raw_score) {
    if (search_use_negamax()) {
        return raw_score;
    }
    return state->side_to_move == ENGINE_WHITE ? raw_score : -raw_score;
}

static int search_child_score(EngineState *state, int depth, int alpha, int beta, SearchWindowMode mode, int legal_moves, bool root_maximizing, bool *has_stop) {
    int score;
    if (search_use_negamax()) {
        if (mode == SEARCH_WINDOW_PVS) {
            if (legal_moves == 1) {
                score = -search_negamax(state, depth, -beta, -alpha, 1, true, mode);
            } else {
                score = -search_negamax(state, depth, -alpha - 1, -alpha, 1, true, SEARCH_WINDOW_ALPHA_BETA);
                if (score > alpha && score < beta) {
                    score = -search_negamax(state, depth, -beta, -alpha, 1, true, mode);
                }
            }
        } else if (mode == SEARCH_WINDOW_ALPHA_BETA) {
            score = -search_negamax(state, depth, -beta, -alpha, 1, true, mode);
        } else {
            score = -search_negamax(state, depth, -ENGINE_INF, ENGINE_INF, 1, true, mode);
        }
    } else if (mode == SEARCH_WINDOW_PVS) {
        if (legal_moves == 1) {
            score = search_minimax(state, depth, alpha, beta, 1, true, mode);
        } else if (root_maximizing) {
            score = search_minimax(state, depth, alpha, alpha + 1, 1, true, SEARCH_WINDOW_ALPHA_BETA);
            if (score > alpha && score < beta) {
                score = search_minimax(state, depth, alpha, beta, 1, true, mode);
            }
        } else {
            score = search_minimax(state, depth, beta - 1, beta, 1, true, SEARCH_WINDOW_ALPHA_BETA);
            if (score > alpha && score < beta) {
                score = search_minimax(state, depth, alpha, beta, 1, true, mode);
            }
        }
    } else if (mode == SEARCH_WINDOW_ALPHA_BETA) {
        score = search_minimax(state, depth, alpha, beta, 1, true, mode);
    } else {
        score = search_minimax(state, depth, -ENGINE_INF, ENGINE_INF, 1, true, mode);
    }
    *has_stop = state->stop;
    return score;
}

static bool run_root_iteration(EngineState *state, EngineMoveList *root_moves, int depth, SearchWindowMode mode, int previous_score, EngineMove *best_move, int *best_score) {
    EngineMove hash_move;
    bool has_hash = false;
    bool maximizing = state->side_to_move == ENGINE_WHITE;
    int alpha = -ENGINE_INF;
    int beta = ENGINE_INF;
    int local_best = search_use_negamax() || maximizing ? -ENGINE_INF : ENGINE_INF;
    EngineMove local_move = root_moves->moves[0];
    int i;

#if !CFG_ASPIRATION_WINDOWS
    (void)previous_score;
#endif

#if CFG_ASPIRATION_WINDOWS
    if (mode != SEARCH_WINDOW_NONE && depth > 2 && previous_score > -ENGINE_INF / 2 && previous_score < ENGINE_INF / 2) {
        alpha = previous_score - 40;
        beta = previous_score + 40;
    }
#endif

#if CFG_HASH_MOVE
    int tt_score;
    if (mode != SEARCH_WINDOW_NONE && search_ops()->tt_probe(search_ops()->state_key(state), 0, -ENGINE_INF, ENGINE_INF, &tt_score, &hash_move)) {
        has_hash = true;
    }
#endif
    search_ops()->order_moves(state, root_moves, 0, has_hash ? &hash_move : NULL);

    for (i = 0; i < root_moves->count; ++i) {
        EngineMove move = root_moves->moves[i];
        Undo undo;
        EngineState snapshot;
        uint64_t nodes_after;
        bool stop_after = false;
        int score;
        int child_depth = depth - 1;

        if (!search_prepare_child(state, &move, &undo, &snapshot)) {
            continue;
        }

        state->nodes += 1;
        score = search_child_score(state, child_depth, alpha, beta, mode, i + 1, maximizing, &stop_after);

        nodes_after = state->nodes;
        stop_after = state->stop;
        search_restore_child(state, &move, &undo, &snapshot, nodes_after, stop_after);

        if (state->stop) {
            break;
        }

        if (search_use_negamax() || maximizing) {
            if (score > local_best) {
                local_best = score;
                local_move = move;
            }
            if (mode != SEARCH_WINDOW_NONE && score > alpha) {
                alpha = score;
            }
        } else {
            if (score < local_best) {
                local_best = score;
                local_move = move;
            }
            if (mode != SEARCH_WINDOW_NONE && score < beta) {
                beta = score;
            }
        }
    }

    if (!state->stop) {
        *best_move = local_move;
        *best_score = local_best;
        search_ops()->move_to_front(root_moves, &local_move);
        return true;
    }
    return false;
}

EngineSearchResult engine_search(EngineState *state, int max_depth, int movetime_ms) {
    EngineSearchResult result;
    EngineMoveList root_moves;
    EngineMove best_move;
    int best_score = search_use_negamax() || state == NULL || state->side_to_move == ENGINE_WHITE ? -ENGINE_INF : ENGINE_INF;
    int depth;
    SearchWindowMode mode = search_window_mode();

    memset(&result, 0, sizeof(result));
    memset(&best_move, 0, sizeof(best_move));

    if (state == NULL) {
        return result;
    }

    if (max_depth <= 0) {
        max_depth = state->max_depth_hint;
    }
    if (movetime_ms == 0) {
#if CFG_TIME_MANAGEMENT
        movetime_ms = state->movetime_ms > 0 ? state->movetime_ms : 150;
#else
        movetime_ms = 200;
#endif
    }

    state->nodes = 0;
    state->stop = false;
    if (movetime_ms < 0) {
        state->deadline_ms = 0;
    } else {
        state->deadline_ms = search_ops()->now_ms() + movetime_ms;
    }

#if CFG_OPENING_BOOK
    if (state->plies_from_start <= 1) {
        EngineMove book;
        EngineMoveList list;
        if (state->side_to_move == ENGINE_WHITE) {
            search_ops()->parse_move_uci("e2e4", &book);
        } else {
            search_ops()->parse_move_uci("e7e5", &book);
        }
        search_ops()->generate_moves(state, &list, false);
        if (search_ops()->find_move_in_list(&list, &book, &best_move)) {
            result.best_move = best_move;
            result.score_cp = search_ops()->evaluate_position(state);
            result.depth = 1;
            result.nodes = 1;
            result.has_move = true;
            return result;
        }
    }
#endif

    search_ops()->generate_moves(state, &root_moves, false);
    if (root_moves.count == 0) {
        result.has_move = false;
        result.score_cp = search_ops()->in_check(state, state->side_to_move) ? root_score_to_cp(state, mate_score_absolute(state, 0)) : 0;
        return result;
    }

#if CFG_FIFTY_MOVE_RULE
    if (state->halfmove_clock >= 100) {
        result.best_move = root_moves.moves[0];
        result.score_cp = 0;
        result.depth = 0;
        result.nodes = 0;
        result.has_move = true;
        return result;
    }
#endif

#if CFG_THREEFOLD_REPETITION
    if (search_ops()->repetition_count(state) >= 2) {
        result.best_move = root_moves.moves[0];
        result.score_cp = 0;
        result.depth = 0;
        result.nodes = 0;
        result.has_move = true;
        return result;
    }
#endif

#if CFG_ITERATIVE_DEEPENING
    for (depth = 1; depth <= max_depth; ++depth) {
        int iteration_score = best_score;
        if (!run_root_iteration(state, &root_moves, depth, mode, best_score, &best_move, &iteration_score)) {
            break;
        }
        best_score = iteration_score;
        result.depth = depth;
        result.has_move = true;
        result.best_move = best_move;
        result.score_cp = root_score_to_cp(state, best_score);
        if (state->stop) {
            break;
        }
    }
#else
    depth = max_depth;
    if (run_root_iteration(state, &root_moves, depth, mode, best_score, &best_move, &best_score)) {
        result.depth = depth;
        result.has_move = true;
        result.best_move = best_move;
        result.score_cp = root_score_to_cp(state, best_score);
    }
#endif

    if (!result.has_move) {
        result.best_move = root_moves.moves[0];
        result.has_move = true;
        result.score_cp = 0;
    }
    result.nodes = state->nodes;
    return result;
}

const char *engine_search_core_name(void) {
    static char name[96];
    static bool initialized = false;
    const char *core;

    if (initialized) {
        return name;
    }

#if CFG_PRINCIPAL_VARIATION_SEARCH && CFG_ALPHA_BETA && CFG_NEGAMAX
    core = "Negamax+AlphaBeta+PVS";
#elif CFG_PRINCIPAL_VARIATION_SEARCH && CFG_ALPHA_BETA
    core = "Minimax+AlphaBeta+PVS";
#elif CFG_ALPHA_BETA && CFG_NEGAMAX
    core = "Negamax+AlphaBeta";
#elif CFG_ALPHA_BETA
    core = "Minimax+AlphaBeta";
#elif CFG_NEGAMAX
    core = "Negamax";
#else
    core = "Minimax";
#endif

#if CFG_ITERATIVE_DEEPENING
    snprintf(name, sizeof(name), "%s+ID", core);
#else
    snprintf(name, sizeof(name), "%s", core);
#endif
    initialized = true;
    return name;
}
