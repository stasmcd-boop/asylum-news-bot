import json

from openai import OpenAI

from app.config import settings
from app.intelligence import IntelligenceAnalysis
from app.models import NewsItem


def fallback_editorial_text(item: NewsItem, analysis: IntelligenceAnalysis) -> tuple[str, str]:
    urgency = {"high": "срочно", "medium": "важно", "low": "обычно"}.get(analysis.urgency, analysis.urgency)
    date = item.published_at.date().isoformat() if item.published_at else "дата публикации не указана"
    affected = ", ".join(analysis.affected_groups[:3]) if analysis.affected_groups else "категория пока не определена"
    deadline = f" Срок, который нужно проверить: {analysis.deadline}." if analysis.deadline else ""
    effective = f" Дата вступления в силу: {analysis.effective_date}." if analysis.effective_date else ""
    summary = f"{analysis.plain_summary_ru} Новость: «{item.title}»."
    explanation = (
        f"{item.source} опубликовал материал ({date}) по теме «{item.title}». "
        f"Предварительно это может касаться: {affected}. "
        f"Срочность: {urgency}; оценка влияния: {analysis.impact_score}/100. "
        f"{analysis.new_rule_ru} {analysis.possible_consequences_ru}"
        f"{deadline}{effective} "
        "Это редакционная выжимка для первичной оценки: перед публикацией откройте источник, "
        "проверьте точные формулировки и не добавляйте неподтвержденные выводы."
    )
    return summary, explanation


def build_editorial_text(item: NewsItem, extracted_text: str, analysis: IntelligenceAnalysis) -> tuple[str, str]:
    if not settings.openai_api_key or settings.openai_api_key.startswith("paste_"):
        return fallback_editorial_text(item, analysis)

    prompt = f"""
Сделай редакторскую выжимку на русском для иммиграционной новости США.
Не давай юридическую консультацию. Не выдумывай факты.
Верни только JSON с ключами russian_summary и russian_explanation.

Источник: {item.source}
Заголовок: {item.title}
Категория: {item.category}
Срочность: {analysis.urgency}
URL: {item.url}

Текст:
{(extracted_text or item.summary or item.title)[:7000]}
""".strip()
    try:
        response = OpenAI(api_key=settings.openai_api_key).chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": "Ты точный русскоязычный редактор иммиграционных новостей США."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=700,
        )
        raw = response.choices[0].message.content or ""
        data = json.loads(raw)
        summary = str(data.get("russian_summary", "")).strip()
        explanation = str(data.get("russian_explanation", "")).strip()
        if summary and explanation:
            return summary, explanation
    except Exception as exc:
        print(f"AI editorial text failed: {repr(exc)}")
    return fallback_editorial_text(item, analysis)
