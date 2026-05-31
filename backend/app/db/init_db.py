import time
from sqlalchemy import text

from app.db.session import engine
from app.models.entities import Base


def init_db(retries: int = 20, delay: float = 1.5) -> None:
    last_error: Exception | None = None
    for _ in range(retries):
        try:
            with engine.begin() as conn:
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            Base.metadata.create_all(bind=engine)
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE knowledge_bases ADD COLUMN IF NOT EXISTS category VARCHAR(32) DEFAULT 'policy'"))
                conn.execute(text("UPDATE knowledge_bases SET category = 'policy' WHERE category IS NULL OR category = ''"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_knowledge_bases_category ON knowledge_bases(category)"))
            return
        except Exception as exc:
            last_error = exc
            time.sleep(delay)
    raise RuntimeError(f"database init failed: {last_error}") from last_error
