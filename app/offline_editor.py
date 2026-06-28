from html import escape

from app.models import NewsItem

IMPORTANCE = {
    "important": "🔴 ВАЖНО",
    "medium": "🟠 ВАЖНО ЗНАТЬ",
    "info": "🟢 ИНФОРМАЦИЯ",
}

CATEGORY_RU = {
    "asylum": "убежище / asylum",
    "court": "иммиграционный суд / EOIR",
    "ead": "разрешение на работу / EAD",
    "tps": "Temporary Protected Status / TPS",
    "parole": "humanitarian parole",
    "deportation": "депортация / removal",
    "policy": "новые правила и процедуры",
    "immigration": "иммиграция США",
    "general": "иммиграция США",
}

TITLE_HINTS = {
    "ead": "Изменения по разрешениям на работу в США",
    "asylum": "Новое обновление по теме убежища в США",
    "court": "Обновление, связанное с иммиграционными процедурами",
    "tps": "Обновление по TPS",
    "parole": "Обновление по humanitarian parole",
    "deportation": "Обновление по removal / deportation",
    "policy": "Официальное изменение в иммиграционных правилах США",
}


def build_offline_post(item: NewsItem) -> str:
    label = IMPORTANCE.get(item.importance, "🟢 ИНФОРМАЦИЯ")
    category = CATEGORY_RU.get(item.category, "иммиграция США")
    title = TITLE_HINTS.get(item.category, "Официальное обновление по иммиграции США")
    date = item.published_at.date().isoformat() if item.published_at else "дата не указана"

    original = escape(item.title)
    source = escape(item.source)
    url = escape(item.url)

    post = f"""{label}
<b>{escape(title)}</b>

<b>Что произошло</b>
Опубликован официальный документ: <b>{original}</b>.
Источник: {source}. Дата публикации: {escape(date)}.

<b>Кого может касаться</b>
Это может быть полезно людям, которые следят за темами: {escape(category)}, USCIS, EOIR, EAD, TPS, parole, immigration court или removal proceedings.

<b>Что это значит простыми словами</b>
Сейчас бот работает в режиме без OpenAI: он находит официальные документы, определяет тему и важность, но не делает глубокий юридический разбор текста. После подключения OpenAI API здесь будет подробное объяснение простым русским языком.

<b>Что делать сейчас</b>
Проверьте официальный источник. Если документ касается вашей ситуации, лучше сохранить ссылку и при необходимости обсудить её с иммиграционным специалистом.

<b>Официальный источник</b>
{url}

Это информационный пост, не юридическая консультация."""
    return post[:3900]
