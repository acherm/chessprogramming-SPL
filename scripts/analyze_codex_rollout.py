#!/usr/bin/env python3
"""
Analyze a Codex rollout transcript for the chessprogramming-vm SPL project.

The script focuses on reconstructing the engineering story from the local
Codex Desktop JSONL rollout:

- user prompts and their heuristic SPL-lifecycle categories
- tool usage and command categories
- timeline/activity statistics
- LaTeX tables and JSON/CSV exports suitable for a paper draft
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


DEFAULT_WORKSPACE = Path("/Users/mathieuacher/SANDBOX/chessprogramming-vm")
DEFAULT_STATE_DB = Path("/Users/mathieuacher/.codex/state_5.sqlite")


PROMPT_CATEGORY_RULES: list[tuple[str, list[str]]] = [
    (
        "status_meta",
        [
            r"^go$",
            r"^continue$",
            r"^retry$",
            r"^yes please$",
            r"^please go ahead$",
            r"^status\?$",
            r"^statu\?$",
            r"ignore the image",
        ],
    ),
    (
        "commit_documentation",
        [
            r"\bcommit\b",
            r"\breadme\b",
            r"\bdocument\b",
            r"report on current assessment",
        ],
    ),
    (
        "deep_variability_setup",
        [
            r"\bsetup\b",
            r"variant,\s*setup",
            r"recommended setup",
            r"runtime book",
            r"runtime feature",
            r"ownbook",
            r"\bponder(?:ing)?\b",
        ],
    ),
    (
        "commonality_optimization",
        [
            r"\bcommonality\b",
            r"search efficiency",
            r"depth gap",
            r"dominant issue",
            r"tt/time-management",
            r"king-square caching",
            r"limitation of search depth",
            r"optimiz",
        ],
    ),
    (
        "feature_modeling",
        [
            r"feature model",
            r"featureide",
            r"chessprogramming\.org",
            r"\bpipeline\b",
            r"\bcache\b",
            r"\bmatrix\b",
            r"\bcrawl",
            r"\bfetch\b",
            r"\bconstraints\b",
            r"\bdepth ?= ?4\b",
            r"depth max",
            r"comparison table of chess engines",
        ],
    ),
    (
        "spl_implementation",
        [
            r"product line of chess engines",
            r"family of chess engines",
            r"implement a product line",
            r"compile-time options",
            r"implement .* in c",
            r"c langage",
            r"derive one variant",
            r"valid configuration.*chess engine",
            r"configuration that would implement such a chess engine",
        ],
    ),
    (
        "feature_completion",
        [
            r"real implementation of each feature",
            r"implement full tournament legality",
            r"features truly implemented",
            r"magic bitboards",
            r"weak/aliased features",
            r"fully implemented",
            r"selectable feature",
        ],
    ),
    (
        "modularity_refactoring",
        [
            r"\bphase 1\b",
            r"\bphase 2\b",
            r"\bphase 3\b",
            r"\bmodular",
            r"\brefactor",
            r"feature interactions",
            r"intermediate groups",
            r"\bpromote\b",
            r"board representations with different search strategies",
        ],
    ),
    (
        "testing_validation",
        [
            r"\bperft\b",
            r"not passing",
            r"variants? not passing",
            r"\billegal moves?\b",
            r"\bmandatory\b",
            r"\blegality\b",
            r"\bpass\b",
            r"justification of some constraints",
        ],
    ),
    (
        "benchmarking_comparison",
        [
            r"\btournament\b",
            r"\bstockfish\b",
            r"\belo\b",
            r"\bmatch\b",
            r"\banker?\b",
            r"\bcutechess",
            r"\bassessment\b",
            r"best configurations",
            r"best supposed variants",
            r"larger match",
            r"stronger anchor",
        ],
    ),
]


COMMAND_CATEGORY_RULES: list[tuple[str, list[str]]] = [
    ("benchmarking", [r"cutechess-cli", r"stockfish", r"\belo\b", r"\bmatch\b", r"\btournament\b"]),
    ("testing", [r"^pytest\b", r"\bperft\b", r"\bsmoke\b", r"\buci\b", r"\blegality\b"]),
    ("versioning", [r"^git\b"]),
    ("exploration", [r"^rg\b", r"^sed\b", r"^cat\b", r"^nl\b", r"^ls\b", r"^find\b", r"^wc\b", r"^pwd\b", r"^tail\b", r"^head\b"]),
    ("process", [r"^ps\b", r"^kill\b", r"^pkill\b", r"^pgrep\b"]),
    ("build_run", [r"\bpython3\b", r"\bPYTHONPATH=src\b", r"^make\b"]),
]


def tex_escape(value: str) -> str:
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    for src, dst in replacements.items():
        value = value.replace(src, dst)
    return value


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def parse_timestamp(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def classify_prompt(text: str) -> str:
    normalized = normalize_whitespace(text).lower()
    for category, patterns in PROMPT_CATEGORY_RULES:
        if any(re.search(pattern, normalized) for pattern in patterns):
            return category
    return "other"


def classify_command(cmd: str) -> str:
    normalized = cmd.strip()
    if not normalized:
        return "other"
    for category, patterns in COMMAND_CATEGORY_RULES:
        if any(re.search(pattern, normalized, re.IGNORECASE) for pattern in patterns):
            return category
    return "other"


@dataclass
class TurnRecord:
    index: int
    timestamp: str
    message: str
    category: str
    tool_calls: Counter[str] = field(default_factory=Counter)
    command_categories: Counter[str] = field(default_factory=Counter)
    commands: list[str] = field(default_factory=list)
    agent_messages: list[str] = field(default_factory=list)
    completed_at: str | None = None


def choose_thread(conn: sqlite3.Connection, workspace: Path, explicit_thread_id: str | None) -> sqlite3.Row:
    conn.row_factory = sqlite3.Row
    if explicit_thread_id:
        row = conn.execute(
            "select * from threads where id = ?",
            (explicit_thread_id,),
        ).fetchone()
        if row is None:
            raise SystemExit(f"Thread {explicit_thread_id!r} not found in {DEFAULT_STATE_DB}")
        return row

    rows = conn.execute(
        """
        select *
        from threads
        where cwd = ?
        order by
            case
                when lower(first_user_message) like '%write a paper%' then 1
                else 0
            end asc,
            tokens_used desc,
            created_at asc
        """,
        (str(workspace),),
    ).fetchall()
    if not rows:
        raise SystemExit(f"No Codex thread found for workspace {workspace}")
    return rows[0]


def parse_rollout(rollout_path: Path) -> dict[str, Any]:
    turns: list[TurnRecord] = []
    type_counts: Counter[str] = Counter()
    payload_type_counts: Counter[str] = Counter()
    function_calls: Counter[str] = Counter()
    command_categories: Counter[str] = Counter()
    prompt_categories: Counter[str] = Counter()
    prompts_per_day: Counter[str] = Counter()
    agent_messages_per_phase: Counter[str] = Counter()
    command_prefixes: Counter[str] = Counter()
    current_turn: TurnRecord | None = None

    with rollout_path.open(errors="replace") as handle:
        for line in handle:
            event = json.loads(line)
            type_counts[event["type"]] += 1

            if event["type"] == "event_msg":
                payload = event["payload"]
                payload_type = payload.get("type", "unknown")
                payload_type_counts[payload_type] += 1

                if payload_type == "user_message":
                    message = payload["message"]
                    category = classify_prompt(message)
                    prompt_categories[category] += 1
                    prompts_per_day[parse_timestamp(event["timestamp"]).date().isoformat()] += 1
                    current_turn = TurnRecord(
                        index=len(turns) + 1,
                        timestamp=event["timestamp"],
                        message=message,
                        category=category,
                    )
                    turns.append(current_turn)
                elif payload_type == "agent_message":
                    phase = payload.get("phase", "unknown")
                    agent_messages_per_phase[phase] += 1
                    if current_turn is not None:
                        current_turn.agent_messages.append(payload.get("message", ""))
                elif payload_type == "task_complete":
                    if current_turn is not None:
                        current_turn.completed_at = event["timestamp"]

            elif event["type"] == "response_item":
                payload = event["payload"]
                payload_type = payload.get("type", "unknown")
                payload_type_counts[f"response:{payload_type}"] += 1

                if payload_type != "function_call":
                    continue

                name = payload["name"]
                function_calls[name] += 1
                if current_turn is not None:
                    current_turn.tool_calls[name] += 1

                if name != "exec_command":
                    continue

                try:
                    arguments = json.loads(payload["arguments"])
                except json.JSONDecodeError:
                    arguments = {"cmd": payload["arguments"]}
                cmd = arguments.get("cmd", "").strip()
                category = classify_command(cmd)
                command_categories[category] += 1
                if current_turn is not None:
                    current_turn.command_categories[category] += 1
                    current_turn.commands.append(cmd)
                first_token = cmd.split()[0] if cmd else "(empty)"
                command_prefixes[first_token] += 1

    samples_by_category: dict[str, list[str]] = defaultdict(list)
    for turn in turns:
        bucket = samples_by_category[turn.category]
        if len(bucket) < 3:
            bucket.append(normalize_whitespace(turn.message))

    overview = {
        "turn_count": len(turns),
        "active_days": len(prompts_per_day),
        "first_prompt_at": turns[0].timestamp if turns else None,
        "last_prompt_at": turns[-1].timestamp if turns else None,
        "type_counts": dict(type_counts),
        "payload_type_counts": dict(payload_type_counts),
        "prompt_categories": dict(prompt_categories),
        "function_calls": dict(function_calls),
        "command_categories": dict(command_categories),
        "command_prefixes": dict(command_prefixes.most_common(20)),
        "prompts_per_day": dict(sorted(prompts_per_day.items())),
        "agent_messages_per_phase": dict(agent_messages_per_phase),
        "samples_by_category": dict(samples_by_category),
    }

    return {
        "overview": overview,
        "turns": turns,
    }


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


def export_turns_csv(turns: list[TurnRecord], path: Path) -> None:
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "turn_index",
                "timestamp",
                "category",
                "message",
                "tool_calls",
                "command_categories",
                "completed_at",
            ]
        )
        for turn in turns:
            writer.writerow(
                [
                    turn.index,
                    turn.timestamp,
                    turn.category,
                    normalize_whitespace(turn.message),
                    json.dumps(dict(turn.tool_calls), ensure_ascii=False),
                    json.dumps(dict(turn.command_categories), ensure_ascii=False),
                    turn.completed_at or "",
                ]
            )


def export_prompt_categories_table(overview: dict[str, Any], path: Path) -> None:
    total = sum(overview["prompt_categories"].values()) or 1
    lines = [
        r"\begin{table}[t]",
        r"\centering",
        r"\caption{Heuristic classification of user prompts in the main Codex engineering thread.}",
        r"\label{tab:codex-prompts}",
        r"\small",
        r"\begin{tabular}{@{}lrr@{}}",
        r"\toprule",
        r"\textbf{Category} & \textbf{Prompts} & \textbf{Share} \\",
        r"\midrule",
    ]
    for category, count in sorted(overview["prompt_categories"].items(), key=lambda item: (-item[1], item[0])):
        share = 100.0 * count / total
        label = tex_escape(category.replace("_", " "))
        lines.append(f"{label} & {count} & {share:.1f}\\% \\\\")
    lines.extend(
        [
            r"\bottomrule",
            r"\end{tabular}",
            r"\end{table}",
        ]
    )
    path.write_text("\n".join(lines) + "\n")


def export_tool_usage_table(overview: dict[str, Any], path: Path) -> None:
    lines = [
        r"\begin{table}[t]",
        r"\centering",
        r"\caption{Codex tool activity in the main engineering thread.}",
        r"\label{tab:codex-tools}",
        r"\small",
        r"\begin{tabular}{@{}lr@{}}",
        r"\toprule",
        r"\textbf{Tool / command family} & \textbf{Count} \\",
        r"\midrule",
    ]
    for name, count in sorted(overview["function_calls"].items(), key=lambda item: (-item[1], item[0])):
        lines.append(f"{tex_escape(name)} & {count} \\\\")
    lines.append(r"\midrule")
    for name, count in sorted(overview["command_categories"].items(), key=lambda item: (-item[1], item[0])):
        lines.append(f"{tex_escape('cmd:' + name)} & {count} \\\\")
    lines.extend(
        [
            r"\bottomrule",
            r"\end{tabular}",
            r"\end{table}",
        ]
    )
    path.write_text("\n".join(lines) + "\n")


def export_summary_markdown(thread_row: sqlite3.Row, overview: dict[str, Any], path: Path) -> None:
    lines = [
        "# Codex Rollout Analysis",
        "",
        f"- Thread id: `{thread_row['id']}`",
        f"- Title: {normalize_whitespace(thread_row['title'])}",
        f"- Rollout: `{thread_row['rollout_path']}`",
        f"- Prompt count: **{overview['turn_count']}**",
        f"- Active days: **{overview['active_days']}**",
        f"- Function calls: **{sum(overview['function_calls'].values())}**",
        "",
        "## Prompt Categories",
        "",
    ]
    for category, count in sorted(overview["prompt_categories"].items(), key=lambda item: (-item[1], item[0])):
        lines.append(f"- `{category}`: {count}")
    lines.extend(["", "## Command Categories", ""])
    for category, count in sorted(overview["command_categories"].items(), key=lambda item: (-item[1], item[0])):
        lines.append(f"- `{category}`: {count}")
    lines.extend(["", "## Sample Prompts", ""])
    for category, samples in sorted(overview["samples_by_category"].items()):
        lines.append(f"### {category}")
        for sample in samples:
            lines.append(f"- {sample}")
        lines.append("")
    path.write_text("\n".join(lines).rstrip() + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, default=DEFAULT_WORKSPACE)
    parser.add_argument("--state-db", type=Path, default=DEFAULT_STATE_DB)
    parser.add_argument("--thread-id")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_WORKSPACE / "paper" / "data",
    )
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(args.state_db)
    try:
        thread_row = choose_thread(conn, args.workspace, args.thread_id)
    finally:
        conn.close()

    rollout_path = Path(thread_row["rollout_path"])
    if not rollout_path.exists():
        raise SystemExit(f"Rollout file not found: {rollout_path}")

    parsed = parse_rollout(rollout_path)
    overview = parsed["overview"]
    turns = parsed["turns"]

    json_payload = {
        "thread_id": thread_row["id"],
        "title": thread_row["title"],
        "first_user_message": thread_row["first_user_message"],
        "rollout_path": thread_row["rollout_path"],
        "overview": overview,
    }

    write_json(args.output_dir / "codex_rollout_summary.json", json_payload)
    export_turns_csv(turns, args.output_dir / "codex_turns.csv")
    export_prompt_categories_table(overview, args.output_dir / "codex_prompt_categories_table.tex")
    export_tool_usage_table(overview, args.output_dir / "codex_tool_usage_table.tex")
    export_summary_markdown(thread_row, overview, args.output_dir / "codex_rollout_summary.md")

    print(json.dumps(json_payload["overview"], indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
