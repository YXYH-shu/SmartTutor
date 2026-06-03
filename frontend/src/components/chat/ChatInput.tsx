import { useState, useRef, useEffect, type KeyboardEvent } from 'react';
import { Send, Loader2 } from 'lucide-react';
import { cn } from '@/utils/cn';

interface Props {
  onSend: (content: string) => void;
  disabled?: boolean;
  placeholder?: string;
}

export function ChatInput({ onSend, disabled, placeholder }: Props) {
  const [value, setValue] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 200) + 'px';
  }, [value]);

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleSend = () => {
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setValue('');
    if (textareaRef.current) textareaRef.current.style.height = 'auto';
  };

  return (
    <div className="border-t border-white/[0.06] bg-[#0a0a0f]/80 backdrop-blur-xl px-4 py-3">
      <div className="mx-auto flex max-w-3xl items-end gap-2 rounded-2xl bg-[#18181b] border border-white/[0.06] px-3 py-2 shadow-elevated focus-within:border-primary-500/30 focus-within:shadow-[0_0_20px_rgba(59,130,246,0.08)] transition-all duration-300">
        <textarea
          ref={textareaRef}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={disabled}
          placeholder={placeholder || '输入你的问题... (Enter 发送, Shift+Enter 换行)'}
          rows={1}
          className={cn(
            'flex-1 resize-none bg-transparent px-2 py-2 text-sm text-gray-200',
            'placeholder:text-gray-500',
            'focus:outline-none',
            'scrollbar-thin',
            disabled && 'cursor-not-allowed opacity-50',
          )}
        />

        <button
          onClick={handleSend}
          disabled={disabled || !value.trim()}
          className={cn(
            'flex h-9 w-9 shrink-0 items-center justify-center rounded-xl transition-all duration-200',
            value.trim() && !disabled
              ? 'bg-primary-600 text-white hover:bg-primary-500 active:scale-95 shadow-sm'
              : 'bg-white/[0.04] text-gray-500',
          )}
        >
          {disabled ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
        </button>
      </div>
    </div>
  );
}
