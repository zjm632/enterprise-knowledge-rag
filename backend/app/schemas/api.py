from datetime import datetime
from pydantic import BaseModel, Field


class KnowledgeBaseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str = ""
    category: str = Field(default="policy", pattern="^(policy|business|general)$")


class LoginRequest(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class RoleSwitchRequest(BaseModel):
    role: str = Field(min_length=1)


class UserOut(BaseModel):
    username: str
    name: str
    role: str
    role_label: str
    access_scope: str
    avatar: str = ""


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class KnowledgeBaseOut(BaseModel):
    id: str
    name: str
    description: str
    category: str = "policy"
    category_label: str = "制度类"
    created_at: datetime
    document_count: int = 0


class DocumentOut(BaseModel):
    id: str
    knowledge_base_id: str
    filename: str
    file_type: str
    status: str
    error_message: str
    chunk_count: int
    char_count: int
    created_at: datetime


class ChunkOut(BaseModel):
    id: str
    document_name: str
    content: str
    chunk_index: int
    page_number: int | None
    paragraph_index: int | None
    char_length: int
    token_estimate: int


class AskRequest(BaseModel):
    question: str = Field(min_length=1)
    top_k: int = Field(default=8, ge=1, le=20)
    use_rerank: bool = True


class CitationOut(BaseModel):
    chunk_id: str
    document_name: str
    chunk_index: int
    page_number: int | None = None
    snippet: str
    score: float


class AskResponse(BaseModel):
    answer: str
    citations: list[CitationOut]
    retrieval_results: list[dict]
    latency_ms: int
    model_name: str
    token_estimate: int
    hit_knowledge_base: bool
    prompt_version: str
    rewritten_query: str = ""


class QALogOut(BaseModel):
    id: str
    knowledge_base_id: str
    question: str
    answer: str
    citations: list
    retrieval_results: dict
    latency_ms: int
    model_name: str
    token_estimate: int
    hit_knowledge_base: bool
    prompt_version: str
    created_at: datetime


class RebuildResponse(BaseModel):
    document_id: str
    status: str
    chunk_count: int


class ModelConfigOut(BaseModel):
    llm_mode: str
    chat_model: str
    embedding_model: str
    retrieval_top_k: int
    answer_min_score: float
    answer_min_rerank_score: float
    prompt_version: str


class ModelConfigUpdate(BaseModel):
    llm_mode: str | None = None
    chat_model: str | None = None
    embedding_model: str | None = None
    retrieval_top_k: int | None = Field(default=None, ge=1, le=20)
    answer_min_score: float | None = Field(default=None, ge=0, le=1)
    answer_min_rerank_score: float | None = Field(default=None, ge=0, le=1)
    prompt_version: str | None = None


class EvalCaseOut(BaseModel):
    knowledge_base_id: str
    question: str
    expected_keyword: str = ""


class EvalSummaryOut(BaseModel):
    case_count: int
    cases: list[EvalCaseOut]
    log_count: int
    retrieval_hit_rate: float
    refusal_rate: float
    avg_latency_ms: float
    citation_rate: float
    recent_results: list[dict]
