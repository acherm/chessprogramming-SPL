from __future__ import annotations

import json
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

from .config import (
    DEFAULT_DISCOVERY_CHECKPOINT_EVERY,
    DEFAULT_MAX_DISCOVERY_PAGES,
    DEFAULT_MAX_FETCH_FAILURES_PER_PAGE,
)
from .fetcher import CPWFetcher, FetchError
from .models import PageDocument, Paths
from .parser import normalize_title


def _is_engine_page(document: PageDocument) -> bool:
    title_lower = document.title.lower()
    categories = " ".join(document.categories).lower()

    if "chess engine" in categories or "engines" in categories:
        return True

    if title_lower.startswith("engine ") or title_lower.endswith(" chess engine"):
        return True

    engine_markers = ["author", "rating", "uci", "xboard"]
    marker_hits = sum(1 for marker in engine_markers if marker in document.text.lower())
    return marker_hits >= 2 and "engine" in document.text.lower()


def classify_page(document: PageDocument) -> str:
    title = document.title.lower()

    if _is_engine_page(document):
        return "engine"

    if title.startswith("category:") or title.startswith("portal:"):
        return "meta"

    if title.startswith("main page") or title.startswith("index"):
        return "meta"

    return "technique"


def _is_followable_title(title: str) -> bool:
    if not title:
        return False

    disallowed_prefixes = ("File:", "Special:", "Help:")
    if title.startswith(disallowed_prefixes):
        return False

    return True


def _normalize_seed_titles(seed_titles: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for title in seed_titles:
        normalized = normalize_title(title)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        out.append(normalized)
    return out


def _load_state(path: Path) -> dict | None:
    if not path.exists():
        return None

    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    if not isinstance(payload, dict):
        return None
    return payload


def _state_matches(state: dict, seed_titles: list[str]) -> bool:
    state_seeds = state.get("seed_titles", [])
    if not isinstance(state_seeds, list):
        return False
    return sorted(str(seed) for seed in state_seeds) == sorted(seed_titles)


def _save_state(
    path: Path,
    seed_titles: list[str],
    queue: deque[str],
    visited: set[str],
    failed: dict[str, int],
    warnings: list[str],
    completed: bool,
    stop_reason: str,
) -> None:
    payload = {
        "seed_titles": list(seed_titles),
        "queue": list(queue),
        "visited": sorted(visited),
        "failed": dict(sorted(failed.items())),
        "warnings": warnings[-300:],
        "completed": completed,
        "stop_reason": stop_reason,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)


def reset_discovery_state(paths: Paths) -> None:
    if paths.discovery_state_path.exists():
        paths.discovery_state_path.unlink()


def _load_pages_by_titles(fetcher: CPWFetcher, titles: set[str]) -> list[PageDocument]:
    pages: list[PageDocument] = []
    for title in sorted(titles):
        doc = fetcher.load_cached_document(title)
        if doc is None:
            continue
        doc.page_type = classify_page(doc)  # type: ignore[assignment]
        pages.append(doc)
    return pages


def discover_snapshot(
    fetcher: CPWFetcher,
    seed_titles: list[str],
    max_pages: int = DEFAULT_MAX_DISCOVERY_PAGES,
    allow_network: bool = True,
    resume: bool = True,
    fresh: bool = False,
    checkpoint_every: int = DEFAULT_DISCOVERY_CHECKPOINT_EVERY,
    max_failures_per_page: int = DEFAULT_MAX_FETCH_FAILURES_PER_PAGE,
) -> tuple[list[PageDocument], list[str]]:
    state_path = fetcher.paths.discovery_state_path
    normalized_seeds = _normalize_seed_titles(seed_titles)

    if fresh:
        reset_discovery_state(fetcher.paths)

    queue: deque[str]
    queued: set[str]
    visited: set[str]
    failed: dict[str, int]
    warnings: list[str]

    loaded_state = _load_state(state_path) if resume else None
    if loaded_state is not None and _state_matches(loaded_state, normalized_seeds):
        queue = deque(normalize_title(item) for item in loaded_state.get("queue", []))
        queued = set(queue)
        visited = {normalize_title(item) for item in loaded_state.get("visited", [])}
        failed = {normalize_title(k): int(v) for k, v in loaded_state.get("failed", {}).items()}
        warnings = [str(item) for item in loaded_state.get("warnings", [])]
    else:
        queue = deque(normalized_seeds)
        queued = set(normalized_seeds)
        visited = set()
        failed = {}
        warnings = []

    attempts_since_checkpoint = 0
    max_failures = max(1, max_failures_per_page)
    checkpoint_every = max(1, checkpoint_every)

    while queue and len(visited) < max_pages:
        title = normalize_title(queue.popleft())
        queued.discard(title)
        if not title or title in visited:
            continue

        try:
            page = fetcher.fetch_page(title, allow_network=allow_network)
        except FetchError as exc:
            failures = failed.get(title, 0) + 1
            failed[title] = failures
            warnings.append(str(exc))
            if allow_network and failures < max_failures and title not in queued:
                queue.append(title)
                queued.add(title)
            attempts_since_checkpoint += 1
            if attempts_since_checkpoint >= checkpoint_every:
                _save_state(
                    state_path,
                    normalized_seeds,
                    queue,
                    visited,
                    failed,
                    warnings,
                    completed=False,
                    stop_reason="checkpoint",
                )
                attempts_since_checkpoint = 0
            continue

        page.page_type = classify_page(page)  # type: ignore[assignment]
        visited.add(title)
        failed.pop(title, None)

        for link in page.links:
            linked_title = normalize_title(link)
            if not linked_title:
                continue
            if linked_title in visited or linked_title in queued:
                continue
            if not _is_followable_title(linked_title):
                continue
            if linked_title.startswith("Category:") and len(linked_title) > 80:
                continue
            queue.append(linked_title)
            queued.add(linked_title)

        attempts_since_checkpoint += 1
        if attempts_since_checkpoint >= checkpoint_every:
            _save_state(
                state_path,
                normalized_seeds,
                queue,
                visited,
                failed,
                warnings,
                completed=False,
                stop_reason="checkpoint",
            )
            attempts_since_checkpoint = 0

    completed = len(queue) == 0
    if len(visited) >= max_pages and queue:
        stop_reason = f"max_pages_reached:{max_pages}"
    elif completed:
        stop_reason = "queue_exhausted"
    else:
        stop_reason = "stopped"

    _save_state(
        state_path,
        normalized_seeds,
        queue,
        visited,
        failed,
        warnings,
        completed=completed,
        stop_reason=stop_reason,
    )

    pages = _load_pages_by_titles(fetcher, visited)
    return pages, warnings


def discover_from_cache(fetcher: CPWFetcher) -> list[PageDocument]:
    pages = fetcher.iter_cached_documents()
    for page in pages:
        page.page_type = classify_page(page)  # type: ignore[assignment]
    return pages


def extract_engine_pages(pages: list[PageDocument]) -> list[PageDocument]:
    return [page for page in pages if page.page_type == "engine"]


def extract_non_engine_pages(pages: list[PageDocument]) -> list[PageDocument]:
    return [page for page in pages if page.page_type != "engine"]
