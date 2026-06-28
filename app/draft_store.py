import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List

from app.config import settings
from app.intelligence import IntelligenceAnalysis, analyze_item
from app.models import NewsItem
from app.offline_editor import build_offline_post

DRAFT_STATUSES = {"collected", "analyzed", "draft_ready", "published", "ignored"}


def draft_id_for_url(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass
class DraftRecord:
    id: str
    source: str
    title: str
    url: str
    status: str
    category: str
    importance: str
    analysis: dict
    draft_text: str
    published_at: str = ""
    created_at: str = ""
    updated_at: str = ""
    tags: List[str] = field(default_factory=list)

    @classmethod
    def from_item(cls, item: NewsItem, analysis: IntelligenceAnalysis | None = None) -> "DraftRecord":
        analysis = analysis or analyze_item(item)
        now = utc_now_iso()
        return cls(
            id=draft_id_for_url(item.url),
            source=item.source,
            title=item.title,
            url=item.url,
            status="draft_ready",
            category=item.category,
            importance=item.importance,
            analysis=analysis.to_dict(),
            draft_text=build_offline_post(item),
            published_at=item.published_at.isoformat() if item.published_at else "",
            created_at=now,
            updated_at=now,
            tags=analysis.tags,
        )

    @classmethod
    def from_dict(cls, data: dict) -> "DraftRecord":
        return cls(
            id=data.get("id", ""),
            source=data.get("source", ""),
            title=data.get("title", ""),
            url=data.get("url", ""),
            status=data.get("status", "collected"),
            category=data.get("category", "general"),
            importance=data.get("importance", "info"),
            analysis=data.get("analysis", {}),
            draft_text=data.get("draft_text", ""),
            published_at=data.get("published_at", ""),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            tags=list(data.get("tags", [])),
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "source": self.source,
            "title": self.title,
            "url": self.url,
            "status": self.status,
            "category": self.category,
            "importance": self.importance,
            "analysis": self.analysis,
            "draft_text": self.draft_text,
            "published_at": self.published_at,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "tags": self.tags,
        }


class DraftStore:
    def __init__(self, state_dir: Path | None = None) -> None:
        self.state_dir = state_dir or settings.state_dir
        self.path = self.state_dir / "drafts.json"
        self.state_dir.mkdir(parents=True, exist_ok=True)

    def _load(self) -> dict[str, DraftRecord]:
        if not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        return {row.get("id", ""): DraftRecord.from_dict(row) for row in data if row.get("id")}

    def _save(self, drafts: dict[str, DraftRecord]) -> None:
        rows = sorted(drafts.values(), key=lambda draft: draft.updated_at, reverse=True)
        self.path.write_text(
            json.dumps([draft.to_dict() for draft in rows], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def ingest_items(self, items: Iterable[NewsItem]) -> List[DraftRecord]:
        drafts = self._load()
        changed = False
        for item in items:
            draft_id = draft_id_for_url(item.url)
            if draft_id in drafts:
                continue
            drafts[draft_id] = DraftRecord.from_item(item)
            changed = True
        if changed:
            self._save(drafts)
        return list(drafts.values())

    def list_drafts(
        self,
        query: str = "",
        category: str = "",
        urgency: str = "",
        source: str = "",
        status: str = "",
    ) -> List[DraftRecord]:
        drafts = list(self._load().values())
        result = []
        for draft in drafts:
            text = " ".join([draft.title, draft.source, " ".join(draft.tags)]).lower()
            if query and not all(part in text for part in query.lower().split()):
                continue
            if category and draft.category != category:
                continue
            if urgency and draft.analysis.get("urgency") != urgency:
                continue
            if source and source.lower() not in draft.source.lower():
                continue
            if status and draft.status != status:
                continue
            result.append(draft)
        return sorted(result, key=lambda draft: (draft.status != "draft_ready", -draft.analysis.get("impact_score", 0), draft.updated_at), reverse=False)

    def get(self, draft_id: str) -> DraftRecord | None:
        return self._load().get(draft_id)

    def update(self, draft_id: str, draft_text: str | None = None, status: str | None = None) -> DraftRecord | None:
        drafts = self._load()
        draft = drafts.get(draft_id)
        if not draft:
            return None
        if draft_text is not None:
            draft.draft_text = draft_text
        if status is not None:
            if status not in DRAFT_STATUSES:
                raise ValueError(f"Unsupported draft status: {status}")
            draft.status = status
        draft.updated_at = utc_now_iso()
        drafts[draft_id] = draft
        self._save(drafts)
        return draft

    def update_by_url(self, url: str, draft_text: str | None = None, status: str | None = None) -> DraftRecord | None:
        return self.update(draft_id_for_url(url), draft_text=draft_text, status=status)
