from __future__ import annotations

import json

from cpw_variability.config import resolve_paths
from cpw_variability.discovery import discover_snapshot
from cpw_variability.fetcher import CPWFetcher
from cpw_variability.models import PageDocument


def _page(title: str, links: list[str]) -> PageDocument:
    return PageDocument(
        title=title,
        url=f"https://www.chessprogramming.org/{title.replace(' ', '_')}",
        source_type="html",
        retrieved_at="2026-01-01T00:00:00+00:00",
        content_hash=f"h_{title}",
        text=f"{title} references several techniques.",
        headings=[title],
        links=links,
        bold_terms=[title],
        categories=["Search"],
        page_type="technique",
    )


def test_discovery_resumes_from_saved_state(tmp_path):
    paths = resolve_paths(root=tmp_path)
    fetcher = CPWFetcher(paths)

    fetcher.cache_document(_page("Main_Page", ["Alpha-Beta"]))
    fetcher.cache_document(_page("Alpha-Beta", ["Quiescence Search"]))
    fetcher.cache_document(_page("Quiescence Search", []))

    pages_first, _ = discover_snapshot(
        fetcher,
        seed_titles=["Main_Page"],
        max_pages=1,
        allow_network=False,
        resume=True,
        fresh=True,
        checkpoint_every=1,
    )
    assert len(pages_first) == 1
    assert paths.discovery_state_path.exists()

    state_after_first = json.loads(paths.discovery_state_path.read_text(encoding="utf-8"))
    assert state_after_first["queue"]
    assert state_after_first["completed"] is False

    pages_second, _ = discover_snapshot(
        fetcher,
        seed_titles=["Main_Page"],
        max_pages=5,
        allow_network=False,
        resume=True,
        checkpoint_every=1,
    )

    titles = {page.title for page in pages_second}
    assert {"Main_Page", "Alpha-Beta", "Quiescence Search"}.issubset(titles)

    state_after_second = json.loads(paths.discovery_state_path.read_text(encoding="utf-8"))
    assert state_after_second["completed"] is True
    assert state_after_second["queue"] == []
