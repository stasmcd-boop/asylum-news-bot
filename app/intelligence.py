from dataclasses import dataclass, field
from datetime import datetime, timezone
import re
from typing import List

from app.models import NewsItem


@dataclass
class IntelligenceAnalysis:
    urgency: str
    impact_score: int = 0
    action_required: bool = False
    deadline: str = ""
    affected_groups: List[str] = field(default_factory=list)
    plain_summary_ru: str = ""
    recommended_action: str = ""
    previous_rules_ru: str = ""
    action_steps_ru: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    confidence: str = "medium"

    def to_dict(self) -> dict:
        return {
            "urgency": self.urgency,
            "impact_score": self.impact_score,
            "action_required": self.action_required,
            "deadline": self.deadline,
            "affected_groups": self.affected_groups,
            "plain_russian_summary": self.plain_summary_ru,
            "recommended_action": self.recommended_action,
            "previous_rules_ru": self.previous_rules_ru,
            "action_steps_ru": self.action_steps_ru,
            "tags": self.tags,
            "confidence": self.confidence,
        }


GROUPS_BY_CATEGORY = {
    "asylum": ["люди с делами об убежище", "заявители на credible fear / reasonable fear", "адвокаты и аккредитованные представители"],
    "court": ["люди в immigration court", "люди с removal proceedings", "представители и переводчики"],
    "ead": ["заявители на разрешение на работу", "люди с pending asylum / TPS / parole", "работодатели, проверяющие документы"],
    "tps": ["люди с TPS", "люди, которые планируют продление TPS", "семьи заявителей TPS"],
    "parole": ["люди с humanitarian parole", "спонсоры и семьи заявителей", "люди, ожидающие разрешение на въезд"],
    "deportation": ["люди с риском removal / deportation", "люди с финальными приказами", "семьи и представители"],
    "policy": ["люди, которых затрагивают новые правила", "иммиграционные представители", "организации помощи мигрантам"],
    "immigration": ["иммигранты в США", "семьи заявителей", "иммиграционные представители"],
}

SUMMARY_BY_CATEGORY = {
    "asylum": "Это обновление связано с темой убежища или проверок страха преследования. Нужно сверить официальный источник, потому что такие изменения могут влиять на сроки, требования или порядок рассмотрения.",
    "court": "Это обновление связано с иммиграционным судом или процедурами removal. Оно может влиять на повестки, слушания, сроки или процесс ведения дела.",
    "ead": "Это обновление связано с разрешениями на работу. Оно может быть важно для людей, которые подают, продлевают или ожидают EAD.",
    "tps": "Это обновление связано с Temporary Protected Status. Важно проверить даты регистрации, продления и требования для конкретной страны.",
    "parole": "Это обновление связано с parole. Оно может касаться права на въезд, продления статуса или связанных документов.",
    "deportation": "Это обновление связано с removal или deportation. Такие новости требуют особенно внимательной проверки официального текста.",
    "policy": "Это официальное изменение правил или процедур. Его смысл зависит от даты вступления в силу и конкретной категории заявителей.",
    "immigration": "Это обновление относится к иммиграционной системе США. Перед действиями нужно прочитать официальный источник и проверить применимость к своей ситуации.",
}


def detect_deadline(item: NewsItem) -> str:
    text = f"{item.title} {item.summary}"
    patterns = [
        r"\b(?:by|until|before)\s+([A-Z][a-z]+ \d{1,2}, \d{4})\b",
        r"\b(deadline|effective date)[:\s]+([A-Z][a-z]+ \d{1,2}, \d{4})\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.I)
        if not match:
            continue
        value = match.group(match.lastindex or 1)
        if value.lower() in {"deadline", "effective date"} and match.lastindex and match.lastindex >= 2:
            value = match.group(2)
        try:
            return datetime.strptime(value, "%B %d, %Y").replace(tzinfo=timezone.utc).date().isoformat()
        except ValueError:
            continue
    return ""


def determine_urgency(item: NewsItem) -> str:
    text = f"{item.title} {item.summary}".lower()
    if item.importance == "important":
        return "high"
    if any(term in text for term in ["deadline", "effective", "terminated", "court order", "fee", "extended"]):
        return "high"
    if item.importance == "medium":
        return "medium"
    return "low"


def calculate_impact_score(item: NewsItem, urgency: str, deadline: str) -> int:
    score = {"important": 70, "medium": 45, "info": 20}.get(item.importance, 20)
    score += {"high": 20, "medium": 10, "low": 0}.get(urgency, 0)
    score += {
        "asylum": 8,
        "court": 8,
        "ead": 7,
        "tps": 7,
        "deportation": 10,
        "policy": 6,
    }.get(item.category, 3)
    if deadline:
        score += 5
    return min(score, 100)


def analyze_item(item: NewsItem) -> IntelligenceAnalysis:
    category = item.category if item.category in GROUPS_BY_CATEGORY else "immigration"
    urgency = determine_urgency(item)
    deadline = detect_deadline(item)
    impact_score = calculate_impact_score(item, urgency, deadline)
    action_required = urgency == "high" or bool(deadline) or impact_score >= 75
    tags = sorted({category, item.importance, urgency, item.source.lower().replace(" ", "-")})
    recommended_action = (
        "Проверьте официальный документ сегодня и сохраните ссылку; если новость касается вашего дела, обсудите ее с иммиграционным специалистом."
        if action_required
        else "Сохраните ссылку и следите за обновлениями по этой теме."
    )

    previous_rules = (
        "Из заголовка и краткого описания нельзя надежно сравнить с предыдущими правилами. "
        "Для точного сравнения нужно читать полный официальный документ."
    )
    if item.importance == "important":
        previous_rules = (
            "Вероятно, это меняет или уточняет действующий порядок. "
            "Нужно отдельно проверить дату вступления в силу, переходные правила и исключения."
        )

    return IntelligenceAnalysis(
        urgency=urgency,
        impact_score=impact_score,
        action_required=action_required,
        deadline=deadline,
        affected_groups=GROUPS_BY_CATEGORY[category],
        plain_summary_ru=SUMMARY_BY_CATEGORY[category],
        recommended_action=recommended_action,
        previous_rules_ru=previous_rules,
        action_steps_ru=[
            "Открыть официальный источник и проверить дату публикации.",
            recommended_action,
            "Сохранить ссылку, если тема касается вашей ситуации.",
            "Не менять стратегию по делу без консультации с иммиграционным специалистом.",
        ],
        tags=tags,
        confidence="medium" if item.summary else "low",
    )
