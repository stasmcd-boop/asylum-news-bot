from html import escape

from app.intelligence import analyze_item
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
    analysis = analyze_item(item)
    affected = "\n".join(f"• {escape(group)}" for group in analysis.affected_groups)
    actions = "\n".join(f"• {escape(step)}" for step in analysis.action_steps_ru)
    deadline = escape(analysis.deadline or "не обнаружен автоматически")

    post = f"""{label}
<b>{escape(title)}</b>

<b>Что произошло</b>
Опубликован официальный документ: <b>{original}</b>.
Источник: {source}. Дата публикации: {escape(date)}.
Оценка влияния: <b>{analysis.impact_score}/100</b>. Срочность: <b>{escape(analysis.urgency)}</b>.

<b>Кого может касаться</b>
{affected}

<b>Что это значит простыми словами</b>
{escape(analysis.plain_summary_ru)}

<b>Сравнение с прежними правилами</b>
{escape(analysis.previous_rules_ru)}

<b>Дедлайн</b>
{deadline}

<b>Рекомендованное действие</b>
{escape(analysis.recommended_action)}

<b>Что делать сейчас</b>
{actions}

<b>Официальный источник</b>
{url}

Информационный пост, не юридическая консультация."""
    return post[:3900]
