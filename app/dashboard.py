from collections import Counter
from datetime import datetime
from typing import Iterable

from app.bot_runner import collect_new_items, fresh_items
from app.config import settings
from app.local_state import LocalState
from app.sources import fetch_all_sources


def dashboard_stats() -> dict:
    all_items = fetch_all_sources()
    fresh_60 = fresh_items(all_items, days=60)
    pending = collect_new_items(limit=100, days=60)
    state = LocalState()
    sources = Counter(item.source for item in fresh_60)
    categories = Counter(item.category for item in fresh_60)
    importance = Counter(item.importance for item in fresh_60)
    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "total_found": len(all_items),
        "fresh_60": len(fresh_60),
        "pending": len(pending),
        "published_local": len(state.published_urls),
        "telegram_online": bool(settings.telegram_bot_token and settings.telegram_channel),
        "openai_configured": bool(settings.openai_api_key and not settings.openai_api_key.startswith("paste_")),
        "sources": sources,
        "categories": categories,
        "importance": importance,
    }


def importance_class(value: str) -> str:
    if value == "important":
        return "danger"
    if value == "medium":
        return "warning"
    return "success"
