from dataclasses import dataclass
from typing import Literal
from urllib.parse import quote_plus

SourceType = Literal["rss", "federal_register", "google_news"]


@dataclass(frozen=True)
class SourceConfig:
    name: str
    type: SourceType
    url: str = ""
    priority: int = 5
    enabled: bool = True
    group: str = "official"
    fresh_days: int = 60


def google_news_url(query: str) -> str:
    return "https://news.google.com/rss/search?q=" + quote_plus(query) + "&hl=en-US&gl=US&ceid=US:en"


SOURCES = [
    SourceConfig("USCIS Newsroom", "rss", "https://www.uscis.gov/news/rss-feed.xml", 10, True, "official", 60),
    SourceConfig("DOJ EOIR News", "rss", "https://www.justice.gov/news/rss?f%5B0%5D=field_pr_component%3A361", 9, True, "official", 60),
    SourceConfig("DOJ Civil Division", "rss", "https://www.justice.gov/news/rss?f%5B0%5D=field_pr_component%3A196", 7, True, "official", 60),
    SourceConfig("DHS News", "rss", "https://www.dhs.gov/news-releases/press-releases/rss.xml", 9, True, "official", 60),
    SourceConfig("ICE Newsroom", "rss", "https://www.ice.gov/news/rss.xml", 8, True, "official", 60),
    SourceConfig("CBP Newsroom", "rss", "https://www.cbp.gov/newsroom/rss.xml", 8, True, "official", 60),
    SourceConfig("White House", "rss", "https://www.whitehouse.gov/briefing-room/feed/", 10, True, "official", 60),
    SourceConfig("Federal Register", "federal_register", priority=8, group="official", fresh_days=90),

    SourceConfig("Reuters Immigration", "google_news", google_news_url("site:reuters.com immigration asylum OR deportation OR USCIS OR DHS"), 8, True, "news", 14),
    SourceConfig("AP Immigration", "google_news", google_news_url("site:apnews.com immigration asylum OR deportation OR migrants OR DHS"), 8, True, "news", 14),
    SourceConfig("NPR Immigration", "google_news", google_news_url("site:npr.org immigration asylum OR deportation OR migrants"), 6, True, "news", 14),
    SourceConfig("PBS Immigration", "google_news", google_news_url("site:pbs.org immigration asylum OR deportation OR migrants"), 6, True, "news", 14),
    SourceConfig("Politico Immigration", "google_news", google_news_url("site:politico.com immigration asylum OR deportation OR DHS"), 7, True, "news", 14),
    SourceConfig("CNN Immigration", "google_news", google_news_url("site:cnn.com immigration asylum OR deportation OR migrants"), 5, True, "news", 10),
    SourceConfig("NYTimes Immigration", "google_news", google_news_url("site:nytimes.com immigration asylum OR deportation OR migrants"), 6, True, "news", 10),

    SourceConfig("AILA", "google_news", google_news_url("site:aila.org asylum USCIS EOIR TPS parole deportation"), 7, True, "professional", 30),
    SourceConfig("American Immigration Council", "google_news", google_news_url("site:americanimmigrationcouncil.org asylum USCIS EOIR immigration court"), 7, True, "professional", 30),
    SourceConfig("TRAC Immigration", "google_news", google_news_url("site:trac.syr.edu immigration court asylum EOIR"), 7, True, "data", 30),
]


def enabled_sources():
    return [source for source in SOURCES if source.enabled]


def source_priority(name: str) -> int:
    for source in SOURCES:
        if source.name == name:
            return source.priority
    return 5


def source_fresh_days(name: str) -> int:
    for source in SOURCES:
        if source.name == name:
            return source.fresh_days
    return 30
