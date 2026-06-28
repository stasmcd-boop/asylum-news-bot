import json
from pathlib import Path
from typing import Set

from app.config import settings


class LocalState:
    def __init__(self, state_dir: Path | None = None) -> None:
        self.state_dir = state_dir or settings.state_dir
        self.published_file = self.state_dir / "published_urls.json"
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.published_urls: Set[str] = self._load_urls()

    def _load_urls(self) -> Set[str]:
        if not self.published_file.exists():
            return set()
        try:
            data = json.loads(self.published_file.read_text(encoding="utf-8"))
            return set(data if isinstance(data, list) else [])
        except Exception:
            return set()

    def is_published(self, url: str) -> bool:
        return url in self.published_urls

    def mark_published(self, url: str) -> None:
        self.published_urls.add(url)
        self.published_file.write_text(
            json.dumps(sorted(self.published_urls), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
