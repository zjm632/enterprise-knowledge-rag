import re

from app.services.embedding import tokenize_for_mock_embedding
from app.services.prompts import load_prompt


QUESTION_STOPWORDS = {
    "please",
    "tell",
    "about",
    "what",
    "which",
    "how",
    "why",
    "when",
    "where",
    "is",
    "are",
    "the",
    "a",
    "an",
}

CHINESE_STOP_PHRASES = [
    "请问",
    "帮我",
    "一下",
    "是什么",
    "有哪些",
    "怎么",
    "如何",
    "可以",
    "请",
    "吗",
    "呢",
    "？",
    "?",
]


def rewrite_query(question: str) -> str:
    """Create a compact retrieval query without changing user intent."""
    normalized = re.sub(r"\s+", " ", question).strip()
    rewritten = normalized
    for phrase in CHINESE_STOP_PHRASES:
        rewritten = rewritten.replace(phrase, " ")
    terms = []
    for token in re.findall(r"[A-Za-z0-9_]{2,}", rewritten.lower()):
        if token not in QUESTION_STOPWORDS:
            terms.append(token)
    cjk_terms = [term for term in tokenize_for_mock_embedding(rewritten) if re.search(r"[\u4e00-\u9fff]", term)]

    compact_terms = _dedupe_preserve_order(terms + cjk_terms)
    if not compact_terms:
        return normalized
    compact = " ".join(compact_terms[:32])
    return compact if len(compact) >= 2 else normalized


def query_rewrite_prompt() -> str:
    return load_prompt("query_rewrite_prompt.md")


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    seen = set()
    result = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result
