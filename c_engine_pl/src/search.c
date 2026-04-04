#include "engine_search_internal.h"

#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "generated/variant_config.h"

#define QUIESCENCE_MAX_DEPTH 8
#define SEARCH_FLAG_CAPTURE 1
#define OPENING_BOOK_DEFAULT_PATH "c_engine_pl/books/default_openings.txt"
#define OPENING_BOOK_MAX_LINE 1024
#define OPENING_BOOK_MAX_MOVES 64

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
#endif

#if CFG_DELTA_PRUNING || CFG_NULL_MOVE_PRUNING
static int search_piece_abs(int piece) {
    return piece >= 0 ? piece : -piece;
}
#endif

#if CFG_NULL_MOVE_PRUNING
static bool search_side_has_non_pawn_material(const EngineState *state, int side) {
    int sq;

    for (sq = 0; sq < 64; ++sq) {
        int piece = state->board[sq];
        if (piece == 0) {
            continue;
        }
        if ((piece > 0 ? ENGINE_WHITE : ENGINE_BLACK) != side) {
            continue;
        }
        if (search_piece_abs(piece) != 1 && search_piece_abs(piece) != 6) {
            return true;
        }
    }
    return false;
}

static void search_push_history(EngineState *state, uint64_t key) {
    int i;

    if (state->history_count < ENGINE_MAX_HISTORY) {
        state->position_history[state->history_count++] = key;
        return;
    }

    for (i = 1; i < ENGINE_MAX_HISTORY; ++i) {
        state->position_history[i - 1] = state->position_history[i];
    }
    state->position_history[ENGINE_MAX_HISTORY - 1] = key;
    state->history_count = ENGINE_MAX_HISTORY;
}

static void search_prepare_null_state(const EngineState *state, EngineState *tmp) {
    *tmp = *state;
    tmp->side_to_move ^= 1;
    tmp->plies_from_start += 1;
    tmp->en_passant_square = -1;
    if (tmp->halfmove_clock < 1000) {
        tmp->halfmove_clock += 1;
    }
    search_push_history(tmp, search_ops()->state_key(tmp));
}

static int search_null_reduction(int depth) {
    return depth >= 6 ? 3 : 2;
}
#endif

#if CFG_LATE_MOVE_REDUCTIONS
static int search_lmr_reduction(int depth, int move_number) {
    if (depth >= 6 && move_number >= 8) {
        return 2;
    }
    return 1;
}
#endif

static bool search_use_minimax(void) {
#if CFG_MINIMAX
    return true;
#else
    return false;
#endif
}

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

static bool search_soft_deadline_reached(const EngineState *state) {
    return state != NULL && state->soft_deadline_ms > 0 && search_ops()->now_ms() >= state->soft_deadline_ms;
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
static int search_child_score(EngineState *state, int depth, int alpha, int beta, SearchWindowMode mode, int legal_moves, bool root_maximizing, bool *has_stop);

#if CFG_OPENING_BOOK
static const char *search_opening_book_path(const EngineState *state) {
    if (state != NULL && state->opening_book_path[0] != '\0') {
        return state->opening_book_path;
    }
    return OPENING_BOOK_DEFAULT_PATH;
}

static void search_book_trim(char *line) {
    char *start;
    size_t length;

    if (line == NULL) {
        return;
    }

    start = line;
    while (*start != '\0' && isspace((unsigned char)*start)) {
        start += 1;
    }
    if (start != line) {
        memmove(line, start, strlen(start) + 1);
    }

    length = strlen(line);
    while (length > 0 && isspace((unsigned char)line[length - 1])) {
        line[length - 1] = '\0';
        length -= 1;
    }
}

static int search_split_book_moves(char *line, char *moves[OPENING_BOOK_MAX_MOVES]) {
    char *token;
    int count = 0;
    char *cursor = line;
    char *comment = NULL;

    if (line == NULL) {
        return 0;
    }

    comment = strchr(cursor, '#');
    if (comment != NULL) {
        *comment = '\0';
    }
    comment = strchr(cursor, ';');
    if (comment != NULL) {
        *comment = '\0';
    }

    while (*cursor != '\0' && isspace((unsigned char)*cursor)) {
        cursor += 1;
    }
    if (*cursor == '\0') {
        return 0;
    }

    if (strncmp(cursor, "startpos", 8) == 0 && (cursor[8] == '\0' || isspace((unsigned char)cursor[8]))) {
        cursor += 8;
        while (*cursor != '\0' && isspace((unsigned char)*cursor)) {
            cursor += 1;
        }
    }
    if (strncmp(cursor, "moves", 5) == 0 && (cursor[5] == '\0' || isspace((unsigned char)cursor[5]))) {
        cursor += 5;
    }
    while (*cursor != '\0' && isspace((unsigned char)*cursor)) {
        cursor += 1;
    }
    if (*cursor == '\0') {
        return 0;
    }

    token = strtok(cursor, " \t\r\n");
    while (token != NULL && count < OPENING_BOOK_MAX_MOVES) {
        moves[count++] = token;
        token = strtok(NULL, " \t\r\n");
    }
    return count;
}

static bool search_book_add_candidate(
    const EngineMoveList *legal_moves,
    const char *candidate_uci,
    EngineMove candidates[OPENING_BOOK_MAX_MOVES],
    int *candidate_count
) {
    EngineMove parsed;
    EngineMove matched;
    int i;

    if (legal_moves == NULL || candidate_uci == NULL || candidate_count == NULL) {
        return false;
    }
    if (*candidate_count >= OPENING_BOOK_MAX_MOVES) {
        return false;
    }
    if (!search_ops()->parse_move_uci(candidate_uci, &parsed)) {
        return false;
    }
    if (!search_ops()->find_move_in_list(legal_moves, &parsed, &matched)) {
        return false;
    }
    for (i = 0; i < *candidate_count; ++i) {
        if (
            candidates[i].from == matched.from &&
            candidates[i].to == matched.to &&
            candidates[i].promotion == matched.promotion
        ) {
            return false;
        }
    }
    candidates[*candidate_count] = matched;
    *candidate_count += 1;
    return true;
}

static void search_init_book_state(const EngineState *state, EngineState *tmp) {
    if (state == NULL || tmp == NULL) {
        return;
    }
    memset(tmp, 0, sizeof(*tmp));
    tmp->pondering_enabled = state->pondering_enabled;
    tmp->opening_book_enabled = state->opening_book_enabled;
    tmp->max_depth_hint = state->max_depth_hint;
    tmp->movetime_ms = state->movetime_ms;
    snprintf(tmp->opening_book_path, sizeof(tmp->opening_book_path), "%s", search_opening_book_path(state));
    engine_set_startpos(tmp);
}

static void search_match_book_line(
    const EngineState *state,
    const EngineMoveList *legal_moves,
    char *moves[OPENING_BOOK_MAX_MOVES],
    int move_count,
    EngineMove candidates[OPENING_BOOK_MAX_MOVES],
    int *candidate_count
) {
    EngineState tmp;
    uint64_t target_key;
    int i;

    if (
        state == NULL ||
        legal_moves == NULL ||
        moves == NULL ||
        move_count <= 0 ||
        candidate_count == NULL
    ) {
        return;
    }

    if (state->plies_from_start == 0) {
        search_book_add_candidate(legal_moves, moves[0], candidates, candidate_count);
        return;
    }

    search_init_book_state(state, &tmp);
    target_key = search_ops()->state_key(state);

    for (i = 0; i < move_count; ++i) {
        if (engine_apply_move_uci(&tmp, moves[i]) != 0) {
            return;
        }
        if (tmp.plies_from_start > state->plies_from_start) {
            return;
        }
        if (tmp.plies_from_start == state->plies_from_start && search_ops()->state_key(&tmp) == target_key) {
            if (i + 1 < move_count) {
                search_book_add_candidate(legal_moves, moves[i + 1], candidates, candidate_count);
            }
            return;
        }
    }
}

static bool search_opening_book_move(EngineState *state, EngineMove *best_move) {
    FILE *book;
    char line[OPENING_BOOK_MAX_LINE];
    EngineMoveList legal_moves;
    EngineMove candidates[OPENING_BOOK_MAX_MOVES];
    int candidate_count = 0;
    uint64_t key;
    const char *path;

    if (state == NULL || best_move == NULL || !state->opening_book_enabled) {
        return false;
    }

    path = search_opening_book_path(state);
    book = fopen(path, "r");
    if (book == NULL) {
        return false;
    }

    search_ops()->generate_moves(state, &legal_moves, false);
    if (legal_moves.count <= 0) {
        fclose(book);
        return false;
    }

    while (fgets(line, sizeof(line), book) != NULL && candidate_count < OPENING_BOOK_MAX_MOVES) {
        char *moves[OPENING_BOOK_MAX_MOVES];
        int move_count;

        search_book_trim(line);
        move_count = search_split_book_moves(line, moves);
        if (move_count <= 0) {
            continue;
        }
        search_match_book_line(state, &legal_moves, moves, move_count, candidates, &candidate_count);
    }

    fclose(book);

    if (candidate_count <= 0) {
        return false;
    }

    key = search_ops()->state_key(state);
    *best_move = candidates[(int)(key % (uint64_t)candidate_count)];
    return true;
}
#endif

static int search_negamax_with_mode(
    EngineState *state,
    int depth,
    int alpha,
    int beta,
    int ply,
    SearchWindowMode mode,
    int move_number
) {
    int score;

    if (mode == SEARCH_WINDOW_PVS) {
        if (move_number == 1) {
            return -search_negamax(state, depth, -beta, -alpha, ply, true, mode);
        }
        score = -search_negamax(state, depth, -alpha - 1, -alpha, ply, true, SEARCH_WINDOW_ALPHA_BETA);
        if (score > alpha && score < beta) {
            score = -search_negamax(state, depth, -beta, -alpha, ply, true, mode);
        }
        return score;
    }

    if (mode == SEARCH_WINDOW_ALPHA_BETA) {
        return -search_negamax(state, depth, -beta, -alpha, ply, true, mode);
    }
    return -search_negamax(state, depth, -ENGINE_INF, ENGINE_INF, ply, true, mode);
}

static int search_minimax_with_mode(
    EngineState *state,
    int depth,
    int alpha,
    int beta,
    int ply,
    SearchWindowMode mode,
    int move_number,
    bool maximizing
) {
    int score;

    if (mode == SEARCH_WINDOW_PVS) {
        if (move_number == 1) {
            return search_minimax(state, depth, alpha, beta, ply, true, mode);
        }
        if (maximizing) {
            score = search_minimax(state, depth, alpha, alpha + 1, ply, true, SEARCH_WINDOW_ALPHA_BETA);
        } else {
            score = search_minimax(state, depth, beta - 1, beta, ply, true, SEARCH_WINDOW_ALPHA_BETA);
        }
        if (score > alpha && score < beta) {
            score = search_minimax(state, depth, alpha, beta, ply, true, mode);
        }
        return score;
    }

    if (mode == SEARCH_WINDOW_ALPHA_BETA) {
        return search_minimax(state, depth, alpha, beta, ply, true, mode);
    }
    return search_minimax(state, depth, -ENGINE_INF, ENGINE_INF, ply, true, mode);
}

static bool search_root_pass(
    EngineState *state,
    EngineMoveList *root_moves,
    int depth,
    SearchWindowMode mode,
    int alpha,
    int beta,
    EngineMove *best_move,
    int *best_score
) {
    EngineMove hash_move;
    bool has_hash = false;
    bool maximizing = state->side_to_move == ENGINE_WHITE;
    int local_best = search_use_negamax() || maximizing ? -ENGINE_INF : ENGINE_INF;
    EngineMove local_move = root_moves->moves[0];
    int i;

#if CFG_HASH_MOVE
    if (mode != SEARCH_WINDOW_NONE) {
        int tt_score;
        if (search_ops()->tt_probe(search_ops()->state_key(state), 0, -ENGINE_INF, ENGINE_INF, 0, &tt_score, &hash_move)) {
            has_hash = true;
        }
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
            return false;
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

    *best_move = local_move;
    *best_score = local_best;
    return true;
}

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
    bool side_in_check;

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
        if (search_ops()->tt_probe(key, depth, -ENGINE_INF, ENGINE_INF, ply, &tt_score, &hash_move)) {
            return tt_score;
        }
    } else {
        if (search_ops()->tt_probe(key, depth, alpha, beta, ply, &tt_score, &hash_move)) {
            return tt_score;
        }
#if CFG_HASH_MOVE
        if (search_ops()->tt_probe(key, 0, -ENGINE_INF, ENGINE_INF, ply, &tt_score, &hash_move)) {
            has_hash_move = true;
        }
#endif
    }

    side_in_check = search_ops()->in_check(state, state->side_to_move);
#if !CFG_RAZORING && !CFG_NULL_MOVE_PRUNING && !CFG_FUTILITY_PRUNING && !CFG_LATE_MOVE_REDUCTIONS
    (void)side_in_check;
#endif

#if CFG_RAZORING
    if (mode != SEARCH_WINDOW_NONE && depth == 1 && !side_in_check) {
        int eval = search_ops()->evaluate_position(state);
        if (eval + 120 <= alpha) {
            return quiescence_negamax(state, alpha, beta, ply, 0);
        }
    }
#endif

#if CFG_NULL_MOVE_PRUNING
    if (
        mode == SEARCH_WINDOW_ALPHA_BETA &&
        allow_null &&
        depth >= 3 &&
        !side_in_check &&
        search_side_has_non_pawn_material(state, state->side_to_move)
    ) {
        EngineState tmp;
        int score;
        int reduction = search_null_reduction(depth);

        search_prepare_null_state(state, &tmp);
        score = -search_negamax(&tmp, depth - 1 - reduction, -beta, -beta + 1, ply + 1, false, SEARCH_WINDOW_ALPHA_BETA);
        if (score >= beta) {
            if (depth >= 6) {
                int verify = search_negamax(state, depth - 1 - reduction, beta - 1, beta, ply + 1, false, SEARCH_WINDOW_ALPHA_BETA);
                if (verify >= beta) {
                    return beta;
                }
            } else {
                return beta;
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
        int full_child_depth = depth - 1;
        int reduction = 0;

#if CFG_FUTILITY_PRUNING
        if (mode != SEARCH_WINDOW_NONE && depth == 1 && !side_in_check && !(move.flags & SEARCH_FLAG_CAPTURE)) {
            int eval = search_ops()->evaluate_position(state);
            if (eval + 90 <= alpha) {
                continue;
            }
        }
#endif

        if (!search_prepare_child(state, &move, &undo, &snapshot)) {
            continue;
        }

        legal_moves += 1;
        state->nodes += 1;

#if CFG_LATE_MOVE_REDUCTIONS
        if (
            mode != SEARCH_WINDOW_NONE &&
            !side_in_check &&
            full_child_depth >= 2 &&
            legal_moves > 4 &&
            !(move.flags & SEARCH_FLAG_CAPTURE)
        ) {
            reduction = search_lmr_reduction(depth, legal_moves);
            if (reduction > full_child_depth) {
                reduction = full_child_depth;
            }
            child_depth = full_child_depth - reduction;
        }
#endif

        if (reduction > 0) {
            score = -search_negamax(state, child_depth, -alpha - 1, -alpha, ply + 1, true, SEARCH_WINDOW_ALPHA_BETA);
            if (score > alpha) {
                score = search_negamax_with_mode(state, full_child_depth, alpha, beta, ply + 1, mode, legal_moves);
            }
        } else {
            score = search_negamax_with_mode(state, full_child_depth, alpha, beta, ply + 1, mode, legal_moves);
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
        search_ops()->tt_store(key, depth, best_score, flag, ply, &best_move);
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
    bool side_in_check;

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
        if (search_ops()->tt_probe(key, depth, -ENGINE_INF, ENGINE_INF, ply, &tt_score, &hash_move)) {
            return tt_score;
        }
    } else {
        if (search_ops()->tt_probe(key, depth, alpha, beta, ply, &tt_score, &hash_move)) {
            return tt_score;
        }
#if CFG_HASH_MOVE
        if (search_ops()->tt_probe(key, 0, -ENGINE_INF, ENGINE_INF, ply, &tt_score, &hash_move)) {
            has_hash_move = true;
        }
#endif
    }

    side_in_check = search_ops()->in_check(state, state->side_to_move);
#if !CFG_RAZORING && !CFG_NULL_MOVE_PRUNING && !CFG_FUTILITY_PRUNING && !CFG_LATE_MOVE_REDUCTIONS
    (void)side_in_check;
#endif

#if CFG_RAZORING
    if (mode != SEARCH_WINDOW_NONE && depth == 1 && !side_in_check) {
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
    if (
        mode == SEARCH_WINDOW_ALPHA_BETA &&
        allow_null &&
        depth >= 3 &&
        !side_in_check &&
        search_side_has_non_pawn_material(state, state->side_to_move)
    ) {
        EngineState tmp;
        int score;
        int reduction = search_null_reduction(depth);

        search_prepare_null_state(state, &tmp);
        if (maximizing) {
            score = search_minimax(&tmp, depth - 1 - reduction, beta - 1, beta, ply + 1, false, SEARCH_WINDOW_ALPHA_BETA);
            if (score >= beta) {
                if (depth >= 6) {
                    int verify = search_minimax(state, depth - 1 - reduction, beta - 1, beta, ply + 1, false, SEARCH_WINDOW_ALPHA_BETA);
                    if (verify >= beta) {
                        return beta;
                    }
                } else {
                    return beta;
                }
            }
        } else {
            score = search_minimax(&tmp, depth - 1 - reduction, alpha, alpha + 1, ply + 1, false, SEARCH_WINDOW_ALPHA_BETA);
            if (score <= alpha) {
                if (depth >= 6) {
                    int verify = search_minimax(state, depth - 1 - reduction, alpha, alpha + 1, ply + 1, false, SEARCH_WINDOW_ALPHA_BETA);
                    if (verify <= alpha) {
                        return alpha;
                    }
                } else {
                    return alpha;
                }
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
        int full_child_depth = depth - 1;
        int reduction = 0;

#if CFG_FUTILITY_PRUNING
        if (mode != SEARCH_WINDOW_NONE && depth == 1 && !side_in_check && !(move.flags & SEARCH_FLAG_CAPTURE)) {
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

        if (!search_prepare_child(state, &move, &undo, &snapshot)) {
            continue;
        }

        legal_moves += 1;
        state->nodes += 1;

#if CFG_LATE_MOVE_REDUCTIONS
        if (
            mode != SEARCH_WINDOW_NONE &&
            !side_in_check &&
            full_child_depth >= 2 &&
            legal_moves > 4 &&
            !(move.flags & SEARCH_FLAG_CAPTURE)
        ) {
            reduction = search_lmr_reduction(depth, legal_moves);
            if (reduction > full_child_depth) {
                reduction = full_child_depth;
            }
            child_depth = full_child_depth - reduction;
        }
#endif

        if (reduction > 0) {
            if (maximizing) {
                score = search_minimax(state, child_depth, alpha, alpha + 1, ply + 1, true, SEARCH_WINDOW_ALPHA_BETA);
                if (score > alpha) {
                    score = search_minimax_with_mode(state, full_child_depth, alpha, beta, ply + 1, mode, legal_moves, maximizing);
                }
            } else {
                score = search_minimax(state, child_depth, beta - 1, beta, ply + 1, true, SEARCH_WINDOW_ALPHA_BETA);
                if (score < beta) {
                    score = search_minimax_with_mode(state, full_child_depth, alpha, beta, ply + 1, mode, legal_moves, maximizing);
                }
            }
        } else {
            score = search_minimax_with_mode(state, full_child_depth, alpha, beta, ply + 1, mode, legal_moves, maximizing);
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
        search_ops()->tt_store(key, depth, best_score, flag, ply, &best_move);
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
        score = search_negamax_with_mode(state, depth, alpha, beta, 1, mode, legal_moves);
    } else {
        score = search_minimax_with_mode(state, depth, alpha, beta, 1, mode, legal_moves, root_maximizing);
    }
    *has_stop = state->stop;
    return score;
}

static bool run_root_iteration(EngineState *state, EngineMoveList *root_moves, int depth, SearchWindowMode mode, int previous_score, EngineMove *best_move, int *best_score) {
    int alpha = -ENGINE_INF;
    int beta = ENGINE_INF;

#if !CFG_ASPIRATION_WINDOWS
    (void)previous_score;
#endif

#if CFG_ASPIRATION_WINDOWS
    bool use_aspiration = false;
    int aspiration_delta = 40;
    if (mode != SEARCH_WINDOW_NONE && depth > 2 && previous_score > -ENGINE_INF / 2 && previous_score < ENGINE_INF / 2) {
        use_aspiration = true;
        alpha = previous_score - 40;
        beta = previous_score + 40;
    }
#endif

    for (;;) {
        EngineMove local_move;
        int local_best;

        if (!search_root_pass(state, root_moves, depth, mode, alpha, beta, &local_move, &local_best)) {
            return false;
        }

#if CFG_ASPIRATION_WINDOWS
        if (use_aspiration && (local_best <= alpha || local_best >= beta)) {
            aspiration_delta *= 2;
            if (aspiration_delta > ENGINE_INF / 2) {
                use_aspiration = false;
                alpha = -ENGINE_INF;
                beta = ENGINE_INF;
            } else {
                alpha = previous_score - aspiration_delta;
                beta = previous_score + aspiration_delta;
                if (alpha < -ENGINE_INF) {
                    alpha = -ENGINE_INF;
                }
                if (beta > ENGINE_INF) {
                    beta = ENGINE_INF;
                }
                if (alpha <= -ENGINE_INF && beta >= ENGINE_INF) {
                    use_aspiration = false;
                }
            }
            continue;
        }
#endif

        *best_move = local_move;
        *best_score = local_best;
        search_ops()->move_to_front(root_moves, &local_move);
        return true;
    }
}

EngineSearchResult engine_search(EngineState *state, int max_depth, int movetime_ms) {
    EngineSearchResult result;
    EngineMoveList root_moves;
    EngineMove best_move;
    int best_score = (
        state == NULL ||
        search_use_negamax() ||
        !search_use_minimax() ||
        state->side_to_move == ENGINE_WHITE
    ) ? -ENGINE_INF : ENGINE_INF;
    int depth;
    int64_t start_ms = 0;
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
    start_ms = search_ops()->now_ms();
    state->soft_deadline_ms = 0;
    if (movetime_ms < 0) {
        state->deadline_ms = 0;
    } else {
        state->soft_deadline_ms = start_ms + movetime_ms;
#if CFG_TIME_MANAGEMENT
        if (state->exact_movetime) {
            state->deadline_ms = state->soft_deadline_ms;
        } else {
            int hard_budget = movetime_ms <= 30 ? movetime_ms + 10 : movetime_ms + movetime_ms / 3;
            if (hard_budget > movetime_ms + 1000) {
                hard_budget = movetime_ms + 1000;
            }
            state->deadline_ms = start_ms + hard_budget;
        }
#else
        state->deadline_ms = state->soft_deadline_ms;
#endif
    }

    search_ops()->tt_new_search();

#if CFG_OPENING_BOOK
    if (search_opening_book_move(state, &best_move)) {
        result.best_move = best_move;
        result.score_cp = search_ops()->evaluate_position(state);
        result.depth = 1;
        result.nodes = 1;
        result.has_move = true;
        return result;
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
        if (search_soft_deadline_reached(state)) {
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
#elif CFG_PRINCIPAL_VARIATION_SEARCH && CFG_ALPHA_BETA && CFG_MINIMAX
    core = "Minimax+AlphaBeta+PVS";
#elif CFG_ALPHA_BETA && CFG_NEGAMAX
    core = "Negamax+AlphaBeta";
#elif CFG_ALPHA_BETA && CFG_MINIMAX
    core = "Minimax+AlphaBeta";
#elif CFG_NEGAMAX
    core = "Negamax";
#elif CFG_MINIMAX
    core = "Minimax";
#else
    core = "Search";
#endif

#if CFG_ITERATIVE_DEEPENING
    snprintf(name, sizeof(name), "%s+ID", core);
#else
    snprintf(name, sizeof(name), "%s", core);
#endif
    initialized = true;
    return name;
}
