from datetime import datetime
from typing import List

from app.ai_editor import AIEditor
from app.local_state import LocalState
from app.models import NewsItem
from app.offline_editor import build_offline_post
from app.sources import fetch_all_sources
from app.telegram_client import TelegramClient


def sort_items(items: List[NewsItem]) -> List[NewsItem]:
    priority = {"important": 0, "medium": 1, "info": 2}
    return sorted(
        items,
        key=lambda x: (priority.get(x.importance, 9), x.published_at or datetime.min),
    )


def build_post(item: NewsItem, use_ai: bool = True) -> str:
    if use_ai:
        editor = AIEditor()
        post = editor.build_post(item)
        if editor.enabled and not editor.last_error:
            return post
    return build_offline_post(item)


def collect_new_items(limit: int = 3) -> List[NewsItem]:
    state = LocalState()
    items = sort_items(fetch_all_sources())
    return [item for item in items if not state.is_published(item.url)][:limit]


def publish_new_items(bot_token: str, channel: str, limit: int = 1, use_ai: bool = True) -> int:
    state = LocalState()
    client = TelegramClient(bot_token, channel)
    items = collect_new_items(limit=limit)

    published = 0
    for item in items:
        post = build_post(item, use_ai=use_ai)
        client.send_message(post)
        state.mark_published(item.url)
        published += 1
        print(f"Published: {item.title}")

    if published == 0:
        print("No new items to publish.")
    return published


def build_daily_summary_text() -> str:
    items = sort_items(fetch_all_sources())[:10]
    if not items:
        return "📌 <b>Daily summary</b>\n\nСегодня релевантных обновлений не найдено."

    lines = ["📌 <b>Daily summary: immigration news USA</b>", ""]
    for idx, item in enumerate(items, 1):
        date = item.published_at.date().isoformat() if item.published_at else "no-date"
        lines.append(f"{idx}. <b>{item.title}</b>")
        lines.append(f"   {item.source} | {date} | {item.importance} | {item.category}")
        lines.append(f"   {item.url}")
        lines.append("")
    lines.append("Это информационная сводка, не юридическая консультация.")
    return "\n".join(lines)[:3900]
