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

  return (
    <div className={cn('group flex gap-3 px-6 py-4 animate-fade-in-up', isUser ? 'flex-row-reverse' : '')}>
      {/* Avatar */}
      <div
        className={cn(
          'flex h-8 w-8 shrink-0 items-center justify-center rounded-full',
          isUser
            ? 'bg-accent text-white'
            : 'bg-accent-soft text-accent',
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
            'prose prose-sm prose-invert max-w-none rounded-xl',
            isUser
              ? 'bg-accent/85 text-white px-5 py-3.5 prose-p:text-white/95 prose-code:text-accent/80 shadow-[inset_0_1px_0_rgba(255,255,255,0.08)]'
              : 'border border-border-subtle bg-bg-elevated text-text-primary px-5 py-4',
          )}
        >
          {!isUser && hasThinking && (
            <div className="mb-3">
              <ThinkingView steps={steps} />
              <div className="my-2 border-t border-border-subtle" />
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
                      <div className="flex items-center justify-between bg-bg-base/60 px-3 py-1.5 text-12 text-text-tertiary">
                        <span>{match[1]}</span>
                        <button
                          onClick={() => navigator.clipboard.writeText(codeStr)}
                          className="hover:text-text-primary"
                        >
                          <Copy size={12} />
                        </button>
                      </div>
                      <SyntaxHighlighter
                        style={oneDark}
                        language={match[1]}
                        PreTag="div"
                        customStyle={{ margin: 0, borderRadius: 0, background: 'var(--color-bg-elevated)' }}
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
            <span className="ml-2 font-mono text-12 text-text-tertiary">
              {formatTime(message.created_at)}
            </span>
          </div>
        )}

        {isUser && (
          <p className="mt-1 text-right font-mono text-12 text-text-tertiary">
            {formatTime(message.created_at)}
          </p>
        )}
      </div>
    </div>
  );
}

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
        'rounded-lg p-1 transition-all duration-200',
        active
          ? 'text-accent'
          : 'text-text-tertiary hover:text-accent hover:bg-bg-elevated/50',
      )}
    >
      {icon}
    </button>
  );
}

function formatTime(iso: string) {
  const d = new Date(iso);
  return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
}
