from __future__ import annotations

from cpw_variability.config import resolve_paths
from cpw_variability.fetcher import CPWFetcher
from cpw_variability.models import PageDocument


def test_cache_key_and_manifest_integrity(tmp_path):
    paths = resolve_paths(root=tmp_path)
    fetcher = CPWFetcher(paths)

    key = fetcher.title_to_key("Monte-Carlo Tree Search")
    assert key == "Monte_Carlo_Tree_Search"

    doc = PageDocument(
        title="Monte-Carlo Tree Search",
        url="https://www.chessprogramming.org/Monte-Carlo_Tree_Search",
        source_type="html",
        retrieved_at="2026-01-01T00:00:00+00:00",
        content_hash="abc123",
        text="Monte-Carlo Tree Search is a strategy.",
        headings=["Monte-Carlo Tree Search"],
        links=["Search"],
        bold_terms=["MCTS"],
        categories=["Search"],
        page_type="technique",
    )

    fetcher.cache_document(doc)

    fetcher_reloaded = CPWFetcher(paths)
    loaded = fetcher_reloaded.load_cached_document("Monte-Carlo Tree Search")
    assert loaded is not None
    assert loaded.title == doc.title
    assert paths.cache_manifest_path.exists()

    manifest = fetcher_reloaded.manifest
    entry = manifest["pages"]["Monte-Carlo Tree Search"]
    assert entry["local_path"].endswith("Monte_Carlo_Tree_Search.json")
