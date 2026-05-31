export interface KnowledgeBase {
  id: string;
  name: string;
  description: string;
  category: 'policy' | 'business' | 'general';
  category_label: string;
  created_at: string;
  document_count: number;
}

export interface CurrentUser {
  username: string;
  name: string;
  role: string;
  role_label: string;
  access_scope: string;
  avatar?: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  user: CurrentUser;
}

export interface DocumentItem {
  id: string;
  knowledge_base_id: string;
  filename: string;
  file_type: string;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  error_message: string;
  chunk_count: number;
  char_count: number;
  created_at: string;
}

export interface Citation {
  chunk_id: string;
  document_name: string;
  chunk_index: number;
  page_number?: number | null;
  snippet: string;
  score: number;
}

export interface RetrievalResult {
  chunk_id: string;
  document_name: string;
  content?: string;
  chunk_index: number;
  page_number?: number | null;
  vector_score: number;
  keyword_score: number;
  vector_rank_score?: number;
  keyword_rank_score?: number;
  rerank_score: number;
  final_score: number;
  sources: string;
  matched_terms?: string[];
}

export interface AskResponse {
  answer: string;
  citations: Citation[];
  retrieval_results: RetrievalResult[];
  latency_ms: number;
  model_name: string;
  token_estimate: number;
  hit_knowledge_base: boolean;
  prompt_version: string;
  rewritten_query?: string;
}

export interface QALog {
  id: string;
  knowledge_base_id: string;
  question: string;
  answer: string;
  citations: Citation[];
  retrieval_results: { items?: RetrievalResult[] };
  latency_ms: number;
  model_name: string;
  token_estimate: number;
  hit_knowledge_base: boolean;
  prompt_version: string;
  created_at: string;
}

export interface ChunkItem {
  id: string;
  document_name: string;
  content: string;
  chunk_index: number;
  page_number?: number | null;
  paragraph_index?: number | null;
  char_length: number;
  token_estimate: number;
}

export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

export interface ModelConfig {
  llm_mode: string;
  chat_model: string;
  embedding_model: string;
  retrieval_top_k: number;
  answer_min_score: number;
  answer_min_rerank_score: number;
  prompt_version: string;
}

export interface EvalSummary {
  case_count: number;
  cases: Array<{
    knowledge_base_id: string;
    question: string;
    expected_keyword: string;
  }>;
  log_count: number;
  retrieval_hit_rate: number;
  refusal_rate: number;
  avg_latency_ms: number;
  citation_rate: number;
  recent_results: QALog[];
}
