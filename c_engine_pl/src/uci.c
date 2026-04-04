#include "uci.h"

#include <ctype.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "engine.h"
#include "generated/variant_config.h"

static void trim_newline(char *line) {
    size_t length;
    if (line == NULL) {
        return;
    }
    length = strlen(line);
    while (length > 0 && (line[length - 1] == '\n' || line[length - 1] == '\r')) {
        line[length - 1] = '\0';
        length -= 1;
    }
}

#if CFG_PONDERING
typedef struct PonderSession {
    pthread_t thread;
    pthread_mutex_t mutex;
    bool mutex_ready;
    bool active;
    bool stop_requested;
    bool has_result;
    bool joinable;
    bool explicit_depth;
    int requested_depth;
    int search_slice_ms;
    EngineState base_state;
    EngineSearchResult latest_result;
} PonderSession;

static void ponder_session_init(PonderSession *session) {
    if (session == NULL) {
        return;
    }
    memset(session, 0, sizeof(*session));
    if (pthread_mutex_init(&session->mutex, NULL) == 0) {
        session->mutex_ready = true;
    }
}

static void ponder_session_join(PonderSession *session) {
    if (session == NULL || !session->joinable) {
        return;
    }
    pthread_join(session->thread, NULL);
    session->joinable = false;
}

static void ponder_session_destroy(PonderSession *session) {
    if (session == NULL) {
        return;
    }
    if (session->mutex_ready) {
        if (session->active) {
            pthread_mutex_lock(&session->mutex);
            session->stop_requested = true;
            pthread_mutex_unlock(&session->mutex);
        }
        ponder_session_join(session);
        pthread_mutex_destroy(&session->mutex);
        session->mutex_ready = false;
    }
}

static bool ponder_session_should_stop(PonderSession *session) {
    bool stop_requested;

    if (session == NULL || !session->mutex_ready) {
        return true;
    }
    pthread_mutex_lock(&session->mutex);
    stop_requested = session->stop_requested;
    pthread_mutex_unlock(&session->mutex);
    return stop_requested;
}

static void ponder_session_publish(PonderSession *session, const EngineSearchResult *result) {
    if (session == NULL || result == NULL || !session->mutex_ready) {
        return;
    }
    pthread_mutex_lock(&session->mutex);
    if (result->has_move && (!session->has_result || result->depth >= session->latest_result.depth)) {
        session->latest_result = *result;
        session->has_result = true;
    }
    pthread_mutex_unlock(&session->mutex);
}

static void *ponder_session_worker(void *arg) {
    PonderSession *session = (PonderSession *)arg;
    EngineState base_state;
    bool explicit_depth = false;
    int requested_depth = 0;
    int search_slice_ms = 75;
    int depth = 1;

    if (session == NULL || !session->mutex_ready) {
        return NULL;
    }

    pthread_mutex_lock(&session->mutex);
    base_state = session->base_state;
    explicit_depth = session->explicit_depth;
    requested_depth = session->requested_depth;
    search_slice_ms = session->search_slice_ms;
    pthread_mutex_unlock(&session->mutex);

    if (requested_depth < 1) {
        requested_depth = base_state.max_depth_hint > 0 ? base_state.max_depth_hint + 4 : 8;
    }

    while (!ponder_session_should_stop(session)) {
        EngineState iter = base_state;
        EngineSearchResult result;
        int target_depth = requested_depth;

        if (!explicit_depth) {
            target_depth = depth;
        }

        result = engine_search(&iter, target_depth, explicit_depth ? -1 : search_slice_ms);
        ponder_session_publish(session, &result);

        if (explicit_depth) {
            break;
        }
        if (depth < ENGINE_MAX_PLY / 2) {
            depth += 1;
        }
    }

    pthread_mutex_lock(&session->mutex);
    session->active = false;
    pthread_mutex_unlock(&session->mutex);
    return NULL;
}

static bool ponder_session_stop(PonderSession *session, EngineSearchResult *result) {
    bool has_result = false;

    if (session == NULL || !session->mutex_ready) {
        return false;
    }
    if (!session->joinable) {
        return false;
    }

    pthread_mutex_lock(&session->mutex);
    session->stop_requested = true;
    pthread_mutex_unlock(&session->mutex);
    ponder_session_join(session);

    pthread_mutex_lock(&session->mutex);
    if (session->has_result) {
        has_result = true;
        if (result != NULL) {
            *result = session->latest_result;
        }
    }
    session->active = false;
    session->stop_requested = false;
    session->has_result = false;
    memset(&session->latest_result, 0, sizeof(session->latest_result));
    pthread_mutex_unlock(&session->mutex);
    return has_result;
}

static bool ponder_session_start(PonderSession *session, const EngineState *state, int requested_depth, bool explicit_depth, int search_slice_ms) {
    if (session == NULL || state == NULL || !session->mutex_ready) {
        return false;
    }

    ponder_session_stop(session, NULL);

    pthread_mutex_lock(&session->mutex);
    session->base_state = *state;
    session->requested_depth = requested_depth;
    session->explicit_depth = explicit_depth;
    session->search_slice_ms = search_slice_ms > 0 ? search_slice_ms : 75;
    session->stop_requested = false;
    session->has_result = false;
    session->active = true;
    memset(&session->latest_result, 0, sizeof(session->latest_result));
    pthread_mutex_unlock(&session->mutex);

    if (pthread_create(&session->thread, NULL, ponder_session_worker, session) != 0) {
        pthread_mutex_lock(&session->mutex);
        session->active = false;
        pthread_mutex_unlock(&session->mutex);
        return false;
    }

    session->joinable = true;
    return true;
}
#endif

static bool parse_go_value(const char *line, const char *name, int *out_value) {
    char pattern[32];
    const char *token;

    if (line == NULL || name == NULL || out_value == NULL) {
        return false;
    }

    snprintf(pattern, sizeof(pattern), " %s ", name);
    token = strstr(line, pattern);
    if (token == NULL) {
        return false;
    }
    *out_value = atoi(token + strlen(pattern));
    return true;
}

static int parse_movetime(const char *line, int side_to_move, bool has_depth, bool *is_exact) {
    int movetime = 0;
    int wtime = 0;
    int btime = 0;
    int winc = 0;
    int binc = 0;
    int movestogo = 0;
    bool has_wtime;
    bool has_btime;
    bool has_winc;
    bool has_binc;
    bool has_movestogo;

    if (is_exact != NULL) {
        *is_exact = false;
    }

    if (parse_go_value(line, "movetime", &movetime) && movetime > 0) {
        if (is_exact != NULL) {
            *is_exact = true;
        }
        return movetime;
    }

    has_wtime = parse_go_value(line, "wtime", &wtime);
    has_btime = parse_go_value(line, "btime", &btime);
    has_winc = parse_go_value(line, "winc", &winc);
    has_binc = parse_go_value(line, "binc", &binc);
    has_movestogo = parse_go_value(line, "movestogo", &movestogo);

    if (has_wtime || has_btime) {
        int side_time = side_to_move == 0 ? (has_wtime ? wtime : 0) : (has_btime ? btime : 0);
        int side_inc = side_to_move == 0 ? (has_winc ? winc : 0) : (has_binc ? binc : 0);
        int horizon = has_movestogo ? movestogo : 30;
        int reserve;
        int usable;
        int allocation;
        int max_allocation;

        if (side_time > 0) {
            if (horizon < 1) {
                horizon = 1;
            }
            if (horizon > 60) {
                horizon = 60;
            }
            if (!has_movestogo && side_time < 15000) {
                horizon = 20;
            }
            reserve = side_inc > 0 ? 30 : 50;
            reserve += side_time / 40;
            if (horizon <= 5) {
                reserve += side_time / 20;
            }
            if (reserve > side_time / 2) {
                reserve = side_time / 2;
            }
            usable = side_time - reserve;
            if (usable < 20) {
                usable = side_time > 20 ? side_time - 10 : side_time;
            }
            allocation = usable / horizon + (side_inc * 3) / 4;
            if (side_time < 2000) {
                int panic_horizon = horizon > 8 ? horizon : 8;
                allocation = usable / panic_horizon + side_inc / 2;
            }
            max_allocation = horizon > 1 ? usable / 2 : usable - 5;
            if (!has_movestogo) {
                int adaptive_cap = usable / 3;
                if (adaptive_cap > max_allocation) {
                    max_allocation = adaptive_cap;
                }
            }
            if (max_allocation < 20) {
                max_allocation = usable;
            }
            if (allocation < 20) {
                allocation = 20;
            }
            if (allocation > max_allocation) {
                allocation = max_allocation;
            }
            if (allocation > side_time - 5) {
                allocation = side_time - 5;
            }
            if (allocation < 1) {
                allocation = 1;
            }
            return allocation;
        }
    }

    /* In depth-only mode, disable time cutoffs and search the full requested depth. */
    if (has_depth) {
        return -1;
    }
    return 150;
}

static void handle_position(EngineState *state, char *args) {
    char *moves;
    char *token;

    if (state == NULL || args == NULL) {
        return;
    }

    if (strncmp(args, "startpos", 8) == 0) {
        engine_set_startpos(state);
        moves = strstr(args, " moves ");
    } else if (strncmp(args, "fen ", 4) == 0) {
#if CFG_FEN
        char fen[ENGINE_MAX_FEN];
        int index = 0;
        const char *cursor = args + 4;
        while (*cursor != '\0' && index < (int)sizeof(fen) - 1) {
            if (cursor[0] == ' ' && cursor[1] == 'm' && cursor[2] == 'o' && cursor[3] == 'v' && cursor[4] == 'e' && cursor[5] == 's') {
                break;
            }
            fen[index++] = *cursor;
            cursor += 1;
        }
        fen[index] = '\0';
        while (index > 0 && fen[index - 1] == ' ') {
            fen[index - 1] = '\0';
            index -= 1;
        }
        if (engine_set_fen(state, fen) != 0) {
            engine_set_startpos(state);
        }
        moves = strstr(args, " moves ");
#else
        return;
#endif
    } else {
        return;
    }

    if (moves == NULL) {
        return;
    }

    moves += 7;
    token = strtok(moves, " ");
    while (token != NULL) {
        if (engine_apply_move_uci(state, token) != 0) {
            printf("info string warning failed_to_apply_move %s\n", token);
            fflush(stdout);
        }
        token = strtok(NULL, " ");
    }
}

static void handle_setoption(EngineState *state, const char *args) {
    const char *value;

    if (state == NULL || args == NULL) {
        return;
    }

#if CFG_PONDERING
    if (strstr(args, "name Ponder") != NULL) {
        if (strstr(args, "value true") != NULL) {
            state->pondering_enabled = true;
        } else if (strstr(args, "value false") != NULL) {
            state->pondering_enabled = false;
        }
    }
#endif

#if CFG_OPENING_BOOK
    if (strstr(args, "name OwnBook") != NULL) {
        if (strstr(args, "value false") != NULL) {
            state->opening_book_enabled = false;
        } else if (strstr(args, "value true") != NULL) {
            state->opening_book_enabled = true;
        }
    }
    if (strstr(args, "name BookFile") != NULL) {
        value = strstr(args, " value ");
        if (value != NULL) {
            value += 7;
            if (*value != '\0') {
                snprintf(state->opening_book_path, sizeof(state->opening_book_path), "%s", value);
            }
        }
    }
#endif

#if !CFG_OPENING_BOOK
    (void)value;
#endif
}

static void handle_legalmoves(EngineState *state) {
    EngineMoveList list;
    int i;

    if (state == NULL) {
        return;
    }
    if (engine_generate_legal_moves(state, &list) < 0) {
        printf("info string legalmoves error\n");
        fflush(stdout);
        return;
    }

    printf("info string legalmoves count %d\n", list.count);
    for (i = 0; i < list.count; ++i) {
        char uci[6];
        engine_move_to_uci(&list.moves[i], uci);
        printf("info string legalmove %s\n", uci);
    }
    fflush(stdout);
}

static void handle_perft(EngineState *state, const char *args) {
    int depth = -1;
    uint64_t nodes;
    int parsed = 0;

    if (state == NULL) {
        return;
    }
    if (args == NULL) {
        printf("info string perft error invalid arguments\n");
        fflush(stdout);
        return;
    }

    while (*args != '\0' && isspace((unsigned char)*args)) {
        args += 1;
    }
    if (strncmp(args, "depth", 5) == 0 && isspace((unsigned char)args[5])) {
        args += 5;
    }
    while (*args != '\0' && isspace((unsigned char)*args)) {
        args += 1;
    }
    if (sscanf(args, "%d%n", &depth, &parsed) != 1 || depth < 0) {
        printf("info string perft error expected: perft <depth>\n");
        fflush(stdout);
        return;
    }

    nodes = engine_perft(state, depth);
    printf("info string perft depth %d nodes %llu\n", depth, (unsigned long long)nodes);
    fflush(stdout);
}

static void handle_eval(EngineState *state) {
    int score_cp;
    char summary[256];

    if (state == NULL) {
        return;
    }

    score_cp = engine_static_eval(state);
    engine_variant_summary(summary, sizeof(summary));
    printf("info string %s\n", summary);
    printf("info string static_eval cp %d\n", score_cp);
    fflush(stdout);
}

int uci_loop(void) {
    EngineState state;
    char line[2048];
#if CFG_PONDERING
    PonderSession ponder_session;
#endif

    engine_init(&state);
#if CFG_PONDERING
    ponder_session_init(&ponder_session);
#endif

    while (fgets(line, sizeof(line), stdin) != NULL) {
        trim_newline(line);

        if (strcmp(line, "uci") == 0) {
#if CFG_UCI
            engine_print_compiled_features(stdout);
            printf("uciok\n");
            fflush(stdout);
#else
            printf("info string UCI feature disabled in this variant\n");
            printf("uciok\n");
            fflush(stdout);
#endif
            continue;
        }

        if (strcmp(line, "isready") == 0) {
            printf("readyok\n");
            fflush(stdout);
            continue;
        }

        if (strcmp(line, "ucinewgame") == 0) {
#if CFG_PONDERING
            ponder_session_stop(&ponder_session, NULL);
#endif
            engine_set_startpos(&state);
            continue;
        }

        if (strncmp(line, "position ", 9) == 0) {
#if CFG_PONDERING
            ponder_session_stop(&ponder_session, NULL);
#endif
            handle_position(&state, line + 9);
            continue;
        }

        if (strncmp(line, "setoption ", 10) == 0) {
            handle_setoption(&state, line + 10);
            continue;
        }

        if (strcmp(line, "legalmoves") == 0) {
            handle_legalmoves(&state);
            continue;
        }

        if (strncmp(line, "perft", 5) == 0) {
            handle_perft(&state, line + 5);
            continue;
        }

        if (strcmp(line, "eval") == 0) {
            handle_eval(&state);
            continue;
        }

        if (strncmp(line, "go", 2) == 0) {
            EngineSearchResult result;
            char bestmove[6] = "0000";
            int depth = state.max_depth_hint;
            int movetime;
            bool exact_movetime = false;
            bool has_depth = false;
#if CFG_PONDERING
            bool ponder_request = false;
            int ponder_slice_ms = 75;
#endif
            const char *dtoken = strstr(line, " depth ");
            if (dtoken != NULL) {
                int parsed = atoi(dtoken + 7);
                if (parsed > 0) {
                    depth = parsed;
                    has_depth = true;
                }
            }
            movetime = parse_movetime(line, state.side_to_move, has_depth, &exact_movetime);
            state.exact_movetime = exact_movetime;
            state.movetime_ms = movetime;
#if CFG_PONDERING
            ponder_request = strcmp(line, "go ponder") == 0 || strstr(line, " ponder ") != NULL;
            if (movetime > 0) {
                ponder_slice_ms = movetime / 3;
                if (ponder_slice_ms < 50) {
                    ponder_slice_ms = 50;
                }
                if (ponder_slice_ms > 200) {
                    ponder_slice_ms = 200;
                }
            }
            if (ponder_request) {
                if (state.pondering_enabled && ponder_session_start(&ponder_session, &state, depth, has_depth, ponder_slice_ms)) {
                    continue;
                }
            } else {
                ponder_session_stop(&ponder_session, NULL);
            }
#endif
            result = engine_search(&state, depth, movetime);
            if (result.has_move) {
                engine_move_to_uci(&result.best_move, bestmove);
            }
            printf("info depth %d score cp %d nodes %llu pv %s\n",
                   result.depth,
                   result.score_cp,
                   (unsigned long long)result.nodes,
                   bestmove);
            printf("bestmove %s\n", bestmove);
            fflush(stdout);
            continue;
        }

        if (strcmp(line, "ponderhit") == 0) {
#if CFG_PONDERING
            EngineSearchResult result;
            char bestmove[6] = "0000";

            if (!ponder_session_stop(&ponder_session, &result)) {
                result = engine_search(&state, state.max_depth_hint, state.movetime_ms);
            }
            if (result.has_move) {
                engine_move_to_uci(&result.best_move, bestmove);
            }
            printf("info depth %d score cp %d nodes %llu pv %s\n",
                   result.depth,
                   result.score_cp,
                   (unsigned long long)result.nodes,
                   bestmove);
            printf("bestmove %s\n", bestmove);
            fflush(stdout);
#endif
            continue;
        }

        if (strcmp(line, "stop") == 0) {
#if CFG_PONDERING
            EngineSearchResult result;
            char bestmove[6] = "0000";

            if (ponder_session_stop(&ponder_session, &result)) {
                if (result.has_move) {
                    engine_move_to_uci(&result.best_move, bestmove);
                }
                printf("info depth %d score cp %d nodes %llu pv %s\n",
                       result.depth,
                       result.score_cp,
                       (unsigned long long)result.nodes,
                       bestmove);
                printf("bestmove %s\n", bestmove);
                fflush(stdout);
            }
#endif
            continue;
        }

        if (strcmp(line, "d") == 0 || strcmp(line, "debug") == 0) {
            char summary[256];
            engine_variant_summary(summary, sizeof(summary));
            printf("info string %s\n", summary);
            fflush(stdout);
            continue;
        }

        if (strcmp(line, "quit") == 0) {
#if CFG_PONDERING
            ponder_session_stop(&ponder_session, NULL);
#endif
            break;
        }
    }

#if CFG_PONDERING
    ponder_session_destroy(&ponder_session);
#endif
    return 0;
}
