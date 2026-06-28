from datetime import datetime, timedelta, timezone
from typing import List

from app.ai_editor import AIEditor
from app.config import settings
from app.draft_store import DraftStore, draft_id_for_url
from app.local_state import LocalState
from app.models import NewsItem
from app.offline_editor import build_offline_post
from app.source_registry import source_fresh_days, source_priority
from app.sources import fetch_all_sources, rank_items
from app.telegram_client import TelegramClient


def sort_items(items: List[NewsItem]) -> List[NewsItem]:
    return rank_items(items)


def fresh_items(items: List[NewsItem], days: int = 60) -> List[NewsItem]:
    result = []
    now = datetime.now(timezone.utc)
    for item in items:
        if not item.published_at:
            continue
        published = item.published_at
        if published.tzinfo is None:
            published = published.replace(tzinfo=timezone.utc)
        source_days = min(days, source_fresh_days(item.source))
        cutoff = now - timedelta(days=source_days)
        if published >= cutoff:
            result.append(item)
    return result


def build_post(item: NewsItem, use_ai: bool = True) -> str:
    if use_ai:
        editor = AIEditor()
        post = editor.build_post(item)
        if editor.enabled and not editor.last_error:
            return post
    return build_offline_post(item)


def collect_new_items(limit: int = 3, days: int = 60) -> List[NewsItem]:
    state = LocalState()
    items = sort_items(fresh_items(fetch_all_sources(), days=days))
    return [item for item in items if not state.is_published(item.url)][:limit]


def publish_new_items(bot_token: str, channel: str, limit: int = 1, use_ai: bool = True, days: int = 60) -> int:
    state = LocalState()
    store = DraftStore()
    client = TelegramClient(bot_token, channel)
    items = collect_new_items(limit=limit, days=days)
    store.ingest_items(items)

    published = 0
    for item in items:
        draft = store.get(draft_id_for_url(item.url))
        if draft and draft.status in {"published", "ignored"}:
            continue
        post = draft.draft_text if draft else build_post(item, use_ai=use_ai)
        client.send_message(post)
        state.mark_published(item.url)
        store.update_by_url(item.url, draft_text=post, status="published")
        published += 1
        print(f"Published: {item.title}")

    if published == 0:
        print("No new items to publish.")
    return published


def build_daily_summary_text(days: int = 1) -> str:
    items = sort_items(fresh_items(fetch_all_sources(), days=days))[:10]
    today = datetime.now(settings.timezone_info()).strftime("%Y-%m-%d")
    if not items:
        return f"📌 <b>Daily summary: {today}</b>\n\nСегодня свежих релевантных обновлений не найдено."

    lines = [f"📌 <b>Daily summary: {today}</b>", ""]
    lines.append(f"Найдено свежих материалов: {len(items)}")
    lines.append("")
    for idx, item in enumerate(items, 1):
        date = item.published_at.date().isoformat() if item.published_at else "no-date"
        lines.append(f"{idx}. <b>{item.title}</b>")
        lines.append(f"   {item.source} | {date} | {item.importance} | {item.category}")
        lines.append(f"   {item.url}")
        lines.append("")
    lines.append("Это информационная сводка, не юридическая консультация.")
    return "\n".join(lines)[:3900]
