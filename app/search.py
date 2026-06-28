from typing import Iterable, List

from app.intelligence import analyze_item
from app.models import NewsItem


def matches_query(item: NewsItem, query: str) -> bool:
    if not query:
        return True
    text = " ".join([item.title, item.summary, item.source, item.category, item.importance]).lower()
    return all(part in text for part in query.lower().split())


def filter_items(
    items: Iterable[NewsItem],
    query: str = "",
    category: str = "",
    importance: str = "",
    urgency: str = "",
) -> List[NewsItem]:
    result: List[NewsItem] = []
    for item in items:
        analysis = analyze_item(item)
        if category and item.category != category:
            continue
        if importance and item.importance != importance:
            continue
        if urgency and analysis.urgency != urgency:
            continue
        if not matches_query(item, query):
            continue
        result.append(item)
    return result
