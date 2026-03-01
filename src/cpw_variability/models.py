from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

FeatureKind = Literal["mandatory", "optional", "or", "xor"]
SupportStatus = Literal["SUPPORTED", "UNSUPPORTED_EXPLICIT", "UNKNOWN"]


@dataclass
class FeatureNode:
    id: str
    name: str
    parent_id: str | None
    kind: FeatureKind = "optional"
    description: str = ""
    aliases: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TraceRecord:
    id: str
    feature_id: str
    source_url: str
    source_title: str
    snippet: str
    confidence: float
    rule_id: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EngineFeatureStatus:
    engine_id: str
    feature_id: str
    status: SupportStatus
    evidence_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PageCacheEntry:
    url: str
    retrieved_at: str
    content_hash: str
    source_type: Literal["api", "html"]
    local_path: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PageDocument:
    title: str
    url: str
    source_type: Literal["api", "html"]
    retrieved_at: str
    content_hash: str
    text: str
    headings: list[str] = field(default_factory=list)
    links: list[str] = field(default_factory=list)
    bold_terms: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    page_type: Literal["engine", "technique", "meta"] = "technique"
    raw_payload_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "PageDocument":
        return cls(**payload)


@dataclass
class Paths:
    root: Path
    data_dir: Path
    cache_dir: Path
    cache_pages_dir: Path
    cache_raw_dir: Path
    cache_manifest_path: Path
    outputs_dir: Path
    discovered_pages_path: Path
    discovery_state_path: Path
    feature_model_json_path: Path
    feature_model_featureide_path: Path
    feature_traces_csv_path: Path
    engine_feature_matrix_csv_path: Path
    engine_feature_matrix_md_path: Path
    run_report_path: Path

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_pages_dir.mkdir(parents=True, exist_ok=True)
        self.cache_raw_dir.mkdir(parents=True, exist_ok=True)
        self.outputs_dir.mkdir(parents=True, exist_ok=True)
