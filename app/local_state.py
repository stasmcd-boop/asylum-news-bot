import json
from pathlib import Path
from typing import Set

STATE_DIR = Path(".state")
PUBLISHED_FILE = STATE_DIR / "published_urls.json"


class LocalState:
    def __init__(self) -> None:
        STATE_DIR.mkdir(exist_ok=True)
        self.published_urls: Set[str] = self._load_urls()

    def _load_urls(self) -> Set[str]:
        if not PUBLISHED_FILE.exists():
            return set()
        try:
            data = json.loads(PUBLISHED_FILE.read_text(encoding="utf-8"))
            return set(data if isinstance(data, list) else [])
        except Exception:
            return set()

    def is_published(self, url: str) -> bool:
        return url in self.published_urls

    def mark_published(self, url: str) -> None:
        self.published_urls.add(url)
        PUBLISHED_FILE.write_text(
            json.dumps(sorted(self.published_urls), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
