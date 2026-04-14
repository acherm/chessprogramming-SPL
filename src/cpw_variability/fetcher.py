from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.robotparser import RobotFileParser

try:
    import requests
except Exception:  # pragma: no cover - optional dependency fallback
    requests = None

from .config import (
    BASE_URL,
    DEFAULT_HTTP_BACKOFF_SECONDS,
    DEFAULT_MAX_HTTP_RETRIES,
    DEFAULT_MIN_REQUEST_INTERVAL_SECONDS,
    DEFAULT_TIMEOUT_SECONDS,
    DEFAULT_USER_AGENT,
)
from .models import PageCacheEntry, PageDocument, Paths
from .parser import parse_html_content


class FetchError(Exception):
    """Raised when a page cannot be fetched from cache or network."""


class CPWFetcher:
    def __init__(
        self,
        paths: Paths,
        base_url: str = BASE_URL,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
        user_agent: str = DEFAULT_USER_AGENT,
        min_request_interval_seconds: float = DEFAULT_MIN_REQUEST_INTERVAL_SECONDS,
        max_http_retries: int = DEFAULT_MAX_HTTP_RETRIES,
        http_backoff_seconds: float = DEFAULT_HTTP_BACKOFF_SECONDS,
        respect_robots: bool = True,
    ):
        self.paths = paths
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.user_agent = user_agent
        self.min_request_interval_seconds = max(0.0, min_request_interval_seconds)
        self.max_http_retries = max(1, max_http_retries)
        self.http_backoff_seconds = max(0.0, http_backoff_seconds)
        self.respect_robots = respect_robots

        self._last_request_monotonic: float | None = None
        self._robots_initialized = False
        self._robots: RobotFileParser | None = None

        self.paths.ensure_dirs()
        self.manifest = self._load_manifest()

    def _load_manifest(self) -> dict[str, dict]:
        if not self.paths.cache_manifest_path.exists():
            return {"pages": {}}

        with self.paths.cache_manifest_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)

        if "pages" not in payload:
            payload["pages"] = {}
        return payload

    def _save_manifest(self) -> None:
        self.paths.cache_manifest_path.parent.mkdir(parents=True, exist_ok=True)
        with self.paths.cache_manifest_path.open("w", encoding="utf-8") as handle:
            json.dump(self.manifest, handle, indent=2, sort_keys=True)

    @staticmethod
    def _title_variants(title: str) -> list[str]:
        variants = [title.strip()]
        variants.append(title.replace("_", " ").strip())
        variants.append(title.replace(" ", "_").strip())
        out: list[str] = []
        seen: set[str] = set()
        for variant in variants:
            if variant and variant not in seen:
                seen.add(variant)
                out.append(variant)
        return out

    @staticmethod
    def title_to_key(title: str) -> str:
        safe = "".join(ch if ch.isalnum() else "_" for ch in title.strip())
        safe = "_".join(part for part in safe.split("_") if part)
        return safe[:160] or "untitled"

    def _document_path(self, title: str) -> Path:
        return self.paths.cache_pages_dir / f"{self.title_to_key(title)}.json"

    def _raw_path(self, title: str, suffix: str) -> Path:
        return self.paths.cache_raw_dir / f"{self.title_to_key(title)}.{suffix}"

    def _hash_payload(self, payload: str) -> str:
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def cache_document(self, document: PageDocument) -> None:
        doc_path = self._document_path(document.title)
        doc_path.parent.mkdir(parents=True, exist_ok=True)
        with doc_path.open("w", encoding="utf-8") as handle:
            json.dump(document.to_dict(), handle, indent=2, ensure_ascii=False)

        entry = PageCacheEntry(
            url=document.url,
            retrieved_at=document.retrieved_at,
            content_hash=document.content_hash,
            source_type=document.source_type,
            local_path=str(doc_path),
        )
        self.manifest["pages"][document.title] = entry.to_dict()
        self._save_manifest()

    def load_cached_document(self, title: str) -> PageDocument | None:
        pages = self.manifest.get("pages", {})
        entry_raw = None
        for variant in self._title_variants(title):
            if variant in pages:
                entry_raw = pages[variant]
                break
        if not entry_raw:
            return None

        local_path = Path(entry_raw["local_path"])
        if not local_path.exists():
            return None

        with local_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)

        return PageDocument.from_dict(payload)

    def iter_cached_documents(self) -> list[PageDocument]:
        docs: list[PageDocument] = []
        for title in sorted(self.manifest.get("pages", {}).keys()):
            doc = self.load_cached_document(title)
            if doc is not None:
                docs.append(doc)
        return docs

    def fetch_page(self, title: str, allow_network: bool = True) -> PageDocument:
        cached = self.load_cached_document(title)
        if cached is not None:
            return cached

        if not allow_network:
            raise FetchError(f"Cache miss for '{title}' and network is disabled")

        api_payload = self._fetch_via_api(title)
        if api_payload is not None:
            document = self._build_document_from_api(title, api_payload)
            self.cache_document(document)
            return document

        html_payload = self._fetch_via_html(title)
        if html_payload is not None:
            document = self._build_document_from_html(title, html_payload)
            self.cache_document(document)
            return document

        raise FetchError(f"Unable to fetch page '{title}' from API or HTML")

    def _throttle(self) -> None:
        if self.min_request_interval_seconds <= 0.0:
            return

        now = time.monotonic()
        if self._last_request_monotonic is None:
            return

        elapsed = now - self._last_request_monotonic
        remaining = self.min_request_interval_seconds - elapsed
        if remaining > 0:
            time.sleep(remaining)

    def _mark_request(self) -> None:
        self._last_request_monotonic = time.monotonic()

    def _headers(self) -> dict[str, str]:
        return {
            "User-Agent": self.user_agent,
            "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
        }

    def _init_robots(self) -> None:
        if self._robots_initialized or not self.respect_robots:
            self._robots_initialized = True
            return

        robots_url = f"{self.base_url}/robots.txt"
        parser = RobotFileParser()
        parser.set_url(robots_url)

        try:
            if requests is not None:
                self._throttle()
                response = requests.get(robots_url, timeout=self.timeout_seconds, headers=self._headers())
                self._mark_request()
                if response.status_code >= 400:
                    self._robots = None
                    self._robots_initialized = True
                    return
                parser.parse(response.text.splitlines())
            else:
                self._throttle()
                parser.read()
                self._mark_request()
            self._robots = parser
        except Exception:
            self._robots = None
        finally:
            self._robots_initialized = True

    def _allowed_by_robots(self, url: str) -> bool:
        if not self.respect_robots:
            return True

        self._init_robots()
        if self._robots is None:
            return True

        try:
            return bool(self._robots.can_fetch(self.user_agent, url))
        except Exception:
            return True

    def _request_with_retries(self, url: str, mode: str) -> str | dict:
        last_error: Exception | None = None

        for attempt in range(self.max_http_retries):
            try:
                self._throttle()
                if mode == "json":
                    payload = self._http_get_json_once(url)
                else:
                    payload = self._http_get_text_once(url)
                self._mark_request()
                return payload
            except Exception as exc:  # pragma: no cover - retry behavior is hard to force deterministically
                self._mark_request()
                last_error = exc
                if attempt >= self.max_http_retries - 1:
                    break
                backoff = self.http_backoff_seconds * (2**attempt)
                if backoff > 0:
                    time.sleep(backoff)

        if last_error is None:
            raise FetchError(f"Unexpected request failure for {url}")
        raise last_error

    def _http_get_text_once(self, url: str) -> str:
        if requests is not None:
            response = requests.get(url, timeout=self.timeout_seconds, headers=self._headers())
            response.raise_for_status()
            response.encoding = response.encoding or "utf-8"
            return response.text

        request = Request(url, headers=self._headers())
        with urlopen(request, timeout=self.timeout_seconds) as response:  # noqa: S310
            return response.read().decode("utf-8", errors="replace")

    def _http_get_json_once(self, url: str) -> dict:
        if requests is not None:
            response = requests.get(url, timeout=self.timeout_seconds, headers=self._headers())
            response.raise_for_status()
            return response.json()

        request = Request(url, headers=self._headers())
        with urlopen(request, timeout=self.timeout_seconds) as response:  # noqa: S310
            body = response.read().decode("utf-8", errors="replace")
            return json.loads(body)

    def _fetch_via_api(self, title: str) -> dict | None:
        params = {
            "action": "parse",
            "page": title,
            "prop": "text|links|categories|sections",
            "format": "json",
            "redirects": "1",
        }
        url = f"{self.base_url}/api.php?{urlencode(params)}"

        if not self._allowed_by_robots(url):
            return None

        try:
            payload = self._request_with_retries(url, mode="json")
        except (HTTPError, URLError, TimeoutError, ValueError, OSError, FetchError):
            return None
        except Exception:
            return None

        assert isinstance(payload, dict)
        parsed = payload.get("parse")
        if not parsed:
            return None

        text_html = parsed.get("text", {}).get("*")
        if not text_html:
            return None

        raw_path = self._raw_path(title, "api.json")
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        with raw_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)

        return {
            "api_url": url,
            "page_url": f"{self.base_url}/{title.replace(' ', '_')}",
            "html": text_html,
            "links": [item.get("*") for item in parsed.get("links", []) if item.get("*")],
            "categories": [item.get("*") for item in parsed.get("categories", []) if item.get("*")],
            "raw_path": str(raw_path),
        }

    def _fetch_via_html(self, title: str) -> dict | None:
        page_url = f"{self.base_url}/{title.replace(' ', '_')}"

        if not self._allowed_by_robots(page_url):
            return None

        try:
            html = self._request_with_retries(page_url, mode="text")
        except (HTTPError, URLError, TimeoutError, OSError, FetchError):
            return None
        except Exception:
            return None

        assert isinstance(html, str)
        if not html.strip():
            return None

        raw_path = self._raw_path(title, "html")
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_text(html, encoding="utf-8")

        return {
            "page_url": page_url,
            "html": html,
            "raw_path": str(raw_path),
        }

    def _build_document_from_api(self, title: str, payload: dict) -> PageDocument:
        parsed = parse_html_content(payload["html"])
        links = sorted(set(parsed["links"]) | set(payload.get("links", [])))
        categories = sorted(set(parsed["categories"]) | set(payload.get("categories", [])))

        retrieved_at = datetime.now(timezone.utc).isoformat()
        content_hash = self._hash_payload(payload["html"])

        return PageDocument(
            title=title,
            url=payload["page_url"],
            source_type="api",
            retrieved_at=retrieved_at,
            content_hash=content_hash,
            text=str(parsed["text"]),
            headings=list(parsed["headings"]),
            links=links,
            bold_terms=list(parsed["bold_terms"]),
            categories=categories,
            raw_payload_path=payload.get("raw_path"),
        )

    def _build_document_from_html(self, title: str, payload: dict) -> PageDocument:
        parsed = parse_html_content(payload["html"])

        retrieved_at = datetime.now(timezone.utc).isoformat()
        content_hash = self._hash_payload(payload["html"])

        return PageDocument(
            title=title,
            url=payload["page_url"],
            source_type="html",
            retrieved_at=retrieved_at,
            content_hash=content_hash,
            text=str(parsed["text"]),
            headings=list(parsed["headings"]),
            links=list(parsed["links"]),
            bold_terms=list(parsed["bold_terms"]),
            categories=list(parsed["categories"]),
            raw_payload_path=payload.get("raw_path"),
        )
