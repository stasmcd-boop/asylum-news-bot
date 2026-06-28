import feedparser
import requests
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Iterable, List

from app.models import NewsItem
from app.filters import is_relevant, detect_category, detect_importance

RSS_SOURCES = [
    {
        "name": "USCIS News",
        "url": "https://www.uscis.gov/news/rss-feed.xml",
    },
    {
        "name": "DOJ EOIR",
        "url": "https://www.justice.gov/news/rss?f%5B0%5D=field_pr_component%3A361",
    },
]


def _parse_date(value: str | None):
    if not value:
        return None
    try:
        return parsedate_to_datetime(value)
    except Exception:
        return None


def fetch_rss_sources() -> List[NewsItem]:
    items: List[NewsItem] = []
    for source in RSS_SOURCES:
        parsed = feedparser.parse(source["url"])
        for entry in parsed.entries[:20]:
            title = getattr(entry, "title", "").strip()
            link = getattr(entry, "link", "").strip()
            summary = getattr(entry, "summary", "").strip()
            published = _parse_date(getattr(entry, "published", None))
            if not title or not link:
                continue
            if not is_relevant(title, summary):
                continue
            items.append(
                NewsItem(
                    source=source["name"],
                    title=title,
                    url=link,
                    published_at=published,
                    summary=summary,
                    category=detect_category(title, summary),
                    importance=detect_importance(title, summary),
                )
            )
    return items


def fetch_federal_register() -> List[NewsItem]:
    params = {
        "conditions[agencies][]": ["homeland-security-department", "justice-department"],
        "conditions[term]": "asylum OR immigration OR deportation OR employment authorization OR temporary protected status",
        "order": "newest",
        "per_page": 20,
    }
    response = requests.get("https://www.federalregister.gov/api/v1/documents.json", params=params, timeout=30)
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
        items.append(
            NewsItem(
                source="Federal Register",
                title=title,
                url=url,
                published_at=published,
                summary=summary,
                category=detect_category(title, summary),
                importance=detect_importance(title, summary),
            )
        )
    return items


def fetch_all_sources() -> List[NewsItem]:
    collected: List[NewsItem] = []
    for fetcher in [fetch_rss_sources, fetch_federal_register]:
        try:
            collected.extend(fetcher())
        except Exception as exc:
            print(f"Source fetch failed: {fetcher.__name__}: {exc}")
    seen = set()
    unique: List[NewsItem] = []
    for item in collected:
        if item.url in seen:
            continue
        seen.add(item.url)
        unique.append(item)
    return unique
