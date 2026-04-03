#include "uci.h"

#include <ctype.h>
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

static int parse_movetime(const char *line, int side_to_move, bool has_depth) {
    int movetime = 0;
    int wtime = 0;
    int btime = 0;
    int winc = 0;
    int binc = 0;
    bool has_wtime;
    bool has_btime;
    bool has_winc;
    bool has_binc;

    if (parse_go_value(line, "movetime", &movetime) && movetime > 0) {
        return movetime;
    }

    has_wtime = parse_go_value(line, "wtime", &wtime);
    has_btime = parse_go_value(line, "btime", &btime);
    has_winc = parse_go_value(line, "winc", &winc);
    has_binc = parse_go_value(line, "binc", &binc);

    if (has_wtime || has_btime) {
        int side_time = side_to_move == 0 ? (has_wtime ? wtime : 0) : (has_btime ? btime : 0);
        int side_inc = side_to_move == 0 ? (has_winc ? winc : 0) : (has_binc ? binc : 0);
        if (side_time > 0) {
            int allocation = side_time / 30 + side_inc / 2;
            if (allocation < 20) {
                allocation = 20;
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
#else
    (void)args;
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

    engine_init(&state);

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
            engine_set_startpos(&state);
            continue;
        }

        if (strncmp(line, "position ", 9) == 0) {
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
            bool has_depth = false;
            const char *dtoken = strstr(line, " depth ");
            if (dtoken != NULL) {
                int parsed = atoi(dtoken + 7);
                if (parsed > 0) {
                    depth = parsed;
                    has_depth = true;
                }
            }
            movetime = parse_movetime(line, state.side_to_move, has_depth);
            if (state.pondering_enabled) {
#if CFG_PONDERING
                depth += 1;
#endif
            }
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

        if (strcmp(line, "d") == 0 || strcmp(line, "debug") == 0) {
            char summary[256];
            engine_variant_summary(summary, sizeof(summary));
            printf("info string %s\n", summary);
            fflush(stdout);
            continue;
        }

        if (strcmp(line, "quit") == 0) {
            break;
        }
    }

    return 0;
}
