import api from './api';
import type { Message, StreamChunk, FeedbackRequest } from '@/types';

const BASE_URL = import.meta.env.VITE_API_URL || '';

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
      onStep?: (label: string) => void;
      onDone?: (meta: { workflow?: string; stage?: string }) => void;
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
              callbacks.onStep?.(chunk.label || '');
            } else if (chunk.type === 'done') {
              callbacks.onDone?.({
                workflow: chunk.workflow,
                stage: chunk.stage,
              });
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
      onStep?: (label: string) => void;
      onDone?: (meta: { workflow?: string; stage?: string }) => void;
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
              callbacks.onStep?.(chunk.label || '');
            } else if (chunk.type === 'done') {
              callbacks.onDone?.({
                workflow: chunk.workflow,
                stage: chunk.stage,
              });
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
