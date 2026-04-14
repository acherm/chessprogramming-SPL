# Commonality Optimization Round 3

Additional fix applied:
- king-square caching plus pin/check-aware legal-move fast path

| position | prev depth | new depth | prev nodes | new nodes | prev nps | new nps | prev attack | new attack | |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| startpos | 7 | 7 | 998400 | 1287168 | 498950 | 643584 | 13967823 | 12805036 |
| italian_dev | 6 | 7 | 855040 | 1209344 | 427520 | 602863 | 13453868 | 11784901 |
| queens_gambit | 6 | 6 | 939008 | 1154048 | 469269 | 572728 | 13176207 | 11619556 |

Main reading:
- start position keeps depth 7 but gains a large node-throughput increase.
- italian_dev now reaches depth 7 at the same 2-second budget.
- attack counts drop despite more total nodes, which is the intended signal for the legality fast path.