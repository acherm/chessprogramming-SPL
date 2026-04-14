# Session Bundle

This directory contains the Codex-session material included in the replication artifact.

- `engineering_thread_raw.jsonl` is the full engineering session that begins with the feature-model prompt.
- `engineering_thread.md` and `engineering_thread_turns.json` are normalized exports of that raw rollout.
- `design_variant_experiments_trimmed.md` and `design_variant_experiments_trimmed.json` are normalized exports of the experiment thread.

The experiment thread was trimmed selectively rather than truncated. The excluded turns are the ones whose user prompts were explicitly about editing paper text or modifying `paper/main.tex`. The exact dropped turn identifiers are stored as source line numbers from the original rollout.
