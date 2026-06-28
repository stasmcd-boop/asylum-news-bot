import re

CORE_KEYWORDS = [
    "asylum", "refugee", "credible fear", "reasonable fear", "withholding of removal",
    "immigration court", "eoir", "uscis", "ice", "cbp", "dhs",
    "tps", "temporary protected status", "humanitarian parole", "parole",
    "ead", "employment authorization", "work permit", "i-765",
    "removal proceedings", "removal", "deportation", "notice to appear", "nta",
    "policy manual", "executive order", "final rule", "interim final rule",
    "border", "migrant", "noncitizen", "alien registration",
]

ALWAYS_INCLUDE = [
    "asylum", "credible fear", "reasonable fear", "withholding of removal",
    "immigration court", "eoir", "removal proceedings", "deportation",
    "tps", "temporary protected status", "employment authorization", "ead",
    "humanitarian parole", "alien registration", "notice to appear",
]

NOISE_KEYWORDS = [
    "h-1b", "h1b", "h-2a", "h-2b", "l-1", "o-1", "f-1", "j-1",
    "student", "exchange visitor", "nonimmigrant worker", "tourism", "tourist visa",
    "eb-1", "eb-2", "eb-3", "investor", "entrepreneur", "naturalization ceremony",
]

CATEGORY_RULES = {
    "asylum": ["asylum", "credible fear", "reasonable fear", "refugee", "withholding of removal"],
    "court": ["immigration court", "eoir", "notice to appear", "nta", "removal proceedings"],
    "ead": ["ead", "employment authorization", "work permit", "i-765"],
    "tps": ["tps", "temporary protected status"],
    "parole": ["humanitarian parole", "parole"],
    "deportation": ["deportation", "removal"],
    "border": ["border", "cbp", "migrant"],
    "policy": ["policy manual", "rule", "executive order", "federal register", "alien registration"],
}

IMPORTANT_RULES = [
    "final rule", "interim final rule", "effective", "deadline", "court order",
    "supreme court", "executive order", "terminated", "extended", "redesignated",
    "alien registration", "policy manual", "removal proceedings", "deportation",
]


def contains_term(text: str, term: str) -> bool:
    pattern = rf"(?<![a-z0-9]){re.escape(term.lower())}(?![a-z0-9])"
    return re.search(pattern, text) is not None


def contains_any_term(text: str, terms: list[str]) -> bool:
    return any(contains_term(text, term) for term in terms)


def is_relevant(title: str, summary: str = "") -> bool:
    text = f"{title} {summary}".lower()
    if any(keyword in text for keyword in ALWAYS_INCLUDE):
        return True
    if any(noise in text for noise in NOISE_KEYWORDS) and not any(keyword in text for keyword in ALWAYS_INCLUDE):
        return False
    return any(keyword in text for keyword in CORE_KEYWORDS)


def detect_category(title: str, summary: str = "") -> str:
    text = f"{title} {summary}".lower()
    for category, words in CATEGORY_RULES.items():
        if contains_any_term(text, words):
            return category
    return "immigration"


def detect_importance(title: str, summary: str = "") -> str:
    text = f"{title} {summary}".lower()
    if contains_any_term(text, IMPORTANT_RULES):
        return "important"
    if any(word in text for word in ["asylum", "deportation", "removal", "ead", "tps", "parole"]):
        return "medium"
    return "info"
