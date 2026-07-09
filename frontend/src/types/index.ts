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
  // 新增(后端 task 7 字段,旧会话可能为 null)
  knowledge_points?: KnowledgeNode[] | null;
  highlight_agent?: string | null;
}

export interface ConversationCreate {
  title?: string;
  workflow_type?: string;
}

/* ── Message ──────────────────────────────────────────────────── */

export interface ThinkingStep {
  step: string;
  label: string;
  content: string;
  status?: 'running' | 'completed';
}

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
  thinking_steps?: ThinkingStep[] | null;
}

export interface EmotionState {
  emotion: string;
  intensity: number;
  trend?: string;
}

/* ── SSE Stream ───────────────────────────────────────────────── */

export interface StreamChunk {
  type: 'content' | 'done' | 'error' | 'step' | 'thinking';
  content?: string;
  workflow?: string;
  stage?: string;
  detail?: string;
  label?: string;
  step?: string;
  thinking_steps?: ThinkingStep[] | null;
  // 新增(后端契约升级后会出现;旧后端不返回)
  done?: StreamDonePayload;
}

/* ── Turn-level data (新视觉组件用) ──────────────────────────── */

// 知识节点(用于 Path Bar / 认知地图 / 左栏缩略图)
export interface KnowledgeNode {
  id: string;
  label: string;
  mastery?: number;       // 0..1,可选
  isHighlight?: boolean;  // 本轮重点
  isActive?: boolean;     // 正在被处理
  status?: 'mastered' | 'developing' | 'weak' | 'unknown';
}

// Agent 时间线项(用于 Trace Timeline / Agent Interaction Log)
export interface AgentTimelineItem {
  agentName: string;       // 内部名,如 'cognitive_diagnosis'
  agentLabel?: string;     // 中文显示名
  startedAt: number;       // 时间戳 ms
  durationMs?: number;     // 完成后填
  status: 'pending' | 'running' | 'completed' | 'error';
  isFocus?: boolean;       // 本轮重点
  output?: any;            // agent 输出(精简版)
}

// KT 诊断摘要(本轮)
export interface KtSummary {
  knowledgeStates?: Array<{
    skillId: string;
    skillName?: string;
    mastery: number;
    status?: string;
  }>;
  weakPoints?: string[];
  diagnosisSummary?: string;
  diagnosisSource?: string;
  modelInfo?: Record<string, unknown>;
  metrics?: Record<string, unknown>;
}

// 轮次级聚合数据(一个对话轮 = 用户发一条消息 + AI 完整回复)
export interface TurnData {
  turnId: string;
  touchedNodes: KnowledgeNode[];           // 本轮触及的知识节点
  focusAgents: string[];                   // 本轮重点 agent 内部名列表
  agentTimeline: AgentTimelineItem[];      // agent 调用时间线
  trajectory?: string[];                   // 知识点轨迹(kp_id 顺序)
  ktSummary?: KtSummary;                   // KT 诊断摘要
  startedAt: number;
  endedAt?: number;
}

// SSE done 事件 payload 类型(扩展兼容)
export interface StreamDonePayload {
  workflow?: string;
  stage?: string;
  // 新增字段(后端契约升级后会出现;旧后端不返回)
  turnId?: string;
  focusAgents?: string[];
  touchedNodes?: KnowledgeNode[];
  trajectory?: string[];
  ktSummary?: KtSummary;
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
