import { useRef, useEffect } from 'react';
import {
  BookOpen,
  Target,
  Users,
  BarChart3,
  Sparkles,
} from 'lucide-react';
import { MessageBubble } from './MessageBubble';
import { ChatInput } from './ChatInput';
import { useChatStore } from '@/stores/chatStore';
import { useAuthStore } from '@/stores/authStore';
import { chatService } from '@/services/chat.service';
import { toast } from 'sonner';

interface Props {
  onRegenerate?: () => void;
}

export function ChatContainer({ onRegenerate }: Props) {
  const {
    messages,
    currentConversationId,
    isLoading,
    isStreaming,
    streamingContent,
    addMessage,
    updateStreamingContent,
    finishStreaming,
    setLoading,
    setAbortController,
    cancelStream,
  } = useChatStore();
  const { accessToken } = useAuthStore();
  const bottomRef = useRef<HTMLDivElement>(null);

  /* ── Auto-scroll ──────────────────────────────────────────── */
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, streamingContent]);

  /* ── Cancel stream on unmount ────────────────────────────── */
  useEffect(() => {
    return () => { cancelStream(); };
  }, [cancelStream]);

  /* ── Send handler (SSE streaming) ──────────────────────────── */
  const handleSend = async (content: string) => {
    if (!currentConversationId || !accessToken) return;

    // Cancel any existing stream before starting a new one
    cancelStream();

    // Optimistically add user message
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

  /* ── Regenerate handler ───────────────────────────────────── */
  const handleRegenerate = async () => {
    if (!currentConversationId || !accessToken) return;

    // Cancel any existing stream
    cancelStream();

    // Remove the last assistant message from UI
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

  /* ── Empty state ──────────────────────────────────────────── */
  if (!currentConversationId) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-8 px-4">
        <div className="text-center">
          <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-primary-100 dark:bg-primary-900/30">
            <Sparkles size={32} className="text-primary-500" />
          </div>
          <h2 className="mb-2 text-2xl font-bold text-gray-800 dark:text-gray-200">
            你好，同学！
          </h2>
          <p className="text-gray-500 dark:text-gray-400">
            选择左侧对话开始学习，或创建一个新对话
          </p>
        </div>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {quickActions.map((a) => (
            <button
              key={a.label}
              onClick={a.onClick}
              className="flex flex-col items-center gap-2 rounded-xl border border-gray-200 px-5 py-4 text-sm text-gray-600 transition hover:border-primary-300 hover:bg-primary-50 dark:border-gray-700 dark:text-gray-400 dark:hover:border-primary-600 dark:hover:bg-primary-900/20"
            >
              <a.icon size={22} className="text-primary-500" />
              {a.label}
            </button>
          ))}
        </div>
      </div>
    );
  }

  /* ── Messages ─────────────────────────────────────────────── */
  return (
    <div className="flex h-full flex-col">
      <div className="flex-1 overflow-y-auto scrollbar-thin">
        {messages.length === 0 && !isStreaming && (
          <div className="flex h-full items-center justify-center text-gray-400">
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

        {/* Streaming content bubble */}
        {isStreaming && (
          <MessageBubble
            message={{
              id: 'streaming',
              conversation_id: currentConversationId,
              role: 'assistant',
              content: streamingContent || ' ',
              created_at: new Date().toISOString(),
            }}
            isLast
          />
        )}

        {/* Loading dots */}
        {isLoading && !isStreaming && (
          <div className="flex items-center gap-3 px-4 py-3">
            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-primary-100 dark:bg-primary-900/30">
              <div className="flex gap-1">
                <span className="h-1.5 w-1.5 animate-bounce-dot rounded-full bg-primary-400 [animation-delay:-0.32s]" />
                <span className="h-1.5 w-1.5 animate-bounce-dot rounded-full bg-primary-400 [animation-delay:-0.16s]" />
                <span className="h-1.5 w-1.5 animate-bounce-dot rounded-full bg-primary-400" />
              </div>
            </div>
            <span className="text-sm text-gray-400">正在思考...</span>
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

/* ── Quick Actions ──────────────────────────────────────────── */

const quickActions = [
  {
    label: '开始诊断',
    icon: BarChart3,
    onClick: () => {},
  },
  {
    label: '制定计划',
    icon: Target,
    onClick: () => {},
  },
  {
    label: '找学习伙伴',
    icon: Users,
    onClick: () => {},
  },
  {
    label: '复习评估',
    icon: BookOpen,
    onClick: () => {},
  },
];
