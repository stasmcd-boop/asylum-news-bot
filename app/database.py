from typing import Optional
from supabase import create_client, Client

from app.config import settings
from app.models import NewsItem


class Database:
    def __init__(self) -> None:
        self.client: Optional[Client] = None
        if settings.supabase_url and settings.supabase_service_key:
            self.client = create_client(settings.supabase_url, settings.supabase_service_key)

    def enabled(self) -> bool:
        return self.client is not None

    def news_exists(self, url: str) -> bool:
        if not self.client:
            return False
        result = self.client.table("news_items").select("id").eq("url", url).limit(1).execute()
        return bool(result.data)

    def save_news(self, item: NewsItem, status: str = "collected") -> None:
        if not self.client:
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
        self.client.table("news_items").upsert(payload, on_conflict="url").execute()
