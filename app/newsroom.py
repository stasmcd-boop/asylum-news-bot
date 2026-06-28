from collections import Counter
from datetime import datetime, timezone
from typing import Iterable, List

from app.draft_store import DraftRecord


TIMELINE_CATEGORIES = ["tps", "asylum", "court", "ead", "ice", "cbp", "parole"]


def _date_prefix(value: str) -> str:
    return value[:10] if value else ""


def dashboard_stats(drafts: Iterable[DraftRecord], diagnostics: Iterable) -> dict:
    today = datetime.now(timezone.utc).date().isoformat()
    drafts = list(drafts)
    diagnostics = list(diagnostics)
    return {
        "new_news": sum(1 for draft in drafts if _date_prefix(draft.collected_at) == today),
        "important_news": sum(1 for draft in drafts if draft.importance == "important" or draft.impact_score >= 75),
        "awaiting_review": sum(1 for draft in drafts if draft.status in {"draft_ready", "edited", "analyzed"}),
        "published_today": sum(1 for draft in drafts if draft.status == "published" and _date_prefix(draft.updated_at) == today),
        "ignored": sum(1 for draft in drafts if draft.status == "ignored"),
        "ai_processed": sum(1 for draft in drafts if draft.russian_summary and draft.russian_explanation),
        "collector_health": f"{sum(1 for item in diagnostics if item.ok)}/{len(diagnostics)}" if diagnostics else "0/0",
    }


def draft_search_text(draft: DraftRecord) -> str:
    return " ".join(
        [
            draft.title,
            draft.source,
            draft.extracted_text,
            draft.russian_summary,
            draft.russian_explanation,
            " ".join(draft.tags),
            " ".join(draft.affected_groups),
        ]
    ).lower()


def search_drafts(drafts: Iterable[DraftRecord], query: str) -> List[DraftRecord]:
    if not query:
        return list(drafts)
    parts = query.lower().split()
    return [draft for draft in drafts if all(part in draft_search_text(draft) for part in parts)]


def related_drafts(current: DraftRecord, drafts: Iterable[DraftRecord], limit: int = 5) -> List[DraftRecord]:
    current_terms = set(current.tags) | {current.category}
    scored = []
    for draft in drafts:
        if draft.id == current.id:
            continue
        terms = set(draft.tags) | {draft.category}
        score = len(current_terms & terms)
        if draft.source == current.source:
            score += 1
        if score:
            scored.append((score, draft))
    return [draft for _score, draft in sorted(scored, key=lambda row: (-row[0], row[1].published_at), reverse=False)[:limit]]


def timeline_for_category(drafts: Iterable[DraftRecord], category: str) -> List[DraftRecord]:
    return sorted(
        [draft for draft in drafts if draft.category == category],
        key=lambda draft: draft.published_at or draft.collected_at,
    )


def topic_counts(drafts: Iterable[DraftRecord]) -> Counter:
    return Counter(draft.category for draft in drafts)
