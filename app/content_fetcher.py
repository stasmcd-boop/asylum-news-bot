import re
from dataclasses import dataclass
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

REQUEST_HEADERS = {"User-Agent": "AsylumNewsBot/0.3 (+https://github.com/stasmcd-boop/asylum-news-bot)"}


@dataclass
class ArticleContent:
    extracted_text: str = ""
    image_url: str = ""
    error: str = ""


def clean_text(text: str, max_chars: int = 12000) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_chars]


def extract_readable_text_from_html(html: str, max_chars: int = 12000) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "nav", "footer", "header", "aside", "form"]):
        tag.decompose()

    article = soup.find("article") or soup.find("main")
    if article:
        text = article.get_text(" ", strip=True)
    else:
        text = soup.get_text(" ", strip=True)
    return clean_text(text, max_chars=max_chars)


def extract_image_url_from_html(html: str, base_url: str = "") -> str:
    soup = BeautifulSoup(html, "html.parser")
    selectors = [
        ("meta", {"property": "og:image"}, "content"),
        ("meta", {"name": "twitter:image"}, "content"),
        ("meta", {"property": "twitter:image"}, "content"),
    ]
    for tag_name, attrs, value_attr in selectors:
        tag = soup.find(tag_name, attrs=attrs)
        value = tag.get(value_attr, "").strip() if tag else ""
        if value:
            return urljoin(base_url, value)

    root = soup.find("article") or soup.find("main") or soup
    for image in root.find_all("img"):
        src = image.get("src") or image.get("data-src") or ""
        width = int(image.get("width") or 0) if str(image.get("width") or "").isdigit() else 0
        height = int(image.get("height") or 0) if str(image.get("height") or "").isdigit() else 0
        alt = image.get("alt", "").lower()
        if not src or any(word in src.lower() + " " + alt for word in ["logo", "icon", "avatar", "sprite"]):
            continue
        if width and height and (width < 180 or height < 120):
            continue
        return urljoin(base_url, src)
    return ""


def fetch_article_content(url: str, max_chars: int = 12000) -> ArticleContent:
    try:
        response = requests.get(url, timeout=30, headers=REQUEST_HEADERS)
        response.raise_for_status()
    except Exception as exc:
        return ArticleContent(error=repr(exc))

    return ArticleContent(
        extracted_text=extract_readable_text_from_html(response.text, max_chars=max_chars),
        image_url=extract_image_url_from_html(response.text, base_url=url),
    )


def fetch_page_text(url: str, max_chars: int = 8000) -> str:
    content = fetch_article_content(url, max_chars=max_chars)
    if content.error:
        print(f"Full text fetch failed: {content.error}")
    return content.extracted_text
