from pathlib import Path
import json

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.repositories import ChunkRepository, DocumentRepository, KnowledgeBaseRepository, QALogRepository
from app.schemas.api import (
    AskRequest,
    AskResponse,
    EvalSummaryOut,
    KnowledgeBaseCreate,
    LoginRequest,
    LoginResponse,
    ModelConfigOut,
    ModelConfigUpdate,
    RebuildResponse,
    RoleSwitchRequest,
    UserOut,
)
from app.services.auth import (
    KB_CATEGORY_LABELS,
    POLICY_KB_CATEGORY,
    ROLE_SCOPES,
    authenticate,
    can_access_kb_category,
    create_access_token,
    current_user_from_request,
    has_permission,
    require_permission,
)
from app.services.ingestion import IngestionService
from app.services.parsing import SUPPORTED_EXTENSIONS
from app.services.rag import RAGService

router = APIRouter()


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "app": get_settings().app_name}


@router.post("/auth/login", response_model=LoginResponse)
def login(payload: LoginRequest) -> dict:
    user = authenticate(payload.username, payload.password)
    return {"access_token": create_access_token(user), "token_type": "bearer", "user": user}


@router.get("/auth/me", response_model=UserOut)
def get_current_user(request: Request) -> dict:
    return current_user_from_request(request)


@router.post("/auth/switch-role", response_model=LoginResponse)
def switch_role(payload: RoleSwitchRequest, request: Request) -> dict:
    user = current_user_from_request(request)
    if payload.role not in ROLE_SCOPES:
        raise HTTPException(status_code=400, detail="unsupported role")
    if user["username"] != "admin":
        raise HTTPException(status_code=403, detail="only admin demo account can switch roles")
    user["role"] = payload.role
    role_label, access_scope = ROLE_SCOPES[payload.role]
    user["role_label"] = role_label
    user["access_scope"] = access_scope
    return {"access_token": create_access_token(user), "token_type": "bearer", "user": user}


@router.post("/knowledge-bases")
def create_knowledge_base(payload: KnowledgeBaseCreate, request: Request, db: Session = Depends(get_db)) -> dict:
    user = current_user_from_request(request)
    require_permission(user, "knowledge_base:create")
    kb = KnowledgeBaseRepository(db).create(payload.name, payload.description, payload.category)
    return _kb_to_dict(kb, 0)


@router.get("/knowledge-bases")
def list_knowledge_bases(request: Request, db: Session = Depends(get_db)) -> list[dict]:
    user = current_user_from_request(request)
    repo = KnowledgeBaseRepository(db)
    docs = DocumentRepository(db)
    items = repo.list() if has_permission(user, "knowledge_base:read_all") else repo.list_by_categories({POLICY_KB_CATEGORY})
    return [_kb_to_dict(kb, len(docs.list_by_kb(kb.id))) for kb in items if can_access_kb_category(user, kb.category)]


@router.delete("/knowledge-bases/{kb_id}")
def delete_knowledge_base(kb_id: str, request: Request, db: Session = Depends(get_db)) -> dict:
    user = current_user_from_request(request)
    require_permission(user, "knowledge_base:delete")
    _ensure_kb_access(db, kb_id, user)
    if not KnowledgeBaseRepository(db).delete(kb_id):
        raise HTTPException(status_code=404, detail="knowledge base not found")
    return {"deleted": True}


@router.get("/knowledge-bases/{kb_id}/documents")
def list_documents(kb_id: str, request: Request, db: Session = Depends(get_db)) -> list[dict]:
    user = current_user_from_request(request)
    _ensure_kb_access(db, kb_id, user)
    return [_doc_to_dict(doc) for doc in DocumentRepository(db).list_by_kb(kb_id)]


@router.post("/knowledge-bases/{kb_id}/documents")
async def upload_document(kb_id: str, request: Request, file: UploadFile = File(...), db: Session = Depends(get_db)) -> dict:
    user = current_user_from_request(request)
    require_permission(user, "document:write")
    _ensure_kb_access(db, kb_id, user)
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"unsupported file type: {suffix}")
    content = await file.read()
    service = IngestionService(db)
    path = service.save_upload(kb_id, file.filename or "upload.txt", content)
    doc = DocumentRepository(db).create(kb_id, Path(path).name, suffix.lstrip("."), path)
    doc = service.ingest_document(doc)
    return _doc_to_dict(doc)


@router.get("/documents/{document_id}/chunks")
def list_chunks(document_id: str, request: Request, db: Session = Depends(get_db)) -> list[dict]:
    user = current_user_from_request(request)
    doc = DocumentRepository(db).get(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="document not found")
    _ensure_kb_access(db, doc.knowledge_base_id, user)
    return [_chunk_to_dict(chunk) for chunk in ChunkRepository(db).list_by_document(document_id)]


@router.post("/documents/{document_id}/rebuild", response_model=RebuildResponse)
def rebuild_document(document_id: str, request: Request, db: Session = Depends(get_db)) -> dict:
    user = current_user_from_request(request)
    require_permission(user, "document:write")
    doc = DocumentRepository(db).get(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="document not found")
    _ensure_kb_access(db, doc.knowledge_base_id, user)
    doc = IngestionService(db).ingest_document(doc)
    return {"document_id": doc.id, "status": doc.status, "chunk_count": doc.chunk_count}


@router.post("/knowledge-bases/{kb_id}/ask", response_model=AskResponse)
def ask(kb_id: str, payload: AskRequest, request: Request, db: Session = Depends(get_db)) -> dict:
    user = current_user_from_request(request)
    require_permission(user, "qa:ask")
    _ensure_kb_access(db, kb_id, user)
    return RAGService(db).ask(kb_id, payload.question, payload.top_k)


@router.post("/knowledge-bases/{kb_id}/ask/stream")
def ask_stream(kb_id: str, payload: AskRequest, request: Request, db: Session = Depends(get_db)) -> StreamingResponse:
    user = current_user_from_request(request)
    require_permission(user, "qa:ask")
    _ensure_kb_access(db, kb_id, user)
    events = list(RAGService(db).ask_stream_events(kb_id, payload.question, payload.top_k))

    def event_source():
        for event in events:
            yield f"event: {event['event']}\ndata: {json.dumps(event['data'], ensure_ascii=False)}\n\n"

    return StreamingResponse(event_source(), media_type="text/event-stream")


@router.get("/qa-logs")
def list_qa_logs(request: Request, db: Session = Depends(get_db), limit: int = 100) -> list[dict]:
    user = current_user_from_request(request)
    require_permission(user, "logs:read")
    return [_log_to_dict(log) for log in QALogRepository(db).list(limit) if _can_access_kb_id(db, log.knowledge_base_id, user)]


@router.get("/model-config", response_model=ModelConfigOut)
def get_model_config(request: Request) -> dict:
    user = current_user_from_request(request)
    require_permission(user, "model_config:read")
    return _model_config_to_dict()


@router.post("/model-config", response_model=ModelConfigOut)
def update_model_config(payload: ModelConfigUpdate, request: Request) -> dict:
    user = current_user_from_request(request)
    require_permission(user, "model_config:write")
    settings = get_settings()
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(settings, field, value)
    return _model_config_to_dict()


@router.get("/eval/summary", response_model=EvalSummaryOut)
def eval_summary(request: Request, db: Session = Depends(get_db)) -> dict:
    user = current_user_from_request(request)
    require_permission(user, "eval:read")
    logs = [_log_to_dict(log) for log in QALogRepository(db).list(500) if _can_access_kb_id(db, log.knowledge_base_id, user)]
    cases = _load_eval_cases()
    total = max(len(logs), 1)
    hit_count = sum(1 for log in logs if log["hit_knowledge_base"])
    refusal_count = len(logs) - hit_count
    cited_count = sum(1 for log in logs if log["citations"])
    latency = sum(int(log["latency_ms"] or 0) for log in logs)
    return {
        "case_count": len(cases),
        "cases": cases,
        "log_count": len(logs),
        "retrieval_hit_rate": round(hit_count / total, 4) if logs else 0,
        "refusal_rate": round(refusal_count / total, 4) if logs else 0,
        "avg_latency_ms": round(latency / total, 2) if logs else 0,
        "citation_rate": round(cited_count / total, 4) if logs else 0,
        "recent_results": logs[:10],
    }


def _ensure_kb(db: Session, kb_id: str) -> None:
    if not KnowledgeBaseRepository(db).get(kb_id):
        raise HTTPException(status_code=404, detail="knowledge base not found")


def _ensure_kb_access(db: Session, kb_id: str, user: dict) -> None:
    kb = KnowledgeBaseRepository(db).get(kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="knowledge base not found")
    if not can_access_kb_category(user, kb.category):
        raise HTTPException(status_code=403, detail="knowledge base access denied")


def _can_access_kb_id(db: Session, kb_id: str, user: dict) -> bool:
    kb = KnowledgeBaseRepository(db).get(kb_id)
    return bool(kb and can_access_kb_category(user, kb.category))


def _kb_to_dict(kb, document_count: int) -> dict:
    return {
        "id": kb.id,
        "name": kb.name,
        "description": kb.description,
        "category": kb.category,
        "category_label": KB_CATEGORY_LABELS.get(kb.category, kb.category),
        "created_at": kb.created_at,
        "document_count": document_count,
    }


def _model_config_to_dict() -> dict:
    settings = get_settings()
    return {
        "llm_mode": settings.llm_mode,
        "chat_model": settings.chat_model,
        "embedding_model": settings.embedding_model,
        "retrieval_top_k": settings.retrieval_top_k,
        "answer_min_score": settings.answer_min_score,
        "answer_min_rerank_score": settings.answer_min_rerank_score,
        "prompt_version": settings.prompt_version,
    }


def _load_eval_cases() -> list[dict]:
    settings = get_settings()
    candidates = [Path(settings.eval_cases_path), Path("eval_cases.json"), Path("../eval_cases.json")]
    cases_path = next((path for path in candidates if path.exists()), candidates[0])
    if not cases_path.exists():
        return []
    try:
        cases = json.loads(cases_path.read_text(encoding="utf-8"))
    except Exception:
        return []
    return [
        {
            "knowledge_base_id": str(item.get("knowledge_base_id", "")),
            "question": str(item.get("question", "")),
            "expected_keyword": str(item.get("expected_keyword", "")),
        }
        for item in cases
        if isinstance(item, dict)
    ]


def _doc_to_dict(doc) -> dict:
    return {
        "id": doc.id,
        "knowledge_base_id": doc.knowledge_base_id,
        "filename": doc.filename,
        "file_type": doc.file_type,
        "status": doc.status,
        "error_message": doc.error_message,
        "chunk_count": doc.chunk_count,
        "char_count": doc.char_count,
        "created_at": doc.created_at,
    }


def _chunk_to_dict(chunk) -> dict:
    return {
        "id": chunk.id,
        "document_name": chunk.document_name,
        "content": chunk.content,
        "chunk_index": chunk.chunk_index,
        "page_number": chunk.page_number,
        "paragraph_index": chunk.paragraph_index,
        "char_length": chunk.char_length,
        "token_estimate": chunk.token_estimate,
    }


def _log_to_dict(log) -> dict:
    return {
        "id": log.id,
        "knowledge_base_id": log.knowledge_base_id,
        "question": log.question,
        "answer": log.answer,
        "citations": log.citations,
        "retrieval_results": log.retrieval_results,
        "latency_ms": log.latency_ms,
        "model_name": log.model_name,
        "token_estimate": log.token_estimate,
        "hit_knowledge_base": log.hit_knowledge_base,
        "prompt_version": log.prompt_version,
        "created_at": log.created_at,
    }
