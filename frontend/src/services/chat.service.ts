import api from './api';
import type { Message, StreamChunk, FeedbackRequest, StreamDonePayload } from '@/types';

const BASE_URL = import.meta.env.VITE_API_URL || '';

// 把后端原始 SSE done 数据规范化为 StreamDonePayload(兼容 snake_case / camelCase)
function parseDonePayload(raw: any): StreamDonePayload {
  const p: StreamDonePayload = {};
  if (!raw || typeof raw !== 'object') return p;
  // 每个字段独立 ?? 兜底,确保旧后端不返回时不报错
  p.workflow = raw.workflow ?? raw.workflow_type;
  p.stage = raw.stage;
  p.turnId = raw.turnId ?? raw.turn_id;
  // focusAgents / touchedNodes / ktSummary 也兼容 snake_case
  const focusAgentsRaw = raw.focusAgents ?? raw.focus_agents;
  if (Array.isArray(focusAgentsRaw)) {
    p.focusAgents = focusAgentsRaw.filter((x) => typeof x === 'string');
  }
  p.trajectory = Array.isArray(raw.trajectory)
    ? raw.trajectory.filter((x: unknown) => typeof x === 'string')
    : undefined;
  const touchedRaw = raw.touchedNodes ?? raw.touched_nodes;
  if (Array.isArray(touchedRaw)) {
    p.touchedNodes = touchedRaw
      .map((n: any) => {
        if (!n || typeof n !== 'object') return null;
        const id = n.id ?? n.kp_id ?? n.skillId;
        if (!id) return null;
        return {
          id: String(id),
          label: n.label ?? n.name ?? n.skillName ?? String(id),
          mastery: typeof n.mastery === 'number' ? n.mastery : undefined,
          isHighlight: typeof n.isHighlight === 'boolean' ? n.isHighlight : (typeof n.is_highlight === 'boolean' ? n.is_highlight : undefined),
          isActive: typeof n.isActive === 'boolean' ? n.isActive : (typeof n.is_active === 'boolean' ? n.is_active : undefined),
          status: n.status,
        };
      })
      .filter((n): n is NonNullable<typeof n> => n !== null);
  }
  const ktRaw = raw.ktSummary ?? raw.kt_summary;
  if (ktRaw && typeof ktRaw === 'object') {
    const summary: StreamDonePayload['ktSummary'] = {};
    if (Array.isArray(ktRaw.knowledgeStates ?? ktRaw.knowledge_states)) {
      const ks = (ktRaw.knowledgeStates ?? ktRaw.knowledge_states) as any[];
      summary.knowledgeStates = ks
        .map((s) => {
          if (!s || typeof s !== 'object') return null;
          const skillId = s.skillId ?? s.skill_id ?? s.id;
          if (!skillId) return null;
          return {
            skillId: String(skillId),
            skillName: s.skillName ?? s.skill_name ?? s.name ?? String(skillId),
            mastery: typeof s.mastery === 'number' ? s.mastery : 0,
            status: typeof s.status === 'string' ? s.status : undefined,
          };
        })
        .filter((s): s is NonNullable<typeof s> => s !== null);
    }
    if (Array.isArray(ktRaw.weakPoints ?? ktRaw.weak_points)) {
      summary.weakPoints = (ktRaw.weakPoints ?? ktRaw.weak_points).filter(
        (x: unknown) => typeof x === 'string',
      );
    }
    const diagSummary = ktRaw.diagnosisSummary ?? ktRaw.diagnosis_summary;
    if (typeof diagSummary === 'string') summary.diagnosisSummary = diagSummary;
    const diagSource = ktRaw.diagnosisSource ?? ktRaw.diagnosis_source;
    if (typeof diagSource === 'string') summary.diagnosisSource = diagSource;
    const modelInfo = ktRaw.modelInfo ?? ktRaw.model_info;
    if (modelInfo && typeof modelInfo === 'object') {
      summary.modelInfo = modelInfo as Record<string, unknown>;
    }
    if (ktRaw.metrics && typeof ktRaw.metrics === 'object') {
      summary.metrics = ktRaw.metrics as Record<string, unknown>;
    }
    p.ktSummary = summary;
  }
  const guideRaw = raw.safetyGuide ?? raw.safety_guide;
  if (guideRaw && typeof guideRaw === 'object') {
    const safeQuery = guideRaw.safeQuery ?? guideRaw.safe_query;
    const optionsRaw = guideRaw.options ?? guideRaw.learning_options;
    const recommendedRaw = guideRaw.recommendedOption ?? guideRaw.recommended_option;
    const options = Array.isArray(optionsRaw)
      ? optionsRaw.filter((x: unknown): x is string => typeof x === 'string' && x.trim().length > 0)
      : [];
    if (typeof safeQuery === 'string' && safeQuery.trim() && options.length > 0) {
      p.safetyGuide = {
        safeQuery: safeQuery.trim(),
        options: options.slice(0, 3),
        recommendedOption:
          typeof recommendedRaw === 'string' && options.includes(recommendedRaw.trim())
            ? recommendedRaw.trim()
            : options[0],
      };
    }
  }
  return p;
}

export const chatService = {
  /**
   * Non-streaming send.  Returns the full assistant message.
   */
  async sendMessage(conversationId: string, content: string) {
    const res = await api.post('/api/v1/chat/send', {
      conversation_id: conversationId,
      content,
    });
    return res.data;
  },

  /**
   * SSE streaming send.
   *
   * Uses native `fetch` + `ReadableStream` so we can pass the JWT
   * header manually while still streaming the response.
   */
  async sendMessageStream(
    conversationId: string,
    content: string,
    accessToken: string,
    callbacks: {
      onChunk: (chunk: string) => void;
      onStep?: (label: string, step?: string) => void;
      onThinking?: (content: string, step: string, label: string) => void;
      onDone?: (payload: StreamDonePayload) => void;
      onError?: (err: string) => void;
    },
    signal?: AbortSignal,
  ): Promise<void> {
    const url = `${BASE_URL}/api/v1/chat/stream`;
    try {
      const resp = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({ conversation_id: conversationId, content }),
        signal,
      });

      if (!resp.ok) {
        callbacks.onError?.(`Server error ${resp.status}`);
        return;
      }

      const reader = resp.body?.getReader();
      if (!reader) {
        callbacks.onError?.('No response body');
        return;
      }

      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        // Parse SSE lines
        const lines = buffer.split('\n');
        buffer = lines.pop() || ''; // keep incomplete line

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          const raw = line.slice(6).trim();
          if (!raw) continue;

          try {
            const chunk: StreamChunk = JSON.parse(raw);
            if (chunk.type === 'content' && chunk.content) {
              callbacks.onChunk(chunk.content);
            } else if (chunk.type === 'step') {
              callbacks.onStep?.(chunk.label || '', chunk.step);
            } else if (chunk.type === 'thinking') {
              callbacks.onThinking?.(chunk.content || '', chunk.step || '', chunk.label || '');
            } else if (chunk.type === 'done') {
              // 解析完整 StreamDonePayload(兼容旧后端仅返回 workflow/stage)
              const payload = parseDonePayload({
                ...chunk,
                ...(chunk.done || {}),
              });
              callbacks.onDone?.(payload);
            } else if (chunk.type === 'error') {
              callbacks.onError?.(chunk.detail || 'Stream error');
            }
          } catch {
            // Ignore malformed JSON – could be [DONE] text
          }
        }
      }
    } catch (err: any) {
      if (err.name === 'AbortError') return; // silently ignore abort
      callbacks.onError?.(err.message || 'Network error');
    }
  },

  async sendFeedback(data: FeedbackRequest): Promise<void> {
    await api.post('/api/v1/chat/feedback', data);
  },

  async regenerateStream(
    conversationId: string,
    accessToken: string,
    callbacks: {
      onChunk: (chunk: string) => void;
      onStep?: (label: string, step?: string) => void;
      onThinking?: (content: string, step: string, label: string) => void;
      onDone?: (payload: StreamDonePayload) => void;
      onError?: (err: string) => void;
    },
    signal?: AbortSignal,
  ): Promise<void> {
    const url = `${BASE_URL}/api/v1/chat/regenerate`;
    try {
      const resp = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({ conversation_id: conversationId }),
        signal,
      });

      if (!resp.ok) {
        const errData = await resp.json().catch(() => ({}));
        callbacks.onError?.(errData.detail || `Server error ${resp.status}`);
        return;
      }

      const reader = resp.body?.getReader();
      if (!reader) {
        callbacks.onError?.('No response body');
        return;
      }

      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          const raw = line.slice(6).trim();
          if (!raw) continue;

          try {
            const chunk: StreamChunk = JSON.parse(raw);
            if (chunk.type === 'content' && chunk.content) {
              callbacks.onChunk(chunk.content);
            } else if (chunk.type === 'step') {
              callbacks.onStep?.(chunk.label || '', chunk.step);
            } else if (chunk.type === 'thinking') {
              callbacks.onThinking?.(chunk.content || '', chunk.step || '', chunk.label || '');
            } else if (chunk.type === 'done') {
              const payload = parseDonePayload({
                ...chunk,
                ...(chunk.done || {}),
              });
              callbacks.onDone?.(payload);
            } else if (chunk.type === 'error') {
              callbacks.onError?.(chunk.detail || 'Stream error');
            }
          } catch {
            // Ignore malformed JSON
          }
        }
      }
    } catch (err: any) {
      if (err.name === 'AbortError') return;
      callbacks.onError?.(err.message || 'Network error');
    }
  },

  async getHistory(
    conversationId: string,
    beforeId?: string,
    limit = 20,
  ): Promise<Message[]> {
    const params: Record<string, unknown> = {
      conversation_id: conversationId,
      limit,
    };
    if (beforeId) params.before_id = beforeId;
    const res = await api.get('/api/v1/chat/history', { params });
    return res.data.items;
  },
};
