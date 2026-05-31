from abc import ABC, abstractmethod
import re

from app.core.config import get_settings
from app.services.embedding import tokenize_for_mock_embedding
from app.services.rag_constants import REFUSAL_ANSWER
from app.services.text_focus import extract_focus_terms, leading_heading, matches_focus, strip_outer_heading


class ChatProvider(ABC):
    model_name: str

    @abstractmethod
    def answer(self, system_prompt: str, user_prompt: str) -> str:
        raise NotImplementedError


class MockChatProvider(ChatProvider):
    model_name = "mock-chat"

    def answer(self, system_prompt: str, user_prompt: str) -> str:
        question = _extract_between(user_prompt, "QUESTION:", "REWRITTEN_QUERY:").strip()
        rewritten_query = _extract_between(user_prompt, "REWRITTEN_QUERY:", "SOURCES:").strip()
        source_area = _extract_between(user_prompt, "SOURCES:", "INSTRUCTIONS:").strip()
        source_blocks = _parse_source_blocks(source_area)
        if not source_blocks:
            return REFUSAL_ANSWER

        query = rewritten_query or question
        selected_sentences = _select_relevant_sentences(query, source_blocks, question)
        if not selected_sentences:
            return REFUSAL_ANSWER

        return _format_mock_answer(question, selected_sentences)


class OpenAIChatProvider(ChatProvider):
    def __init__(self, api_key: str, base_url: str, model: str):
        from openai import OpenAI

        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model_name = model

    def answer(self, system_prompt: str, user_prompt: str) -> str:
        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.1,
        )
        return response.choices[0].message.content or REFUSAL_ANSWER


def get_chat_provider() -> ChatProvider:
    settings = get_settings()
    if settings.llm_mode.lower() == "openai" and settings.openai_api_key:
        return OpenAIChatProvider(settings.openai_api_key, settings.openai_base_url, settings.chat_model)
    return MockChatProvider()


def _extract_between(text: str, start_marker: str, end_marker: str) -> str:
    start = text.find(start_marker)
    if start < 0:
        return ""
    start += len(start_marker)
    end = text.find(end_marker, start)
    if end < 0:
        end = len(text)
    return text[start:end]


def _parse_source_blocks(source_area: str) -> list[str]:
    blocks = re.split(r"\n?\[SOURCE\s+\d+\]\n?", source_area)
    contents: list[str] = []
    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        content_lines = [
            line
            for line in lines
            if not line.startswith(("document=", "chunk_index=", "page=", "score="))
        ]
        content = _clean_text("\n".join(content_lines))
        if content:
            contents.append(content)
    return contents


def _clean_text(text: str) -> str:
    text = re.sub(r"^#{1,6}\s*", "", text, flags=re.MULTILINE)
    text = text.replace("□", " ")
    text = text.replace("■", " ")
    text = text.replace("●", " ")
    text = re.sub(r"[\u0000-\u001f\u007f]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip(" -:：")


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[。！？!?；;])\s*|\n+", text)
    return [_clean_text(part) for part in parts if _clean_text(part)]


def _select_relevant_sentences(query: str, source_blocks: list[str], question: str = "") -> list[str]:
    query_terms = set(tokenize_for_mock_embedding(query))
    focus_terms = [] if _is_company_question(question) else extract_focus_terms(question or query)
    selected: list[tuple[float, str]] = []
    for block in source_blocks:
        in_focus_scope = not focus_terms
        for sentence in _split_sentences(block):
            if focus_terms:
                if matches_focus(sentence, focus_terms):
                    in_focus_scope = True
                elif leading_heading(sentence):
                    in_focus_scope = False
                if not in_focus_scope:
                    continue
            sentence_terms = set(tokenize_for_mock_embedding(sentence))
            overlap = len(query_terms & sentence_terms)
            score = overlap / max(len(query_terms), 1)
            if focus_terms and any(term in sentence for term in focus_terms):
                score += 0.25
            if score > 0:
                selected.append((score, sentence))
    selected.sort(key=lambda item: item[0], reverse=True)

    unique_sentences: list[str] = []
    seen = set()
    for _, sentence in selected:
        if sentence in seen:
            continue
        seen.add(sentence)
        unique_sentences.append(sentence)
        if len(unique_sentences) >= 8:
            break
    return unique_sentences


def _format_mock_answer(question: str, sentences: list[str]) -> str:
    if _is_material_question(question):
        materials = _extract_materials(sentences)
        if materials:
            lines = [f"{index + 1}. {item}" for index, item in enumerate(materials)]
            return "报销需要准备以下材料：\n" + "\n".join(lines)

    if _is_process_question(question):
        answer = _format_process_answer(question, sentences)
        if answer:
            return answer

    if _is_company_question(question):
        answer = _format_company_answer(sentences)
        if answer:
            return answer

    if _is_policy_question(question):
        answer = _format_policy_answer(question, sentences)
        if answer:
            return answer

    if len(sentences) == 1:
        return strip_outer_heading(sentences[0])
    return "\n".join(f"{index + 1}. {strip_outer_heading(sentence)}" for index, sentence in enumerate(sentences[:3]))


def _is_material_question(question: str) -> bool:
    return any(word in question for word in ["材料", "资料", "需要哪些", "提交什么", "准备什么"])


def _is_company_question(question: str) -> bool:
    return any(word in question for word in ["什么公司", "哪个公司", "公司是", "公司介绍", "这是什么"])


def _is_process_question(question: str) -> bool:
    return any(word in question for word in ["流程", "步骤", "怎么走", "如何办理", "怎么申请", "办理方式"])


def _is_policy_question(question: str) -> bool:
    return any(word in question for word in ["制度", "政策", "规则", "规范", "办法"])


def _format_policy_answer(question: str, sentences: list[str]) -> str:
    focus_terms = extract_focus_terms(question)
    focused = [_strip_item_number(strip_outer_heading(sentence)) for sentence in sentences if matches_focus(sentence, focus_terms)]
    focused = _dedupe_sentences(focused)
    if not focused:
        return ""

    title = f"{focus_terms[0]}制度" if focus_terms else "相关制度"
    lines = [f"{index + 1}. {sentence}" for index, sentence in enumerate(focused[:4])]
    return f"{title}包括：\n" + "\n".join(lines)


def _format_process_answer(question: str, sentences: list[str]) -> str:
    target_terms = _process_target_terms(question)
    candidates = []
    for sentence in sentences:
        if not _looks_like_process_sentence(sentence):
            continue
        if target_terms and not any(term in sentence for term in target_terms):
            continue
        candidates.append(sentence)

    if not candidates:
        return ""

    for candidate in candidates:
        chain = _extract_process_chain(candidate)
        if chain:
            title = _process_answer_title(question)
            lines = [f"{index + 1}. {step}" for index, step in enumerate(chain)]
            return f"{title}如下：\n" + "\n".join(lines)

    return candidates[0]


def _process_target_terms(question: str) -> list[str]:
    return extract_focus_terms(question)


def _process_answer_title(question: str) -> str:
    terms = _process_target_terms(question)
    if terms:
        return f"{terms[0]}流程"
    return "流程"


def _looks_like_process_sentence(sentence: str) -> bool:
    return "→" in sentence or "->" in sentence or any(word in sentence for word in ["流程步骤", "流程", "步骤"])


def _extract_process_chain(sentence: str) -> list[str]:
    normalized = strip_outer_heading(sentence).replace("->", "→").replace("=>", "→")
    if "→" not in normalized:
        return []

    start = normalized.find("→")
    prefix = normalized[:start]
    first_step = re.sub(r"^.*?(?:流程步骤|流程|步骤)\s*", "", prefix)
    first_step = _strip_process_step(first_step)
    tail_steps = [_strip_process_step(step) for step in normalized[start + 1 :].split("→")]
    steps = [first_step, *tail_steps]
    return [step for step in steps if step]


def _strip_process_step(step: str) -> str:
    step = _clean_text(step)
    step = re.sub(r"^[一二三四五六七八九十]+、", "", step)
    step = re.sub(r"^\d+(?:\.\d+)?[、.．]?\s*", "", step)
    step = re.sub(r"^(员工入职转正|转正|流程步骤|流程|步骤)\s*", "", step)
    return step.strip(" 。；;，,")


def _strip_item_number(sentence: str) -> str:
    return re.sub(r"^\d+(?:\.\d+)?[、.．]\s*", "", sentence).strip()


def _dedupe_sentences(sentences: list[str]) -> list[str]:
    result = []
    seen = set()
    for sentence in sentences:
        cleaned = _clean_text(sentence)
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        result.append(cleaned)
    return result


def _format_company_answer(sentences: list[str]) -> str:
    text = " ".join(sentences)
    company = _extract_company_name(text)
    focus = _extract_phrase(text, [r"专注于(.+?)(?:。|；|;|$)", r"聚焦(.+?)(?:。|；|;|$)"])
    services = _extract_phrase(text, [r"主要服务(.+?)(?:。|；|;|$)", r"主营业务范围包括(.+?)(?:。|；|;|$)", r"主打(.+?)(?:。|；|;|$)"])

    if not company and not focus and not services:
        return ""

    parts = []
    if company:
        parts.append(f"这是 {company}。")
    if focus:
        parts.append(f"公司主要专注于{focus}。")
    if services:
        parts.append(f"主要业务包括{services}。")
    return "\n".join(parts)


def _extract_company_name(text: str) -> str:
    matches = re.findall(
        r"([\u4e00-\u9fffA-Za-z0-9（）()·]{2,40}(?:股份有限公司|信息技术有限公司|科技有限公司|有限公司|集团|公司))",
        text,
    )
    if matches:
        return max(matches, key=len)
    return ""


def _extract_phrase(text: str, patterns: list[str]) -> str:
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return _clean_text(match.group(1)).rstrip("。")
    return ""


def _extract_materials(sentences: list[str]) -> list[str]:
    text = "。".join(sentences)
    patterns = [
        r"申请材料包括(.+?)(?:。|；|;|$)",
        r"材料包括(.+?)(?:。|；|;|$)",
        r"包括(.+?)(?:。|；|;|$)",
        r"需要提交(.+?)(?:。|；|;|$)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if not match:
            continue
        items = _split_material_items(match.group(1))
        if items:
            return items

    for sentence in sentences:
        if not _looks_like_material_sentence(sentence):
            continue
        match = re.search(r"需要(.+?)(?:。|；|;|$)", sentence)
        if match:
            items = _split_material_items(match.group(1))
            if items:
                return items
    return []


def _looks_like_material_sentence(sentence: str) -> bool:
    return any(word in sentence for word in ["发票", "材料", "资料", "说明", "审批", "记录", "项目归属"])


def _split_material_items(raw: str) -> list[str]:
    raw = re.sub(r"^(准备|提交|提供)", "", raw).strip()
    raw = raw.replace("以及", "、").replace("和", "、").replace("及", "、")
    items = [item.strip(" ，,、。；;") for item in re.split(r"[、,，]", raw) if item.strip(" ，,、。；;")]
    return [_normalize_material_item(item) for item in items if _normalize_material_item(item)]


def _normalize_material_item(item: str) -> str:
    item = re.sub(r"^(相关的|必要的)", "", item).strip()
    item = item.replace("负责人审批", "负责人审批记录") if item.endswith("负责人审批") else item
    return item
