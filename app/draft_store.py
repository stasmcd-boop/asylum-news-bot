import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List

from app.config import settings
from app.content_fetcher import ArticleContent, fetch_article_content
from app.editorial_text import build_editorial_text
from app.intelligence import IntelligenceAnalysis, analyze_item
from app.models import NewsItem
from app.offline_editor import build_offline_post

DRAFT_STATUSES = {"collected", "analyzed", "draft_ready", "edited", "published", "ignored"}


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
    telegram_text: str
    source_type: str = "official"
    published_at: str = ""
    collected_at: str = ""
    extracted_text: str = ""
    russian_summary: str = ""
    russian_explanation: str = ""
    affected_groups: List[str] = field(default_factory=list)
    urgency: str = ""
    impact_score: int = 0
    recommended_action: str = ""
    image_url: str = ""
    created_at: str = ""
    updated_at: str = ""
    tags: List[str] = field(default_factory=list)

    @classmethod
    def from_item(
        cls,
        item: NewsItem,
        analysis: IntelligenceAnalysis | None = None,
        content: ArticleContent | None = None,
        editorial_builder=build_editorial_text,
    ) -> "DraftRecord":
        analysis = analysis or analyze_item(item)
        content = content or ArticleContent()
        extracted_text = content.extracted_text or item.summary
        russian_summary, russian_explanation = editorial_builder(item, extracted_text, analysis)
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
            telegram_text=build_offline_post(item),
            source_type=item.source_type,
            published_at=item.published_at.isoformat() if item.published_at else "",
            collected_at=now,
            extracted_text=extracted_text,
            russian_summary=russian_summary,
            russian_explanation=russian_explanation,
            affected_groups=analysis.affected_groups,
            urgency=analysis.urgency,
            impact_score=analysis.impact_score,
            recommended_action=analysis.recommended_action,
            image_url=content.image_url,
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
            telegram_text=data.get("telegram_text") or data.get("draft_text", ""),
            source_type=data.get("source_type", "official"),
            published_at=data.get("published_at", ""),
            collected_at=data.get("collected_at") or data.get("created_at", ""),
            extracted_text=data.get("extracted_text", ""),
            russian_summary=data.get("russian_summary") or data.get("analysis", {}).get("plain_russian_summary", ""),
            russian_explanation=data.get("russian_explanation") or data.get("analysis", {}).get("previous_rules_ru", ""),
            affected_groups=list(data.get("affected_groups") or data.get("analysis", {}).get("affected_groups", [])),
            urgency=data.get("urgency") or data.get("analysis", {}).get("urgency", ""),
            impact_score=int(data.get("impact_score") or data.get("analysis", {}).get("impact_score", 0)),
            recommended_action=data.get("recommended_action") or data.get("analysis", {}).get("recommended_action", ""),
            image_url=data.get("image_url", ""),
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
            "source_type": self.source_type,
            "published_at": self.published_at,
            "collected_at": self.collected_at,
            "extracted_text": self.extracted_text,
            "russian_summary": self.russian_summary,
            "russian_explanation": self.russian_explanation,
            "affected_groups": self.affected_groups,
            "urgency": self.urgency,
            "impact_score": self.impact_score,
            "recommended_action": self.recommended_action,
            "image_url": self.image_url,
            "telegram_text": self.telegram_text,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "tags": self.tags,
        }


class DraftStore:
    def __init__(
        self,
        state_dir: Path | None = None,
        content_fetcher=fetch_article_content,
        editorial_builder=build_editorial_text,
    ) -> None:
        self.state_dir = state_dir or settings.state_dir
        self.path = self.state_dir / "drafts.json"
        self.content_fetcher = content_fetcher
        self.editorial_builder = editorial_builder
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
                draft = drafts[draft_id]
                if not draft.extracted_text or not draft.russian_summary:
                    analysis = analyze_item(item)
                    content = self.content_fetcher(item.url)
                    extracted_text = content.extracted_text or item.summary
                    russian_summary, russian_explanation = self.editorial_builder(item, extracted_text, analysis)
                    draft.analysis = analysis.to_dict()
                    draft.source_type = item.source_type
                    draft.extracted_text = draft.extracted_text or extracted_text
                    draft.russian_summary = draft.russian_summary or russian_summary
                    draft.russian_explanation = draft.russian_explanation or russian_explanation
                    draft.affected_groups = draft.affected_groups or analysis.affected_groups
                    draft.urgency = draft.urgency or analysis.urgency
                    draft.impact_score = draft.impact_score or analysis.impact_score
                    draft.recommended_action = draft.recommended_action or analysis.recommended_action
                    draft.image_url = draft.image_url or content.image_url
                    draft.tags = draft.tags or analysis.tags
                    draft.updated_at = utc_now_iso()
                    changed = True
                continue
            drafts[draft_id] = DraftRecord.from_item(
                item,
                content=self.content_fetcher(item.url),
                editorial_builder=self.editorial_builder,
            )
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
        return sorted(result, key=lambda draft: (draft.status != "draft_ready", -draft.impact_score, draft.updated_at), reverse=False)

    def get(self, draft_id: str) -> DraftRecord | None:
        return self._load().get(draft_id)

    def update(
        self,
        draft_id: str,
        draft_text: str | None = None,
        status: str | None = None,
        image_url: str | None = None,
    ) -> DraftRecord | None:
        drafts = self._load()
        draft = drafts.get(draft_id)
        if not draft:
            return None
        if draft_text is not None:
            draft.telegram_text = draft_text
            if status is None and draft.status == "draft_ready":
                draft.status = "edited"
        if image_url is not None:
            draft.image_url = image_url
        if status is not None:
            if status not in DRAFT_STATUSES:
                raise ValueError(f"Unsupported draft status: {status}")
            draft.status = status
        draft.updated_at = utc_now_iso()
        drafts[draft_id] = draft
        self._save(drafts)
        return draft

    def update_by_url(
        self,
        url: str,
        draft_text: str | None = None,
        status: str | None = None,
        image_url: str | None = None,
    ) -> DraftRecord | None:
        return self.update(draft_id_for_url(url), draft_text=draft_text, status=status, image_url=image_url)
