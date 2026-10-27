import { create } from 'zustand';
import type {
  Conversation,
  Message,
  ThinkingStep,
  TurnData,
  KnowledgeNode,
  AgentTimelineItem,
  StreamDonePayload,
  SafetyGuide,
} from '@/types';

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
  /** 累积 agent 输出,按 agent name 分桶;切换对话时清空 */
  agentTrace: Record<string, { content: string; label: string; updatedAt: string }>;
  pendingSafetyGuide: SafetyGuide | null;

  // ── 新增:turn 级字段 ──
  /** 当前轮次聚合数据(用户发一条消息 + AI 完整回复 = 一轮) */
  currentTurn: TurnData | null;
  /** 当前对话所有轮次(用于 Trace Timeline 回看) */
  turnHistory: TurnData[];
  /** 当前轮重点 agent 内部名列表(从 currentTurn 派生,单独存方便订阅) */
  currentFocusAgents: string[];
  /** 当前轮触及的知识节点(同上) */
  currentTouchedNodes: KnowledgeNode[];
  /** 当前 active 的知识点(用于 Path Bar 呼吸动画) */
  activeNodeId?: string;
  /** 详情抽屉当前指向的 agent(点击卡片打开,null 时抽屉关闭) */
  selectedDetailAgent: string | null;

  setConversations: (convs: Conversation[]) => void;
  addConversation: (conv: Conversation) => void;
  removeConversation: (id: string) => void;
  updateConversationTitle: (id: string, title: string) => void;
  /** 会话结束(无消息直接结束 / 问卷提交后)时把 ended_at 写入对应会话 */
  markConversationEnded: (id: string) => void;
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

  // ── 新增:turn 级 actions ──
  /** 用户发消息时调用,创建新轮次 */
  startTurn: (turnId?: string) => void;
  /** 收到 SSE step 事件时往 timeline 追加 agent */
  appendTimelineItem: (item: AgentTimelineItem) => void;
  /** patch timeline 里某个 agent 的字段 */
  updateTimelineItem: (agentName: string, patch: Partial<AgentTimelineItem>) => void;
  /** 设置当前 active 的知识点(供 Path Bar 呼吸动画) */
  setActiveNode: (nodeId?: string) => void;
  /** 收到 done 事件时合并 payload 到 currentTurn,推入 turnHistory */
  finalizeTurn: (done: StreamDonePayload) => void;
  /** 切换对话时清空所有 turn 级字段(并清 agentTrace) */
  resetTurn: () => void;
  clearPendingSafetyGuide: () => void;
  /** 设置详情抽屉当前 agent(null 关闭抽屉) */
  setSelectedDetailAgent: (name: string | null) => void;
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
  // turn 级
  currentTurn: null as TurnData | null,
  turnHistory: [] as TurnData[],
  currentFocusAgents: [] as string[],
  currentTouchedNodes: [] as KnowledgeNode[],
  activeNodeId: undefined as string | undefined,
  selectedDetailAgent: null as string | null,
  pendingSafetyGuide: null as SafetyGuide | null,
};

// turn 级初始切片(供 resetTurn 复用,不包含 conversationId 等)
const initialTurnSlice = {
  currentTurn: null as TurnData | null,
  turnHistory: [] as TurnData[],
  currentFocusAgents: [] as string[],
  currentTouchedNodes: [] as KnowledgeNode[],
  activeNodeId: undefined as string | undefined,
  agentTrace: {} as Record<string, { content: string; label: string; updatedAt: string }>,
  selectedDetailAgent: null as string | null,
  pendingSafetyGuide: null as SafetyGuide | null,
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

  markConversationEnded: (id) =>
    set((s) => ({
      conversations: s.conversations.map((c) =>
        c.id === id ? { ...c, ended_at: new Date().toISOString() } : c,
      ),
    })),

  setCurrentConversation: (id) => {
    get().cancelStream();
    // 切对话时清空 turn 级字段 + agentTrace(修原 agentTrace 跨对话不清空 bug)
    set({
      currentConversationId: id,
      messages: [],
      ...initialTurnSlice,
    });
  },

  resetTurn: () =>
    set({ ...initialTurnSlice }),

  clearPendingSafetyGuide: () => set({ pendingSafetyGuide: null }),

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
      // 同步把 agent 写入 timeline(如果还没记录过)
      let currentTurn = s.currentTurn;
      if (agentName && currentTurn) {
        const exists = currentTurn.agentTimeline.some((it) => it.agentName === agentName);
        if (!exists) {
          currentTurn = {
            ...currentTurn,
            agentTimeline: [
              ...currentTurn.agentTimeline,
              {
                agentName,
                agentLabel: step.label || undefined,
                startedAt: Date.now(),
                status: 'running',
              },
            ],
          };
        }
      }
      return {
        thinkingSteps: [...s.thinkingSteps, step],
        currentAgent: agentName ?? s.currentAgent,
        currentTurn,
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
      // 累积到 agentTrace(按 agent name 分桶),切换对话时才清空
      const agentName = step && step.length > 0 ? step : null;
      const agentTrace = { ...s.agentTrace };
      if (agentName) {
        agentTrace[agentName] = {
          content,
          label: label || agentName,
          updatedAt: new Date().toISOString(),
        };
      }
      // 同步更新 timeline 里对应 agent -> completed
      let currentTurn = s.currentTurn;
      if (agentName && currentTurn) {
        const idx = currentTurn.agentTimeline.findIndex((it) => it.agentName === agentName);
        if (idx >= 0) {
          const existing = currentTurn.agentTimeline[idx];
          const updatedTimeline = [...currentTurn.agentTimeline];
          updatedTimeline[idx] = {
            ...existing,
            status: 'completed',
            durationMs: existing.durationMs ?? Date.now() - existing.startedAt,
            output: content,
            agentLabel: existing.agentLabel || label || undefined,
          };
          currentTurn = { ...currentTurn, agentTimeline: updatedTimeline };
        }
      }
      return {
        thinkingSteps: steps,
        agentTrace,
        currentAgent: agentName ?? s.currentAgent,
        currentTurn,
      };
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
    // turn 级字段也保留(用户取消流后仍可在面板看部分时间线)
    set({ isStreaming: false, streamingContent: '', currentStep: null, currentAgent: null, abortController: null, thinkingSteps: [] });
  },

  // ── 新增 turn 级 actions ──

  startTurn: (turnId) => {
    const id =
      turnId ||
      (typeof crypto !== 'undefined' && 'randomUUID' in crypto
        ? crypto.randomUUID()
        : `turn-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`);
    const newTurn: TurnData = {
      turnId: id,
      touchedNodes: [],
      focusAgents: [],
      agentTimeline: [],
      startedAt: Date.now(),
    };
    set({
      currentTurn: newTurn,
      currentFocusAgents: [],
      currentTouchedNodes: [],
      activeNodeId: undefined,
      pendingSafetyGuide: null,
    });
  },

  appendTimelineItem: (item) =>
    set((s) => {
      if (!s.currentTurn) return s; // 没有 currentTurn 时静默忽略
      const exists = s.currentTurn.agentTimeline.some(
        (it) => it.agentName === item.agentName,
      );
      const agentTimeline = exists
        ? s.currentTurn.agentTimeline
        : [...s.currentTurn.agentTimeline, item];
      return {
        currentTurn: { ...s.currentTurn, agentTimeline },
        currentAgent: item.agentName,
      };
    }),

  updateTimelineItem: (agentName, patch) =>
    set((s) => {
      if (!s.currentTurn) return s;
      const idx = s.currentTurn.agentTimeline.findIndex(
        (it) => it.agentName === agentName,
      );
      if (idx < 0) return s;
      const agentTimeline = [...s.currentTurn.agentTimeline];
      agentTimeline[idx] = { ...agentTimeline[idx], ...patch };
      return { currentTurn: { ...s.currentTurn, agentTimeline } };
    }),

  setActiveNode: (nodeId) => set({ activeNodeId: nodeId }),

  finalizeTurn: (done) =>
    set((s) => {
      if (!s.currentTurn) {
        // 极端情况:done 早于 startTurn 到达,补建一个
        return { pendingSafetyGuide: done.safetyGuide ?? null };
      }
      const focusAgents = done.focusAgents ?? s.currentTurn.focusAgents;
      const touchedNodes = done.touchedNodes ?? s.currentTurn.touchedNodes;
      const trajectory = done.trajectory ?? s.currentTurn.trajectory;
      const ktSummary = done.ktSummary ?? s.currentTurn.ktSummary;
      const turnId = done.turnId ?? s.currentTurn.turnId;
      const endedAt = Date.now();
      const finalTurn: TurnData = {
        ...s.currentTurn,
        turnId,
        focusAgents,
        touchedNodes,
        trajectory,
        ktSummary,
        endedAt,
      };
      return {
        currentTurn: finalTurn,
        turnHistory: [...s.turnHistory, finalTurn],
        currentFocusAgents: focusAgents,
        currentTouchedNodes: touchedNodes,
        pendingSafetyGuide: done.safetyGuide ?? null,
      };
    }),

  setSelectedDetailAgent: (name) => set({ selectedDetailAgent: name }),

  reset: () => set(initialState),
}));
