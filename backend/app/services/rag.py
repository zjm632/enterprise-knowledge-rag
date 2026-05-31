import time
import re
from collections.abc import Iterator

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.repositories import ChunkRepository, QALogRepository
from app.services.chunking import estimate_tokens
from app.services.embedding import get_embedding_provider
from app.services.llm import get_chat_provider
from app.services.prompts import current_prompt_version, load_prompt
from app.services.query_rewrite import rewrite_query
from app.services.rag_constants import REFUSAL_ANSWER
from app.services.retrieval import HybridRetriever, RetrievedChunk


def has_reliable_evidence(
    results: list[RetrievedChunk],
    min_score: float,
    min_rerank_score: float = 0.08,
    min_evidence_count: int = 1,
) -> bool:
    reliable = [
        item
        for item in results
        if item.final_score >= min_score
        and (
            item.rerank_score >= min_rerank_score
            or item.keyword_score >= 0.35
            or ("vector" in item.sources and "keyword" in item.sources)
        )
    ]
    return len(reliable) >= min_evidence_count


def reliable_results(
    results: list[RetrievedChunk],
    min_score: float,
    min_rerank_score: float,
) -> list[RetrievedChunk]:
    return [
        item
        for item in results
        if item.final_score >= min_score
        and (
            item.rerank_score >= min_rerank_score
            or item.keyword_score >= 0.35
            or ("vector" in item.sources and "keyword" in item.sources)
        )
    ]


def build_answer_prompt(question: str, rewritten_query: str, results: list[RetrievedChunk]) -> str:
    template = load_prompt("rag_answer_prompt.md")
    context = "\n\n".join(
        "\n".join(
            [
                f"[SOURCE {index + 1}]",
                f"document={item.document_name}",
                f"chunk_index={item.chunk_index}",
                f"page={item.page_number or 'n/a'}",
                f"score={item.final_score:.4f}",
                item.content,
            ]
        )
        for index, item in enumerate(results)
    )
    return template.format(question=question, rewritten_query=rewritten_query, context=context)


def sanitize_answer(answer: str) -> str:
    cleaned = answer.strip()
    if not cleaned:
        return REFUSAL_ANSWER

    blocked_markers = [
        "[SOURCE",
        "document=",
        "chunk_index=",
        "page=",
        "score=",
        "回答规则",
        "系统提示",
        "用户原始问题",
        "检索改写查询",
        "可用引用片段",
        "请基于上面的引用片段回答用户问题",
    ]
    for marker in blocked_markers:
        if marker in cleaned:
            cleaned = cleaned.split(marker, 1)[0].strip()

    cleaned = cleaned.replace("□", " ")
    cleaned = cleaned.replace("■", " ")
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = cleaned.strip()
    if not cleaned:
        return REFUSAL_ANSWER
    return cleaned


class RAGService:
    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()
        self.retriever = HybridRetriever(ChunkRepository(db), get_embedding_provider())
        self.logs = QALogRepository(db)
        self.chat = get_chat_provider()

    def ask(self, knowledge_base_id: str, question: str, top_k: int = 8) -> dict:
        return self._answer(knowledge_base_id, question, top_k)

    def ask_stream_events(self, knowledge_base_id: str, question: str, top_k: int = 8) -> Iterator[dict]:
        yield {"event": "status", "data": {"message": "正在改写查询并检索知识库"}}
        response = self._answer(knowledge_base_id, question, top_k)
        yield {
            "event": "metadata",
            "data": {
                "citations": response["citations"],
                "retrieval_results": response["retrieval_results"],
                "latency_ms": response["latency_ms"],
                "model_name": response["model_name"],
                "token_estimate": response["token_estimate"],
                "hit_knowledge_base": response["hit_knowledge_base"],
                "prompt_version": response["prompt_version"],
                "rewritten_query": response["rewritten_query"],
            },
        }
        for delta in _chunk_answer_for_stream(response["answer"]):
            yield {"event": "token", "data": {"delta": delta}}
        yield {"event": "done", "data": response}

    def _answer(self, knowledge_base_id: str, question: str, top_k: int = 8) -> dict:
        started = time.perf_counter()
        rewritten_query = rewrite_query(question)
        results = self.retriever.retrieve(knowledge_base_id, question, top_k, rewritten_query)
        evidence = reliable_results(results, self.settings.answer_min_score, self.settings.answer_min_rerank_score)
        hit = has_reliable_evidence(
            results,
            self.settings.answer_min_score,
            self.settings.answer_min_rerank_score,
            self.settings.answer_min_evidence_count,
        )

        if hit and evidence:
            system_prompt = load_prompt("system_prompt.md")
            answer_prompt = build_answer_prompt(question, rewritten_query, evidence[:5])
            answer = sanitize_answer(self.chat.answer(system_prompt, answer_prompt))
            if not answer:
                answer = REFUSAL_ANSWER
        else:
            answer = REFUSAL_ANSWER
            evidence = []

        if answer == REFUSAL_ANSWER:
            hit = False
            evidence = []

        citations = [
            {
                "chunk_id": item.chunk_id,
                "document_name": item.document_name,
                "chunk_index": item.chunk_index,
                "page_number": item.page_number,
                "snippet": item.content[:360],
                "score": round(item.final_score, 4),
            }
            for item in evidence[:5]
        ]
        retrieval_results = [
            {
                "chunk_id": item.chunk_id,
                "document_name": item.document_name,
                "chunk_index": item.chunk_index,
                "vector_score": round(item.vector_score, 4),
                "keyword_score": round(item.keyword_score, 4),
                "vector_rank_score": round(item.vector_rank_score, 4),
                "keyword_rank_score": round(item.keyword_rank_score, 4),
                "rerank_score": round(item.rerank_score, 4),
                "final_score": round(item.final_score, 4),
                "sources": item.sources,
                "matched_terms": item.matched_terms or [],
                "content": item.content[:500],
            }
            for item in results
        ]
        latency_ms = int((time.perf_counter() - started) * 1000)
        token_estimate = estimate_tokens(question + answer + "".join(c["snippet"] for c in citations))
        prompt_version = current_prompt_version()
        model_name = self.chat.model_name
        retrieval_payload = {
            "query": question,
            "rewritten_query": rewritten_query,
            "items": retrieval_results,
        }
        self.logs.create(
            knowledge_base_id,
            question,
            answer,
            retrieval_payload,
            citations,
            latency_ms,
            model_name,
            token_estimate,
            hit,
            prompt_version,
        )
        return {
            "answer": answer,
            "citations": citations,
            "retrieval_results": retrieval_results,
            "latency_ms": latency_ms,
            "model_name": model_name,
            "token_estimate": token_estimate,
            "hit_knowledge_base": hit,
            "prompt_version": prompt_version,
            "rewritten_query": rewritten_query,
        }


def _chunk_answer_for_stream(answer: str, chunk_size: int = 12) -> Iterator[str]:
    if answer == REFUSAL_ANSWER:
        yield answer
        return
    for index in range(0, len(answer), chunk_size):
        yield answer[index : index + chunk_size]
