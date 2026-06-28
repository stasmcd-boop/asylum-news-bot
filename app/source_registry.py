from dataclasses import dataclass
from typing import Literal

SourceType = Literal["rss", "federal_register"]


@dataclass(frozen=True)
class SourceConfig:
    name: str
    type: SourceType
    url: str = ""
    priority: int = 5
    enabled: bool = True
    group: str = "official"


SOURCES = [
    SourceConfig(
        name="USCIS Newsroom",
        type="rss",
        url="https://www.uscis.gov/news/rss-feed.xml",
        priority=10,
        group="official",
    ),
    SourceConfig(
        name="DOJ EOIR News",
        type="rss",
        url="https://www.justice.gov/news/rss?f%5B0%5D=field_pr_component%3A361",
        priority=9,
        group="official",
    ),
    SourceConfig(
        name="DOJ Civil Division",
        type="rss",
        url="https://www.justice.gov/news/rss?f%5B0%5D=field_pr_component%3A196",
        priority=7,
        group="official",
    ),
    SourceConfig(
        name="DHS News",
        type="rss",
        url="https://www.dhs.gov/news-releases/press-releases/rss.xml",
        priority=9,
        group="official",
    ),
    SourceConfig(
        name="ICE Newsroom",
        type="rss",
        url="https://www.ice.gov/news/rss.xml",
        priority=8,
        group="official",
    ),
    SourceConfig(
        name="CBP Newsroom",
        type="rss",
        url="https://www.cbp.gov/newsroom/rss.xml",
        priority=8,
        group="official",
    ),
    SourceConfig(
        name="White House",
        type="rss",
        url="https://www.whitehouse.gov/briefing-room/feed/",
        priority=10,
        group="official",
    ),
    SourceConfig(
        name="Federal Register",
        type="federal_register",
        priority=8,
        group="official",
    ),
]


def enabled_sources():
    return [source for source in SOURCES if source.enabled]


def source_priority(name: str) -> int:
    for source in SOURCES:
        if source.name == name:
            return source.priority
    return 5
