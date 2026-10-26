import { useRef, useEffect, useState } from 'react';
import {
  BookOpen,
  Target,
  Users,
  BarChart3,
  Sparkles,
  Bot,
} from 'lucide-react';
import { MessageBubble } from './MessageBubble';
import { ChatInput } from './ChatInput';
import { ThinkingView } from './ThinkingView';
import { useChatStore } from '@/stores/chatStore';
import { useUIStore } from '@/stores/uiStore';
import { useAuthStore } from '@/stores/authStore';
import { chatService } from '@/services/chat.service';
import { toast } from 'sonner';

interface Props {
  onRegenerate?: () => void;
  onQuickAction?: (action: string) => void;
}

export function ChatContainer({ onQuickAction }: Props) {
  const {
    messages,
    currentConversationId,
    isLoading,
    isStreaming,
    streamingContent,
    currentStep,
    thinkingSteps,
    addMessage,
    updateStreamingContent,
    finishStreaming,
    setCurrentStep,
    addThinkingStep,
    completeRunningStep,
    clearThinking,
    setLoading,
    setAbortController,
    cancelStream,
    startTurn,
    finalizeTurn,
    resetTurn,
    pendingSafetyGuide,
    clearPendingSafetyGuide,
  } = useChatStore();
  const { accessToken } = useAuthStore();
  const showAgentResult = useChatStore((s) => s.showAgentResult);
  const setRightPanelOpen = useUIStore((s) => s.setRightPanelOpen);
  const bottomRef = useRef<HTMLDivElement>(null);
  const [handledBuddyOffer, setHandledBuddyOffer] = useState<string | null>(null);
  const [isMatchingBuddy, setIsMatchingBuddy] = useState(false);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, streamingContent, thinkingSteps]);

  useEffect(() => {
    return () => { cancelStream(); };
  }, [cancelStream]);

  // 切换对话时清空 turn 级状态(并清 agentTrace)
  useEffect(() => {
    resetTurn();
  }, [currentConversationId, resetTurn]);

  const handleSend = async (content: string) => {
    if (!accessToken) {
      toast.error('请先登录');
      return;
    }
    if (!currentConversationId) {
      toast.error('请先选择或创建一个对话');
      return;
    }

    cancelStream();
    // 启动新一轮追踪(在 sendMessage 前调用,确保 timeline 能记录后续 step)
    startTurn();

    addMessage({
      id: `temp-user-${Date.now()}`,
      conversation_id: currentConversationId,
      role: 'user',
      content,
      created_at: new Date().toISOString(),
    });

    setLoading(true);

    const ac = new AbortController();
    setAbortController(ac);

    await chatService.sendMessageStream(
      currentConversationId,
      content,
      accessToken,
      {
        onChunk: (chunk) => {
          updateStreamingContent(chunk);
        },
        onStep: (label, step) => {
          setCurrentStep(label);
          addThinkingStep({ content: '', step: step || '', label, status: 'running' });
        },
        onThinking: (content, step, label) => {
          completeRunningStep(content, step, label);
        },
        onDone: (payload) => {
          finalizeTurn(payload);
          finishStreaming();
          setLoading(false);
        },
        onError: (err) => {
          toast.error(err || 'AI 回复出错');
          setLoading(false);
          finishStreaming();
        },
      },
      ac.signal,
    );
  };

  const handleRegenerate = async () => {
    if (!accessToken) {
      toast.error('请先登录');
      return;
    }
    if (!currentConversationId) {
      toast.error('请先选择或创建一个对话');
      return;
    }

    cancelStream();
    startTurn();

    const msgs = useChatStore.getState().messages;
    const lastAssistantIdx = [...msgs].reverse().findIndex((m) => m.role === 'assistant');
    if (lastAssistantIdx !== -1) {
      const removeIdx = msgs.length - 1 - lastAssistantIdx;
      const updated = msgs.filter((_, i) => i !== removeIdx);
      useChatStore.getState().setMessages(updated);
    }

    setLoading(true);
    const ac = new AbortController();
    setAbortController(ac);

    await chatService.regenerateStream(
      currentConversationId,
      accessToken,
      {
        onChunk: (chunk) => {
          updateStreamingContent(chunk);
        },
        onStep: (label, step) => {
          setCurrentStep(label);
          addThinkingStep({ content: '', step: step || '', label, status: 'running' });
        },
        onThinking: (content, step, label) => {
          completeRunningStep(content, step, label);
        },
        onDone: (payload) => {
          finalizeTurn(payload);
          finishStreaming();
          setLoading(false);
        },
        onError: (err) => {
          toast.error(err || '重新生成失败');
          setLoading(false);
          finishStreaming();
        },
      },
      ac.signal,
    );
  };

  const handleGuideSelect = (option: string) => {
    clearPendingSafetyGuide();
    void handleSend(option);
  };

  let lastAssistantIndex = -1;
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    if (messages[index].role === 'assistant') {
      lastAssistantIndex = index;
      break;
    }
  }
  const buddyOfferMessage = lastAssistantIndex === messages.length - 1
    ? messages[lastAssistantIndex]
    : undefined;
  const hasCompletedCorrection = buddyOfferMessage?.thinking_steps?.some(
    (step) => step.step === 'content_corrector' && step.status !== 'running',
  ) === true;
  const alreadyRecommendedBuddies = buddyOfferMessage?.thinking_steps?.some(
    (step) => step.step === 'study_buddy',
  ) === true;
  let buddySourceQuestion = '';
  if (lastAssistantIndex > 0) {
    for (let index = lastAssistantIndex - 1; index >= 0; index -= 1) {
      if (messages[index].role === 'user') {
        buddySourceQuestion = messages[index].content;
        break;
      }
    }
  }
  const showBuddyOffer = Boolean(
    buddyOfferMessage
      && hasCompletedCorrection
      && buddySourceQuestion
      && !alreadyRecommendedBuddies
      && handledBuddyOffer !== buddyOfferMessage.id
      && !isLoading
      && !isStreaming,
  );
  const buddyTopic = /电阻/.test(buddySourceQuestion) ? '电流、电阻等方向' : /电流/.test(buddySourceQuestion) ? '电流等方向' : '当前学习方向';

  const dismissBuddyOffer = (messageId: string) => {
    setHandledBuddyOffer(messageId);
  };

  const handleBuddyRecommendation = async () => {
    if (!buddyOfferMessage || !buddySourceQuestion || !currentConversationId) return;
    const sourceConversationId = currentConversationId;
    const sourceMessageId = buddyOfferMessage.id;
    setIsMatchingBuddy(true);
    showAgentResult('study_buddy', '学伴推荐', undefined, 'running');
    try {
      const output = await chatService.recommendStudyBuddies(
        buddySourceQuestion,
        buddyOfferMessage.content,
      );
      const latestState = useChatStore.getState();
      const latestMessage = latestState.messages[latestState.messages.length - 1];
      if (latestState.currentConversationId !== sourceConversationId || latestMessage?.id !== sourceMessageId) return;
      setRightPanelOpen(true);
      showAgentResult('study_buddy', '学伴推荐', output, 'completed');
      dismissBuddyOffer(sourceMessageId);
    } catch {
      if (useChatStore.getState().currentConversationId === sourceConversationId) {
        showAgentResult('study_buddy', '学伴推荐', undefined, 'error');
        toast.error('学伴推荐暂时不可用，请稍后重试');
      }
    } finally {
      setIsMatchingBuddy(false);
    }
  };

  if (!currentConversationId) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-8 px-4 animate-fade-in-up">
        <div className="text-center">
          <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-xl bg-accent-soft glow-primary-sm">
            <Sparkles size={28} className="text-accent" />
          </div>
          <h2 className="font-heading mb-2 text-24 tracking-tight text-text-primary">
            你好，同学！
          </h2>
          <p className="text-text-tertiary">
            选择左侧对话开始学习，或创建一个新对话
          </p>
        </div>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {quickActions.map((a) => (
            <button
              key={a.label}
              onClick={() => onQuickAction?.(a.action)}
              className="flex flex-col items-center gap-2.5 rounded-xl border border-border-subtle bg-bg-elevated/30 px-6 py-5 text-14 text-text-secondary transition-all duration-200 hover:border-accent/20 hover:bg-accent/5 hover:text-text-primary"
            >
              <a.icon size={20} className="text-accent" />
              {a.label}
            </button>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex-1 overflow-y-auto scrollbar-thin animate-fade-in">
        {messages.length === 0 && !isStreaming && (
          <div className="flex h-full items-center justify-center text-text-tertiary">
            <p>开始一段新的学习旅程吧！</p>
          </div>
        )}

        {messages.map((msg, i) => (
          <MessageBubble
            key={msg.id}
            message={msg}
            isLast={i === messages.length - 1 && !isStreaming}
            onRegenerate={msg.role === 'assistant' ? handleRegenerate : undefined}
          />
        ))}

        {showBuddyOffer && (
          <div className="mx-6 mb-4 ml-[68px] max-w-[75%] rounded-xl border border-cyan-400/20 bg-[linear-gradient(135deg,rgba(6,182,212,.09),rgba(99,102,241,.05))] p-4 animate-fade-in-up">
            <div className="flex items-start gap-3">
              <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-cyan-500/10 text-cyan-500"><Users size={18} /></span>
              <div className="min-w-0 flex-1">
                <p className="text-13 font-semibold text-text-primary">是否需要学习伙伴？</p>
                <p className="mt-1 text-12 leading-5 text-text-secondary">目前认为你在{buddyTopic}还需要继续巩固，是否需要为你推荐几位合适的学伴？</p>
                <div className="mt-3 flex gap-2">
                  <button type="button" onClick={() => void handleBuddyRecommendation()} disabled={isMatchingBuddy} className="rounded-lg bg-cyan-500 px-3 py-1.5 text-12 font-medium text-white transition hover:bg-cyan-400 disabled:cursor-wait disabled:opacity-60">{isMatchingBuddy ? '正在匹配学伴…' : '是，推荐3位学伴'}</button>
                  <button type="button" onClick={() => dismissBuddyOffer(buddyOfferMessage!.id)} disabled={isMatchingBuddy} className="rounded-lg border border-border-subtle px-3 py-1.5 text-12 text-text-secondary transition hover:bg-bg-elevated hover:text-text-primary disabled:opacity-50">否，暂时不用</button>
                </div>
              </div>
            </div>
          </div>
        )}

        {isStreaming && (
          <MessageBubble
            message={{
              id: 'streaming',
              conversation_id: currentConversationId,
              role: 'assistant',
              content: streamingContent || ' ',
              created_at: new Date().toISOString(),
            }}
            thinkingSteps={thinkingSteps.length > 0 ? thinkingSteps : undefined}
            isLast
          />
        )}

        {isLoading && !isStreaming && (
          <div className="flex gap-3 px-6 py-4">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-accent-soft text-accent">
              <Bot size={16} />
            </div>
            <div className="min-w-0 max-w-[75%]">
              {thinkingSteps.length > 0 ? (
                <div className="rounded-xl border border-border-subtle bg-bg-elevated px-4 py-3">
                  <ThinkingView steps={thinkingSteps} />
                  <div className="mt-2 flex items-center gap-2 text-12 text-text-tertiary">
                    <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-accent" />
                    {currentStep || '正在思考...'}
                  </div>
                </div>
              ) : (
                <div className="flex items-center gap-3">
                  <div className="flex h-8 w-8 items-center justify-center rounded-full bg-accent-soft">
                    <div className="flex gap-1">
                      <span className="h-1.5 w-1.5 animate-bounce-dot rounded-full bg-accent [animation-delay:-0.32s]" />
                      <span className="h-1.5 w-1.5 animate-bounce-dot rounded-full bg-accent [animation-delay:-0.16s]" />
                      <span className="h-1.5 w-1.5 animate-bounce-dot rounded-full bg-accent" />
                    </div>
                  </div>
                  <span className="text-14 text-text-tertiary">{currentStep || '正在思考...'}</span>
                </div>
              )}
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      <ChatInput
        onSend={handleSend}
        disabled={isLoading}
        placeholder="输入你的学习问题..."
        guideOptions={pendingSafetyGuide?.options}
        recommendedOption={pendingSafetyGuide?.recommendedOption}
        onSelectGuide={handleGuideSelect}
      />
    </div>
  );
}

const quickActions = [
  {
    label: '开始诊断',
    icon: BarChart3,
    action: 'diagnosis',
  },
  {
    label: '制定计划',
    icon: Target,
    action: 'plan',
  },
  {
    label: '找学习伙伴',
    icon: Users,
    action: 'companion',
  },
  {
    label: '复习评估',
    icon: BookOpen,
    action: 'review',
  },
];
