# Chessprogramming Cache

This public replication artifact keeps only cache metadata:

- `manifest.json`
- `discovery_state.json`

Mirrored CPW page bodies and raw API payloads are intentionally omitted from the public repository.

To rebuild the cache locally, install the project and rerun the fetch stage, for example:

```bash
pip install -e .
PYTHONPATH=src python3 -m cpw_variability.cli fetch --seed implementation --mode snapshot --max-pages 1500
```

Or rerun the full pipeline:

```bash
pip install -e .
PYTHONPATH=src python3 -m cpw_variability.cli run-all --seed implementation --mode snapshot --max-pages 1500
```
