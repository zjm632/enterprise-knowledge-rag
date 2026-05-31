from dataclasses import dataclass

from app.repositories import ChunkRepository
from app.services.embedding import EmbeddingProvider
from app.services.embedding import tokenize_for_mock_embedding
from app.services.text_focus import extract_focus_terms, has_focused_sentence


@dataclass
class RetrievedChunk:
    chunk_id: str
    document_name: str
    content: str
    chunk_index: int
    page_number: int | None
    vector_score: float = 0.0
    keyword_score: float = 0.0
    vector_rank_score: float = 0.0
    keyword_rank_score: float = 0.0
    rerank_score: float = 0.0
    final_score: float = 0.0
    sources: str = ""
    matched_terms: list[str] | None = None


def lexical_overlap_score(query: str, content: str) -> float:
    query_terms = {t for t in tokenize_for_mock_embedding(query) if len(t.strip()) > 0}
    if not query_terms:
        return 0.0
    content_terms = set(tokenize_for_mock_embedding(content))
    content_lower = content.lower()
    hits = sum(1 for term in query_terms if term in content_lower)
    hits += len(query_terms & content_terms)
    score = min(hits / max(len(query_terms), 1), 1.0)

    focus_terms = extract_focus_terms(query)
    if focus_terms:
        score = score + 0.15 if has_focused_sentence(content, focus_terms) else score * 0.35
    return min(score, 1.0)


def matched_terms(query: str, content: str) -> list[str]:
    content_lower = content.lower()
    terms = []
    for term in tokenize_for_mock_embedding(query):
        if term and term not in terms and term.lower() in content_lower:
            terms.append(term)
    return terms[:16]


def normalize_rank_scores(results: list[dict]) -> list[dict]:
    if not results:
        return []
    raw_scores = [max(float(item.get("score", 0.0)), 0.0) for item in results]
    max_score = max(raw_scores) or 1.0
    normalized = []
    for rank, item in enumerate(results, start=1):
        score = max(float(item.get("score", 0.0)), 0.0)
        rank_bonus = 1.0 / (rank + 1)
        normalized.append({**item, "normalized_score": min((score / max_score) * 0.85 + rank_bonus * 0.15, 1.0)})
    return normalized


def merge_and_rerank(query: str, vector_results: list[dict], keyword_results: list[dict], limit: int) -> list[RetrievedChunk]:
    merged: dict[str, RetrievedChunk] = {}

    for item in normalize_rank_scores(vector_results):
        chunk = item["chunk"]
        merged[chunk.id] = RetrievedChunk(
            chunk_id=chunk.id,
            document_name=chunk.document_name,
            content=chunk.content,
            chunk_index=chunk.chunk_index,
            page_number=chunk.page_number,
            vector_score=max(float(item["score"]), 0.0),
            vector_rank_score=max(float(item["normalized_score"]), 0.0),
            sources="vector",
        )

    for item in normalize_rank_scores(keyword_results):
        chunk = item["chunk"]
        existing = merged.get(chunk.id)
        if not existing:
            existing = RetrievedChunk(
                chunk_id=chunk.id,
                document_name=chunk.document_name,
                content=chunk.content,
                chunk_index=chunk.chunk_index,
                page_number=chunk.page_number,
                sources="keyword",
            )
            merged[chunk.id] = existing
        else:
            existing.sources += "+keyword"
        existing.keyword_score = max(existing.keyword_score, float(item["score"]))
        existing.keyword_rank_score = max(existing.keyword_rank_score, float(item["normalized_score"]))

    for item in merged.values():
        item.rerank_score = lexical_overlap_score(query, item.content)
        item.matched_terms = matched_terms(query, item.content)
        source_bonus = 0.08 if "vector" in item.sources and "keyword" in item.sources else 0.0
        item.final_score = min(
            0.48 * item.vector_rank_score + 0.28 * item.keyword_rank_score + 0.24 * item.rerank_score + source_bonus,
            1.0,
        )

    return sorted(merged.values(), key=lambda r: r.final_score, reverse=True)[:limit]


class HybridRetriever:
    def __init__(self, chunks: ChunkRepository, embeddings: EmbeddingProvider):
        self.chunks = chunks
        self.embeddings = embeddings

    def retrieve(self, knowledge_base_id: str, query: str, top_k: int, rewritten_query: str | None = None) -> list[RetrievedChunk]:
        retrieval_query = rewritten_query or query
        query_embedding = self.embeddings.embed_query(retrieval_query)
        vector_results = self.chunks.vector_search(knowledge_base_id, query_embedding, top_k * 2)
        keyword_results = self.chunks.keyword_search(knowledge_base_id, retrieval_query, top_k * 2)
        return merge_and_rerank(retrieval_query, vector_results, keyword_results, top_k)
