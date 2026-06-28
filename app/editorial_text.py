import json

from openai import OpenAI

from app.config import settings
from app.intelligence import IntelligenceAnalysis
from app.models import NewsItem


def fallback_editorial_text(item: NewsItem, analysis: IntelligenceAnalysis) -> tuple[str, str]:
    summary = analysis.plain_summary_ru
    explanation = (
        f"Официальный источник сообщает об обновлении: {item.title}. "
        f"Категория: {item.category}. Срочность: {analysis.urgency}. "
        "Перед любыми действиями важно сверить детали в первоисточнике."
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
