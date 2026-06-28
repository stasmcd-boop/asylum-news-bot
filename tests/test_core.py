import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from app.bot_runner import fresh_items, sort_items
from app.draft_store import DraftStore
from app.filters import detect_category, detect_importance, is_relevant
from app.intelligence import analyze_item, detect_deadline, determine_urgency
from app.local_state import LocalState
from app.models import NewsItem
from app.search import filter_items, matches_query
from app.sources import _parse_page_date, deduplicate_items, rank_items


class FilterTests(unittest.TestCase):
    def test_detects_relevant_asylum_update(self):
        self.assertTrue(is_relevant("USCIS updates asylum procedure", ""))
        self.assertEqual(detect_category("New credible fear guidance", ""), "asylum")
        self.assertEqual(detect_importance("TPS extended for eligible nationals", ""), "important")

    def test_ignores_unrelated_text(self):
        self.assertFalse(is_relevant("Agency announces office renovation", ""))


class BotRunnerTests(unittest.TestCase):
    def test_sort_items_prefers_importance_then_newer_date(self):
        old_important = NewsItem(
            source="A",
            title="Old important",
            url="https://example.com/old",
            published_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
            importance="important",
        )
        new_medium = NewsItem(
            source="B",
            title="New medium",
            url="https://example.com/new",
            published_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            importance="medium",
        )

        self.assertEqual(sort_items([new_medium, old_important]), [old_important, new_medium])

    def test_fresh_items_excludes_items_without_dates(self):
        dated = NewsItem(
            source="A",
            title="Dated",
            url="https://example.com/dated",
            published_at=datetime.now(timezone.utc),
        )
        undated = NewsItem(source="B", title="Undated", url="https://example.com/undated")

        self.assertEqual(fresh_items([dated, undated], days=1), [dated])


class SourceCollectorTests(unittest.TestCase):
    def test_parse_page_date_from_listing_text(self):
        parsed = _parse_page_date("Court Order on Hold Policies June 12, 2026 Some summary text")
        self.assertEqual(parsed, datetime(2026, 6, 12, tzinfo=timezone.utc))

    def test_deduplicate_items_removes_tracking_url_duplicates(self):
        original = NewsItem(
            source="USCIS",
            title="USCIS Updates Asylum Procedure",
            url="https://www.uscis.gov/news/asylum?utm_source=email",
            published_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            importance="medium",
            source_rank=5,
        )
        duplicate = NewsItem(
            source="Mirror",
            title="USCIS Updates Asylum Procedure",
            url="https://www.uscis.gov/news/asylum",
            published_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            importance="medium",
            source_rank=50,
        )

        self.assertEqual(deduplicate_items([duplicate, original]), [original])

    def test_rank_items_prefers_official_source_when_importance_matches(self):
        official = NewsItem(
            source="USCIS",
            title="Official",
            url="https://example.com/official",
            published_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            importance="medium",
            source_rank=5,
        )
        wire = NewsItem(
            source="Wire",
            title="Wire",
            url="https://example.com/wire",
            published_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
            importance="medium",
            source_rank=40,
        )

        self.assertEqual(rank_items([wire, official]), [official, wire])


class LocalStateTests(unittest.TestCase):
    def test_mark_published_persists_to_configured_directory(self):
        with TemporaryDirectory() as tmp:
            state = LocalState(Path(tmp))
            state.mark_published("https://example.com/news")

            saved = json.loads((Path(tmp) / "published_urls.json").read_text(encoding="utf-8"))
            self.assertEqual(saved, ["https://example.com/news"])
            self.assertTrue(LocalState(Path(tmp)).is_published("https://example.com/news"))


class IntelligenceTests(unittest.TestCase):
    def test_determine_urgency_promotes_deadline_language(self):
        item = NewsItem(
            source="USCIS",
            title="USCIS announces filing deadline",
            url="https://example.com/deadline",
            importance="info",
        )

        self.assertEqual(determine_urgency(item), "high")

    def test_analyze_item_returns_affected_groups_and_tags(self):
        item = NewsItem(
            source="USCIS News",
            title="DHS extends Temporary Protected Status",
            url="https://example.com/tps",
            category="tps",
            importance="important",
            summary="TPS extended for eligible nationals.",
        )

        analysis = analyze_item(item)

        self.assertEqual(analysis.urgency, "high")
        self.assertIn("люди с TPS", analysis.affected_groups)
        self.assertIn("tps", analysis.tags)
        self.assertEqual(analysis.confidence, "medium")

    def test_analysis_detects_deadline_and_scores_impact(self):
        item = NewsItem(
            source="USCIS News",
            title="USCIS announces asylum filing deadline by July 15, 2026",
            url="https://example.com/asylum-deadline",
            category="asylum",
            importance="medium",
            summary="Applications must be filed by July 15, 2026.",
        )

        analysis = analyze_item(item)

        self.assertEqual(detect_deadline(item), "2026-07-15")
        self.assertEqual(analysis.urgency, "high")
        self.assertTrue(analysis.action_required)
        self.assertGreaterEqual(analysis.impact_score, 75)
        self.assertEqual(analysis.deadline, "2026-07-15")


class DraftStoreTests(unittest.TestCase):
    def test_ingest_items_persists_structured_draft(self):
        with TemporaryDirectory() as tmp:
            store = DraftStore(Path(tmp))
            item = NewsItem(
                source="USCIS News",
                title="DHS extends Temporary Protected Status",
                url="https://example.com/tps-draft",
                category="tps",
                importance="important",
                summary="TPS extended for eligible nationals.",
            )

            drafts = store.ingest_items([item])
            saved = store.list_drafts(status="draft_ready")

            self.assertEqual(len(drafts), 1)
            self.assertEqual(len(saved), 1)
            self.assertEqual(saved[0].status, "draft_ready")
            self.assertIn("impact_score", saved[0].analysis)
            self.assertIn("Информационный пост, не юридическая консультация.", saved[0].draft_text)

    def test_update_changes_status_and_text(self):
        with TemporaryDirectory() as tmp:
            store = DraftStore(Path(tmp))
            item = NewsItem(source="USCIS", title="EAD update", url="https://example.com/ead-draft", category="ead")
            draft = store.ingest_items([item])[0]

            updated = store.update(draft.id, draft_text="new text", status="ignored")

            self.assertIsNotNone(updated)
            self.assertEqual(store.get(draft.id).status, "ignored")
            self.assertEqual(store.get(draft.id).draft_text, "new text")


class SearchTests(unittest.TestCase):
    def test_matches_query_requires_all_words(self):
        item = NewsItem(
            source="USCIS",
            title="USCIS updates asylum filing deadline",
            url="https://example.com/asylum",
            summary="Important asylum filing update.",
        )

        self.assertTrue(matches_query(item, "asylum deadline"))
        self.assertFalse(matches_query(item, "asylum tps"))

    def test_filter_items_by_category_and_urgency(self):
        tps = NewsItem(
            source="USCIS",
            title="DHS extends TPS deadline",
            url="https://example.com/tps",
            category="tps",
            importance="info",
        )
        ead = NewsItem(
            source="USCIS",
            title="EAD update",
            url="https://example.com/ead",
            category="ead",
            importance="info",
        )

        self.assertEqual(filter_items([tps, ead], category="tps", urgency="high"), [tps])


if __name__ == "__main__":
    unittest.main()
