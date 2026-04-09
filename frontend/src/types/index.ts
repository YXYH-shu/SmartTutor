/* ── Auth ──────────────────────────────────────────────────────── */

export interface User {
  id: string;
  username: string;
  email: string;
  is_active: boolean;
  created_at: string;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface RegisterRequest {
  username: string;
  email: string;
  password: string;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  user: User;
}

/* ── Profile ──────────────────────────────────────────────────── */

export interface UserProfile {
  id: string;
  user_id: string;
  knowledge_graph: Record<string, number>;
  learning_style: string | null;
  current_level: string;
  weak_points: string[];
  preferences: Record<string, unknown>;
  last_diagnosis: string | null;
  updated_at: string;
}

/* ── Conversation ─────────────────────────────────────────────── */

export interface Conversation {
  id: string;
  user_id: string;
  title: string | null;
  workflow_type: string | null;
  created_at: string;
  updated_at: string;
  last_message?: string | null;
}

export interface ConversationCreate {
  title?: string;
  workflow_type?: string;
}

/* ── Message ──────────────────────────────────────────────────── */

export interface Message {
  id: string;
  conversation_id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  agent_type?: string | null;
  emotion_state?: EmotionState | null;
  metadata?: Record<string, unknown> | null;
  created_at: string;
  feedback?: 'up' | 'down' | null;
}

export interface EmotionState {
  emotion: string;
  intensity: number;
  trend?: string;
}

/* ── SSE Stream ───────────────────────────────────────────────── */

export interface StreamChunk {
  type: 'content' | 'done' | 'error';
  content?: string;
  workflow?: string;
  stage?: string;
  detail?: string;
}

/* ── Pagination ───────────────────────────────────────────────── */

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  has_next: boolean;
}

/* ── Feedback ─────────────────────────────────────────────────── */

export interface FeedbackRequest {
  message_id: string;
  feedback_type: 'thumb_up' | 'thumb_down';
  comment?: string;
}
