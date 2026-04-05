# Commonality Optimization Round 2

Additional fix applied:
- precomputed knight/king attack masks for bitboard attack tests and move generation

| position | prev depth | new depth | prev nodes | new nodes | prev nps | new nps | prev move | new move |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| startpos | 6 | 7 | 811008 | 998400 | 405301 | 498950 | d2d4 | d2d4 |
| italian_dev | 6 | 6 | 764928 | 855040 | 381891 | 427520 | d2d3 | d2d3 |
| queens_gambit | 6 | 6 | 801792 | 939008 | 399896 | 469269 | f8b4 | b8c6 |

Main reading:
- `startpos` improves from depth 6 to depth 7 at the same 2-second budget.
- `italian_dev` and `queens_gambit` stay at depth 6 but with higher node throughput.
- attack checking remains the dominant shared cost center; the optimization helped throughput but did not remove that bottleneck.