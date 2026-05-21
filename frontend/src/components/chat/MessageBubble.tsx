import { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism';
import {
  ThumbsUp,
  ThumbsDown,
  Copy,
  RefreshCw,
  Check,
  Bot,
  User as UserIcon,
} from 'lucide-react';
import { cn } from '@/utils/cn';
import type { Message, ThinkingStep } from '@/types';
import { ThinkingView } from './ThinkingView';
import { chatService } from '@/services/chat.service';
import { toast } from 'sonner';

interface Props {
  message: Message;
  isLast?: boolean;
  onRegenerate?: () => void;
  thinkingSteps?: ThinkingStep[];
}

export function MessageBubble({ message, isLast, onRegenerate, thinkingSteps }: Props) {
  const [feedback, setFeedback] = useState<'up' | 'down' | null>(message.feedback || null);
  const [copied, setCopied] = useState(false);
  const isUser = message.role === 'user';

  const steps = thinkingSteps || message.thinking_steps || [];
  const hasThinking = steps.length > 0;

  /* ── Handlers ────────────────────────────────────────────── */
  const handleFeedback = async (type: 'up' | 'down') => {
    const newFb = feedback === type ? null : type;
    setFeedback(newFb);
    try {
      await chatService.sendFeedback({
        message_id: message.id,
        feedback_type: newFb === 'up' ? 'thumb_up' : 'thumb_down',
      });
    } catch {
      toast.error('反馈提交失败');
    }
  };

  const handleCopy = async () => {
    await navigator.clipboard.writeText(message.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  /* ── Render ──────────────────────────────────────────────── */
  return (
    <div className={cn('group flex gap-3 px-4 py-3', isUser ? 'flex-row-reverse' : '')}>
      {/* Avatar */}
      <div
        className={cn(
          'flex h-8 w-8 shrink-0 items-center justify-center rounded-full',
          isUser
            ? 'bg-primary-600 text-white'
            : 'bg-primary-100 text-primary-600 dark:bg-primary-900/40 dark:text-primary-400',
        )}
      >
        {isUser ? <UserIcon size={16} /> : <Bot size={16} />}
      </div>

      {/* Bubble */}
      <div
        className={cn(
          'max-w-[75%] min-w-0',
          isUser ? 'items-end' : 'items-start',
        )}
      >
        <div
          className={cn(
            'prose prose-sm dark:prose-invert max-w-none rounded-2xl px-4 py-3',
            isUser
              ? 'rounded-msg-user bg-primary-600 text-white prose-p:text-white prose-code:text-primary-100'
              : 'rounded-msg-ai border border-gray-200 bg-white text-gray-800 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-200',
          )}
        >
          {/* Thinking section (embedded, assistant only) */}
          {!isUser && hasThinking && (
            <div className="mb-3">
              <ThinkingView steps={steps} />
              <div className="my-2 border-t border-gray-100 dark:border-gray-700" />
            </div>
          )}

          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              code({ node, className, children, ...props }) {
                const match = /language-(\w+)/.exec(className || '');
                const codeStr = String(children).replace(/\n$/, '');
                if (match) {
                  return (
                    <div className="relative my-2 overflow-hidden rounded-lg">
                      <div className="flex items-center justify-between bg-gray-900 px-3 py-1.5 text-xs text-gray-400">
                        <span>{match[1]}</span>
                        <button
                          onClick={() => navigator.clipboard.writeText(codeStr)}
                          className="hover:text-white"
                        >
                          <Copy size={12} />
                        </button>
                      </div>
                      <SyntaxHighlighter
                        style={oneDark}
                        language={match[1]}
                        PreTag="div"
                        customStyle={{ margin: 0, borderRadius: 0 }}
                      >
                        {codeStr}
                      </SyntaxHighlighter>
                    </div>
                  );
                }
                return (
                  <code className={className} {...props}>
                    {children}
                  </code>
                );
              },
            }}
          >
            {message.content}
          </ReactMarkdown>
        </div>

        {/* Action bar (AI only) */}
        {!isUser && (
          <div className="mt-1.5 flex items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100 hover:!opacity-100">
            <ActionButton
              active={feedback === 'up'}
              onClick={() => handleFeedback('up')}
              icon={<ThumbsUp size={14} />}
            />
            <ActionButton
              active={feedback === 'down'}
              onClick={() => handleFeedback('down')}
              icon={<ThumbsDown size={14} />}
            />
            <ActionButton
              onClick={handleCopy}
              icon={copied ? <Check size={14} /> : <Copy size={14} />}
            />
            {isLast && onRegenerate && (
              <ActionButton
                onClick={onRegenerate}
                icon={<RefreshCw size={14} />}
              />
            )}
            <span className="ml-2 text-xs text-gray-400">
              {formatTime(message.created_at)}
            </span>
          </div>
        )}

        {/* User timestamp */}
        {isUser && (
          <p className="mt-1 text-right text-xs text-gray-400">
            {formatTime(message.created_at)}
          </p>
        )}
      </div>
    </div>
  );
}

/* ── Sub-components ────────────────────────────────────────── */

function ActionButton({
  icon,
  onClick,
  active,
}: {
  icon: React.ReactNode;
  onClick: () => void;
  active?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        'rounded-md p-1 transition',
        active
          ? 'text-primary-500'
          : 'text-gray-400 hover:bg-gray-100 hover:text-gray-600 dark:hover:bg-gray-700',
      )}
    >
      {icon}
    </button>
  );
}

/* ── Helpers ────────────────────────────────────────────────── */

function formatTime(iso: string) {
  const d = new Date(iso);
  return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
}
