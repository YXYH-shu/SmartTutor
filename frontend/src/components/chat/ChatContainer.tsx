import { useRef, useEffect, useState } from 'react';
import {
  BookOpen,
  Target,
  Users,
  BarChart3,
  Sparkles,
  Bot,
  CheckCircle2,
  LogOut,
} from 'lucide-react';
import { MessageBubble } from './MessageBubble';
import { ChatInput } from './ChatInput';
import { ThinkingView } from './ThinkingView';
import { SessionEndDialog } from './SessionEndDialog';
import { useChatStore } from '@/stores/chatStore';
import { useAuthStore } from '@/stores/authStore';
import { chatService } from '@/services/chat.service';
import { conversationService } from '@/services/conversation.service';
import { toast } from 'sonner';

interface Props {
  onRegenerate?: () => void;
  onQuickAction?: (action: string) => void;
}

export function ChatContainer({ onQuickAction }: Props) {
  const {
    conversations,
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
    markConversationEnded,
  } = useChatStore();
  const { accessToken } = useAuthStore();
  const bottomRef = useRef<HTMLDivElement>(null);
  const currentConversation = conversations.find(
    (c) => c.id === currentConversationId,
  );
  const isEnded = !!currentConversation?.ended_at;
  const [endDialogOpen, setEndDialogOpen] = useState(false);

  const handleEndSession = async () => {
    if (!currentConversationId) return;
    const hasUserMsg = messages.some((m) => m.role === 'user');
    // 没发过消息:直接结束,无需问卷
    if (!hasUserMsg) {
      try {
        await conversationService.end(currentConversationId);
        markConversationEnded(currentConversationId);
        toast.success('会话已结束');
      } catch (e: any) {
        toast.error(e?.response?.data?.detail ?? '结束会话失败，请重试');
      }
      return;
    }
    // 已有对话内容:先完成 3 道问卷再结束
    setEndDialogOpen(true);
  };

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
    if (isEnded) {
      toast.error('会话已结束，无法发送新消息');
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
    if (isEnded) {
      toast.error('会话已结束，无法发送新消息');
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

      <div className="flex items-center justify-end border-t border-border-subtle px-4 py-2">
        {isEnded ? (
          <div className="mr-auto flex items-center gap-1.5">
            <CheckCircle2 className="h-3.5 w-3.5 text-status-success" />
            <span className="text-12 text-text-tertiary">
              该会话已结束，可查看历史消息
            </span>
          </div>
        ) : (
          <button
            onClick={handleEndSession}
            disabled={isLoading || isStreaming}
            className="flex items-center gap-1.5 rounded-xl border border-border-subtle px-3 py-1.5 text-12 text-text-secondary hover:border-border-strong hover:text-text-primary disabled:opacity-50"
          >
            <LogOut className="h-3.5 w-3.5" />
            结束本次会话
          </button>
        )}
      </div>

      <ChatInput
        onSend={handleSend}
        disabled={isLoading || isEnded}
        placeholder={isEnded ? '会话已结束' : '输入你的学习问题...'}
        guideOptions={pendingSafetyGuide?.options}
        recommendedOption={pendingSafetyGuide?.recommendedOption}
        onSelectGuide={handleGuideSelect}
      />

      <SessionEndDialog
        open={endDialogOpen}
        conversationId={currentConversationId ?? ''}
        onClose={() => setEndDialogOpen(false)}
        onEnded={() => {
          if (currentConversationId) markConversationEnded(currentConversationId);
          setEndDialogOpen(false);
        }}
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
