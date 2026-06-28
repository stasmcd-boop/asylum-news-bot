import feedparser
import requests
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import List

from app.filters import detect_category, detect_importance, is_relevant
from app.models import NewsItem
from app.source_registry import enabled_sources


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


def _entry_summary(entry) -> str:
    for attr in ["summary", "description", "subtitle"]:
        value = getattr(entry, attr, "")
        if value:
            return str(value).strip()
    return ""


def fetch_rss_source(source) -> List[NewsItem]:
    items: List[NewsItem] = []
    parsed = feedparser.parse(source.url)
    for entry in parsed.entries[:30]:
        title = getattr(entry, "title", "").strip()
        link = getattr(entry, "link", "").strip()
        summary = _entry_summary(entry)
        published = _parse_date(getattr(entry, "published", None) or getattr(entry, "updated", None))
        if not title or not link:
            continue
        if not is_relevant(title, summary):
            continue
        items.append(
            NewsItem(
                source=source.name,
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
    terms = [
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
    params = {
        "conditions[agencies][]": ["homeland-security-department", "justice-department"],
        "conditions[term]": " OR ".join(terms),
        "order": "newest",
        "per_page": 50,
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
    for source in enabled_sources():
        try:
            if source.type == "rss":
                collected.extend(fetch_rss_source(source))
            elif source.type == "federal_register":
                collected.extend(fetch_federal_register())
        except Exception as exc:
            print(f"Source fetch failed: {source.name}: {exc}")
    seen = set()
    unique: List[NewsItem] = []
    for item in collected:
        key = item.url.strip().lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique
