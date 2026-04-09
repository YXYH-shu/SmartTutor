import { create } from 'zustand';
import type { Conversation, Message } from '@/types';

interface ChatState {
  conversations: Conversation[];
  currentConversationId: string | null;
  messages: Message[];
  isLoading: boolean;
  isStreaming: boolean;
  streamingContent: string;
  abortController: AbortController | null;

  setConversations: (convs: Conversation[]) => void;
  addConversation: (conv: Conversation) => void;
  removeConversation: (id: string) => void;
  updateConversationTitle: (id: string, title: string) => void;
  setCurrentConversation: (id: string | null) => void;
  setMessages: (msgs: Message[]) => void;
  addMessage: (msg: Message) => void;
  updateStreamingContent: (chunk: string) => void;
  finishStreaming: () => void;
  setLoading: (v: boolean) => void;
  setStreaming: (v: boolean) => void;
  setAbortController: (ac: AbortController | null) => void;
  cancelStream: () => void;
  reset: () => void;
}

const initialState = {
  conversations: [],
  currentConversationId: null as string | null,
  messages: [],
  isLoading: false,
  isStreaming: false,
  streamingContent: '',
  abortController: null as AbortController | null,
};

export const useChatStore = create<ChatState>()((set, get) => ({
  ...initialState,

  setConversations: (conversations) => set({ conversations }),

  addConversation: (conv) =>
    set((s) => ({ conversations: [conv, ...s.conversations] })),

  removeConversation: (id) =>
    set((s) => ({
      conversations: s.conversations.filter((c) => c.id !== id),
      currentConversationId:
        s.currentConversationId === id ? null : s.currentConversationId,
      messages: s.currentConversationId === id ? [] : s.messages,
    })),

  updateConversationTitle: (id, title) =>
    set((s) => ({
      conversations: s.conversations.map((c) =>
        c.id === id ? { ...c, title } : c,
      ),
    })),

  setCurrentConversation: (id) => {
    // Cancel any active stream when switching conversations
    get().cancelStream();
    set({ currentConversationId: id, messages: [] });
  },

  setMessages: (messages) => set({ messages }),

  addMessage: (msg) =>
    set((s) => ({ messages: [...s.messages, msg] })),

  updateStreamingContent: (chunk) =>
    set((s) => ({
      isStreaming: true,
      streamingContent: s.streamingContent + chunk,
    })),

  finishStreaming: () =>
    set((s) => {
      const streamMsg: Message = {
        id: `stream-${Date.now()}`,
        conversation_id: s.currentConversationId || '',
        role: 'assistant',
        content: s.streamingContent,
        created_at: new Date().toISOString(),
      };
      return {
        isStreaming: false,
        streamingContent: '',
        abortController: null,
        messages: [...s.messages, streamMsg],
      };
    }),

  setLoading: (isLoading) => set({ isLoading }),
  setStreaming: (isStreaming) => set({ isStreaming }),
  setAbortController: (abortController) => set({ abortController }),

  cancelStream: () => {
    const { abortController, isStreaming } = get();
    if (abortController && isStreaming) {
      abortController.abort();
    }
    set({ isStreaming: false, streamingContent: '', abortController: null });
  },

  reset: () => set(initialState),
}));
