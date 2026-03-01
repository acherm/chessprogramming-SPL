from __future__ import annotations

import re
from html import unescape
from urllib.parse import unquote, urlparse

try:
    from bs4 import BeautifulSoup
except Exception:  # pragma: no cover - optional dependency fallback
    BeautifulSoup = None


def _dedupe(items: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        token = item.strip()
        if not token:
            continue
        if token not in seen:
            seen.add(token)
            out.append(token)
    return out


def normalize_title(title: str) -> str:
    return unescape(title).replace("_", " ").strip()


def internal_title_from_href(href: str) -> str | None:
    if not href or href.startswith("#"):
        return None

    parsed = urlparse(href)
    if parsed.scheme and parsed.netloc and "chessprogramming.org" not in parsed.netloc:
        return None

    path = parsed.path
    if not path:
        return None

    if path.startswith("/wiki/"):
        title = path[len("/wiki/") :]
    elif path.startswith("/"):
        title = path[1:]
    else:
        title = path

    if not title or title.startswith("Special:") or title.startswith("File:"):
        return None

    return normalize_title(unquote(title))


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", text)
    return [p.strip() for p in parts if len(p.strip()) >= 12]


def _parse_with_bs4(html: str) -> dict[str, list[str] | str]:
    parser_name = "lxml"
    try:
        soup = BeautifulSoup(html, parser_name)
    except Exception:  # pragma: no cover - lxml not available
        soup = BeautifulSoup(html, "html.parser")

    for node in soup(["script", "style"]):
        node.extract()

    headings = [h.get_text(" ", strip=True) for h in soup.find_all(re.compile(r"^h[1-4]$"))]
    bold_terms = [b.get_text(" ", strip=True) for b in soup.find_all(["b", "strong"])]

    links: list[str] = []
    for a in soup.find_all("a", href=True):
        title = internal_title_from_href(a["href"])
        if title:
            links.append(title)

    categories: list[str] = []
    cat_node = soup.find(id="catlinks")
    if cat_node:
        for a in cat_node.find_all("a", href=True):
            candidate = normalize_title(a.get_text(" ", strip=True))
            if candidate and candidate.lower() != "categories":
                categories.append(candidate)

    text = soup.get_text(" ", strip=True)
    text = re.sub(r"\s+", " ", text).strip()

    return {
        "text": text,
        "headings": _dedupe(headings),
        "links": _dedupe(links),
        "bold_terms": _dedupe(bold_terms),
        "categories": _dedupe(categories),
    }


def _parse_with_regex(html: str) -> dict[str, list[str] | str]:
    link_matches = re.findall(r'href="([^"]+)"', html)
    links = [internal_title_from_href(link) for link in link_matches]
    links = [x for x in links if x]

    headings = re.findall(r"<h[1-4][^>]*>(.*?)</h[1-4]>", html, flags=re.IGNORECASE | re.DOTALL)
    headings = [re.sub(r"<[^>]+>", "", h).strip() for h in headings]

    bold_terms = re.findall(r"<(?:strong|b)\b[^>]*>(.*?)</(?:strong|b)>", html, flags=re.IGNORECASE | re.DOTALL)
    bold_terms = [re.sub(r"<[^>]+>", "", b).strip() for b in bold_terms]

    categories: list[str] = []
    cat_block_match = re.search(
        r'<div[^>]+id=["\']catlinks["\'][^>]*>(.*?)</div>',
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if cat_block_match:
        cat_block = cat_block_match.group(1)
        cat_links = re.findall(r'href="([^"]+)"[^>]*>(.*?)</a>', cat_block, flags=re.IGNORECASE | re.DOTALL)
        for _, label in cat_links:
            label_clean = re.sub(r"<[^>]+>", "", label).strip()
            if label_clean and label_clean.lower() != "categories":
                categories.append(normalize_title(label_clean))

    text = re.sub(r"<script.*?</script>", " ", html, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<style.*?</style>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(re.sub(r"\s+", " ", text)).strip()

    return {
        "text": text,
        "headings": _dedupe(headings),
        "links": _dedupe(links),
        "bold_terms": _dedupe(bold_terms),
        "categories": _dedupe(categories),
    }


def parse_html_content(html: str) -> dict[str, list[str] | str]:
    if BeautifulSoup is not None:
        parsed = _parse_with_bs4(html)
    else:  # pragma: no cover - only if bs4 is unavailable
        parsed = _parse_with_regex(html)

    parsed["sentences"] = split_sentences(parsed["text"])
    return parsed
