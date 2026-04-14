# External Access Report

This report re-analyzes the recorded Codex sessions to answer a specific question:
did the coding agent roam the web freely, or did it mostly stay within the local CPW snapshot and repository artifacts?

- Analysis cutoff: `2026-04-10T00:00:00Z`

## Main Result

The recorded endeavor was overwhelmingly **snapshot-local**, not web-browsing-driven.
- Browser/search-style tool calls recorded in the relevant threads: **0**
- Explicit network-style shell commands (`curl`, `wget`, `lynx`) before the cutoff: **1**

The only explicit outbound network-style shell command found in the recorded sessions was:

- `2026-03-01T07:48:32.116Z` in `019ca85a`: `curl -I -L --max-time 15 https://www.chessprogramming.org/Main_Page`

This should be interpreted carefully:
- an early `curl -I` reachability probe to CPW is recorded, but it failed with DNS resolution in the sandbox;
- the main engineering workflow then relied on the dedicated CPW fetch/cache pipeline and, after the cache existed, repeatedly used offline `run-all`, `build-model`, and `build-matrix` commands;
- the user explicitly stated that they could run the polite crawl on their side, which matches the cache-first/offline-first organization of the project.

## Per-Thread Summary

| Thread | Web/search tool calls | CPW fetch/build activity | Explicit network shell commands |
| --- | ---: | --- | ---: |
| `019ca85a` | 0 | fetch=1, fetch-help=1, run-all-offline=5, run-all-non-offline=0, build-model=20, build-matrix=6 | 1 |
| `019d7355` | 0 | fetch=0, fetch-help=0, run-all-offline=0, run-all-non-offline=0, build-model=0, build-matrix=0 | 0 |
| `019d7399` | 0 | fetch=0, fetch-help=0, run-all-offline=0, run-all-non-offline=0, build-model=0, build-matrix=0 | 0 |

## User-Provided URLs

The user did provide a few URLs directly in prompts, but these were sparse and task-specific rather than signs of free web exploration:

- `2026-03-01T10:33:31.232Z` in `019ca85a`: `https://www.chessprogramming.org/0x88`, `https://www.chessprogramming.org/Bitboards`
- `2026-04-09T17:52:26.999Z` in `019d7355`: `https://conf.researchr.org/home/variability-2026`

## Interpretation

The sessions do **not** support a story in which the agent routinely searched the wider web ``here and there'' for missing domain knowledge.
A more accurate description is:

- CPW was the intended knowledge source.
- A local cache/snapshot was deliberately constructed early and then reused.
- The engineering, experiments, and paper-writing stages mostly operated on local artifacts, generated reports, and the maintained codebase.
- The recorded agent had some technical means to probe or extend CPW through the dedicated fetch pipeline, but there is no evidence of broad ad hoc browsing across external sources.

So, for the paper, the safest wording is that the project was **CPW-centered and snapshot-driven**, with only very limited recorded external probing.

