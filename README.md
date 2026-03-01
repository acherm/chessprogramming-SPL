# CPW Variability Pipeline

Automated pipeline that mines chessprogramming.org into a traceable SPL feature model and engine/feature matrix.

## Safe Crawling and Resume

- Cache-first strategy: pages already in `data/chessprogramming_cache/` are never fetched again.
- Polite requests: crawl delay + retries with exponential backoff.
- `robots.txt` respected by default.
- Discovery state persisted to `data/chessprogramming_cache/discovery_state.json` for resumable runs.

Recommended crawl command:

```bash
PYTHONPATH=src python3 -m cpw_variability.cli fetch \
  --seed main \
  --mode snapshot \
  --max-pages 600 \
  --crawl-delay 2.0 \
  --http-retries 3 \
  --http-backoff 2.0
```

Resume behavior:

- Re-run the same `fetch` command to continue from saved queue/visited state.
- Use `--fresh` to discard previous discovery state and restart traversal.
- Use `--offline` to operate strictly from cache.
