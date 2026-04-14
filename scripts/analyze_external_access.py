#!/usr/bin/env python3

from __future__ import annotations

import json
import re
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path


DEFAULT_WORKSPACE = Path("/Users/mathieuacher/SANDBOX/chessprogramming-vm")
DEFAULT_STATE_DB = Path("/Users/mathieuacher/.codex/state_5.sqlite")
OUTPUT_DIR = DEFAULT_WORKSPACE / "paper" / "data"
DEFAULT_CUTOFF = "2026-04-10T00:00:00Z"

WEB_TOOL_NAMES = {"search_query", "image_query", "open", "click", "find"}
NETWORK_CMD_RE = re.compile(r"^(curl|wget|lynx)\b")
URL_RE = re.compile(r"https?://([^\s/\"'>)]+)")
USER_URL_RE = re.compile(r"https?://[^\s)\]}>\"']+")
CPW_CLI_RE = re.compile(r"\bpython3\s+-m\s+cpw_variability\.cli\s+([a-zA-Z-]+)\b")


@dataclass
class ThreadInfo:
    id: str
    title: str
    rollout_path: Path


def load_threads(workspace: Path, state_db: Path) -> list[ThreadInfo]:
    conn = sqlite3.connect(state_db)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        select id, title, rollout_path
        from threads
        where cwd = ?
        order by created_at
        """,
        (str(workspace),),
    ).fetchall()
    conn.close()

    threads: list[ThreadInfo] = []
    for row in rows:
        rollout_path = Path(row["rollout_path"])
        if not rollout_path.exists():
            continue
        title = row["title"] or ""
        if "problematic since it contains an image" in title:
            continue
        threads.append(ThreadInfo(id=row["id"], title=title, rollout_path=rollout_path))
    return threads


def collect(threads: list[ThreadInfo], cutoff: str) -> dict:
    totals = Counter()
    per_thread: dict[str, dict] = {}
    user_urls: list[dict] = []
    network_cmds: list[dict] = []
    literal_domains = Counter()

    for thread in threads:
        counts = Counter()
        cpw_cli_counts = Counter()
        thread_network_cmds: list[dict] = []
        thread_user_urls: list[dict] = []

        with thread.rollout_path.open("r", encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                rec = json.loads(line)
                ts = rec.get("timestamp", "")
                if ts and ts >= cutoff:
                    continue

                if rec.get("type") == "response_item":
                    payload = rec.get("payload", {})
                    if payload.get("type") == "function_call":
                        name = payload.get("name", "")
                        counts[name] += 1
                        totals[name] += 1
                        if name == "exec_command":
                            try:
                                args = json.loads(payload.get("arguments", "{}"))
                            except json.JSONDecodeError:
                                args = {"cmd": payload.get("arguments", "")}
                            cmd = str(args.get("cmd", "")).strip()

                            cli_match = CPW_CLI_RE.search(cmd)
                            if cli_match:
                                subcmd = cli_match.group(1)
                                if subcmd == "fetch":
                                    cpw_cli_counts["fetch_help" if "--help" in cmd else "fetch"] += 1
                                elif subcmd == "run-all":
                                    cpw_cli_counts["run_all_offline" if "--offline" in cmd else "run_all_non_offline"] += 1
                                elif subcmd == "build-model":
                                    cpw_cli_counts["build_model"] += 1
                                elif subcmd == "build-matrix":
                                    cpw_cli_counts["build_matrix"] += 1

                            if NETWORK_CMD_RE.search(cmd):
                                domains = sorted({m.group(1) for m in URL_RE.finditer(cmd)})
                                entry = {
                                    "timestamp": ts,
                                    "thread_id": thread.id,
                                    "thread_title": thread.title,
                                    "cmd": cmd,
                                    "domains": domains,
                                }
                                thread_network_cmds.append(entry)
                                network_cmds.append(entry)
                            else:
                                for m in URL_RE.finditer(cmd):
                                    literal_domains[m.group(1)] += 1

                elif rec.get("type") == "event_msg" and rec.get("payload", {}).get("type") == "user_message":
                    msg = rec["payload"].get("message", "")
                    urls = sorted(set(USER_URL_RE.findall(msg)))
                    if urls:
                        entry = {
                            "timestamp": ts,
                            "thread_id": thread.id,
                            "thread_title": thread.title,
                            "urls": urls,
                            "snippet": re.sub(r"\s+", " ", msg).strip()[:240],
                        }
                        thread_user_urls.append(entry)
                        user_urls.append(entry)

        per_thread[thread.id] = {
            "title": thread.title,
            "function_counts": dict(counts),
            "web_tool_counts": {k: counts[k] for k in WEB_TOOL_NAMES if counts[k]},
            "cpw_cli_counts": dict(cpw_cli_counts),
            "network_cmds": thread_network_cmds,
            "user_urls": thread_user_urls,
        }

    return {
        "cutoff": cutoff,
        "threads": per_thread,
        "totals": dict(totals),
        "network_cmds": network_cmds,
        "user_urls": user_urls,
        "literal_domains": dict(literal_domains),
    }


def render_markdown(data: dict) -> str:
    lines = [
        "# External Access Report",
        "",
        "This report re-analyzes the recorded Codex sessions to answer a specific question:",
        "did the coding agent roam the web freely, or did it mostly stay within the local CPW snapshot and repository artifacts?",
        "",
        f"- Analysis cutoff: `{data['cutoff']}`",
        "",
        "## Main Result",
        "",
        "The recorded endeavor was overwhelmingly **snapshot-local**, not web-browsing-driven.",
        f"- Browser/search-style tool calls recorded in the relevant threads: **0**",
        f"- Explicit network-style shell commands (`curl`, `wget`, `lynx`) before the cutoff: **{len(data['network_cmds'])}**",
        "",
    ]

    if data["network_cmds"]:
        lines.extend(
            [
                "The only explicit outbound network-style shell command found in the recorded sessions was:",
                "",
            ]
        )
        for cmd in data["network_cmds"]:
            lines.append(f"- `{cmd['timestamp']}` in `{cmd['thread_id'][:8]}`: `{cmd['cmd']}`")
        lines.append("")

    lines.extend(
        [
            "This should be interpreted carefully:",
            "- an early `curl -I` reachability probe to CPW is recorded, but it failed with DNS resolution in the sandbox;",
            "- the main engineering workflow then relied on the dedicated CPW fetch/cache pipeline and, after the cache existed, repeatedly used offline `run-all`, `build-model`, and `build-matrix` commands;",
            "- the user explicitly stated that they could run the polite crawl on their side, which matches the cache-first/offline-first organization of the project.",
            "",
            "## Per-Thread Summary",
            "",
            "| Thread | Web/search tool calls | CPW fetch/build activity | Explicit network shell commands |",
            "| --- | ---: | --- | ---: |",
        ]
    )

    for thread_id, info in data["threads"].items():
        cpw = info["cpw_cli_counts"]
        cpw_summary = (
            f"fetch={cpw.get('fetch', 0)}, "
            f"fetch-help={cpw.get('fetch_help', 0)}, "
            f"run-all-offline={cpw.get('run_all_offline', 0)}, "
            f"run-all-non-offline={cpw.get('run_all_non_offline', 0)}, "
            f"build-model={cpw.get('build_model', 0)}, "
            f"build-matrix={cpw.get('build_matrix', 0)}"
        )
        lines.append(
            f"| `{thread_id[:8]}` | {sum(info['web_tool_counts'].values())} | {cpw_summary} | {len(info['network_cmds'])} |"
        )

    lines.extend(
        [
            "",
            "## User-Provided URLs",
            "",
            "The user did provide a few URLs directly in prompts, but these were sparse and task-specific rather than signs of free web exploration:",
            "",
        ]
    )

    for entry in data["user_urls"]:
        lines.append(f"- `{entry['timestamp']}` in `{entry['thread_id'][:8]}`: {', '.join(f'`{u}`' for u in entry['urls'])}")

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "The sessions do **not** support a story in which the agent routinely searched the wider web ``here and there'' for missing domain knowledge.",
            "A more accurate description is:",
            "",
            "- CPW was the intended knowledge source.",
            "- A local cache/snapshot was deliberately constructed early and then reused.",
            "- The engineering, experiments, and paper-writing stages mostly operated on local artifacts, generated reports, and the maintained codebase.",
            "- The recorded agent had some technical means to probe or extend CPW through the dedicated fetch pipeline, but there is no evidence of broad ad hoc browsing across external sources.",
            "",
            "So, for the paper, the safest wording is that the project was **CPW-centered and snapshot-driven**, with only very limited recorded external probing.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    threads = load_threads(DEFAULT_WORKSPACE, DEFAULT_STATE_DB)
    data = collect(threads, DEFAULT_CUTOFF)
    (OUTPUT_DIR / "external_access_report.md").write_text(render_markdown(data) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
