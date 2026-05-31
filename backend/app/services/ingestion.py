from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.entities import Chunk, Document
from app.repositories import ChunkRepository, DocumentRepository
from app.services.chunking import split_sections_into_chunks
from app.services.embedding import get_embedding_provider
from app.services.parsing import parse_document


class IngestionService:
    def __init__(self, db: Session):
        self.db = db
        self.documents = DocumentRepository(db)
        self.chunks = ChunkRepository(db)
        self.settings = get_settings()

    def ingest_document(self, doc: Document) -> Document:
        self.documents.update_status(doc, "processing")
        try:
            sections = parse_document(doc.file_path)
            chunk_specs = split_sections_into_chunks(
                sections,
                self.settings.chunk_size,
                self.settings.chunk_overlap,
                self.settings.min_chunk_size,
            )
            embeddings = get_embedding_provider().embed_texts([chunk.content for chunk in chunk_specs]) if chunk_specs else []
            self.chunks.clear_document(doc.id)
            chunk_rows = [
                Chunk(
                    knowledge_base_id=doc.knowledge_base_id,
                    document_id=doc.id,
                    document_name=doc.filename,
                    content=chunk.content,
                    chunk_index=chunk.chunk_index,
                    page_number=chunk.page_number,
                    paragraph_index=chunk.paragraph_index,
                    char_length=chunk.char_length,
                    token_estimate=chunk.token_estimate,
                    embedding=embeddings[index],
                )
                for index, chunk in enumerate(chunk_specs)
            ]
            if chunk_rows:
                self.chunks.bulk_create(chunk_rows)
            return self.documents.finalize(doc, len(chunk_rows), sum(c.char_length for c in chunk_specs))
        except Exception as exc:
            return self.documents.update_status(doc, "failed", str(exc))

    def save_upload(self, knowledge_base_id: str, filename: str, content: bytes) -> str:
        upload_root = Path(self.settings.upload_dir) / knowledge_base_id
        upload_root.mkdir(parents=True, exist_ok=True)
        safe_name = Path(filename).name
        target = upload_root / safe_name
        if target.exists():
            stem, suffix = target.stem, target.suffix
            target = upload_root / f"{stem}-{len(list(upload_root.glob(stem + '*')))}{suffix}"
        target.write_bytes(content)
        return str(target)
