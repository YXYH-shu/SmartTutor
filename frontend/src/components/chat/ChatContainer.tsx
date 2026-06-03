import { useRef, useEffect } from 'react';
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
  } = useChatStore();
  const { accessToken } = useAuthStore();
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, streamingContent, thinkingSteps]);

  useEffect(() => {
    return () => { cancelStream(); };
  }, [cancelStream]);

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
        onStep: (label) => {
          setCurrentStep(label);
          addThinkingStep({ content: '', step: '', label, status: 'running' });
        },
        onThinking: (content, step, label) => {
          completeRunningStep(content, step, label);
        },
        onDone: () => {
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
        onStep: (label) => {
          setCurrentStep(label);
          addThinkingStep({ content: '', step: '', label, status: 'running' });
        },
        onThinking: (content, step, label) => {
          completeRunningStep(content, step, label);
        },
        onDone: () => {
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

  if (!currentConversationId) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-8 px-4 animate-fade-in-up">
        <div className="text-center">
          <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-primary-500/10 glow-primary-sm">
            <Sparkles size={28} className="text-primary-400" />
          </div>
          <h2 className="font-heading mb-2 text-2xl tracking-tight text-white">
            你好，同学！
          </h2>
          <p className="text-gray-500">
            选择左侧对话开始学习，或创建一个新对话
          </p>
        </div>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {quickActions.map((a) => (
            <button
              key={a.label}
              onClick={() => onQuickAction?.(a.action)}
              className="flex flex-col items-center gap-2.5 rounded-2xl border border-white/[0.06] bg-white/[0.02] px-6 py-5 text-sm text-gray-400 transition-all duration-200 hover:border-primary-500/20 hover:bg-primary-500/5 hover:text-gray-200"
            >
              <a.icon size={20} className="text-primary-400" />
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
          <div className="flex h-full items-center justify-center text-gray-500">
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
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary-500/10 text-primary-400">
              <Bot size={16} />
            </div>
            <div className="min-w-0 max-w-[75%]">
              {thinkingSteps.length > 0 ? (
                <div className="rounded-2xl border border-white/[0.06] bg-[#18181b] px-4 py-3">
                  <ThinkingView steps={thinkingSteps} />
                  <div className="mt-2 flex items-center gap-2 text-xs text-gray-500">
                    <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-primary-500" />
                    {currentStep || '正在思考...'}
                  </div>
                </div>
              ) : (
                <div className="flex items-center gap-3">
                  <div className="flex h-8 w-8 items-center justify-center rounded-full bg-primary-500/10">
                    <div className="flex gap-1">
                      <span className="h-1.5 w-1.5 animate-bounce-dot rounded-full bg-primary-400 [animation-delay:-0.32s]" />
                      <span className="h-1.5 w-1.5 animate-bounce-dot rounded-full bg-primary-400 [animation-delay:-0.16s]" />
                      <span className="h-1.5 w-1.5 animate-bounce-dot rounded-full bg-primary-400" />
                    </div>
                  </div>
                  <span className="text-sm text-gray-500">{currentStep || '正在思考...'}</span>
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
