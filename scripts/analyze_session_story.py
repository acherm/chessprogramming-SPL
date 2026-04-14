#!/usr/bin/env python3

from __future__ import annotations

import json
import re
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


DEFAULT_WORKSPACE = Path("/Users/mathieuacher/SANDBOX/chessprogramming-vm")
DEFAULT_STATE_DB = Path("/Users/mathieuacher/.codex/state_5.sqlite")
OUTPUT_DIR = DEFAULT_WORKSPACE / "paper" / "data"


INTERACTION_RULES: list[tuple[str, list[str]]] = [
    (
        "status_sync",
        [
            r"^go$",
            r"^continue$",
            r"^retry$",
            r"^status\??$",
            r"^statu\??$",
            r"^yes please$",
            r"^please go ahead$",
        ],
    ),
    (
        "quality_gate",
        [
            r"\bperft\b",
            r"\blegality\b",
            r"\billegal\b",
            r"\bpass\b",
            r"\btest\b",
            r"\btournament\b",
            r"\bstockfish\b",
            r"\belo\b",
            r"\bmatch\b",
            r"\bbenchmark\b",
            r"\bassessment\b",
        ],
    ),
    (
        "course_correction",
        [
            r"\bmisunderstanding\b",
            r"\bbig general issue\b",
            r"\bnot fully implemented\b",
            r"\bstrange\b",
            r"\bwhy\b",
            r"\bproblem\b",
            r"\bI don't get\b",
            r"\bissue\b",
            r"\btoo much\b",
            r"\bunclear\b",
            r"\bwrong\b",
            r"\bcosmetic\b",
            r"\breview\b",
        ],
    ),
    (
        "documentation_commit",
        [
            r"\bcommit\b",
            r"\breadme\b",
            r"\bdocument\b",
            r"\breport\b",
        ],
    ),
    (
        "goal_setting",
        [
            r"\bi'd like\b",
            r"\bplease\b",
            r"\blet's\b",
            r"\bcan you\b",
            r"\bimplement\b",
            r"\bbuild\b",
            r"\borganize\b",
            r"\bderive\b",
            r"\badd\b",
            r"\bpromote\b",
            r"\bmove to\b",
            r"\bimprove\b",
        ],
    ),
]


MICROMANAGEMENT_PATTERNS = [
    r"\bline\s+\d+",
    r"\breplace\b",
    r"\brename\b",
    r"\bexact\b",
    r"```",
    r"/Users/",
    r"\b[A-Za-z0-9_/-]+\.(?:c|h|py|md|json|xml)\b",
]


BROKEN_THREAD_PATTERN = "problematic since it contains an image"


@dataclass
class ThreadSummary:
    id: str
    created_at: int
    title: str
    first_user_message: str
    model: str | None
    reasoning_effort: str | None
    tokens_used: int
    rollout_path: Path
    prompt_count: int
    first_prompt_at: str | None
    last_prompt_at: str | None
    tool_calls: Counter[str]
    command_categories: Counter[str]
    model_mix: Counter[str]
    prompts: list[tuple[str, str]]


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def classify_interaction(text: str) -> str:
    lowered = normalize(text).lower()
    for category, patterns in INTERACTION_RULES:
        if any(re.search(pattern, lowered) for pattern in patterns):
            return category
    return "other"


def parse_rollout(rollout_path: Path) -> tuple[list[tuple[str, str]], Counter[str], Counter[str], Counter[str]]:
    prompts: list[tuple[str, str]] = []
    tool_calls: Counter[str] = Counter()
    command_categories: Counter[str] = Counter()
    model_mix: Counter[str] = Counter()

    for line in rollout_path.open("r", encoding="utf-8", errors="ignore"):
        record = json.loads(line)
        if record.get("type") == "event_msg" and record.get("payload", {}).get("type") == "user_message":
            prompts.append((record["timestamp"], record["payload"]["message"]))
        elif record.get("type") == "response_item":
            payload = record.get("payload", {})
            if payload.get("type") == "function_call":
                name = payload.get("name", "")
                tool_calls[name] += 1
                if name == "exec_command":
                    try:
                        arguments = json.loads(payload.get("arguments", "{}"))
                    except json.JSONDecodeError:
                        arguments = {"cmd": payload.get("arguments", "")}
                    cmd = str(arguments.get("cmd", "")).strip()
                    if re.search(r"cutechess-cli|stockfish|\belo\b|\bmatch\b|\btournament\b", cmd, re.IGNORECASE):
                        command_categories["benchmarking"] += 1
                    elif re.search(r"^pytest\b|\bperft\b|\bsmoke\b|\blegality\b|\buci\b", cmd, re.IGNORECASE):
                        command_categories["testing"] += 1
                    elif re.search(r"^git\b", cmd, re.IGNORECASE):
                        command_categories["versioning"] += 1
                    elif re.search(r"^rg\b|^sed\b|^cat\b|^ls\b|^find\b|^wc\b|^head\b|^tail\b|^nl\b", cmd, re.IGNORECASE):
                        command_categories["exploration"] += 1
                    else:
                        command_categories["other"] += 1
        elif record.get("type") == "turn_context":
            model_mix[record["payload"].get("model", "unknown")] += 1

    return prompts, tool_calls, command_categories, model_mix


def load_threads(workspace: Path, state_db: Path) -> list[ThreadSummary]:
    conn = sqlite3.connect(state_db)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        select id, created_at, title, first_user_message, model, reasoning_effort, tokens_used, rollout_path
        from threads
        where cwd = ?
        order by created_at
        """,
        (str(workspace),),
    ).fetchall()
    conn.close()

    threads: list[ThreadSummary] = []
    for row in rows:
        first = normalize(row["first_user_message"])
        if BROKEN_THREAD_PATTERN in first:
            continue
        rollout_path = Path(row["rollout_path"])
        if not rollout_path.exists():
            continue
        prompts, tool_calls, command_categories, model_mix = parse_rollout(rollout_path)
        threads.append(
            ThreadSummary(
                id=row["id"],
                created_at=row["created_at"],
                title=row["title"],
                first_user_message=row["first_user_message"],
                model=row["model"],
                reasoning_effort=row["reasoning_effort"],
                tokens_used=row["tokens_used"],
                rollout_path=rollout_path,
                prompt_count=len(prompts),
                first_prompt_at=prompts[0][0] if prompts else None,
                last_prompt_at=prompts[-1][0] if prompts else None,
                tool_calls=tool_calls,
                command_categories=command_categories,
                model_mix=model_mix,
                prompts=prompts,
            )
        )
    return threads


def load_cache_metrics(workspace: Path) -> dict[str, int | str]:
    manifest_path = workspace / "data" / "chessprogramming_cache" / "manifest.json"
    discovery_state_path = workspace / "data" / "chessprogramming_cache" / "discovery_state.json"
    run_report_path = workspace / "outputs" / "run_report.md"
    metrics: dict[str, int | str] = {}
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        metrics["cached_pages"] = len(manifest.get("pages", []))
    if discovery_state_path.exists():
        state = json.loads(discovery_state_path.read_text())
        metrics["seed_titles"] = len(state.get("seed_titles", []))
        metrics["visited_pages"] = len(state.get("visited", []))
        metrics["failed_pages"] = len(state.get("failed", []))
        metrics["warnings"] = len(state.get("warnings", []))
        metrics["stop_reason"] = state.get("stop_reason", "")
    if run_report_path.exists():
        metrics["run_report_path"] = str(run_report_path)
    return metrics


def choose_representative_prompts(
    prompts: list[tuple[str, str]], limit: int = 5, match: str | None = None, max_chars: int = 420
) -> list[tuple[str, str]]:
    selected: list[tuple[str, str]] = []
    for timestamp, message in prompts:
        text = normalize(message)
        if match and not re.search(match, text, re.IGNORECASE):
            continue
        if len(text) > max_chars:
            text = text[: max_chars - 1].rstrip() + "…"
        selected.append((timestamp, text))
        if len(selected) >= limit:
            break
    return selected


def prompt_style_metrics(prompts: list[tuple[str, str]]) -> dict[str, int | float]:
    interaction_counts: Counter[str] = Counter()
    micromanagement_like = 0
    lengths: list[int] = []
    for _, message in prompts:
        text = normalize(message)
        lengths.append(len(text))
        interaction_counts[classify_interaction(text)] += 1
        if any(re.search(pattern, text, re.IGNORECASE) for pattern in MICROMANAGEMENT_PATTERNS):
            micromanagement_like += 1
    lengths_sorted = sorted(lengths)
    median_length = lengths_sorted[len(lengths_sorted) // 2] if lengths_sorted else 0
    return {
        "median_prompt_chars": median_length,
        "micromanagement_like_prompts": micromanagement_like,
        "goal_setting": interaction_counts["goal_setting"],
        "course_correction": interaction_counts["course_correction"],
        "quality_gate": interaction_counts["quality_gate"],
        "status_sync": interaction_counts["status_sync"],
        "documentation_commit": interaction_counts["documentation_commit"],
        "other": interaction_counts["other"],
    }


def active_day_count(prompts: list[tuple[str, str]]) -> int:
    days = {
        datetime.fromisoformat(timestamp.replace("Z", "+00:00")).date().isoformat()
        for timestamp, _ in prompts
    }
    return len(days)


def markdown_thread_table(threads: list[ThreadSummary]) -> list[str]:
    lines = [
        "| Thread | Focus | User prompts | Model metadata | Turn-context model mix | Tokens used |",
        "| --- | --- | ---: | --- | --- | ---: |",
    ]
    for thread in threads:
        focus = normalize(thread.first_user_message)[:70] + ("..." if len(normalize(thread.first_user_message)) > 70 else "")
        model_meta = f"`{thread.model or 'unknown'}`"
        if thread.reasoning_effort:
            model_meta += f" / `{thread.reasoning_effort}`"
        model_mix = ", ".join(f"`{name}` x {count}" for name, count in thread.model_mix.items())
        lines.append(
            f"| `{thread.id[:8]}` | {focus} | {thread.prompt_count} | {model_meta} | {model_mix} | {thread.tokens_used:,} |"
        )
    return lines


def build_report(workspace: Path, threads: list[ThreadSummary]) -> str:
    engineering = next(thread for thread in threads if "feature model" in thread.first_user_message.lower())
    paper_thread = next(thread for thread in threads if "write a paper for variability" in thread.first_user_message.lower())
    experiment_thread = next(thread for thread in threads if "time to perform experiments" in thread.first_user_message.lower())
    cache = load_cache_metrics(workspace)
    total_tokens = sum(thread.tokens_used for thread in threads)
    style = prompt_style_metrics(engineering.prompts)
    engineering_active_days = active_day_count(engineering.prompts)

    phase_prompts = [
        ("Bootstrapping a local CPW snapshot and mining pipeline", choose_representative_prompts(engineering.prompts, limit=4)),
        ("Repairing and constraining the feature space", choose_representative_prompts(engineering.prompts, limit=4, match=r"feature model|constraint|mandatory|optional|misunderstanding|improve the pipeline")),
        ("Turning the model into an executable SPL in C", choose_representative_prompts(engineering.prompts, limit=5, match=r"product line|real implementation|legality|derive one variant|perft")),
        ("Refining features, modularity, commonality, and setup", choose_representative_prompts(engineering.prompts, limit=6, match=r"not fully implemented|phase 1|phase 2|promote|commonality|setup")),
        ("Scaling experiments and paper synthesis", choose_representative_prompts(experiment_thread.prompts + paper_thread.prompts, limit=6)),
    ]
    phase_deliverables = {
        "Bootstrapping a local CPW snapshot and mining pipeline": [
            "A safe, resumable, cache-first CPW acquisition pipeline instead of live scraping on every turn.",
            "The first local corpus, traceability artifacts, and engine-feature mining outputs.",
        ],
        "Repairing and constraining the feature space": [
            "A shift from noisy wiki terms toward executable chess-engine variation points.",
            "Explicit cleanup of editorial artifacts and addition of core anchors such as board-representation techniques.",
        ],
        "Turning the model into an executable SPL in C": [
            "A first C product line with generated configuration headers, compile-time flags, and derivable variants.",
            "Initial legality, protocol, and perft-oriented functionality to make variants compile and run.",
        ],
        "Refining features, modularity, commonality, and setup": [
            "Substantial rework of shallow features, modularization of search/evaluation/setup code, and pairwise-combination checks.",
            "Promotion, removal, or relocation of features as the line between configurable variability and commonality became clearer.",
        ],
        "Scaling experiments and paper synthesis": [
            "Family-wide screening, realistic tournaments, plots, and the paper itself.",
            "A transition from 'can it compile?' to 'how robust and diverse are the derived variants?'",
        ],
    }

    lines = [
        "# Session Story Report",
        "",
        "This report focuses on the *story* of the endeavor rather than only the artifact inventory.",
        "It re-analyzes the local Codex rollouts and thread metadata to describe how the work was actually carried out: which prompts drove the work, what was developed and gathered at each stage, how a local snapshot of Chessprogramming.org (CPW) was built and reused, what kind of supervision the human provided, and how testing and observations governed the interaction.",
        "",
        "## 1. Scope",
        "",
        f"- Workspace: `{workspace}`",
        f"- Relevant Codex threads analyzed: **{len(threads)}**",
        f"- Total tokens recorded across these threads: **{total_tokens:,}**",
        f"- Main engineering thread prompts: **{engineering.prompt_count}** over **{engineering_active_days}** active days",
        f"- Experiment thread prompts: **{experiment_thread.prompt_count}**",
        f"- Paper thread prompts: **{paper_thread.prompt_count}**",
        "",
        "### Thread Set",
        "",
        *markdown_thread_table(threads),
        "",
        "## 2. Starting Point: From Wiki Knowledge to a Local CPW Snapshot",
        "",
        "A defining aspect of the sessions is that the work did **not** start from an existing codebase to modify, nor from live web queries on every turn.",
        "The initial prompts asked for a traceable feature model and comparison table derived from CPW, and almost immediately constrained the acquisition strategy: use a safe, resumable, cache-first workflow rather than an aggressive scraper.",
        "The result is a local CPW snapshot that became the shared substrate for all later SPL work.",
        "",
        f"- Seed titles in discovery state: **{cache.get('seed_titles', 'n/a')}**",
        f"- Visited pages during snapshot crawl: **{cache.get('visited_pages', 'n/a')}**",
        f"- Cached page entries in `manifest.json`: **{cache.get('cached_pages', 'n/a')}**",
        f"- Failed page fetches recorded in discovery state: **{cache.get('failed_pages', 'n/a')}**",
        f"- Recorded crawl warnings: **{cache.get('warnings', 'n/a')}**",
        f"- Crawl stop reason: `{cache.get('stop_reason', 'n/a')}`",
        "",
        "This local snapshot matters methodologically.",
        "Later feature-model revisions, C implementation work, benchmarking scripts, and even the paper itself were grounded in a stable offline corpus rather than a moving web target.",
        "The challenge was therefore to operationalize a wiki-like body of knowledge into SPL artifacts, not simply to automate edits on an existing engine repository.",
        "",
        "## 3. Timeline and Main Deliverables",
        "",
    ]

    for title, prompts in phase_prompts:
        lines.append(f"### {title}")
        lines.append("")
        lines.append("What was developed or gathered in this phase:")
        lines.append("")
        for deliverable in phase_deliverables[title]:
            lines.append(f"- {deliverable}")
        lines.append("")
        lines.append("Representative prompts:")
        lines.append("")
        for timestamp, prompt in prompts:
            lines.append(f"- `{timestamp}`: {prompt}")
        lines.append("")

    lines.extend(
        [
            "## 4. Interaction Style",
            "",
            "The key observation is that the intent was **not** to micro-manage the coding agent line by line.",
            "The user mostly acted as a supervisor at the SPL-engineering level: setting goals, defining quality gates, correcting major misconceptions, and redirecting the work when it became conceptually wrong or behaviorally suspicious.",
            "This is close to a Level-3-like ambition in the sense of supervising tasks and outcomes across multiple files and SE/SPLE activities, but it should not be read as a maturity claim that such a level has already been achieved.",
            "",
            "| Signal | Count |",
            "| --- | ---: |",
            f"| Median prompt length (characters) | {style['median_prompt_chars']} |",
            f"| Goal-setting prompts (heuristic) | {style['goal_setting']} |",
            f"| Course-correction prompts (heuristic) | {style['course_correction']} |",
            f"| Quality-gate prompts (heuristic) | {style['quality_gate']} |",
            f"| Status-sync prompts (heuristic) | {style['status_sync']} |",
            f"| Commit/documentation prompts (heuristic) | {style['documentation_commit']} |",
            f"| Broadly micromanagement-like prompts | {style['micromanagement_like_prompts']} / {engineering.prompt_count} |",
            "",
            "### What Supervision Looked Like",
            "",
            "- High-level specification: the early prompts defined the mining pipeline, traceability requirements, cache policy, and expected outputs rather than prescribing internal code structure line by line.",
            "- Conceptual correction: when the model drifted toward years, names, and editorial noise, the user redirected the agent toward a narrower and more executable feature space.",
            "- Behavioral correction: when `CFG_NEGAMAX` turned out to be cosmetic, the intervention was at the level of feature honesty, not a review of every changed line.",
            "- Quality gates: perft, legality, tournaments, and anchored Elo acted as the main governance mechanism.",
            "- Incremental SPL refinement: features were repeatedly added, removed, promoted, constrained, or moved into commonality/setup space.",
            "",
            "Representative supervision prompts from the engineering thread:",
            "",
            "- `2026-03-01T10:33:31Z`: major review of the noisy feature model in FeatureIDE",
            "- `2026-03-04T23:19:25Z`: “I want a real implementation of each feature”",
            "- `2026-03-05T08:44:22Z`: “why are variants not passing?”",
            "- `2026-04-02T12:29:39Z`: “most of the features are simply not fully implemented”",
            "- `2026-04-05T11:41:59Z`: “search efficiency ... is it in the commonality space?”",
            "",
            "## 5. Testing and Observation as the Main Control Loop",
            "",
            "The sessions rely heavily on testing, not as a final validation step, but as the central mechanism for steering the work.",
            "",
            f"- Testing-related `exec_command` families in the engineering thread: **{engineering.command_categories.get('testing', 0)}**",
            f"- Benchmarking-related `exec_command` families in the engineering thread: **{engineering.command_categories.get('benchmarking', 0)}**",
            "",
            "Three kinds of evidence repeatedly shaped decisions:",
            "",
            "- Functional gates: smoke runs, legality checks, and perft.",
            "- Comparative observations: tournaments, Stockfish anchors, and Elo-oriented assessments.",
            "- Structural observations: feature-model review, suspiciously small features, and later guarded-vs-span diagnostics.",
            "",
            "This confirms that the endeavor was neither prompt-only ideation nor blind code generation.",
            "It was an incremental engineering loop in which tests and measurements repeatedly triggered SPL-level redesign decisions.",
            "",
            "## 6. Model Choice and Cost Note",
            "",
            "The sessions also matter as a statement about *which* systems were used.",
            "",
            f"- Main engineering thread turn-context mix: {', '.join(f'`{m}` x {c}' for m, c in engineering.model_mix.items())}",
            f"- Paper thread metadata: model `{paper_thread.model}` with reasoning effort `{paper_thread.reasoning_effort}`",
            f"- Experiment thread metadata: model `{experiment_thread.model}` with reasoning effort `{experiment_thread.reasoning_effort}`",
            "",
            "This means the later analysis, experiment orchestration, and paper-drafting work relied on a frontier model (`GPT-5.4`) at extra-high reasoning effort.",
            "The engineering story is therefore partly a frontier-model story and a costly one.",
            "It remains unclear whether weaker closed models or open-weight models would show comparable SPL-engineering capabilities under the same conditions.",
            "",
            "## 7. Main Takeaways for the Paper",
            "",
            "Section 2 of the paper should foreground the following points:",
            "",
            "- The endeavor started from a request to mine CPW into a traceable, cache-first local knowledge base rather than from an existing codebase.",
            "- Supervision was mainly strategic and conceptual, not line-by-line code review.",
            "- The work was incremental: features were refined, constrained, promoted, removed, or moved to commonality/setup space over time.",
            "- Testing and benchmarking were central interaction mechanisms.",
            "- The current results are exploratory and built with costly frontier systems, which matters for external validity.",
            "",
            "## 8. Open Questions Raised by the Sessions",
            "",
            "- How good are the currently implemented features, beyond compiling and passing current gates?",
            "- How can partially implemented or suspicious features be detected earlier and more automatically?",
            "- How should domain knowledge from CPW be operationalized to guide coding agents more reliably?",
            "- How far can functional and performance testing be automated for family-wide assessment?",
            "- Can substantially higher Elo levels be reached without collapsing the SPL into one tuned product?",
            "- How different would the outcome be with weaker frontier models or open-weight coding agents?",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    threads = load_threads(DEFAULT_WORKSPACE, DEFAULT_STATE_DB)
    report = build_report(DEFAULT_WORKSPACE, threads)
    (OUTPUT_DIR / "session_story_report.md").write_text(report + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
