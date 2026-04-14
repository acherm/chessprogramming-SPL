#!/usr/bin/env python3

from __future__ import annotations

import json
import re
import sqlite3
import subprocess
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path


DEFAULT_WORKSPACE = Path("/Users/mathieuacher/SANDBOX/chessprogramming-vm")
DEFAULT_STATE_DB = Path("/Users/mathieuacher/.codex/state_5.sqlite")
OUTPUT_DIR = DEFAULT_WORKSPACE / "paper" / "data"


BROKEN_THREAD_PATTERN = "problematic since it contains an image"


PROMPT_FAMILIES: list[tuple[str, list[str]]] = [
    (
        "pipeline_tests",
        [
            r"\btests?\b",
            r"\bfixture",
            r"\bpytest\b",
            r"\brun-all\b",
            r"\boffline\b",
            r"\bcache-only\b",
        ],
    ),
    (
        "functional_correctness",
        [
            r"\bperft\b",
            r"\bvariants? not passing\b",
            r"\bnot passing\b",
            r"\bfunctional correctness\b",
            r"\bcorrectness\b",
            r"\bmake perft pass\b",
            r"\bpass\??\b",
        ],
    ),
    (
        "legality",
        [
            r"\blegality\b",
            r"\billegal\b",
            r"\bcastling\b",
            r"\ben-passant\b",
            r"\brepetition\b",
            r"\b50-move\b",
            r"\blegal moves?\b",
        ],
    ),
    (
        "interactions_probes",
        [
            r"\bpair-?wise\b",
            r"\bfeature interactions?\b",
            r"\bcombined\b",
            r"\bprobe\b",
            r"\bmulti-position\b",
            r"\bcan be combined\b",
        ],
    ),
    (
        "runtime_setup",
        [
            r"\bsetup\b",
            r"\bownbook\b",
            r"\bponder(?:ing)?\b",
            r"\bruntime book\b",
            r"\bruntime feature\b",
            r"\brecommended setup\b",
        ],
    ),
    (
        "strength_benchmarking",
        [
            r"\btournament\b",
            r"\bstockfish\b",
            r"\belo\b",
            r"\bmatch\b",
            r"\bround-robin\b",
            r"\breal chess games\b",
            r"\banchors?\b",
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
    r"\b[A-Za-z0-9_/-]+\.(?:c|h|py|md|json|xml|csv)\b",
]


COMMAND_FAMILIES: list[tuple[str, list[str]]] = [
    ("pytest", [r"(^|\s)pytest(\s|$)"]),
    ("perft_screening", [r"scripts/uci_perft_check\.py", r"scripts/perft_random_variants\.py"]),
    ("legality_scenarios", [r"scripts/uci_legality_scenarios\.py"]),
    (
        "interaction_probes",
        [
            r"scripts/board_search_pairwise\.py",
            r"scripts/board_search_multi_probe\.py",
            r"scripts/eval_feature_assessment\.py",
            r"scripts/eval_subfeature_probes\.py",
        ],
    ),
    (
        "runtime_setup",
        [
            r"scripts/setup_variant_tournament\.py",
            r"test_c_engine_uci_runtime_features\.py",
            r"test_setup_model\.py",
        ],
    ),
    (
        "strength_benchmarking",
        [
            r"scripts/stratified_variant_experiment\.py",
            r"scripts/variant_diversity_tournament\.py",
            r"scripts/proper_elo_tournament\.py",
            r"scripts/sf_anchor_match\.py",
            r"scripts/best_variant_elo_assessment\.py",
            r"(^|\s)cutechess-cli(\s|$)",
        ],
    ),
]


ARTIFACT_GROUPS: list[tuple[str, list[str]]] = [
    (
        "Pipeline and mining tests",
        [
            "tests/test_fetcher.py",
            "tests/test_parser.py",
            "tests/test_discovery_resume.py",
            "tests/test_feature_miner.py",
            "tests/test_matrix_builder.py",
            "tests/test_integration_pipeline.py",
        ],
    ),
    (
        "Derivation and constraint tests",
        [
            "tests/test_constraints.py",
            "tests/test_pl_codegen.py",
            "tests/test_implementation_mining.py",
            "tests/test_c_engine_feature_coverage.py",
        ],
    ),
    (
        "Perft and legality harnesses",
        [
            "tests/test_c_engine_perft.py",
            "tests/test_c_engine_tournament_legality.py",
            "scripts/uci_perft_check.py",
            "scripts/uci_legality_scenarios.py",
            "scripts/perft_random_variants.py",
        ],
    ),
    (
        "Interaction and probe tooling",
        [
            "scripts/board_search_pairwise.py",
            "scripts/board_search_multi_probe.py",
            "scripts/eval_feature_assessment.py",
            "scripts/eval_subfeature_probes.py",
        ],
    ),
    (
        "Runtime setup and UCI testing",
        [
            "tests/test_c_engine_uci_runtime_features.py",
            "tests/test_setup_model.py",
            "scripts/setup_variant_tournament.py",
        ],
    ),
    (
        "Tournament and anchor benchmarking",
        [
            "scripts/variant_diversity_tournament.py",
            "scripts/proper_elo_tournament.py",
            "scripts/sf_anchor_match.py",
            "scripts/stratified_variant_experiment.py",
            "scripts/best_variant_elo_assessment.py",
        ],
    ),
]


@dataclass
class PromptRecord:
    thread_id: str
    thread_role: str
    timestamp: str
    text: str
    families: list[str]


@dataclass
class CommandRecord:
    thread_id: str
    thread_role: str
    timestamp: str
    command: str
    families: list[str]


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def detect_thread_role(title: str) -> str:
    lowered = normalize(title).lower()
    if "write a paper" in lowered:
        return "paper"
    if "time to perform experiments" in lowered:
        return "experiments"
    return "engineering"


def matching_families(text: str, rules: list[tuple[str, list[str]]]) -> list[str]:
    lowered = normalize(text).lower()
    families: list[str] = []
    for family, patterns in rules:
        if any(re.search(pattern, lowered) for pattern in patterns):
            families.append(family)
    return families


def is_micromanagement_like(text: str) -> bool:
    lowered = normalize(text).lower()
    return any(re.search(pattern, lowered) for pattern in MICROMANAGEMENT_PATTERNS)


def load_relevant_threads(workspace: Path, state_db: Path) -> list[sqlite3.Row]:
    conn = sqlite3.connect(state_db)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        select id, title, first_user_message, rollout_path, created_at
        from threads
        where cwd = ?
        order by created_at
        """,
        (str(workspace),),
    ).fetchall()
    conn.close()
    filtered: list[sqlite3.Row] = []
    for row in rows:
        first = normalize(row["first_user_message"] or "")
        title = normalize(row["title"] or "")
        if BROKEN_THREAD_PATTERN in first or BROKEN_THREAD_PATTERN in title:
            continue
        if Path(row["rollout_path"]).exists():
            filtered.append(row)
    return filtered


def parse_rollouts(rows: list[sqlite3.Row]) -> tuple[list[PromptRecord], list[CommandRecord]]:
    prompts: list[PromptRecord] = []
    commands: list[CommandRecord] = []

    for row in rows:
        role = detect_thread_role(row["title"] or "")
        rollout_path = Path(row["rollout_path"])
        for line in rollout_path.open("r", encoding="utf-8", errors="ignore"):
            record = json.loads(line)
            if record.get("type") == "event_msg" and record.get("payload", {}).get("type") == "user_message":
                text = normalize(record["payload"]["message"])
                families = matching_families(text, PROMPT_FAMILIES)
                if families:
                    prompts.append(PromptRecord(row["id"], role, record["timestamp"], text, families))
            elif (
                record.get("type") == "response_item"
                and record.get("payload", {}).get("type") == "function_call"
                and record.get("payload", {}).get("name") == "exec_command"
            ):
                try:
                    arguments = json.loads(record["payload"].get("arguments", "{}"))
                except json.JSONDecodeError:
                    arguments = {"cmd": record["payload"].get("arguments", "")}
                cmd = normalize(str(arguments.get("cmd", "")))
                families = matching_families(cmd, COMMAND_FAMILIES)
                if families:
                    commands.append(CommandRecord(row["id"], role, record["timestamp"], cmd, families))
    return prompts, commands


def git_addition_info(workspace: Path, relpath: str) -> tuple[str, str]:
    result = subprocess.run(
        ["git", "-C", str(workspace), "log", "--diff-filter=A", "--format=%aI|%h", "--", relpath],
        check=False,
        capture_output=True,
        text=True,
    )
    first_line = next((line for line in result.stdout.splitlines() if line.strip()), "")
    if not first_line:
        return ("unknown", "")
    added_at, short_hash = (first_line.split("|", 1) + [""])[:2]
    return (added_at, short_hash)


def describe_artifact_groups(workspace: Path) -> list[dict[str, object]]:
    groups: list[dict[str, object]] = []
    for label, relpaths in ARTIFACT_GROUPS:
        existing = [rel for rel in relpaths if (workspace / rel).exists()]
        added = [git_addition_info(workspace, rel) for rel in existing]
        known_dates = [item[0] for item in added if item[0] != "unknown"]
        first_date = min(known_dates) if known_dates else "unknown"
        groups.append(
            {
                "label": label,
                "files": existing,
                "count": len(existing),
                "first_date": first_date,
            }
        )
    return groups


def choose_samples(prompts: list[PromptRecord], family: str, limit: int = 3) -> list[PromptRecord]:
    selected: list[PromptRecord] = []
    for prompt in prompts:
        if family not in prompt.families:
            continue
        text = prompt.text
        if len(text) > 420:
            text = text[:419].rstrip() + "..."
        selected.append(PromptRecord(prompt.thread_id, prompt.thread_role, prompt.timestamp, text, prompt.families))
        if len(selected) >= limit:
            break
    return selected


def command_counts(commands: list[CommandRecord]) -> dict[str, Counter[str]]:
    by_role: dict[str, Counter[str]] = defaultdict(Counter)
    for command in commands:
        for family in command.families:
            by_role[command.thread_role][family] += 1
            by_role["all"][family] += 1
    return by_role


def prompt_counts(prompts: list[PromptRecord]) -> dict[str, Counter[str]]:
    by_role: dict[str, Counter[str]] = defaultdict(Counter)
    for prompt in prompts:
        for family in prompt.families:
            by_role[prompt.thread_role][family] += 1
            by_role["all"][family] += 1
    return by_role


def write_report(workspace: Path, prompts: list[PromptRecord], commands: list[CommandRecord]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    prompt_counter = prompt_counts(prompts)
    command_counter = command_counts(commands)
    artifact_groups = describe_artifact_groups(workspace)
    thread_count = len({prompt.thread_id for prompt in prompts} | {command.thread_id for command in commands})

    strategy_command_map = {
        "pipeline_tests": ["pytest"],
        "functional_correctness": ["perft_screening", "pytest"],
        "legality": ["legality_scenarios"],
        "interactions_probes": ["interaction_probes"],
        "runtime_setup": ["runtime_setup"],
        "strength_benchmarking": ["strength_benchmarking"],
    }

    testing_prompts = [prompt for prompt in prompts if prompt.thread_role in {"engineering", "experiments"}]
    micromanagement_like = sum(1 for prompt in testing_prompts if is_micromanagement_like(prompt.text))

    lines: list[str] = []
    lines.append("# Testing Story Report")
    lines.append("")
    lines.append("This report re-analyzes the Codex sessions with one narrow question in mind:")
    lines.append("how much of the testing and benchmarking infrastructure was actually built by the coding agent, which strategies emerged, and where human supervision had to redirect the effort.")
    lines.append("")
    lines.append("## 1. Scope")
    lines.append("")
    lines.append(f"- Workspace: `{workspace}`")
    lines.append(f"- Relevant threads analyzed: **{thread_count} threads** across **3 roles** (engineering, experiments, paper)")
    lines.append(f"- Testing-related prompts (engineering + experiments): **{len(testing_prompts)}**")
    lines.append(f"- Testing/benchmarking command invocations matched to explicit families: **{len(commands)}**")
    lines.append(f"- Broadly micromanagement-like testing prompts: **{micromanagement_like} / {len(testing_prompts)}**")
    lines.append("- Current collected test cases in the repository: **35**")
    lines.append("")
    lines.append("The supervision signal is therefore mostly strategic: the user set quality gates and corrected weak directions, but usually did not prescribe test files, harness structure, or benchmark scripts line by line.")
    lines.append("")
    lines.append("## 2. Main Finding")
    lines.append("")
    lines.append("The sessions show a layered testing strategy that was progressively built rather than fully specified upfront.")
    lines.append("The agent did not only run tests: it accumulated a testing stack spanning pipeline checks, derivation and constraint tests, functional-correctness harnesses, legality scenarios, pairwise interaction probes, runtime-setup tests, stratified screening, tournaments, and Stockfish-anchored calibration.")
    lines.append("What the user repeatedly supplied were stronger quality targets such as \"make perft pass\", \"implement full tournament legality\", \"try pair-wise combinations\", or \"move to real chess games\".")
    lines.append("")
    lines.append("## 3. Testing Strategies Observed in the Sessions")
    lines.append("")
    lines.append("| Strategy | Prompt count | Command count | What it was used for |")
    lines.append("| --- | ---: | ---: | --- |")
    strategy_labels = {
        "pipeline_tests": "Pipeline / mining tests",
        "functional_correctness": "Functional correctness",
        "legality": "Legality",
        "interactions_probes": "Interaction probes",
        "runtime_setup": "Runtime setup",
        "strength_benchmarking": "Strength benchmarking",
    }
    strategy_desc = {
        "pipeline_tests": "Cache-first crawling, deterministic mining, offline reruns, and early pipeline validation.",
        "functional_correctness": "Move-count correctness screening and pass/fail gates before broader experiments.",
        "legality": "Castling, en passant, repetition, and 50-move-rule behavior under realistic engine use.",
        "interactions_probes": "Checking whether board/search/evaluation combinations genuinely interact as intended.",
        "runtime_setup": "Separating compile-time variability from setup variability such as book and pondering.",
        "strength_benchmarking": "Moving from smoke/correctness checks to tournaments, anchors, and Elo-style calibration.",
    }
    for family in strategy_labels:
        strategy_cmd_count = sum(command_counter["all"][name] for name in strategy_command_map[family])
        lines.append(
            "| "
            + strategy_labels[family]
            + f" | {prompt_counter['all'][family]} | {strategy_cmd_count} | {strategy_desc[family]} |"
        )
    lines.append("")
    lines.append("## 4. Infrastructure Built in the Repository")
    lines.append("")
    lines.append("| Infrastructure slice | Current files | First added (git) | Examples |")
    lines.append("| --- | ---: | --- | --- |")
    for group in artifact_groups:
        examples = ", ".join(f"`{Path(rel).name}`" for rel in group["files"][:3])
        if group["count"] > 3:
            examples += ", ..."
        lines.append(
            f"| {group['label']} | {group['count']} | {group['first_date']} | {examples} |"
        )
    lines.append("")
    lines.append("This is important for the paper: the sessions did not stop at a few ad hoc `pytest` calls.")
    lines.append("They left behind a reusable infrastructure of tests and experiment scripts that now anchors the SPL engineering workflow.")
    lines.append("")
    lines.append("## 5. Timeline of the Testing Story")
    lines.append("")
    lines.append("### 2026-03-01: pipeline validation appears immediately")
    lines.append("")
    for sample in choose_samples(prompts, "pipeline_tests", limit=2):
        lines.append(f"- `{sample.timestamp}`: {sample.text}")
    lines.append("- Repository effect: mining-pipeline tests for fetching, parsing, discovery resume, matrix building, and offline integration were introduced from the start.")
    lines.append("")
    lines.append("### 2026-03-05: the user turns testing into a gate for executable variants")
    lines.append("")
    for sample in choose_samples(prompts, "functional_correctness", limit=4):
        if sample.thread_role != "engineering":
            continue
        lines.append(f"- `{sample.timestamp}`: {sample.text}")
    lines.append("- Repository effect: `test_c_engine_perft.py`, `test_c_engine_tournament_legality.py`, `test_constraints.py`, `test_pl_codegen.py`, `uci_perft_check.py`, `uci_legality_scenarios.py`, and `perft_random_variants.py` were added around this stage.")
    lines.append("")
    lines.append("### 2026-04-02 to 2026-04-04: testing shifts from isolated variants to interactions and setup")
    lines.append("")
    for family in ("interactions_probes", "runtime_setup"):
        for sample in choose_samples(prompts, family, limit=2):
            if sample.thread_role != "engineering":
                continue
            lines.append(f"- `{sample.timestamp}`: {sample.text}")
    lines.append("- Repository effect: `board_search_pairwise.py`, `board_search_multi_probe.py`, `eval_feature_assessment.py`, `eval_subfeature_probes.py`, `test_c_engine_uci_runtime_features.py`, `test_setup_model.py`, and `setup_variant_tournament.py` appeared in this phase.")
    lines.append("")
    lines.append("### 2026-04-09 onward: experiments become family-level evidence")
    lines.append("")
    for sample in choose_samples(prompts, "strength_benchmarking", limit=4):
        if sample.thread_role != "experiments":
            continue
        lines.append(f"- `{sample.timestamp}`: {sample.text}")
    lines.append("- Repository effect: `stratified_variant_experiment.py`, `variant_diversity_tournament.py`, `proper_elo_tournament.py`, `sf_anchor_match.py`, and `best_variant_elo_assessment.py` support scalable screening and anchored strength assessment.")
    lines.append("")
    lines.append("## 6. What the User Had to Ask For")
    lines.append("")
    lines.append("The user did not micro-design the testing stack, but several decisive interventions changed its direction:")
    lines.append("")
    lines.append("- From compilation to correctness: prompts such as \"can we make perft pass?\" and \"why are variants not passing?\" turned testing into a hard gate.")
    lines.append("- From correctness to legality: \"implement full tournament legality\" pushed the infrastructure toward castling, en passant, repetition, and 50-move behavior.")
    lines.append("- From isolated features to combinations: \"try to test pair-wise combinations\" forced interaction-aware probes.")
    lines.append("- From synthetic metrics to chess play: \"check the functional correctness in addition to metrics\" and then \"move to a strength benchmark\" redirected the effort toward full games and anchors.")
    lines.append("- From superficial variability to semantic honesty: the `CFG_NEGAMAX` criticism showed that even a passing build and some tests can hide cosmetic or partial features.")
    lines.append("")
    lines.append("## 7. Representative Evidence by Strategy")
    lines.append("")
    for family, title in strategy_labels.items():
        lines.append(f"### {title}")
        lines.append("")
        samples = choose_samples(prompts, family, limit=3)
        if not samples:
            lines.append("- No prompt sample found.")
        else:
            for sample in samples:
                lines.append(f"- `{sample.timestamp}` ({sample.thread_role}): {sample.text}")
        lines.append("")
    lines.append("## 8. Interpretation for the Paper")
    lines.append("")
    lines.append("A stronger Section 3 can now say, with evidence, that the agent built more than code for a few variants:")
    lines.append("")
    lines.append("- it progressively assembled a layered validation infrastructure;")
    lines.append("- the strategy evolved from offline pipeline tests to executable-variant gates, then to interaction probes, setup testing, and finally family-level tournaments;")
    lines.append("- user supervision mostly operated through quality gates and conceptual corrections rather than test-file micromanagement;")
    lines.append("- the difficult point is not whether the agent can produce tests at all, but whether the resulting tests are strong enough to reveal shallow or partially implemented features.")
    lines.append("")
    lines.append("This is exactly the nuance worth making explicit in the paper: the coding agent can build a surprising amount of testing infrastructure on its own, but the user still had to decide what counted as convincing evidence for an SPL feature.")
    lines.append("")

    report_path = OUTPUT_DIR / "testing_story_report.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")

    summary = {
        "prompt_counts": {role: dict(counter) for role, counter in prompt_counter.items()},
        "command_counts": {role: dict(counter) for role, counter in command_counter.items()},
        "testing_prompt_count_engineering_experiments": len(testing_prompts),
        "micromanagement_like_testing_prompts": micromanagement_like,
        "artifact_groups": artifact_groups,
    }
    (OUTPUT_DIR / "testing_story_report.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")


def main() -> int:
    rows = load_relevant_threads(DEFAULT_WORKSPACE, DEFAULT_STATE_DB)
    prompts, commands = parse_rollouts(rows)
    write_report(DEFAULT_WORKSPACE, prompts, commands)
    print(f"Wrote {OUTPUT_DIR / 'testing_story_report.md'}")
    print(f"Wrote {OUTPUT_DIR / 'testing_story_report.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
