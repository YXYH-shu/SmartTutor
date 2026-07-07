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
  /** 流式期间的思考步骤,对话结束后清空(转移到 message.thinking_steps) */
  thinkingSteps: ThinkingStep[];
  thinkingExpanded: boolean;
  /** 当前正在执行的 agent 内部名(后端 SSE step 字段),对话中实时更新 */
  currentAgent: string | null;
  /** 累积 agent 输出,按 agent name 分桶;不随对话结束清空,供右侧面板持续展示 */
  agentTrace: Record<string, { content: string; label: string; updatedAt: string }>;

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
  currentAgent: null as string | null,
  agentTrace: {} as Record<string, { content: string; label: string; updatedAt: string }>,
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
      // 把所有残留 running 状态的 step 标记为 completed
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
        currentAgent: null,
        abortController: null,
        // 流式期间数据清空(已转移到 streamMsg.thinking_steps),
        // 但 agentTrace 保留 — 右侧面板持续展示
        thinkingSteps: [],
        messages: [...s.messages, streamMsg],
      };
    }),

  setLoading: (isLoading) => set({ isLoading }),
  setStreaming: (isStreaming) => set({ isStreaming }),
  setAbortController: (abortController) => set({ abortController }),
  setCurrentStep: (currentStep) => set({ currentStep }),

  addThinkingStep: (step) =>
    set((s) => {
      // step.step 是后端推的 agent 内部名(如 "cognitive_diagnosis"),
      // 实时更新 currentAgent 让右侧面板自动跟随
      const agentName = step.step && step.step.length > 0 ? step.step : null;
      return {
        thinkingSteps: [...s.thinkingSteps, step],
        currentAgent: agentName ?? s.currentAgent,
      };
    }),

  completeRunningStep: (content, step, label) =>
    set((s) => {
      // 找到最后一条 running step,改为 completed
      const steps = [...s.thinkingSteps];
      for (let i = steps.length - 1; i >= 0; i--) {
        if (steps[i].status === 'running') {
          steps[i] = { ...steps[i], status: 'completed', content, step, label };
          break;
        }
      }
      // 累积到 agentTrace(按 agent name 分桶),对话结束后不清空
      const agentName = step && step.length > 0 ? step : null;
      const agentTrace = { ...s.agentTrace };
      if (agentName) {
        agentTrace[agentName] = {
          content,
          label: label || agentName,
          updatedAt: new Date().toISOString(),
        };
      }
      return { thinkingSteps: steps, agentTrace, currentAgent: agentName ?? s.currentAgent };
    }),

  clearThinking: () =>
    set({ thinkingSteps: [], currentAgent: null }),

  toggleThinkingExpanded: () => set((s) => ({ thinkingExpanded: !s.thinkingExpanded })),

  cancelStream: () => {
    const { abortController, isStreaming } = get();
    if (abortController && isStreaming) {
      abortController.abort();
    }
    // 注意:agentTrace 不清空,保留最近一次诊断结果供面板展示
    set({ isStreaming: false, streamingContent: '', currentStep: null, currentAgent: null, abortController: null, thinkingSteps: [] });
  },

  reset: () => set(initialState),
}));
