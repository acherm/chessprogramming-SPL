# Commonality Optimizations Benchmark

Commonality fixes applied:
- removed the implicit timed-search depth cap at `max_depth_hint=5`
- cached position key and pawn key instead of rescanning the full board
- replaced full backend rebuild on every move with incremental updates
- removed full-state copy per candidate in legal move filtering
- replaced mobility pseudo-move generation with direct mobility counting

| position | before depth | after depth | before nodes | after nodes | before sec | after sec | before move | after move |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| startpos | 5 | 6 | 56269 | 761856 | 0.269 | 2.004 | d2d4 | d2d4 |
| italian_dev | 5 | 5 | 182975 | 699392 | 1.216 | 2.009 | d2d3 | d2d3 |
| queens_gambit | 5 | 6 | 154676 | 714752 | 0.821 | 2.006 | f8b4 | f8b4 |
