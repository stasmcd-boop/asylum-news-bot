KEYWORDS = [
    "asylum", "refugee", "credible fear", "reasonable fear",
    "immigration court", "eoir", "uscis", "ice", "cbp", "dhs",
    "tps", "temporary protected status", "humanitarian parole", "parole",
    "ead", "employment authorization", "work permit",
    "removal", "deportation", "notice to appear", "nta",
    "policy manual", "executive order", "federal register",
    "border", "migrant", "immigration", "noncitizen",
]

CATEGORY_RULES = {
    "asylum": ["asylum", "credible fear", "reasonable fear", "refugee"],
    "court": ["immigration court", "eoir", "notice to appear", "nta", "removal proceedings"],
    "ead": ["ead", "employment authorization", "work permit"],
    "tps": ["tps", "temporary protected status"],
    "parole": ["humanitarian parole", "parole"],
    "deportation": ["deportation", "removal"],
    "policy": ["policy manual", "rule", "executive order", "federal register"],
}

IMPORTANT_RULES = [
    "final rule", "interim final rule", "effective", "deadline", "court order",
    "supreme court", "executive order", "terminated", "extended", "redesignated",
]


def is_relevant(title: str, summary: str = "") -> bool:
    text = f"{title} {summary}".lower()
    return any(keyword in text for keyword in KEYWORDS)


def detect_category(title: str, summary: str = "") -> str:
    text = f"{title} {summary}".lower()
    for category, words in CATEGORY_RULES.items():
        if any(word in text for word in words):
            return category
    return "immigration"


def detect_importance(title: str, summary: str = "") -> str:
    text = f"{title} {summary}".lower()
    if any(word in text for word in IMPORTANT_RULES):
        return "important"
    if any(word in text for word in ["asylum", "deportation", "removal", "ead", "tps"]):
        return "medium"
    return "info"
