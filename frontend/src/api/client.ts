import axios from 'axios';
import type { AskResponse, ChunkItem, CurrentUser, DocumentItem, EvalSummary, KnowledgeBase, LoginResponse, ModelConfig, QALog } from '../types';

const baseURL = import.meta.env.VITE_API_BASE_URL || '/api';

export const api = axios.create({ baseURL, timeout: 120000 });

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('rag_access_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

export async function login(username: string, password: string) {
  const { data } = await api.post<LoginResponse>('/auth/login', { username, password });
  localStorage.setItem('rag_access_token', data.access_token);
  return data;
}

export async function getCurrentUser() {
  const { data } = await api.get<CurrentUser>('/auth/me');
  return data;
}

export async function switchRole(role: string) {
  const { data } = await api.post<LoginResponse>('/auth/switch-role', { role });
  localStorage.setItem('rag_access_token', data.access_token);
  return data;
}

export function logout() {
  localStorage.removeItem('rag_access_token');
}

export async function listKnowledgeBases() {
  const { data } = await api.get<KnowledgeBase[]>('/knowledge-bases');
  return data;
}

export async function createKnowledgeBase(name: string, description: string, category = 'policy') {
  const { data } = await api.post<KnowledgeBase>('/knowledge-bases', { name, description, category });
  return data;
}

export async function deleteKnowledgeBase(id: string) {
  await api.delete(`/knowledge-bases/${id}`);
}

export async function listDocuments(kbId: string) {
  const { data } = await api.get<DocumentItem[]>(`/knowledge-bases/${kbId}/documents`);
  return data;
}

export async function uploadDocument(kbId: string, file: File) {
  const formData = new FormData();
  formData.append('file', file);
  const { data } = await api.post<DocumentItem>(`/knowledge-bases/${kbId}/documents`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' }
  });
  return data;
}

export async function rebuildDocument(documentId: string) {
  const { data } = await api.post(`/documents/${documentId}/rebuild`);
  return data;
}

export async function listDocumentChunks(documentId: string) {
  const { data } = await api.get<ChunkItem[]>(`/documents/${documentId}/chunks`);
  return data;
}

export async function askKnowledgeBase(kbId: string, question: string, topK: number) {
  const { data } = await api.post<AskResponse>(`/knowledge-bases/${kbId}/ask`, { question, top_k: topK });
  return data;
}

export async function streamAskKnowledgeBase(
  kbId: string,
  question: string,
  topK: number,
  handlers: {
    onToken: (delta: string) => void;
    onMetadata?: (metadata: Partial<AskResponse>) => void;
    onDone: (answer: AskResponse) => void;
  }
) {
  const token = localStorage.getItem('rag_access_token');
  const response = await fetch(`${baseURL}/knowledge-bases/${kbId}/ask/stream`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {})
    },
    body: JSON.stringify({ question, top_k: topK })
  });
  if (!response.ok || !response.body) {
    throw new Error('stream request failed');
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder('utf-8');
  let buffer = '';
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const events = buffer.split('\n\n');
    buffer = events.pop() || '';
    for (const rawEvent of events) {
      const lines = rawEvent.split('\n');
      const event = lines.find((line) => line.startsWith('event: '))?.slice(7);
      const dataLine = lines.find((line) => line.startsWith('data: '));
      if (!event || !dataLine) continue;
      const data = JSON.parse(dataLine.slice(6));
      if (event === 'token') handlers.onToken(data.delta || '');
      if (event === 'metadata') handlers.onMetadata?.(data);
      if (event === 'done') handlers.onDone(data);
    }
  }
}

export async function listQALogs() {
  const { data } = await api.get<QALog[]>('/qa-logs');
  return data;
}

export async function getModelConfig() {
  const { data } = await api.get<ModelConfig>('/model-config');
  return data;
}

export async function updateModelConfig(payload: Partial<ModelConfig>) {
  const { data } = await api.post<ModelConfig>('/model-config', payload);
  return data;
}

export async function getEvalSummary() {
  const { data } = await api.get<EvalSummary>('/eval/summary');
  return data;
}
