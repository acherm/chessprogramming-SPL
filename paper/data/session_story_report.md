# Session Story Report

This report focuses on the *story* of the endeavor rather than only the artifact inventory.
It re-analyzes the local Codex rollouts and thread metadata to describe how the work was actually carried out: which prompts drove the work, what was developed and gathered at each stage, how a local snapshot of Chessprogramming.org (CPW) was built and reused, what kind of supervision the human provided, and how testing and observations governed the interaction.

## 1. Scope

- Workspace: `/Users/mathieuacher/SANDBOX/chessprogramming-vm`
- Relevant Codex threads analyzed: **3**
- Total tokens recorded across these threads: **320,683,577**
- Main engineering thread prompts: **100** over **9** active days
- Experiment thread prompts: **22**
- Paper thread prompts: **23**

### Thread Set

| Thread | Focus | User prompts | Model metadata | Turn-context model mix | Tokens used |
| --- | --- | ---: | --- | --- | ---: |
| `019ca85a` | I'd like to build a feature model (as in software product line) of the... | 100 | `gpt-5.4` / `low` | `gpt-5.3-codex` x 773, `gpt-5.4` x 64 | 249,337,097 |
| `019d7355` | I'd like to write a paper for VARIABILITY 2026 https://conf.researchr.... | 23 | `gpt-5.4` / `xhigh` | `gpt-5.4` x 27 | 37,466,731 |
| `019d7399` | it's time to perform experiments I was thinking especially to derive N... | 22 | `gpt-5.4` / `xhigh` | `gpt-5.4` x 24 | 33,879,749 |

## 2. Starting Point: From Wiki Knowledge to a Local CPW Snapshot

A defining aspect of the sessions is that the work did **not** start from an existing codebase to modify, nor from live web queries on every turn.
The initial prompts asked for a traceable feature model and comparison table derived from CPW, and almost immediately constrained the acquisition strategy: use a safe, resumable, cache-first workflow rather than an aggressive scraper.
The result is a local CPW snapshot that became the shared substrate for all later SPL work.

- Seed titles in discovery state: **29**
- Visited pages during snapshot crawl: **1200**
- Cached page entries in `manifest.json`: **1318**
- Failed page fetches recorded in discovery state: **205**
- Recorded crawl warnings: **215**
- Crawl stop reason: `max_pages_reached:1200`

This local snapshot matters methodologically.
Later feature-model revisions, C implementation work, benchmarking scripts, and even the paper itself were grounded in a stable offline corpus rather than a moving web target.
The challenge was therefore to operationalize a wiki-like body of knowledge into SPL artifacts, not simply to automate edits on an existing engine repository.

## 3. Timeline and Main Deliverables

### Bootstrapping a local CPW snapshot and mining pipeline

What was developed or gathered in this phase:

- A safe, resumable, cache-first CPW acquisition pipeline instead of live scraping on every turn.
- The first local corpus, traceability artifacts, and engine-feature mining outputs.

Representative prompts:

- `2026-03-01T07:47:17.043Z`: I'd like to build a feature model (as in software product line) of the variability of chess engine implementation... For this, I'd like to rely on chessprogramming.org which is a unique resource describing many techniques, actual chess engines, etc. Please synthesize such a feature model with automated scripts. Each feature should be traced back to a resource and justified. Keep a cache of downloaded resources of ch…
- `2026-03-01T07:53:39.400Z`: PLEASE IMPLEMENT THIS PLAN: # CPW Variability Mining Pipeline and SPL Feature Model ## Summary Build a Python CLI pipeline that mines `chessprogramming.org` into: 1. A 2-3 level SPL feature model (~150 features) in FeatureIDE XML + JSON. 2. Full traceability for each feature (URL + snippet + confidence + justification rule). 3. An all-engines vs all-modeled-features tri-state matrix (`SUPPORTED`, `UNSUPPORTED_EXPLIC…
- `2026-03-01T08:12:22.519Z`: I can run on my side, but I'd like to avoid to be a scrapper, and I'm OK to not flood the website... implement a safe strategy, especially resumable with cache
- `2026-03-01T09:27:11.190Z`: mathieuacher@Mathieus-MacBook-Pro chessprogramming-vm % PYTHONPATH=src python3 -m cpw_variability.cli fetch \ --seed main \ --mode snapshot \ --max-pages 600 \ --crawl-delay 2.0 \ --http-retries 3 \ --http-backoff 2.0 --fresh Fetched/discovered pages: 600 Warnings: 84 what's next?

### Repairing and constraining the feature space

What was developed or gathered in this phase:

- A shift from noisy wiki terms toward executable chess-engine variation points.
- Explicit cleanup of editorial artifacts and addition of core anchors such as board-representation techniques.

Representative prompts:

- `2026-03-01T07:47:17.043Z`: I'd like to build a feature model (as in software product line) of the variability of chess engine implementation... For this, I'd like to rely on chessprogramming.org which is a unique resource describing many techniques, actual chess engines, etc. Please synthesize such a feature model with automated scripts. Each feature should be traced back to a resource and justified. Keep a cache of downloaded resources of ch…
- `2026-03-01T07:53:39.400Z`: PLEASE IMPLEMENT THIS PLAN: # CPW Variability Mining Pipeline and SPL Feature Model ## Summary Build a Python CLI pipeline that mines `chessprogramming.org` into: 1. A 2-3 level SPL feature model (~150 features) in FeatureIDE XML + JSON. 2. Full traceability for each feature (URL + snippet + confidence + justification rule). 3. An all-engines vs all-modeled-features tri-state matrix (`SUPPORTED`, `UNSUPPORTED_EXPLIC…
- `2026-03-01T10:33:31.232Z`: now we should significantly improve the pipeline... here is a partial review of the feature model in FeatureIDE for <and name="BoardRepresentation"> <feature name="1995[edit]" /> <feature name="2000 ...[edit]" /> <feature name="2005[edit]" /> <feature name="2010[edit]" /> <feature name="2015[edit]" /> <feature name="Advances in Computer Chess" /> <feature name="Array" /> <feature name="Assembly" /> <feature name="Bo…
- `2026-03-01T14:43:23.583Z`: it's a bit better... though far from perfect... anyway. Now I want a feature model to guide the implementation of a family of chess engines... the goal is that, for each combination of features (configuration), I got a chess engine variant. It can be implemented with compile-time options. Perhaps some run-time options as well, but I would expect it's more rare. So please adapt the mining of a feature model to reflec…

### Turning the model into an executable SPL in C

What was developed or gathered in this phase:

- A first C product line with generated configuration headers, compile-time flags, and derivable variants.
- Initial legality, protocol, and perft-oriented functionality to make variants compile and run.

Representative prompts:

- `2026-03-01T07:47:17.043Z`: I'd like to build a feature model (as in software product line) of the variability of chess engine implementation... For this, I'd like to rely on chessprogramming.org which is a unique resource describing many techniques, actual chess engines, etc. Please synthesize such a feature model with automated scripts. Each feature should be traced back to a resource and justified. Keep a cache of downloaded resources of ch…
- `2026-03-04T23:07:15.851Z`: leveraging the extracted feature model at depth=4 and mainly using compile-time options (corresponding to features of the feature model), please implement a product line of chess engines in C langage... showcase that out of a valid configuration of the feature model, it is possible to derive/compile the corresponding chess variant, and it should compile/work
- `2026-03-04T23:19:25.453Z`: I want a real implementation of each feature
- `2026-03-04T23:39:27.297Z`: implement full tournament legality” (castling/en-passant/repetition/50-move) and then map additional CPW features on top
- `2026-03-05T08:26:38.386Z`: can we envision to derive one variant, and to make perft pass?

### Refining features, modularity, commonality, and setup

What was developed or gathered in this phase:

- Substantial rework of shallow features, modularization of search/evaluation/setup code, and pairwise-combination checks.
- Promotion, removal, or relocation of features as the line between configurable variability and commonality became clearer.

Representative prompts:

- `2026-04-02T12:29:39.931Z`: OK... there is, I think, a big general issue. the tldr; is that most of the features are simply not fully implemented to say the least... it's just a representative example, but let's consider #if CFG_ALPHA_BETA search_core = "AlphaBeta"; #elif CFG_NEGAMAX search_core = "Negamax"; #else search_core = "Search"; #endif snprintf(out, out_size, "variant=%s board=%s search=%s", PL_VARIANT_NAME, board, search_core); basic…
- `2026-04-02T12:33:52.656Z`: please go with Phase 1... but assess quickly that your modularization pays off and that features can be combined
- `2026-04-02T14:49:46.186Z`: let's go to Phase 2
- `2026-04-02T17:01:44.903Z`: a natural challenge is to handle properly feature interactions and how features combined... specifically here, after Phase 1 and Phase 2, we can combine different board representations with different search strategies, but is it really the case? try to test pair-wise combinations
- `2026-04-03T12:20:47.344Z`: Promote some of these new evaluation subfeatures into first-class feature-model options instead of keeping them grouped under the current evaluation flags... It sounds a great direction. Are these subfeatures documented in chessprogramming.org? what do you consider as a "feature"?
- `2026-04-03T13:10:58.440Z`: yes promote into proper intermediate groups... and commit

### Scaling experiments and paper synthesis

What was developed or gathered in this phase:

- Family-wide screening, realistic tournaments, plots, and the paper itself.
- A transition from 'can it compile?' to 'how robust and diverse are the derived variants?'

Representative prompts:

- `2026-04-09T18:55:51.964Z`: it's time to perform experiments I was thinking especially to derive N variants randomly and show some diversity wrt perft and Elo assessment... and plots some interesting stuff so here is a plan: * Stratified random sampling of many valid variants, then legality + perft + anchored Elo. Please include supposedly worst and best variant, and random one... * Controlled ablations separating feature effects from commonal…
- `2026-04-09T19:37:10.224Z`: can you plot something out of perf_screen.csv? what does it show?
- `2026-04-09T19:41:00.363Z`: I would recommend then a large experiments on N=100 and about perft (btw: check the functional correctness in addition to metrics) and then plot... Then another experiment involving games but this time with N'=20, against Stockfish or each other... I suspect it can be time-consuming. The goal is not to have a reliable Elo, but rather show some *diversity* in the strenght
- `2026-04-09T19:59:04.950Z`: let's run the full N=100 and then plot some interesting stuff
- `2026-04-09T20:07:54.602Z`: please run N=100 and generate plots of interests
- `2026-04-09T20:08:02.047Z`: retry

## 4. Interaction Style

The key observation is that the intent was **not** to micro-manage the coding agent line by line.
The user mostly acted as a supervisor at the SPL-engineering level: setting goals, defining quality gates, correcting major misconceptions, and redirecting the work when it became conceptually wrong or behaviorally suspicious.
This is close to a Level-3-like ambition in the sense of supervising tasks and outcomes across multiple files and SE/SPLE activities, but it should not be read as a maturity claim that such a level has already been achieved.

| Signal | Count |
| --- | ---: |
| Median prompt length (characters) | 62 |
| Goal-setting prompts (heuristic) | 24 |
| Course-correction prompts (heuristic) | 14 |
| Quality-gate prompts (heuristic) | 28 |
| Status-sync prompts (heuristic) | 11 |
| Commit/documentation prompts (heuristic) | 9 |
| Broadly micromanagement-like prompts | 2 / 100 |

### What Supervision Looked Like

- High-level specification: the early prompts defined the mining pipeline, traceability requirements, cache policy, and expected outputs rather than prescribing internal code structure line by line.
- Conceptual correction: when the model drifted toward years, names, and editorial noise, the user redirected the agent toward a narrower and more executable feature space.
- Behavioral correction: when `CFG_NEGAMAX` turned out to be cosmetic, the intervention was at the level of feature honesty, not a review of every changed line.
- Quality gates: perft, legality, tournaments, and anchored Elo acted as the main governance mechanism.
- Incremental SPL refinement: features were repeatedly added, removed, promoted, constrained, or moved into commonality/setup space.

Representative supervision prompts from the engineering thread:

- `2026-03-01T10:33:31Z`: major review of the noisy feature model in FeatureIDE
- `2026-03-04T23:19:25Z`: “I want a real implementation of each feature”
- `2026-03-05T08:44:22Z`: “why are variants not passing?”
- `2026-04-02T12:29:39Z`: “most of the features are simply not fully implemented”
- `2026-04-05T11:41:59Z`: “search efficiency ... is it in the commonality space?”

## 5. Testing and Observation as the Main Control Loop

The sessions rely heavily on testing, not as a final validation step, but as the central mechanism for steering the work.

- Testing-related `exec_command` families in the engineering thread: **206**
- Benchmarking-related `exec_command` families in the engineering thread: **132**

Three kinds of evidence repeatedly shaped decisions:

- Functional gates: smoke runs, legality checks, and perft.
- Comparative observations: tournaments, Stockfish anchors, and Elo-oriented assessments.
- Structural observations: feature-model review, suspiciously small features, and later guarded-vs-span diagnostics.

This confirms that the endeavor was neither prompt-only ideation nor blind code generation.
It was an incremental engineering loop in which tests and measurements repeatedly triggered SPL-level redesign decisions.

## 6. Model Choice and Cost Note

The sessions also matter as a statement about *which* systems were used.

- Main engineering thread turn-context mix: `gpt-5.3-codex` x 773, `gpt-5.4` x 64
- Paper thread metadata: model `gpt-5.4` with reasoning effort `xhigh`
- Experiment thread metadata: model `gpt-5.4` with reasoning effort `xhigh`

This means the later analysis, experiment orchestration, and paper-drafting work relied on a frontier model (`GPT-5.4`) at extra-high reasoning effort.
The engineering story is therefore partly a frontier-model story and a costly one.
It remains unclear whether weaker closed models or open-weight models would show comparable SPL-engineering capabilities under the same conditions.

## 7. Main Takeaways for the Paper

Section 2 of the paper should foreground the following points:

- The endeavor started from a request to mine CPW into a traceable, cache-first local knowledge base rather than from an existing codebase.
- Supervision was mainly strategic and conceptual, not line-by-line code review.
- The work was incremental: features were refined, constrained, promoted, removed, or moved to commonality/setup space over time.
- Testing and benchmarking were central interaction mechanisms.
- The current results are exploratory and built with costly frontier systems, which matters for external validity.

## 8. Open Questions Raised by the Sessions

- How good are the currently implemented features, beyond compiling and passing current gates?
- How can partially implemented or suspicious features be detected earlier and more automatically?
- How should domain knowledge from CPW be operationalized to guide coding agents more reliably?
- How far can functional and performance testing be automated for family-wide assessment?
- Can substantially higher Elo levels be reached without collapsing the SPL into one tuned product?
- How different would the outcome be with weaker frontier models or open-weight coding agents?

