from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Enterprise Knowledge RAG"
    api_prefix: str = "/api"
    database_url: str = "postgresql+psycopg://rag:rag@localhost:5432/rag"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    chat_model: str = "gpt-4o-mini"
    embedding_model: str = "text-embedding-3-small"
    embedding_dim: int = 1536
    llm_mode: str = "mock"
    embedding_mode: str = "mock"

    chunk_size: int = 900
    chunk_overlap: int = 140
    min_chunk_size: int = 120
    retrieval_top_k: int = 8
    answer_min_score: float = 0.22
    answer_min_rerank_score: float = 0.08
    answer_min_evidence_count: int = 1
    upload_dir: str = "data/uploads"
    eval_cases_path: str = "eval_cases.json"
    prompt_version: str = "v1"
    auth_secret_key: str = "dev-rag-secret"
    auth_token_ttl_minutes: int = 1440

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
