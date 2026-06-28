from html import escape

from app.models import NewsItem

IMPORTANCE_LABELS = {
    "important": "🔴 ВАЖНО",
    "medium": "🟠 ВАЖНО ЗНАТЬ",
    "info": "🟢 ИНФОРМАЦИЯ",
}

CATEGORY_LABELS = {
    "asylum": "Убежище",
    "court": "Иммиграционный суд",
    "ead": "Разрешение на работу / EAD",
    "tps": "TPS",
    "parole": "Humanitarian Parole",
    "deportation": "Депортация / Removal",
    "policy": "Новые правила / политика",
    "immigration": "Иммиграция США",
    "general": "Иммиграция США",
}


def build_basic_post(item: NewsItem) -> str:
    importance = IMPORTANCE_LABELS.get(item.importance, "🟢 ИНФОРМАЦИЯ")
    category = CATEGORY_LABELS.get(item.category, item.category)
    date = item.published_at.date().isoformat() if item.published_at else "дата не указана"

    text = (
        f"{importance}\n"
        f"<b>{escape(item.title)}</b>\n\n"
        f"<b>Категория:</b> {escape(category)}\n"
        f"<b>Источник:</b> {escape(item.source)}\n"
        f"<b>Дата:</b> {escape(date)}\n\n"
        "<b>Что известно сейчас:</b>\n"
        "Найден официальный документ/обновление по теме иммиграции США. "
        "На следующем этапе бот будет автоматически делать подробный перевод и объяснение простым языком.\n\n"
        "<b>Кого может касаться:</b>\n"
        "Людей, которые следят за изменениями в asylum, immigration court, EAD, TPS, parole или removal proceedings.\n\n"
        f"<b>Источник:</b> {escape(item.url)}"
    )
    return text[:3900]
