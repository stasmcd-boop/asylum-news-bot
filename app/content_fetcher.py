import re
import requests
from bs4 import BeautifulSoup


def fetch_page_text(url: str, max_chars: int = 8000) -> str:
    try:
        response = requests.get(url, timeout=30, headers={"User-Agent": "AsylumNewsBot/0.1"})
        response.raise_for_status()
    except Exception as exc:
        print(f"Full text fetch failed: {exc}")
        return ""

    soup = BeautifulSoup(response.text, "html.parser")
    for tag in soup(["script", "style", "noscript", "nav", "footer", "header"]):
        tag.decompose()

    text = soup.get_text(" ", strip=True)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_chars]
