import re


GENERIC_TOPIC_WORDS = [
    "管理制度",
    "制度",
    "流程步骤",
    "流程",
    "步骤",
    "政策",
    "规则",
    "规范",
    "办法",
    "要求",
    "条件",
    "材料",
    "资料",
    "说明",
    "介绍",
    "怎么",
    "如何",
    "哪些",
    "什么",
    "是否",
    "可以",
    "需要",
    "请问",
    "帮我",
    "一下",
    "相关",
    "有关",
    "管理",
    "的",
    "吗",
    "呢",
]


def extract_focus_terms(question: str) -> list[str]:
    """Extract the business topic from a user question, e.g. 报销制度 -> 报销."""
    normalized = re.sub(r"\s+", "", question)
    for word in GENERIC_TOPIC_WORDS:
        normalized = normalized.replace(word, " ")

    terms: list[str] = []
    for term in re.split(r"\s+", normalized):
        if len(term) >= 2 and re.search(r"[\u4e00-\u9fffA-Za-z0-9]", term) and term not in terms:
            terms.append(term)
    return terms[:4]


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[。！？!?；;])\s*|\n+", text)
    return [part.strip() for part in parts if part.strip()]


def leading_heading(text: str) -> str:
    cleaned = text.strip()
    patterns = [
        r"^[一二三四五六七八九十]+、\s*([^。；;]+?)(?=\s+\d+(?:[.、．])|\s*$|。|；|;)",
        r"^#{1,6}\s*([^。；;]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, cleaned)
        if match:
            return match.group(1).strip()
    return ""


def leading_item_title(text: str) -> str:
    cleaned = text.strip()
    match = re.search(r"^\d+(?:\.\d+)?[、.．]\s*([^。；;，,：:]+)", cleaned)
    if match:
        return match.group(1).strip()
    match = re.search(r"^[一二三四五六七八九十]+、[^。；;]+?\s+\d+(?:\.\d+)?[、.．]\s*([^。；;，,：:]+)", cleaned)
    if match:
        return match.group(1).strip()
    return ""


def matches_focus(text: str, focus_terms: list[str]) -> bool:
    if not focus_terms:
        return True
    if not any(term in text for term in focus_terms):
        return False

    heading = leading_heading(text)
    if heading and not any(term in heading for term in focus_terms):
        item_title = leading_item_title(text)
        return bool(item_title and any(term in item_title for term in focus_terms))
    return True


def has_focused_sentence(text: str, focus_terms: list[str]) -> bool:
    if not focus_terms:
        return True
    return any(matches_focus(sentence, focus_terms) for sentence in split_sentences(text))


def strip_outer_heading(text: str) -> str:
    cleaned = text.strip()
    cleaned = re.sub(
        r"^[一二三四五六七八九十]+、\s*[^。；;]+?(?=\s+\d+(?:[.、．]))",
        "",
        cleaned,
    ).strip()
    return cleaned
