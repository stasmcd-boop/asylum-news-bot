import re
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import List
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

import feedparser
import requests
from bs4 import BeautifulSoup

from app.filters import detect_category, detect_importance, is_relevant
from app.models import NewsItem
from app.source_registry import SourceConfig, enabled_sources, source_priority

REQUEST_HEADERS = {"User-Agent": "AsylumNewsBot/0.2 (+https://github.com/stasmcd-boop/asylum-news-bot)"}
TRACKING_QUERY_PREFIXES = ("utm_",)
TRACKING_QUERY_KEYS = {"fbclid", "gclid", "mc_cid", "mc_eid"}

FEDERAL_REGISTER_TERMS = [
    "asylum",
    "credible fear",
    "reasonable fear",
    "immigration court",
    "employment authorization",
    "temporary protected status",
    "humanitarian parole",
    "removal proceedings",
    "deportation",
    "alien registration",
]


@dataclass
class SourceDiagnostic:
    source: str
    ok: bool
    fetched: int = 0
    relevant: int = 0
    error: str = ""


@dataclass
class CollectorResult:
    items: List[NewsItem]
    diagnostics: List[SourceDiagnostic]


def _parse_date(value: str | None):
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
        if parsed and parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except Exception:
        return None


def _parse_page_date(text: str):
    match = re.search(r"\b([A-Z][a-z]+ \d{1,2}, \d{4})\b", text)
    if not match:
        return None
    try:
        return datetime.strptime(match.group(1), "%B %d, %Y").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _entry_summary(entry) -> str:
    for attr in ["summary", "description", "subtitle"]:
        value = getattr(entry, attr, "")
        if value:
            return str(value).strip()
    return ""


def _clean_google_news_title(title: str) -> str:
    if " - " in title:
        return title.rsplit(" - ", 1)[0].strip()
    return title.strip()


def _canonical_url(url: str) -> str:
    parts = urlsplit(url.strip())
    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key not in TRACKING_QUERY_KEYS and not key.startswith(TRACKING_QUERY_PREFIXES)
    ]
    path = parts.path.rstrip("/") or parts.path
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, urlencode(query), ""))


def _title_key(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()


def _published_timestamp(item: NewsItem) -> float:
    if not item.published_at:
        return 0
    published = item.published_at
    if published.tzinfo is None:
        published = published.replace(tzinfo=timezone.utc)
    return published.timestamp()


def _item_rank(item: NewsItem) -> tuple[int, int, float]:
    importance = {"important": 0, "medium": 1, "info": 2}
    rank = item.source_rank if item.source_rank != 50 else 100 - source_priority(item.source)
    return (importance.get(item.importance, 9), rank, -_published_timestamp(item))


def rank_items(items: List[NewsItem]) -> List[NewsItem]:
    return sorted(items, key=_item_rank)


def deduplicate_items(items: List[NewsItem]) -> List[NewsItem]:
    unique: List[NewsItem] = []
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()

    for item in rank_items(items):
        url_key = _canonical_url(item.url)
        title_key = _title_key(item.title)
        if url_key in seen_urls or title_key in seen_titles:
            continue
        seen_urls.add(url_key)
        if title_key:
            seen_titles.add(title_key)
        unique.append(item)
    return unique


def _build_item(source: SourceConfig, title: str, link: str, summary: str, published) -> NewsItem:
    importance = detect_importance(title, summary)
    if source.group == "news" and importance == "info":
        importance = "medium"
    return NewsItem(
        source=source.name,
        title=title,
        url=link,
        published_at=published,
        summary=summary,
        category=detect_category(title, summary),
        importance=importance,
        source_rank=100 - source.priority,
        source_type=source.group,
    )


def fetch_rss_source(source: SourceConfig) -> tuple[List[NewsItem], SourceDiagnostic]:
    if not source.enabled:
        return [], SourceDiagnostic(source=source.name, ok=True, error="disabled")

    response = requests.get(source.url, headers=REQUEST_HEADERS, timeout=30)
    response.raise_for_status()
    parsed = feedparser.parse(response.content)
    items: List[NewsItem] = []
    limit = 50 if source.type == "google_news" else 30
    fetched = len(parsed.entries[:limit])

    for entry in parsed.entries[:limit]:
        raw_title = getattr(entry, "title", "").strip()
        title = _clean_google_news_title(raw_title) if source.type == "google_news" else raw_title
        link = getattr(entry, "link", "").strip()
        summary = _entry_summary(entry)
        published = _parse_date(getattr(entry, "published", None) or getattr(entry, "updated", None))
        if not title or not link:
            continue
        if not is_relevant(title, summary):
            continue
        items.append(_build_item(source, title, link, summary, published))

    return items, SourceDiagnostic(source=source.name, ok=True, fetched=fetched, relevant=len(items))


def fetch_page_source(source: SourceConfig) -> tuple[List[NewsItem], SourceDiagnostic]:
    response = requests.get(source.url, headers=REQUEST_HEADERS, timeout=30)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    items: List[NewsItem] = []
    seen: set[str] = set()
    root = soup.find("main") or soup.body or soup
    anchors = root.find_all("a", href=True)

    for anchor in anchors:
        title = anchor.get_text(" ", strip=True)
        if len(title) < 12 or not is_relevant(title):
            continue
        link = _canonical_url(urljoin(source.url, anchor["href"]))
        if link in seen:
            continue
        seen.add(link)
        container = anchor.find_parent(["article", "li"]) or anchor.find_parent(class_=re.compile(r"(views-row|card|teaser|release|item)", re.I))
        context = container.get_text(" ", strip=True) if container else title
        summary = context[:1000]
        items.append(_build_item(source, title, link, summary, _parse_page_date(context)))
        if len(items) >= 30:
            break

    return items, SourceDiagnostic(source=source.name, ok=True, fetched=len(anchors), relevant=len(items))


def fetch_registered_sources() -> CollectorResult:
    items: List[NewsItem] = []
    diagnostics: List[SourceDiagnostic] = []
    for source in enabled_sources():
        if source.type == "federal_register":
            continue
        try:
            if source.type in ["rss", "google_news"]:
                source_items, diagnostic = fetch_rss_source(source)
            else:
                source_items, diagnostic = fetch_page_source(source)
            items.extend(source_items)
            diagnostics.append(diagnostic)
        except Exception as exc:
            diagnostics.append(SourceDiagnostic(source=source.name, ok=False, error=repr(exc)))
    return CollectorResult(items=items, diagnostics=diagnostics)


def fetch_federal_register() -> CollectorResult:
    source = SourceConfig("Federal Register", "federal_register", priority=8, group="official", fresh_days=90)
    params = {
        "conditions[agencies][]": ["homeland-security-department", "justice-department"],
        "conditions[term]": " OR ".join(FEDERAL_REGISTER_TERMS),
        "order": "newest",
        "per_page": 50,
    }
    response = requests.get("https://www.federalregister.gov/api/v1/documents.json", params=params, headers=REQUEST_HEADERS, timeout=30)
    response.raise_for_status()
    data = response.json()
    items: List[NewsItem] = []
    for doc in data.get("results", []):
        title = doc.get("title", "").strip()
        url = doc.get("html_url") or doc.get("pdf_url") or ""
        summary = doc.get("abstract", "") or ""
        pub_date = doc.get("publication_date")
        published = None
        if pub_date:
            try:
                published = datetime.fromisoformat(pub_date).replace(tzinfo=timezone.utc)
            except Exception:
                published = None
        if not title or not url:
            continue
        if not is_relevant(title, summary):
            continue
        items.append(_build_item(source, title, url, summary, published))
    diagnostic = SourceDiagnostic(
        source=source.name,
        ok=True,
        fetched=len(data.get("results", [])),
        relevant=len(items),
    )
    return CollectorResult(items=items, diagnostics=[diagnostic])


def collect_sources() -> CollectorResult:
    collected: List[NewsItem] = []
    diagnostics: List[SourceDiagnostic] = []
    for fetcher in [fetch_registered_sources, fetch_federal_register]:
        try:
            result = fetcher()
            collected.extend(result.items)
            diagnostics.extend(result.diagnostics)
        except Exception as exc:
            diagnostics.append(SourceDiagnostic(source=fetcher.__name__, ok=False, error=repr(exc)))
            print(f"Source fetch failed: {fetcher.__name__}: {exc}")
    return CollectorResult(items=deduplicate_items(collected), diagnostics=diagnostics)


def fetch_all_sources() -> List[NewsItem]:
    return collect_sources().items


def fetch_source_diagnostics() -> List[SourceDiagnostic]:
    return collect_sources().diagnostics
