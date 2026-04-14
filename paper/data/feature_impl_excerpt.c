static SearchWindowMode search_window_mode(void) {
#if CFG_PRINCIPAL_VARIATION_SEARCH && CFG_ALPHA_BETA
  return SEARCH_WINDOW_PVS;
#elif CFG_ALPHA_BETA
  return SEARCH_WINDOW_ALPHA_BETA;
#else
  return SEARCH_WINDOW_NONE;
#endif
}

static int search_child_score(EngineState *state, int depth, int alpha, int beta,
                              SearchWindowMode mode, int legal_moves,
                              bool root_maximizing, bool *has_stop) {
  int score;
#if CFG_NEGAMAX
    score = search_negamax_with_mode(state, depth, alpha, beta, 1, mode, legal_moves);
#else
    score = search_minimax_with_mode(state, depth, alpha, beta, 1, mode,
                                     legal_moves, root_maximizing);
#endif
  *has_stop = state->stop;
  return score;
}

static bool run_root_iteration(EngineState *state, EngineMoveList *root_moves,
                               int depth, SearchWindowMode mode,
  int previous_score, EngineMove *best_move,
                               int *best_score) {
  int alpha = -ENGINE_INF;
  int beta = ENGINE_INF;
#if CFG_ASPIRATION_WINDOWS
  if (mode != SEARCH_WINDOW_NONE && depth > 2 &&
      previous_score > -ENGINE_INF / 2 &&
      previous_score < ENGINE_INF / 2) {
    alpha = previous_score - 40;
    beta = previous_score + 40;
  }
#endif
  /* root-search loop omitted */
  return search_root_pass(state, root_moves, depth, mode, alpha, beta,
                          best_move, best_score);
}
