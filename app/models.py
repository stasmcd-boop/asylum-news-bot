from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class NewsItem:
    source: str
    title: str
    url: str
    published_at: Optional[datetime] = None
    summary: str = ""
    category: str = "general"
    importance: str = "info"
    source_rank: int = 50
    source_type: str = "official"
