from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from cpw_variability.cli import PipelineError, run_all
from cpw_variability.config import resolve_paths
from cpw_variability.discovery import extract_engine_pages
from cpw_variability.exporters import load_feature_model_json
from cpw_variability.fetcher import CPWFetcher
from cpw_variability.matrix_builder import build_engine_feature_matrix
from cpw_variability.model_builder import build_feature_model


def _cache_fixture_pages(paths, sample_pages):
    fetcher = CPWFetcher(paths)
    for page in sample_pages:
        fetcher.cache_document(page)


def test_model_build_and_featureide_export(tmp_path, sample_pages):
    paths = resolve_paths(root=tmp_path)
    result = build_feature_model(sample_pages, depth=3, target_features=30)

    from cpw_variability.exporters import export_feature_model_json, export_featureide_xml

    export_feature_model_json(paths.feature_model_json_path, result.features, result.traces, result.meta)
    export_featureide_xml(paths.feature_model_featureide_path, result.features)

    assert paths.feature_model_json_path.exists()
    assert paths.feature_model_featureide_path.exists()

    tree = ET.parse(paths.feature_model_featureide_path)
    root = tree.getroot()
    assert root.tag == "featureModel"

    features, traces, _ = load_feature_model_json(paths.feature_model_json_path)
    traced_feature_ids = {trace.feature_id for trace in traces}
    assert all(feature.id in traced_feature_ids for feature in features)


def test_matrix_expected_statuses(tmp_path, sample_pages):
    paths = resolve_paths(root=tmp_path)
    _cache_fixture_pages(paths, sample_pages)

    model = build_feature_model(sample_pages, depth=3, target_features=50)
    matrix = build_engine_feature_matrix(extract_engine_pages(sample_pages), model.features)

    alpha_beta_feature_ids = [feature.id for feature in model.features if feature.name.lower() == "alpha-beta"]
    assert alpha_beta_feature_ids
    alpha_beta_feature = alpha_beta_feature_ids[0]

    lookup = {(status.engine_id, status.feature_id): status.status for status in matrix.statuses}
    assert lookup[("stockfish", alpha_beta_feature)] == "SUPPORTED"
    assert lookup[("leela_chess_zero", alpha_beta_feature)] == "UNSUPPORTED_EXPLICIT"


def test_run_all_offline_cache_only(tmp_path, sample_pages):
    paths = resolve_paths(root=tmp_path)
    _cache_fixture_pages(paths, sample_pages)

    summary = run_all(
        paths,
        seed="main",
        mode="snapshot",
        max_pages=80,
        depth=3,
        target_features=40,
        allow_network=False,
    )

    assert summary["metrics"]["engines_discovered"] >= 2
    assert paths.feature_model_json_path.exists()
    assert paths.feature_model_featureide_path.exists()
    assert paths.feature_traces_csv_path.exists()
    assert paths.engine_feature_matrix_csv_path.exists()
    assert paths.engine_feature_matrix_md_path.exists()
    assert paths.run_report_path.exists()


def test_run_all_missing_cache_fails(tmp_path):
    paths = resolve_paths(root=tmp_path)

    with pytest.raises(PipelineError):
        run_all(
            paths,
            seed="main",
            mode="snapshot",
            max_pages=20,
            depth=3,
            target_features=30,
            allow_network=False,
        )
