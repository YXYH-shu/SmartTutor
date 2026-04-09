import api from './api';
import type {
  Conversation,
  ConversationCreate,
  PaginatedResponse,
} from '@/types';

export const conversationService = {
  async list(page = 1, pageSize = 20): Promise<PaginatedResponse<Conversation>> {
    const res = await api.get<PaginatedResponse<Conversation>>(
      '/api/v1/conversations',
      { params: { page, page_size: pageSize } },
    );
    return res.data;
  },

  async create(data: ConversationCreate = {}): Promise<Conversation> {
    const res = await api.post<Conversation>('/api/v1/conversations', data);
    return res.data;
  },

  async getDetail(id: string, limit = 50): Promise<Conversation & { messages: any[] }> {
    const res = await api.get(`/api/v1/conversations/${id}`, {
      params: { limit },
    });
    return res.data;
  },

  async updateTitle(id: string, title: string): Promise<void> {
    await api.put(`/api/v1/conversations/${id}/title`, { title });
  },

  async delete(id: string): Promise<void> {
    await api.delete(`/api/v1/conversations/${id}`);
  },
};
