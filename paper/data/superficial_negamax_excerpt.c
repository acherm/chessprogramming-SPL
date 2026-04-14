void engine_variant_summary(char *out, size_t out_size) {
    const char *search_core;

#if CFG_ALPHA_BETA
    search_core = "AlphaBeta";
#elif CFG_NEGAMAX
    search_core = "Negamax";
#else
    search_core = "Search";
#endif

    snprintf(out, out_size, "variant=%s board=%s search=%s", PL_VARIANT_NAME, board, search_core);
}
