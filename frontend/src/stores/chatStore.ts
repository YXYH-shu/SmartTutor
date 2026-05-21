import { create } from 'zustand';
import type { Conversation, Message, ThinkingStep } from '@/types';

interface ChatState {
  conversations: Conversation[];
  currentConversationId: string | null;
  messages: Message[];
  isLoading: boolean;
  isStreaming: boolean;
  streamingContent: string;
  abortController: AbortController | null;
  currentStep: string | null;
  thinkingSteps: ThinkingStep[];
  thinkingExpanded: boolean;

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
  setCurrentStep: (step: string | null) => void;
  addThinkingStep: (step: ThinkingStep) => void;
  completeRunningStep: (content: string, step: string, label: string) => void;
  clearThinking: () => void;
  toggleThinkingExpanded: () => void;
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
  currentStep: null as string | null,
  thinkingSteps: [] as ThinkingStep[],
  thinkingExpanded: true,
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
      // Mark any remaining running steps as completed
      const finalSteps = s.thinkingSteps.map((step) =>
        step.status === 'running' ? { ...step, status: 'completed' as const } : step,
      );
      const streamMsg: Message = {
        id: `stream-${Date.now()}`,
        conversation_id: s.currentConversationId || '',
        role: 'assistant',
        content: s.streamingContent,
        created_at: new Date().toISOString(),
        thinking_steps: finalSteps.length > 0 ? finalSteps : null,
      };
      return {
        isStreaming: false,
        streamingContent: '',
        currentStep: null,
        abortController: null,
        thinkingSteps: [],
        messages: [...s.messages, streamMsg],
      };
    }),

  setLoading: (isLoading) => set({ isLoading }),
  setStreaming: (isStreaming) => set({ isStreaming }),
  setAbortController: (abortController) => set({ abortController }),
  setCurrentStep: (currentStep) => set({ currentStep }),

  addThinkingStep: (step) =>
    set((s) => ({ thinkingSteps: [...s.thinkingSteps, step] })),

  completeRunningStep: (content, step, label) =>
    set((s) => {
      // Find the last running step and update it to completed with content
      const steps = [...s.thinkingSteps];
      for (let i = steps.length - 1; i >= 0; i--) {
        if (steps[i].status === 'running') {
          steps[i] = { ...steps[i], status: 'completed', content, step, label };
          break;
        }
      }
      return { thinkingSteps: steps };
    }),

  clearThinking: () => set({ thinkingSteps: [] }),
  toggleThinkingExpanded: () => set((s) => ({ thinkingExpanded: !s.thinkingExpanded })),

  cancelStream: () => {
    const { abortController, isStreaming } = get();
    if (abortController && isStreaming) {
      abortController.abort();
    }
    set({ isStreaming: false, streamingContent: '', currentStep: null, abortController: null, thinkingSteps: [] });
  },

  reset: () => set(initialState),
}));
