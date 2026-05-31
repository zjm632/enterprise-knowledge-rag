from __future__ import annotations

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.models.entities import Chunk, Document, KnowledgeBase, QALog
from app.services.embedding import tokenize_for_mock_embedding


class KnowledgeBaseRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, name: str, description: str, category: str = "policy") -> KnowledgeBase:
        kb = KnowledgeBase(name=name, description=description, category=category)
        self.db.add(kb)
        self.db.commit()
        self.db.refresh(kb)
        return kb

    def list(self) -> list[KnowledgeBase]:
        return list(self.db.scalars(select(KnowledgeBase).order_by(KnowledgeBase.created_at.desc())))

    def list_by_categories(self, categories: set[str]) -> list[KnowledgeBase]:
        stmt = select(KnowledgeBase).where(KnowledgeBase.category.in_(categories)).order_by(KnowledgeBase.created_at.desc())
        return list(self.db.scalars(stmt))

    def get(self, kb_id: str) -> KnowledgeBase | None:
        return self.db.get(KnowledgeBase, kb_id)

    def delete(self, kb_id: str) -> bool:
        kb = self.get(kb_id)
        if not kb:
            return False
        self.db.delete(kb)
        self.db.commit()
        return True


class DocumentRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, knowledge_base_id: str, filename: str, file_type: str, file_path: str) -> Document:
        doc = Document(
            knowledge_base_id=knowledge_base_id,
            filename=filename,
            file_type=file_type,
            file_path=file_path,
            status="pending",
        )
        self.db.add(doc)
        self.db.commit()
        self.db.refresh(doc)
        return doc

    def get(self, doc_id: str) -> Document | None:
        return self.db.get(Document, doc_id)

    def list_by_kb(self, knowledge_base_id: str) -> list[Document]:
        stmt = select(Document).where(Document.knowledge_base_id == knowledge_base_id).order_by(Document.created_at.desc())
        return list(self.db.scalars(stmt))

    def update_status(self, doc: Document, status: str, error: str = "") -> Document:
        doc.status = status
        doc.error_message = error
        self.db.commit()
        self.db.refresh(doc)
        return doc

    def finalize(self, doc: Document, chunk_count: int, char_count: int) -> Document:
        doc.status = "completed"
        doc.chunk_count = chunk_count
        doc.char_count = char_count
        self.db.commit()
        self.db.refresh(doc)
        return doc


class ChunkRepository:
    def __init__(self, db: Session):
        self.db = db

    def clear_document(self, document_id: str) -> None:
        self.db.query(Chunk).filter(Chunk.document_id == document_id).delete()
        self.db.commit()

    def bulk_create(self, chunks: list[Chunk]) -> None:
        self.db.add_all(chunks)
        self.db.commit()

    def list_by_document(self, document_id: str) -> list[Chunk]:
        stmt = select(Chunk).where(Chunk.document_id == document_id).order_by(Chunk.chunk_index.asc())
        return list(self.db.scalars(stmt))

    def count_by_kb(self, knowledge_base_id: str) -> int:
        stmt = select(func.count(Chunk.id)).where(Chunk.knowledge_base_id == knowledge_base_id)
        return int(self.db.scalar(stmt) or 0)

    def vector_search(self, knowledge_base_id: str, embedding: list[float], limit: int) -> list[dict]:
        distance = Chunk.embedding.cosine_distance(embedding)
        stmt = (
            select(Chunk, (1 - distance).label("score"))
            .where(Chunk.knowledge_base_id == knowledge_base_id)
            .order_by(distance.asc())
            .limit(limit)
        )
        return [{"chunk": chunk, "score": float(score or 0), "source": "vector"} for chunk, score in self.db.execute(stmt)]

    def keyword_search(self, knowledge_base_id: str, query: str, limit: int) -> list[dict]:
        terms = [term for term in tokenize_for_mock_embedding(query) if len(term) >= 2][:8]
        sql = text(
            """
            SELECT c.*, ts_rank_cd(to_tsvector('simple', c.content), plainto_tsquery('simple', :query)) AS rank
            FROM chunks c
            WHERE c.knowledge_base_id = :kb_id
              AND to_tsvector('simple', c.content) @@ plainto_tsquery('simple', :query)
            ORDER BY rank DESC
            LIMIT :limit
            """
        )
        rows = self.db.execute(sql, {"kb_id": knowledge_base_id, "query": query, "limit": limit}).mappings().all()
        results: list[dict] = []
        for row in rows:
            chunk = self.db.get(Chunk, row["id"])
            results.append({"chunk": chunk, "score": min(float(row["rank"] or 0) * 2, 1.0), "source": "keyword"})
        seen = {item["chunk"].id for item in results if item.get("chunk")}
        for term in terms:
            if len(results) >= limit:
                break
            stmt = (
                select(Chunk)
                .where(Chunk.knowledge_base_id == knowledge_base_id)
                .where(Chunk.content.ilike(f"%{term}%"))
                .limit(limit)
            )
            for chunk in self.db.scalars(stmt):
                if chunk.id in seen:
                    continue
                seen.add(chunk.id)
                results.append({"chunk": chunk, "score": 0.45, "source": "keyword_like"})
                if len(results) >= limit:
                    break
        return results[:limit]


class QALogRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        knowledge_base_id: str,
        question: str,
        answer: str,
        retrieval_results: dict,
        citations: list,
        latency_ms: int,
        model_name: str,
        token_estimate: int,
        hit_knowledge_base: bool,
        prompt_version: str,
    ) -> QALog:
        log = QALog(
            knowledge_base_id=knowledge_base_id,
            question=question,
            answer=answer,
            retrieval_results=retrieval_results,
            citations=citations,
            latency_ms=latency_ms,
            model_name=model_name,
            token_estimate=token_estimate,
            hit_knowledge_base=hit_knowledge_base,
            prompt_version=prompt_version,
        )
        self.db.add(log)
        self.db.commit()
        self.db.refresh(log)
        return log

    def list(self, limit: int = 100) -> list[QALog]:
        stmt = select(QALog).order_by(QALog.created_at.desc()).limit(limit)
        return list(self.db.scalars(stmt))
