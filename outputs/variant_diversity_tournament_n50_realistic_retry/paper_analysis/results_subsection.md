## Results

Our full round-robin evaluated `50` shortlisted variants together with `3` Stockfish anchors under `time control 10+0.1`, yielding `5512` games (`208` per player) across `1378` unique pairings. This design moves beyond anchor-only screening by exposing the internal competitive structure of the variant space.

The resulting strength distribution is broad. Variant scores span from `2.4%` to `93.5%`, with `14` variants finishing above `sf1500` in the overall table and `3` finishing above `sf2000`. The strongest three variants are `stratified_variant_28` (`93.5%`), `phase2_10x12_ab_pvs_id` (`93.3%`), and `phase3_full_eval` (`93.3%`). At the other extreme, `stratified_variant_98` and the other tail variants form a clearly separated weak region of the space.

Perft remains a poor proxy for playing strength in this experiment. The correlation between perft-6 runtime and tournament score is only `-0.360`, showing that faster move generation does not reliably imply stronger play. The board-family and search-tier aggregates also show that strength is structured by architectural choices rather than by raw feature count alone.

Most importantly, the full round-robin reveals internal diversity that anchor-only screening cannot capture. The score ladder and representative pairwise heatmap show that variants with similar anchor-relative performance can still occupy very different positions in the interaction graph. For downstream analysis, we therefore retain a representative set of nine variants, with three representatives from each weak, mid, and strong bucket, extracted directly from the full round-robin results.
