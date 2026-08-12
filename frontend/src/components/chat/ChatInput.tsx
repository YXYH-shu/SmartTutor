import { useState, useRef, useEffect, type KeyboardEvent } from 'react';
import { Send, Loader2, GraduationCap } from 'lucide-react';
import { cn } from '@/utils/cn';

interface Props {
  onSend: (content: string) => void;
  disabled?: boolean;
  placeholder?: string;
  guideOptions?: string[];
  recommendedOption?: string;
  onSelectGuide?: (option: string) => void;
}

export function ChatInput({
  onSend,
  disabled,
  placeholder,
  guideOptions = [],
  recommendedOption,
  onSelectGuide,
}: Props) {
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
    <div className="border-t border-border-subtle bg-bg-base/80 backdrop-blur-xl px-4 py-3">
      {guideOptions.length > 0 && (
        <div className="mx-auto mb-3 max-w-3xl animate-fade-in-up">
          <div className="mb-2 flex items-center gap-2 px-1 text-12 text-text-tertiary">
            <GraduationCap size={14} className="text-accent" />
            <span>🧭 你想先从哪个学科视角开始？</span>
          </div>
          <div className="flex flex-col gap-2">
            {guideOptions.map((option, index) => (
              <button
                key={`${index}-${option}`}
                type="button"
                disabled={disabled}
                onClick={() => onSelectGuide?.(option)}
                className={cn(
                  'group flex w-full items-start gap-3 rounded-xl border border-border-subtle',
                  'bg-bg-elevated/70 px-3.5 py-3 text-left text-14 text-text-secondary',
                  'transition-all duration-200 hover:border-accent/40 hover:bg-accent/5 hover:text-text-primary',
                  'focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent/60',
                  'disabled:cursor-not-allowed disabled:opacity-50',
                )}
              >
                <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-md border border-border-subtle bg-bg-base text-12 text-text-tertiary transition-colors duration-200 group-hover:border-accent/40 group-hover:text-accent">
                  {index + 1}
                </span>
                <span className="leading-5">{option}</span>
                {option === recommendedOption && (
                  <span className="ml-auto shrink-0 rounded-md border border-accent/30 bg-accent/10 px-1.5 py-0.5 text-12 text-accent">
                    ✨ 推荐起点
                  </span>
                )}
              </button>
            ))}
          </div>
        </div>
      )}
      <div className="mx-auto flex max-w-3xl items-end gap-2 rounded-xl bg-bg-elevated border border-border-subtle px-3 py-2 shadow-2 focus-within:border-accent/30 focus-within:shadow-[0_0_20px_var(--color-accent-glow)] transition-all duration-300">
        <textarea
          ref={textareaRef}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={disabled}
          placeholder={
            placeholder ||
            (guideOptions.length > 0
              ? '输入编号，或直接说你想探索的方向…'
              : '输入你的学习问题... (Enter 发送, Shift+Enter 换行)')
          }
          rows={1}
          className={cn(
            'flex-1 resize-none bg-transparent px-2 py-2 text-14 text-text-primary',
            'placeholder:text-text-tertiary',
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
              ? 'bg-accent text-white hover:bg-accent/90 active:scale-95 shadow-sm'
              : 'bg-bg-elevated/50 text-text-tertiary',
          )}
        >
          {disabled ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
        </button>
      </div>
    </div>
  );
}
