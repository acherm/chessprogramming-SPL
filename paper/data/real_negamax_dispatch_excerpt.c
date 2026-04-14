static int search_child_score(
    EngineState *state, int depth, int alpha, int beta,
    SearchWindowMode mode, int legal_moves, bool root_maximizing, bool *has_stop
) {
    int score;
    if (search_use_negamax()) {
        score = search_negamax_with_mode(state, depth, alpha, beta, 1, mode, legal_moves);
    } else {
        score = search_minimax_with_mode(state, depth, alpha, beta, 1, mode, legal_moves, root_maximizing);
    }
    *has_stop = state->stop;
    return score;
}
