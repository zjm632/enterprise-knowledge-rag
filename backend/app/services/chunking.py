from dataclasses import dataclass
import re


DEFAULT_MIN_CHUNK_SIZE = 120


@dataclass
class ParsedSection:
    text: str
    page_number: int | None = None
    paragraph_index: int | None = None


@dataclass
class ChunkSpec:
    content: str
    chunk_index: int
    page_number: int | None
    paragraph_index: int | None
    char_length: int
    token_estimate: int


def estimate_tokens(text: str) -> int:
    latin_words = re.findall(r"[A-Za-z0-9_]+", text)
    cjk_chars = re.findall(r"[\u4e00-\u9fff]", text)
    other_chars = max(len(text) - sum(len(w) for w in latin_words) - len(cjk_chars), 0)
    return max(1, len(latin_words) + len(cjk_chars) + other_chars // 4)


def normalize_text(text: str) -> str:
    cleaned = text.replace("\r\n", "\n").replace("\r", "\n")
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def split_sections_into_chunks(
    sections: list[ParsedSection],
    chunk_size: int = 900,
    overlap: int = 140,
    min_chunk_size: int = DEFAULT_MIN_CHUNK_SIZE,
) -> list[ChunkSpec]:
    """Split parsed sections into retrieval-sized chunks.

    The splitter prefers paragraph and sentence boundaries, avoids chunks that
    are too long, and merges short tail fragments back into the previous chunk
    when metadata allows it.
    """
    chunk_size = max(240, chunk_size)
    min_chunk_size = max(40, min(min_chunk_size, chunk_size // 2))
    overlap = max(0, min(overlap, chunk_size // 3))

    chunks: list[ChunkSpec] = []
    for section in sections:
        text = normalize_text(section.text)
        if not text:
            continue
        for piece in _split_text(text, chunk_size, overlap):
            _append_or_merge(
                chunks,
                piece,
                min_chunk_size=min_chunk_size,
                chunk_size=chunk_size,
                page_number=section.page_number,
                paragraph_index=section.paragraph_index,
            )

    for index, chunk in enumerate(chunks):
        chunk.chunk_index = index
    return chunks


def _split_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    pieces: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        if end < len(text):
            boundary = _best_boundary(text, start, end, chunk_size)
            if boundary:
                end = boundary
        content = text[start:end].strip()
        if content:
            pieces.append(content)
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return pieces


def _best_boundary(text: str, start: int, end: int, chunk_size: int) -> int | None:
    min_end = start + int(chunk_size * 0.55)
    candidates = [
        text.rfind("\n\n", start, end),
        text.rfind("\n", start, end),
        text.rfind("。", start, end),
        text.rfind("；", start, end),
        text.rfind("; ", start, end),
        text.rfind(". ", start, end),
        text.rfind("? ", start, end),
        text.rfind("! ", start, end),
    ]
    boundary = max(candidates)
    if boundary >= min_end:
        return boundary + 1
    return None


def _append_or_merge(
    chunks: list[ChunkSpec],
    content: str,
    min_chunk_size: int,
    chunk_size: int,
    page_number: int | None,
    paragraph_index: int | None,
) -> None:
    if (
        chunks
        and len(content) < min_chunk_size
        and chunks[-1].page_number == page_number
        and chunks[-1].paragraph_index == paragraph_index
        and chunks[-1].char_length + len(content) + 1 <= chunk_size
    ):
        merged = f"{chunks[-1].content}\n{content}".strip()
        chunks[-1].content = merged
        chunks[-1].char_length = len(merged)
        chunks[-1].token_estimate = estimate_tokens(merged)
        return

    chunks.append(
        ChunkSpec(
            content=content,
            chunk_index=len(chunks),
            page_number=page_number,
            paragraph_index=paragraph_index,
            char_length=len(content),
            token_estimate=estimate_tokens(content),
        )
    )
