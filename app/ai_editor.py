from openai import OpenAI

from app.config import settings
from app.content_fetcher import fetch_page_text
from app.models import NewsItem
from app.post_builder import build_basic_post


class AIEditor:
    def __init__(self) -> None:
        self.enabled = bool(settings.openai_api_key and not settings.openai_api_key.startswith("paste_"))
        self.client = OpenAI(api_key=settings.openai_api_key) if self.enabled else None
        self.last_error = ""

    def build_post(self, item: NewsItem, use_full_text: bool = True) -> str:
        if not self.client:
            self.last_error = "OpenAI client is disabled"
            return build_basic_post(item)

        date = item.published_at.date().isoformat() if item.published_at else "unknown"
        full_text = fetch_page_text(item.url) if use_full_text else ""
        source_text = full_text or item.summary or item.title
        print(f"AI editor: enabled=True, model={settings.openai_model}, full_text_chars={len(full_text)}, source_chars={len(source_text)}")

        prompt = f"""
Ты — русскоязычный редактор Telegram-канала об иммиграционных новостях США.
Твоя задача — написать полезный и осторожный Telegram-пост на русском языке по официальному источнику.

Правила:
- Не выдумывай факты.
- Используй только данные из источника ниже.
- Если данных недостаточно, прямо напиши, что требуется проверить полный документ.
- Не давай персональную юридическую консультацию.
- Пиши простым языком для людей, которые интересуются убежищем, судом, EAD, TPS, parole и похожими темами.
- Обязательно оставь ссылку на официальный источник.
- Используй HTML-теги Telegram: <b>...</b>, без Markdown.

Данные:
Источник: {item.source}
Дата: {date}
Категория: {item.category}
Важность: {item.importance}
Оригинальный заголовок: {item.title}
Ссылка: {item.url}

Текст источника:
{source_text[:6500]}

Сделай пост в формате:
🔴/🟠/🟢 <b>Короткий русский заголовок</b>

<b>Что произошло</b>
2-4 предложения.

<b>Кого может касаться</b>
Короткий список или 2-3 предложения.

<b>Что это значит простыми словами</b>
Короткое объяснение.

<b>Что делать сейчас</b>
Осторожные общие шаги: проверить источник, следить за обновлениями, консультироваться со специалистом при необходимости.

<b>Официальный источник</b>
{item.url}

Это информационный пост, не юридическая консультация.
""".strip()

        try:
            response = self.client.chat.completions.create(
                model=settings.openai_model,
                messages=[
                    {"role": "system", "content": "Ты точный и осторожный редактор. Ты не выдумываешь юридические факты."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
                max_tokens=1000,
            )
            text = response.choices[0].message.content or ""
            if not text.strip():
                self.last_error = "OpenAI returned empty text"
                return build_basic_post(item)
            return text[:3900]
        except Exception as exc:
            self.last_error = repr(exc)
            print(f"AI editor failed: {self.last_error}")
            return build_basic_post(item)
