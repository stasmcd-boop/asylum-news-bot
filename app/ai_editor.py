from openai import OpenAI

from app.config import settings
from app.models import NewsItem
from app.post_builder import build_basic_post


class AIEditor:
    def __init__(self) -> None:
        self.enabled = bool(settings.openai_api_key and not settings.openai_api_key.startswith("paste_"))
        self.client = OpenAI(api_key=settings.openai_api_key) if self.enabled else None

    def build_post(self, item: NewsItem) -> str:
        if not self.client:
            return build_basic_post(item)

        date = item.published_at.date().isoformat() if item.published_at else "unknown"
        prompt = f"""
Ты — русскоязычный редактор Telegram-канала об иммиграционных новостях США.
Нужно написать короткий, понятный пост на русском языке по официальному источнику.

Требования:
- не выдумывай факты;
- если данных мало, честно напиши, что нужен полный текст источника;
- язык простой, без сложного юридического стиля;
- структура должна быть удобной для Telegram;
- обязательно укажи официальный источник ссылкой;
- не давай персональную юридическую консультацию;
- добавь короткий дисклеймер: «Это информационный пост, не юридическая консультация.»

Данные новости:
Источник: {item.source}
Дата: {date}
Категория: {item.category}
Важность: {item.importance}
Заголовок: {item.title}
Краткое описание: {item.summary[:1500]}
Ссылка: {item.url}

Формат:
[эмодзи важности] <b>Короткий русский заголовок</b>

<b>Что произошло</b>
...

<b>Кого может касаться</b>
...

<b>Что это значит простыми словами</b>
...

<b>Что делать сейчас</b>
...

<b>Официальный источник</b>
ссылка

Это информационный пост, не юридическая консультация.
""".strip()

        try:
            response = self.client.chat.completions.create(
                model=settings.openai_model,
                messages=[
                    {"role": "system", "content": "Ты пишешь точные, осторожные и полезные посты на русском языке."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
                max_tokens=900,
            )
            text = response.choices[0].message.content or ""
            return text[:3900]
        except Exception as exc:
            print(f"AI editor failed, fallback to basic post: {exc}")
            return build_basic_post(item)
