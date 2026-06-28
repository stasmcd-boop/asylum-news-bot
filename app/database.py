from typing import Optional
from supabase import create_client, Client

from app.config import settings
from app.models import NewsItem


class Database:
    def __init__(self) -> None:
        self.client: Optional[Client] = None
        self.error: Optional[str] = None
        if settings.supabase_url and settings.supabase_service_key:
            try:
                self.client = create_client(settings.supabase_url, settings.supabase_service_key)
            except Exception as exc:
                self.error = f"Supabase disabled: {exc}"
                self.client = None

    def enabled(self) -> bool:
        return self.client is not None and self.error is None

    def news_exists(self, url: str) -> bool:
        if not self.enabled():
            return False
        try:
            result = self.client.table("news_items").select("id").eq("url", url).limit(1).execute()
            return bool(result.data)
        except Exception as exc:
            self.error = f"Supabase query failed: {exc}"
            self.client = None
            return False

    def save_news(self, item: NewsItem, status: str = "collected") -> None:
        if not self.enabled():
            return
        payload = {
            "source": item.source,
            "title_original": item.title,
            "title_ru": None,
            "url": item.url,
            "published_at": item.published_at.isoformat() if item.published_at else None,
            "category": item.category,
            "importance": item.importance,
            "summary_ru": None,
            "post_text_ru": None,
            "image_prompt": None,
            "status": status,
        }
        try:
            self.client.table("news_items").upsert(payload, on_conflict="url").execute()
        except Exception as exc:
            self.error = f"Supabase save failed: {exc}"
            self.client = None
